"""向量索引（VECTOR_SEARCH_PLAN.md §4）：vec0 表读写 + KNN 查询 + backfill

与 Search（FTS5）对等的第三类索引：md 是事实来源，本表随时可清空重建。
embedder_factory 每次调用时从 settings 解析（对齐 ProviderFactory 的每请求
构建哲学），未配 glm key 返回 None → 降级模式：索引/查询静默跳过，FTS 不受影响。
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable

import sqlite_vec

from .providers.embedding import TRUNCATE_CHARS

logger = logging.getLogger(__name__)

# 仅供类型说明：factory 返回 GLMEmbedder / FakeEmbedder / None（缺 key）
EmbedderFactory = Callable[[], object]


@dataclass
class VectorHit:
    entry_id: str
    distance: float  # cosine distance，越小越近


@dataclass
class BackfillResult:
    embedded: int
    failed: int


class VectorIndex:
    def __init__(self, conn: sqlite3.Connection, embedder_factory: EmbedderFactory):
        self._conn = conn
        # 公开属性：测试可整体替换 factory 注入 FakeEmbedder
        self.embedder_factory = embedder_factory

    @property
    def available(self) -> bool:
        """embedding 是否可用（glm key 已配置）"""
        return self._resolve() is not None

    def index_entry(self, entry_id: str, title: str, content: str) -> None:
        """写入路径挂钩：任何失败只告警不抛——绝不阻断条目保存（缺口由 backfill 补）"""
        embedder = self._resolve()
        if embedder is None:
            return
        self._index_locked(embedder, entry_id, title, content)

    def remove_entry(self, entry_id: str) -> None:
        """须在调用方事务内执行（与 Search.remove_entry 同约定）"""
        self._conn.execute("DELETE FROM entries_vec WHERE entry_id = ?", (entry_id,))

    def query(self, text: str, limit: int = 10) -> list[VectorHit]:
        embedder = self._resolve()
        if embedder is None:
            return []
        vector = embedder.embed([text])[0]
        rows = self._conn.execute(
            "SELECT entry_id, distance FROM entries_vec"
            " WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (sqlite_vec.serialize_float32(vector), limit),
        ).fetchall()
        return [VectorHit(row[0], row[1]) for row in rows]

    def clear(self) -> None:
        """清空向量表（须在调用方事务内执行）。只清不嵌——重嵌走显式 rebuild"""
        self._conn.execute("DELETE FROM entries_vec")

    def rebuild(self, storage) -> BackfillResult:
        with self._conn:
            self.clear()
        return self.backfill(storage)

    def status(self) -> tuple[int, int]:
        """(已索引条数, 条目总数)"""
        total = self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        indexed = self._conn.execute("SELECT COUNT(*) FROM entries_vec").fetchone()[0]
        return indexed, total

    def backfill(self, storage, batch: int | None = None) -> BackfillResult:
        """为缺向量的条目补嵌（幂等可续跑）；逐批嵌入、逐批落库，单批失败不中断。
        批大小默认取 embedder 自身的单请求上限（glm 64 / siliconflow 32）"""
        embedder = self._resolve()
        if embedder is None:
            return BackfillResult(0, 0)
        if batch is None:
            batch = getattr(embedder, "max_batch", 64)
        pending = [
            row[0]
            for row in self._conn.execute(
                "SELECT e.id FROM entries e"
                " LEFT JOIN entries_vec v ON v.entry_id = e.id"
                " WHERE v.entry_id IS NULL ORDER BY e.created_at, e.id"
            )
        ]
        embedded = failed = 0
        for start in range(0, len(pending), batch):
            chunk = pending[start : start + batch]
            texts, metas = [], []
            for entry_id in chunk:
                try:
                    entry = storage.get_entry(entry_id)
                except Exception:
                    entry = None  # md 文件缺失/损坏的条目跳过，不拖垮补嵌
                if entry is None:
                    failed += 1
                    continue
                texts.append(f"{entry.title}\n\n{entry.content[:TRUNCATE_CHARS]}")
                metas.append(entry.id)
            if not texts:
                continue
            try:
                vectors = embedder.embed(texts)
                with self._conn:
                    for entry_id, vector in zip(metas, vectors):
                        self._upsert(entry_id, vector)
                embedded += len(texts)
            except Exception as exc:
                logger.warning("backfill 批次失败，本批 %d 条跳过: %s", len(texts), exc)
                failed += len(texts)
        if failed:
            logger.warning("backfill 完成：成功 %d，失败 %d", embedded, failed)
        return BackfillResult(embedded, failed)

    # ── 内部 ──

    def _index_locked(
        self, embedder, entry_id: str, title: str, content: str
    ) -> bool:
        try:
            vector = embedder.embed(
                [f"{title}\n\n{content[:TRUNCATE_CHARS]}"]
            )[0]
            with self._conn:
                self._upsert(entry_id, vector)
            return True
        except Exception as exc:
            logger.warning("向量索引失败，跳过条目 %s: %s", entry_id, exc)
            return False

    def _upsert(self, entry_id: str, vector: list[float]) -> None:
        self._conn.execute(
            "DELETE FROM entries_vec WHERE entry_id = ?", (entry_id,)
        )
        self._conn.execute(
            "INSERT INTO entries_vec (entry_id, embedding) VALUES (?, ?)",
            (entry_id, sqlite_vec.serialize_float32(vector)),
        )

    def _resolve(self):
        try:
            return self.embedder_factory()
        except Exception as exc:
            logger.warning("embedder 解析失败: %s", exc)
            return None

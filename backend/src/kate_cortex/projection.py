"""语义空间三维投影（VECTOR_GRAPH_PLAN.md §2~3）：entries_vec 1024 维 → 3D 点云

只读已存向量，不依赖 embedder、零出网。投影是「派生视图的派生视图」：坐标
不落库，仅进程内存缓存，签名（embedding provider/model + 向量数/条目数/最新
更新时间）不变即复用；固定随机种子保证同输入必同输出，布局跨重启稳定。
numpy/sklearn 全部在函数体内懒加载，应用启动 import 链零变化。
"""

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

SEED = 42  # t-SNE 随机种子：同输入必同输出
MIN_POINTS = 3  # 少于 3 点无投影意义
TSNE_MIN_POINTS = 20  # 低于此数用 PCA（t-SNE 在极小样本上不可靠）
TSNE_MAX_POINTS = 5000  # 超出降级 PCA（个人库预期达不到）
PCA_DIMS = 50  # t-SNE 前置降维目标（标准预处理；小样本自适应收缩到 n-1）

SettingsProvider = Callable[[], dict]


@dataclass
class ProjectionPoint:
    entry_id: str
    title: str
    collections: list[str]
    source: str
    x: float
    y: float
    z: float


@dataclass
class ProjectionResult:
    method: str  # tsne | pca | insufficient
    computed_ms: int
    points: list[ProjectionPoint] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.points)


class ProjectionCache:
    """签名缓存的 3D 投影器；实例挂 app.state.projection，随进程存活"""

    def __init__(self, conn: sqlite3.Connection, settings_provider: SettingsProvider):
        self._conn = conn
        self._settings_provider = settings_provider
        self._cached: tuple[str, ProjectionResult] | None = None

    def get(self, refresh: bool = False) -> ProjectionResult:
        signature = self._signature()
        if signature is None:
            return ProjectionResult(method="insufficient", computed_ms=0)
        if not refresh and self._cached is not None and self._cached[0] == signature:
            return self._cached[1]
        started = time.perf_counter()
        result = self._compute(started)
        self._cached = (signature, result)
        return result

    # ── 内部 ──

    def _signature(self) -> str | None:
        """缓存签名；向量表为空返回 None（每次 GET 走 insufficient 快路径）"""
        vec_count = self._conn.execute(
            "SELECT COUNT(*) FROM entries_vec"
        ).fetchone()[0]
        if vec_count == 0:
            return None
        total, max_updated = self._conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM entries"
        ).fetchone()
        try:
            settings = self._settings_provider() or {}
        except Exception as exc:
            logger.warning("投影签名读取 settings 失败: %s", exc)
            settings = {}
        provider = settings.get("embedding_provider", "glm")
        model = settings.get("embedding_model", "")
        return f"{provider}:{model}:{vec_count}:{total}:{max_updated}"

    def _compute(self, started: float) -> ProjectionResult:
        rows = self._conn.execute(
            "SELECT v.entry_id, e.title, e.source, v.embedding"
            " FROM entries_vec v JOIN entries e ON e.id = v.entry_id"
            " ORDER BY v.entry_id"
        ).fetchall()
        if len(rows) < MIN_POINTS:
            return ProjectionResult("insufficient", _elapsed(started))
        collections_map = self._load_collections()
        method, coords = self._project([row[3] for row in rows], len(rows))
        points = [
            ProjectionPoint(
                entry_id=row[0],
                title=row[1],
                source=row[2],
                collections=collections_map.get(row[0], []),
                x=x,
                y=y,
                z=z,
            )
            for row, (x, y, z) in zip(rows, coords)
        ]
        return ProjectionResult(method, _elapsed(started), points)

    def _project(
        self, blobs: list[bytes], n: int
    ) -> tuple[str, list[tuple[float, float, float]]]:
        """L2 归一化（cosine 语义只看方向）后按阈值分派算法（§2 阈值表）"""
        import numpy as np

        vectors = np.array(
            [np.frombuffer(blob, dtype=np.float32) for blob in blobs],
            dtype=np.float32,
        )
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # 零向量防御
        vectors = vectors / norms
        if n < TSNE_MIN_POINTS or n > TSNE_MAX_POINTS:
            if n > TSNE_MAX_POINTS:
                logger.warning(
                    "条目数 %d 超过 t-SNE 上限 %d，降级 PCA", n, TSNE_MAX_POINTS
                )
            from sklearn.decomposition import PCA

            reduced = PCA(n_components=3).fit_transform(vectors)
            method = "pca"
        else:
            from sklearn.decomposition import PCA
            from sklearn.manifold import TSNE

            # 高维原始向量上直接 t-SNE 优化不稳（实测小样本退化为球壳散点），
            # 先 PCA 降到 ~50 维是标准预处理，实测簇分离 1.4~2.1x → 稳定可用
            pca_dims = min(PCA_DIMS, n - 1)
            reduced_input = PCA(
                n_components=pca_dims, random_state=SEED
            ).fit_transform(vectors)
            reduced = TSNE(
                n_components=3,
                metric="cosine",
                random_state=SEED,
                init="pca",
                # 约束 perplexity < n，且小样本下自适应收缩
                perplexity=min(30.0, (n - 1) / 3.0),
            ).fit_transform(reduced_input)
            method = "tsne"
        return method, _to_cube(reduced)

    def _load_collections(self) -> dict[str, list[str]]:
        """entry_id → 合集名列表（按名称排序，首个作为点色依据）"""
        rows = self._conn.execute(
            "SELECT ec.entry_id, c.name FROM entry_collections ec"
            " JOIN collections c ON c.id = ec.collection_id ORDER BY c.name"
        ).fetchall()
        result: dict[str, list[str]] = {}
        for entry_id, name in rows:
            result.setdefault(entry_id, []).append(name)
        return result


def _to_cube(coords) -> list[tuple[float, float, float]]:
    """以质心为中心等比缩放进 [-1, 1] 立方体（保持相对形状）"""
    import numpy as np

    centered = coords - coords.mean(axis=0)
    peak = float(np.abs(centered).max())
    if peak < 1e-9:
        return [(0.0, 0.0, 0.0)] * len(centered)
    scaled = centered / peak
    return [(float(x), float(y), float(z)) for x, y, z in scaled]


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

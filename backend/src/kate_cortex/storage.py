"""markdown ↔ SQLite 双写存储（DESIGN.md §3.4）：md 是事实来源，SQLite 是索引"""

import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .db import Database
from .frontmatter import (
    SOURCES,
    EntryMeta,
    FrontmatterError,
    dump_markdown,
    parse_markdown,
)
from .linking import extract_links
from .search import Search
from .slugify import slugify
from .vectors import VectorIndex

TRASH_DIR = ".trash"

# 用户档案常驻注入按「个人信息」合集识别（DESIGN.md §7）
PROFILE_COLLECTION = "个人信息"

# 系统合集：档案常驻注入（§7）与自动记忆（§7.1）按合集名识别，删除/重命名
# 会让对应机制对存量条目静默失效——在 storage 层拒绝（创建不受限，
# save_memory 首次落库依赖自动建「记忆」合集）
PROTECTED_COLLECTIONS = frozenset({PROFILE_COLLECTION, "记忆"})

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class EntryNotFound(StorageError):
    pass


class CollectionExists(StorageError):
    pass


class CollectionNotFound(StorageError):
    pass


class ProtectedCollection(StorageError):
    """系统合集（记忆/个人信息）不允许删除或重命名"""


@dataclass
class Entry:
    id: str
    slug: str
    title: str
    tags: list[str]  # 已废弃（v3）：仅透传存量 frontmatter 数据
    collections: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    keywords: list[str]  # 自动记忆（v4）：场景触发词，非记忆条目为空
    importance: int | None  # 自动记忆（v4）：1-5，非记忆条目为 None
    content: str
    file_path: str
    created_at: str
    updated_at: str


@dataclass
class EntrySummary:
    id: str
    slug: str
    title: str
    collections: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    keywords: list[str]
    importance: int | None
    created_at: str
    updated_at: str


@dataclass
class SyncReport:
    unindexed: list[str]
    missing_files: list[str]


class Storage:
    def __init__(
        self,
        config: Config,
        db: Database,
        search: Search,
        vectors: VectorIndex | None = None,
    ):
        self.config = config
        self.vault = Path(config.vault_path)
        self.db = db
        self.conn = db.conn
        self.search = search
        # 向量索引与 FTS 同级（None = 降级为纯 FTS，行为与 v4 一致）
        self.vectors = vectors
        self.vault.mkdir(parents=True, exist_ok=True)

    # ── 创建 ──

    def create_entry(
        self,
        *,
        title: str,
        source: str,
        content: str,
        collections: list[str] | None = None,
        language: str | None = None,
        conversation_id: str | None = None,
        slug: str | None = None,
        keywords: list[str] | None = None,
        importance: int | None = None,
    ) -> Entry:
        if source not in SOURCES:
            raise StorageError(f"source 非法: {source!r}")

        now = _now()
        entry_id = self._next_id()
        final_slug = slug or self._unique_slug(title)
        meta = EntryMeta(
            id=entry_id,
            slug=final_slug,
            title=title,
            tags=[],
            source=source,
            created_at=now,
            updated_at=now,
            collections=_dedup(collections or []),
            language=language,
            conversation=conversation_id,
            keywords=_dedup(keywords or []),
            importance=importance,
        )

        file_path = self._rel_path(entry_id, final_slug)
        md_file = self.vault / file_path
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(dump_markdown(meta, content), encoding="utf-8")
        try:
            self._write_db(meta, content, file_path)
        except Exception:
            md_file.unlink(missing_ok=True)
            raise
        # 事务提交后再补向量：网络失败不阻断保存（index_entry 内部吞错）
        if self.vectors:
            self.vectors.index_entry(entry_id, title, content)

        found = self.get_entry(entry_id)
        assert found is not None
        return found

    # ── 读取 ──

    def get_entry(self, id_or_slug: str) -> Entry | None:
        row = self._find_row(id_or_slug)
        if row is None:
            return None
        return self._read_entry_file(row)

    def list_entries(
        self,
        *,
        collection: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EntrySummary], int]:
        where, params = [], []
        if collection:
            where.append(
                "e.id IN (SELECT ec.entry_id FROM entry_collections ec"
                " JOIN collections c ON c.id = ec.collection_id WHERE c.name = ?)"
            )
            params.append(collection)
        if q:
            expr = self.search.match_expr(q)
            if not expr:
                return [], 0
            where.append("e.id IN (SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?)")
            params.append(expr)
        clause = f" WHERE {' AND '.join(where)}" if where else ""

        total = self.conn.execute(
            f"SELECT COUNT(*) FROM entries e{clause}", params
        ).fetchone()[0]
        rows = self.conn.execute(
            f"SELECT e.* FROM entries e{clause}"
            " ORDER BY e.created_at DESC, e.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [self._to_summary(row) for row in rows], total

    def backlinks(self, entry_id: str) -> list[EntrySummary]:
        rows = self.conn.execute(
            "SELECT e.* FROM entry_links el"
            " JOIN entries tgt ON tgt.slug = el.to_slug"
            " JOIN entries e ON e.id = el.from_id"
            " WHERE tgt.id = ? ORDER BY e.created_at DESC",
            (entry_id,),
        ).fetchall()
        return [self._to_summary(row) for row in rows]

    # ── 更新 ──

    def update_entry(
        self,
        entry_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        collections: list[str] | None = None,
        language: str | None = None,
        keywords: list[str] | None = None,
        importance: int | None = None,
    ) -> Entry:
        row = self._find_row(entry_id)
        if row is None:
            raise EntryNotFound(f"条目不存在: {entry_id}")
        current = self._read_entry_file(row)

        new_title = title if title is not None else current.title
        new_collections = (
            _dedup(collections) if collections is not None else current.collections
        )
        new_content = content if content is not None else current.content
        new_language = language if language is not None else current.language
        new_keywords = _dedup(keywords) if keywords is not None else current.keywords
        new_importance = importance if importance is not None else current.importance
        now = _now()

        meta = EntryMeta(
            id=current.id,
            slug=current.slug,
            title=new_title,
            tags=current.tags,
            source=current.source,
            created_at=current.created_at,
            updated_at=now,
            collections=new_collections,
            language=new_language,
            conversation=current.conversation_id,
            keywords=new_keywords,
            importance=new_importance,
        )
        md_file = self.vault / current.file_path
        md_file.write_text(dump_markdown(meta, new_content), encoding="utf-8")
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE entries SET title=?, language=?, keywords=?, importance=?,"
                    " updated_at=? WHERE id=?",
                    (
                        new_title,
                        new_language,
                        _dump_keywords(new_keywords),
                        new_importance,
                        now,
                        current.id,
                    ),
                )
                self._write_collections(current.id, new_collections)
                self._write_links(current.id, new_content)
                self.search.index_entry(current.id, new_title, new_content)
        except Exception:
            md_file.write_text(
                dump_markdown(
                    EntryMeta(
                        id=current.id, slug=current.slug, title=current.title,
                        tags=current.tags, source=current.source,
                        created_at=current.created_at, updated_at=current.updated_at,
                        collections=current.collections,
                        language=current.language, conversation=current.conversation_id,
                        keywords=current.keywords, importance=current.importance,
                    ),
                    current.content,
                ),
                encoding="utf-8",
            )
            raise
        if self.vectors:
            self.vectors.index_entry(current.id, new_title, new_content)

        updated = self.get_entry(current.id)
        assert updated is not None
        return updated

    # ── 软删 / 恢复 ──

    def delete_entry(self, entry_id: str) -> None:
        row = self._find_row(entry_id)
        if row is None:
            raise EntryNotFound(f"条目不存在: {entry_id}")

        src = self.vault / row["file_path"]
        dst = self.vault / TRASH_DIR / row["file_path"]
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            self.search.remove_entry(entry_id)
            if self.vectors:
                self.vectors.remove_entry(entry_id)

    def restore_entry(self, entry_id: str) -> Entry:
        for md_file in (self.vault / TRASH_DIR).rglob("*.md"):
            try:
                meta, content = parse_markdown(md_file.read_text(encoding="utf-8"))
            except FrontmatterError:
                continue
            if meta.id != entry_id:
                continue
            if self._find_row(meta.id) is not None:
                raise StorageError(f"条目已存在: {meta.id}")
            if self._slug_taken(meta.slug):
                meta.slug = self._unique_slug(meta.slug)
            meta.updated_at = _now()
            rel = self._rel_path(meta.id, meta.slug)
            dest = self.vault / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(md_file), str(dest))
            with self.conn:
                self._write_db(meta, content, rel)
            if self.vectors:
                self.vectors.index_entry(meta.id, meta.title, content)
            restored = self.get_entry(meta.id)
            assert restored is not None
            return restored
        raise EntryNotFound(f"回收站中找不到条目: {entry_id}")

    # ── 同步 ──

    def sync(self) -> SyncReport:
        indexed = {
            row["id"]: row["file_path"]
            for row in self.conn.execute("SELECT id, file_path FROM entries")
        }
        on_disk: dict[str, str] = {}
        for md_file in self._vault_files():
            try:
                meta, _ = parse_markdown(md_file.read_text(encoding="utf-8"))
            except FrontmatterError:
                continue
            on_disk[meta.id] = md_file.as_posix()

        unindexed = [entry_id for entry_id in on_disk if entry_id not in indexed]
        missing = [
            entry_id
            for entry_id, rel in indexed.items()
            if entry_id not in on_disk and not (self.vault / rel).is_file()
        ]
        return SyncReport(unindexed=sorted(unindexed), missing_files=sorted(missing))

    def reindex(self) -> tuple[SyncReport, int]:
        report = self.sync()
        with self.conn:
            self.conn.execute("DELETE FROM entries")
            self.conn.execute("DELETE FROM entries_fts")
            if self.vectors:
                # 只清不嵌（VECTOR_SEARCH_PLAN §0.4）：重嵌走显式 rebuild，避免隐式 API 费用
                self.vectors.clear()
            indexed = 0
            for md_file in self._vault_files():
                try:
                    meta, content = parse_markdown(md_file.read_text(encoding="utf-8"))
                except FrontmatterError:
                    continue
                rel = md_file.relative_to(self.vault).as_posix()
                self._write_db(meta, content, rel)
                indexed += 1
        return report, indexed

    # ── 合集 ──

    def migrate_profile_to_collection(self) -> int:
        """存量迁移（v3）：frontmatter tags 含「个人信息」的条目收进
        「个人信息」合集并从 tags 移除该项。按数据状态判断，幂等可重跑；
        title/content/时间戳不变，故无需更新 entries 行与 FTS"""
        migrated = 0
        for row in self.conn.execute("SELECT * FROM entries").fetchall():
            try:
                entry = self._read_entry_file(row)
                if PROFILE_COLLECTION not in entry.tags:
                    continue
                meta = EntryMeta(
                    id=entry.id,
                    slug=entry.slug,
                    title=entry.title,
                    tags=[t for t in entry.tags if t != PROFILE_COLLECTION],
                    source=entry.source,
                    created_at=entry.created_at,
                    updated_at=entry.updated_at,
                    collections=_dedup([*entry.collections, PROFILE_COLLECTION]),
                    language=entry.language,
                    conversation=entry.conversation_id,
                    keywords=entry.keywords,
                    importance=entry.importance,
                )
                md_file = self.vault / entry.file_path
                md_file.write_text(dump_markdown(meta, entry.content), encoding="utf-8")
                with self.conn:
                    self._write_collections(entry.id, meta.collections)
                migrated += 1
            except Exception as exc:
                logger.warning("档案迁移失败，跳过条目 %s: %s", row["id"], exc)
        return migrated

    def list_collections(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT c.name, COUNT(ec.entry_id) AS cnt FROM collections c"
            " LEFT JOIN entry_collections ec ON ec.collection_id = c.id"
            " GROUP BY c.id ORDER BY c.name"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def create_collection(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise StorageError("合集名不能为空")
        if self._collection_row(name) is not None:
            raise CollectionExists(f"合集已存在: {name}")
        with self.conn:
            self.conn.execute(
                "INSERT INTO collections (name, created_at) VALUES (?, ?)",
                (name, _now()),
            )

    def rename_collection(self, old: str, new: str) -> int:
        if old in PROTECTED_COLLECTIONS:
            raise ProtectedCollection(
                f"「{old}」是系统合集，不能重命名——自动记忆/用户档案按此合集名识别"
            )
        row = self._collection_row(old)
        if row is None:
            raise CollectionNotFound(f"合集不存在: {old}")
        new = new.strip()
        if not new:
            raise StorageError("合集名不能为空")
        if new == old:
            return self._member_count(row[0])
        if self._collection_row(new) is not None:
            raise CollectionExists(f"合集已存在: {new}")

        member_ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT entry_id FROM entry_collections WHERE collection_id = ?",
                (row[0],),
            )
        ]
        with self.conn:
            self.conn.execute(
                "UPDATE collections SET name = ? WHERE id = ?", (new, row[0])
            )
        for entry_id in member_ids:
            entry = self.get_entry(entry_id)
            if entry is None:
                continue
            self.update_entry(
                entry_id,
                collections=[new if c == old else c for c in entry.collections],
            )
        return len(member_ids)

    def delete_collection(self, name: str) -> int:
        if name in PROTECTED_COLLECTIONS:
            raise ProtectedCollection(
                f"「{name}」是系统合集，不能删除——条目可在记忆页/编辑页单独管理或移出"
            )
        row = self._collection_row(name)
        if row is None:
            raise CollectionNotFound(f"合集不存在: {name}")
        member_ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT entry_id FROM entry_collections WHERE collection_id = ?",
                (row[0],),
            )
        ]
        for entry_id in member_ids:
            entry = self.get_entry(entry_id)
            if entry is None:
                continue
            self.update_entry(
                entry_id, collections=[c for c in entry.collections if c != name]
            )
        with self.conn:
            self.conn.execute("DELETE FROM collections WHERE id = ?", (row[0],))
        return len(member_ids)

    def _collection_row(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id FROM collections WHERE name = ?", (name,)
        ).fetchone()

    def _member_count(self, collection_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM entry_collections WHERE collection_id = ?",
            (collection_id,),
        ).fetchone()[0]

    # ── 内部 ──

    def _vault_files(self) -> list[Path]:
        return [
            md
            for md in self.vault.rglob("*.md")
            if TRASH_DIR not in md.relative_to(self.vault).parts
        ]

    def _find_row(self, id_or_slug: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM entries WHERE id = ? OR slug = ?", (id_or_slug, id_or_slug)
        ).fetchone()

    def _read_entry_file(self, row: sqlite3.Row) -> Entry:
        md_file = self.vault / row["file_path"]
        if not md_file.is_file():
            raise StorageError(f"条目文件缺失: {row['file_path']}")
        meta, content = parse_markdown(md_file.read_text(encoding="utf-8"))
        return Entry(
            id=meta.id,
            slug=meta.slug,
            title=meta.title,
            tags=meta.tags,
            collections=meta.collections,
            source=meta.source,
            language=meta.language,
            conversation_id=meta.conversation,
            keywords=meta.keywords,
            importance=meta.importance,
            content=content,
            file_path=row["file_path"],
            created_at=meta.created_at,
            updated_at=meta.updated_at,
        )

    def _to_summary(self, row: sqlite3.Row) -> EntrySummary:
        collections = [
            c_row[0]
            for c_row in self.conn.execute(
                "SELECT c.name FROM entry_collections ec"
                " JOIN collections c ON c.id = ec.collection_id"
                " WHERE ec.entry_id = ? ORDER BY c.name",
                (row["id"],),
            )
        ]
        return EntrySummary(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            collections=collections,
            source=row["source"],
            language=row["language"],
            conversation_id=row["conversation_id"],
            keywords=_load_keywords(row["keywords"]),
            importance=row["importance"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _write_db(self, meta: EntryMeta, content: str, rel_path: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO entries (id, slug, title, language, source,"
                " conversation_id, file_path, created_at, updated_at,"
                " keywords, importance)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    meta.id, meta.slug, meta.title, meta.language,
                    meta.source, meta.conversation, rel_path,
                    meta.created_at, meta.updated_at,
                    _dump_keywords(meta.keywords), meta.importance,
                ),
            )
            self._write_collections(meta.id, meta.collections)
            self._write_links(meta.id, content)
            self.search.index_entry(meta.id, meta.title, content)

    def _write_collections(self, entry_id: str, names: list[str]) -> None:
        self.conn.execute(
            "DELETE FROM entry_collections WHERE entry_id = ?", (entry_id,)
        )
        for name in names:
            self.conn.execute(
                "INSERT OR IGNORE INTO collections (name, created_at) VALUES (?, ?)",
                (name, _now()),
            )
            collection_id = self.conn.execute(
                "SELECT id FROM collections WHERE name = ?", (name,)
            ).fetchone()[0]
            self.conn.execute(
                "INSERT OR IGNORE INTO entry_collections (entry_id, collection_id)"
                " VALUES (?, ?)",
                (entry_id, collection_id),
            )

    def _write_links(self, entry_id: str, content: str) -> None:
        self.conn.execute("DELETE FROM entry_links WHERE from_id = ?", (entry_id,))
        for slug in extract_links(content):
            self.conn.execute(
                "INSERT OR IGNORE INTO entry_links (from_id, to_slug) VALUES (?, ?)",
                (entry_id, slug),
            )

    def _next_id(self) -> str:
        date = datetime.now().strftime("%Y%m%d")
        row = self.conn.execute(
            "SELECT id FROM entries WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
            (f"kc_{date}_%",),
        ).fetchone()
        seq = int(row[0].rsplit("_", 1)[1]) + 1 if row else 1
        return f"kc_{date}_{seq:03d}"

    def _slug_taken(self, slug: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM entries WHERE slug = ?", (slug,)
        ).fetchone() is not None

    def _unique_slug(self, title: str) -> str:
        base = slugify(title)
        candidate = base
        suffix = 2
        while self._slug_taken(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _rel_path(self, entry_id: str, slug: str) -> str:
        date = entry_id[3:11]
        seq = entry_id.rsplit("_", 1)[1]
        return f"{date[:4]}/{date[4:6]}/{date}-{seq}-{slug}.md"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _dump_keywords(keywords: list[str]) -> str | None:
    return json.dumps(keywords, ensure_ascii=False) if keywords else None


def _load_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        return [str(k) for k in json.loads(raw)]
    except (json.JSONDecodeError, TypeError):
        return []


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        item = item.strip()
        if item:
            seen.setdefault(item, None)
    return list(seen)

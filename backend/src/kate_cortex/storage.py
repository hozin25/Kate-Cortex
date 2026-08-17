"""markdown ↔ SQLite 双写存储（DESIGN.md §3.4）：md 是事实来源，SQLite 是索引"""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .db import Database
from .frontmatter import (
    ENTRY_TYPES,
    SOURCES,
    EntryMeta,
    FrontmatterError,
    dump_markdown,
    parse_markdown,
)
from .linking import extract_links
from .search import Search
from .slugify import slugify

TRASH_DIR = ".trash"


class StorageError(Exception):
    pass


class EntryNotFound(StorageError):
    pass


@dataclass
class Entry:
    id: str
    slug: str
    title: str
    type: str
    tags: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    content: str
    file_path: str
    created_at: str
    updated_at: str


@dataclass
class EntrySummary:
    id: str
    slug: str
    title: str
    type: str
    tags: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    created_at: str
    updated_at: str


@dataclass
class SyncReport:
    unindexed: list[str]
    missing_files: list[str]


class Storage:
    def __init__(self, config: Config, db: Database, search: Search):
        self.config = config
        self.vault = Path(config.vault_path)
        self.db = db
        self.conn = db.conn
        self.search = search
        self.vault.mkdir(parents=True, exist_ok=True)

    # ── 创建 ──

    def create_entry(
        self,
        *,
        title: str,
        type: str,
        tags: list[str],
        source: str,
        content: str,
        language: str | None = None,
        conversation_id: str | None = None,
        slug: str | None = None,
    ) -> Entry:
        if type not in ENTRY_TYPES:
            raise StorageError(f"type 非法: {type!r}")
        if source not in SOURCES:
            raise StorageError(f"source 非法: {source!r}")

        now = _now()
        entry_id = self._next_id()
        final_slug = slug or self._unique_slug(title)
        meta = EntryMeta(
            id=entry_id,
            slug=final_slug,
            title=title,
            type=type,
            tags=_dedup(tags),
            source=source,
            created_at=now,
            updated_at=now,
            language=language,
            conversation=conversation_id,
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
        type: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EntrySummary], int]:
        where, params = [], []
        if type:
            where.append("e.type = ?")
            params.append(type)
        if tag:
            where.append(
                "e.id IN (SELECT et.entry_id FROM entry_tags et"
                " JOIN tags t ON t.id = et.tag_id WHERE t.name = ?)"
            )
            params.append(tag)
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
        tags: list[str] | None = None,
        type: str | None = None,
        language: str | None = None,
    ) -> Entry:
        row = self._find_row(entry_id)
        if row is None:
            raise EntryNotFound(f"条目不存在: {entry_id}")
        current = self._read_entry_file(row)

        new_type = type or current.type
        if new_type not in ENTRY_TYPES:
            raise StorageError(f"type 非法: {new_type!r}")
        new_title = title if title is not None else current.title
        new_tags = _dedup(tags) if tags is not None else current.tags
        new_content = content if content is not None else current.content
        new_language = language if language is not None else current.language
        now = _now()

        meta = EntryMeta(
            id=current.id,
            slug=current.slug,
            title=new_title,
            type=new_type,
            tags=new_tags,
            source=current.source,
            created_at=current.created_at,
            updated_at=now,
            language=new_language,
            conversation=current.conversation_id,
        )
        md_file = self.vault / current.file_path
        md_file.write_text(dump_markdown(meta, new_content), encoding="utf-8")
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE entries SET title=?, type=?, language=?, updated_at=? WHERE id=?",
                    (new_title, new_type, new_language, now, current.id),
                )
                self._write_tags(current.id, new_tags)
                self._write_links(current.id, new_content)
                self.search.index_entry(current.id, new_title, new_content, new_tags)
        except Exception:
            md_file.write_text(
                dump_markdown(
                    EntryMeta(
                        id=current.id, slug=current.slug, title=current.title,
                        type=current.type, tags=current.tags, source=current.source,
                        created_at=current.created_at, updated_at=current.updated_at,
                        language=current.language, conversation=current.conversation_id,
                    ),
                    current.content,
                ),
                encoding="utf-8",
            )
            raise

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
            self._cleanup_orphan_tags()

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
            self.conn.execute("DELETE FROM tags")
            self.conn.execute("DELETE FROM entries_fts")
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

    # ── 标签 ──

    def list_tags(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT t.name, COUNT(et.entry_id) AS cnt FROM tags t"
            " LEFT JOIN entry_tags et ON et.tag_id = t.id"
            " GROUP BY t.id ORDER BY t.name"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def delete_tag(self, name: str) -> int:
        row = self.conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise EntryNotFound(f"标签不存在: {name}")
        entry_ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT entry_id FROM entry_tags WHERE tag_id = ?", (row[0],)
            )
        ]
        for entry_id in entry_ids:
            entry = self.get_entry(entry_id)
            if entry is None:
                continue
            self.update_entry(entry_id, tags=[t for t in entry.tags if t != name])
        with self.conn:
            self._cleanup_orphan_tags()
        return len(entry_ids)

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
            type=meta.type,
            tags=meta.tags,
            source=meta.source,
            language=meta.language,
            conversation_id=meta.conversation,
            content=content,
            file_path=row["file_path"],
            created_at=meta.created_at,
            updated_at=meta.updated_at,
        )

    def _to_summary(self, row: sqlite3.Row) -> EntrySummary:
        tags = [
            tag_row[0]
            for tag_row in self.conn.execute(
                "SELECT t.name FROM entry_tags et JOIN tags t ON t.id = et.tag_id"
                " WHERE et.entry_id = ? ORDER BY t.name",
                (row["id"],),
            )
        ]
        return EntrySummary(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            type=row["type"],
            tags=tags,
            source=row["source"],
            language=row["language"],
            conversation_id=row["conversation_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _write_db(self, meta: EntryMeta, content: str, rel_path: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO entries (id, slug, title, type, language, source,"
                " conversation_id, file_path, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    meta.id, meta.slug, meta.title, meta.type, meta.language,
                    meta.source, meta.conversation, rel_path,
                    meta.created_at, meta.updated_at,
                ),
            )
            self._write_tags(meta.id, meta.tags)
            self._write_links(meta.id, content)
            self.search.index_entry(meta.id, meta.title, content, meta.tags)

    def _write_tags(self, entry_id: str, tags: list[str]) -> None:
        self.conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
        for tag in tags:
            self.conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tag_id = self.conn.execute(
                "SELECT id FROM tags WHERE name = ?", (tag,)
            ).fetchone()[0]
            self.conn.execute(
                "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
                (entry_id, tag_id),
            )

    def _write_links(self, entry_id: str, content: str) -> None:
        self.conn.execute("DELETE FROM entry_links WHERE from_id = ?", (entry_id,))
        for slug in extract_links(content):
            self.conn.execute(
                "INSERT OR IGNORE INTO entry_links (from_id, to_slug) VALUES (?, ?)",
                (entry_id, slug),
            )

    def _cleanup_orphan_tags(self) -> None:
        self.conn.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM entry_tags)"
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


def _dedup(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        tag = tag.strip()
        if tag:
            seen.setdefault(tag, None)
    return list(seen)

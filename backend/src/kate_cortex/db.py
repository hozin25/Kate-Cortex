"""SQLite 连接 + 全量 schema + 简易 migration（DESIGN.md §3.3）"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 6

# 向量混合检索（VECTOR_SEARCH_PLAN.md §4）：维度/距离度量在此定死，
# 变更维度须整表重建（rebuild 端点覆盖）
VEC_TABLE_SQL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec USING vec0("
    "entry_id TEXT PRIMARY KEY, embedding float[1024] distance_metric=cosine)"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
  id              TEXT PRIMARY KEY,
  slug            TEXT UNIQUE NOT NULL,
  title           TEXT NOT NULL,
  project         TEXT,
  language        TEXT,
  source          TEXT NOT NULL CHECK (source IN ('manual','chat','import')),
  conversation_id TEXT,
  file_path       TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  keywords        TEXT,
  importance      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entries_conv   ON entries(conversation_id);

CREATE TABLE IF NOT EXISTS collections (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_collections (
  entry_id      TEXT NOT NULL,
  collection_id INTEGER NOT NULL,
  PRIMARY KEY (entry_id, collection_id),
  FOREIGN KEY (entry_id)      REFERENCES entries(id)     ON DELETE CASCADE,
  FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entry_links (
  from_id  TEXT NOT NULL,
  to_slug  TEXT NOT NULL,
  PRIMARY KEY (from_id, to_slug),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
  title_tokens,
  content_tokens,
  entry_id UNINDEXED
);

CREATE TABLE IF NOT EXISTS conversations (
  id          TEXT PRIMARY KEY,
  title       TEXT,
  provider    TEXT NOT NULL,
  model       TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  summary     TEXT,
  summarized_until TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content         TEXT NOT NULL,
  tool_calls      TEXT,
  knowledge_refs  TEXT,
  created_at      TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrated_from: int | None = None
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.vec_enabled = self._load_vec_extension()
        self.init_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def _load_vec_extension(self) -> bool:
        """加载 sqlite-vec 可加载扩展；失败仅告警降级为纯 FTS，不阻塞启动"""
        try:
            import sqlite_vec

            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            return True
        except Exception as exc:
            logger.warning("sqlite-vec 扩展加载失败，向量检索降级为纯 FTS: %s", exc)
            return False

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        row = self._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
        if row[0] == 0:
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        else:
            current = self._conn.execute("SELECT version FROM schema_version").fetchone()[0]
            if current != SCHEMA_VERSION:
                self._migrate(current)
        if self.vec_enabled:
            # vec0 表不进 migration 链：扩展可用性与 schema 版本正交，
            # 每次启动 IF NOT EXISTS 幂等创建，避免「迁移到 v5 但扩展缺失」中间态
            self._conn.execute(VEC_TABLE_SQL)
        self._conn.commit()

    def _migrate(self, current: int) -> None:
        # v1 为基线；后续版本在此按 current 逐步升级
        self.migrated_from = current
        if current < 2:
            self._rebuild_entries_without_type()
        if current < 3:
            self._drop_tag_tables_and_rebuild_fts()
        if current < 4:
            self._add_memory_columns()
        if current < 5:
            pass  # v5：向量检索（entries_vec）。无数据搬迁，建表见 init_schema
        if current < 6:
            self._add_conversation_summary_columns()
        self._conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

    def _rebuild_entries_without_type(self) -> None:
        """v1 → v2：去掉 entries.type 列。SQLite 改列需整表重建（12-step 流程），
        期间必须关外键（PRAGMA 在事务外才生效），且 DROP 会级联清空 entry_tags/entry_links"""
        conn = self._conn
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                CREATE TABLE entries_v2 (
                  id              TEXT PRIMARY KEY,
                  slug            TEXT UNIQUE NOT NULL,
                  title           TEXT NOT NULL,
                  project         TEXT,
                  language        TEXT,
                  source          TEXT NOT NULL CHECK (source IN ('manual','chat','import')),
                  conversation_id TEXT,
                  file_path       TEXT NOT NULL,
                  created_at      TEXT NOT NULL,
                  updated_at      TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO entries_v2 (id, slug, title, project, language, source,"
                " conversation_id, file_path, created_at, updated_at)"
                " SELECT id, slug, title, project, language, source, conversation_id,"
                " file_path, created_at, updated_at FROM entries"
            )
            conn.execute("DROP TABLE entries")
            conn.execute("ALTER TABLE entries_v2 RENAME TO entries")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_created"
                " ON entries(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_conv"
                " ON entries(conversation_id)"
            )
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"迁移后外键校验失败: {violations}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def _drop_tag_tables_and_rebuild_fts(self) -> None:
        """v2 → v3：删除标签功能。DROP tags/entry_tags（先子后父）；entries_fts
        去掉 tag_tokens 列（FTS5 虚表无法改列，整表重建）——索引数据由应用层
        启动时按 md 真相源 reindex 重灌（见 main.py）"""
        conn = self._conn
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            conn.execute("DROP TABLE IF EXISTS entry_tags")
            conn.execute("DROP TABLE IF EXISTS tags")
            conn.execute("DROP TABLE IF EXISTS entries_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE entries_fts USING fts5("
                "title_tokens, content_tokens, entry_id UNINDEXED)"
            )
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"迁移后外键校验失败: {violations}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def _add_memory_columns(self) -> None:
        """v3 → v4：自动记忆功能。entries 加 keywords（JSON 数组，场景触发词）
        与 importance（1-5）两列，均可空——非记忆条目不受影响；纯加列无需
        整表重建，md 真相源里的对应 frontmatter 字段由 reindex/_write_db 带入"""
        conn = self._conn
        conn.commit()
        with conn:
            conn.execute("ALTER TABLE entries ADD COLUMN keywords TEXT")
            conn.execute("ALTER TABLE entries ADD COLUMN importance INTEGER")

    def _add_conversation_summary_columns(self) -> None:
        """v5 → v6：长对话摘要压缩（IMP-7）。conversations 加 summary（≤500 字
        增量摘要）与 summarized_until（已摘要覆盖到的消息时间戳），均可空——
        未触发摘要的会话不受影响。老库无 conversations 表时由 _SCHEMA 兜底
        建表（已含新列），此处按列存在性幂等加列"""
        conn = self._conn
        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        conn.commit()
        with conn:
            if "summary" not in existing:
                conn.execute("ALTER TABLE conversations ADD COLUMN summary TEXT")
            if "summarized_until" not in existing:
                conn.execute("ALTER TABLE conversations ADD COLUMN summarized_until TEXT")

    def close(self) -> None:
        self._conn.close()


def connect(db_path: Path) -> Database:
    return Database(db_path)

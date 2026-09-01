import sqlite3

import pytest

from kate_cortex import db as db_mod

EXPECTED_TABLES = {
    "entries",
    "collections",
    "entry_collections",
    "entry_links",
    "entries_fts",
    "conversations",
    "messages",
    "settings",
    "schema_version",
}


@pytest.fixture
def database(tmp_path):
    return db_mod.connect(tmp_path / "index.sqlite")


class TestSchema:
    def test_creates_all_tables(self, database):
        rows = database.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {row[0] for row in rows}
        assert EXPECTED_TABLES <= tables

    def test_vec_table_matches_extension_availability(self, database):
        rows = database.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {row[0] for row in rows}
        if database.vec_enabled:
            assert "entries_vec" in tables
        else:
            # 扩展缺失时降级：vec 表缺席，其余 schema 正常
            assert "entries_vec" not in tables

    def test_degraded_mode_skips_vec_without_blocking(self, tmp_path):
        class DegradedDatabase(db_mod.Database):
            def _load_vec_extension(self) -> bool:
                return False

        database = DegradedDatabase(tmp_path / "index.sqlite")

        assert not database.vec_enabled
        assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = {
            row[0]
            for row in database.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert EXPECTED_TABLES <= tables

    def test_records_schema_version(self, database):
        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION

    def test_reinit_is_idempotent(self, database):
        database.init_schema()
        database.init_schema()
        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION

    def test_entries_have_no_type_column(self, database):
        columns = {
            row[1]
            for row in database.conn.execute("PRAGMA table_info(entries)")
        }
        assert "type" not in columns

    def test_entries_rejects_invalid_source(self, database):
        with pytest.raises(sqlite3.IntegrityError):
            database.conn.execute(
                "INSERT INTO entries (id, slug, title, source, file_path,"
                " created_at, updated_at) VALUES ('x','x','x','web','x','t','t')"
            )

    def test_messages_cascade_on_conversation_delete(self, database):
        conn = database.conn
        conn.execute(
            "INSERT INTO conversations (id, provider, model, created_at, updated_at)"
            " VALUES ('c1','deepseek','deepseek-chat','t','t')"
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at)"
            " VALUES ('m1','c1','user','hi','t')"
        )
        conn.execute("DELETE FROM conversations WHERE id='c1'")
        remaining = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert remaining == 0


V3_SCHEMA = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE entries (
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
);
CREATE TABLE collections (
  id   INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE entry_collections (
  entry_id TEXT NOT NULL, collection_id INTEGER NOT NULL,
  PRIMARY KEY (entry_id, collection_id),
  FOREIGN KEY (entry_id)      REFERENCES entries(id)     ON DELETE CASCADE,
  FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
);
CREATE TABLE entry_links (
  from_id TEXT NOT NULL, to_slug TEXT NOT NULL, PRIMARY KEY (from_id, to_slug),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE
);
CREATE VIRTUAL TABLE entries_fts USING fts5(title_tokens, content_tokens, entry_id UNINDEXED);
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, title TEXT, provider TEXT NOT NULL, model TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content TEXT NOT NULL, tool_calls TEXT, knowledge_refs TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO schema_version (version) VALUES (3);
INSERT INTO entries (id, slug, title, source, file_path, created_at, updated_at)
  VALUES ('kc_20260818_001', 'old-entry', '旧条目', 'manual', 'a.md', 't', 't');
"""


class TestMigrateV3ToV4:
    def test_adds_memory_columns_and_keeps_rows(self, tmp_path):
        db_path = tmp_path / "index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(V3_SCHEMA)
        conn.commit()
        conn.close()

        database = db_mod.connect(db_path)

        columns = {row[1] for row in database.conn.execute("PRAGMA table_info(entries)")}
        assert {"keywords", "importance"} <= columns

        row = database.conn.execute(
            "SELECT id, keywords, importance FROM entries"
        ).fetchone()
        assert tuple(row) == ("kc_20260818_001", None, None)

        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION
        assert database.migrated_from == 3
        assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []


class TestMigrateV4ToV5:
    def _make_v4_db(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.executescript(V3_SCHEMA)
        conn.execute("ALTER TABLE entries ADD COLUMN keywords TEXT")
        conn.execute("ALTER TABLE entries ADD COLUMN importance INTEGER")
        conn.execute("UPDATE schema_version SET version = 4")
        conn.commit()
        conn.close()

    def test_bumps_version_and_keeps_rows(self, tmp_path):
        db_path = tmp_path / "index.sqlite"
        self._make_v4_db(db_path)

        database = db_mod.connect(db_path)

        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION == 5
        assert database.migrated_from == 4
        row = database.conn.execute("SELECT id FROM entries").fetchone()
        assert row[0] == "kc_20260818_001"
        assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        if database.vec_enabled:
            tables = {
                r[0]
                for r in database.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "entries_vec" in tables


V1_SCHEMA = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE entries (
  id              TEXT PRIMARY KEY,
  slug            TEXT UNIQUE NOT NULL,
  title           TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('note','clip','decision','howto')),
  project         TEXT,
  language        TEXT,
  source          TEXT NOT NULL CHECK (source IN ('manual','chat','import')),
  conversation_id TEXT,
  file_path       TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE entry_tags (
  entry_id TEXT NOT NULL,
  tag_id   INTEGER NOT NULL,
  PRIMARY KEY (entry_id, tag_id),
  FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id)   REFERENCES tags(id)    ON DELETE CASCADE
);
CREATE TABLE entry_links (
  from_id  TEXT NOT NULL,
  to_slug  TEXT NOT NULL,
  PRIMARY KEY (from_id, to_slug),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE
);
INSERT INTO schema_version (version) VALUES (1);
INSERT INTO entries (id, slug, title, type, source, file_path, created_at, updated_at)
  VALUES ('kc_20260818_001', 'old-entry', '旧条目', 'howto', 'manual', 'a.md', 't', 't');
INSERT INTO tags (name) VALUES ('redis');
INSERT INTO entry_tags (entry_id, tag_id) VALUES ('kc_20260818_001', 1);
INSERT INTO entry_links (from_id, to_slug) VALUES ('kc_20260818_001', 'other');
"""


class TestMigrateV1ToCurrent:
    def test_rebuilds_entries_without_type_and_keeps_related_rows(self, tmp_path):
        db_path = tmp_path / "index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(V1_SCHEMA)
        conn.commit()
        conn.close()

        database = db_mod.connect(db_path)

        columns = {row[1] for row in database.conn.execute("PRAGMA table_info(entries)")}
        assert "type" not in columns
        assert columns >= {"id", "slug", "title", "source", "file_path", "created_at"}

        row = database.conn.execute("SELECT id, slug, title FROM entries").fetchone()
        assert tuple(row) == ("kc_20260818_001", "old-entry", "旧条目")

        link_rows = database.conn.execute("SELECT * FROM entry_links").fetchall()
        assert [tuple(r) for r in link_rows] == [("kc_20260818_001", "other")]

        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION
        assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []

        tables = {
            row[0]
            for row in database.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"collections", "entry_collections"} <= tables
        # v3：标签表随迁移链一并移除
        assert not {"tags", "entry_tags"} & tables
        assert database.migrated_from == 1


V2_SCHEMA = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE entries (
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
);
CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE entry_tags (
  entry_id TEXT NOT NULL,
  tag_id   INTEGER NOT NULL,
  PRIMARY KEY (entry_id, tag_id),
  FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id)   REFERENCES tags(id)    ON DELETE CASCADE
);
CREATE TABLE collections (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE entry_collections (
  entry_id      TEXT NOT NULL,
  collection_id INTEGER NOT NULL,
  PRIMARY KEY (entry_id, collection_id),
  FOREIGN KEY (entry_id)      REFERENCES entries(id)     ON DELETE CASCADE,
  FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
);
CREATE TABLE entry_links (
  from_id  TEXT NOT NULL,
  to_slug  TEXT NOT NULL,
  PRIMARY KEY (from_id, to_slug),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE
);
CREATE VIRTUAL TABLE entries_fts USING fts5(
  title_tokens, content_tokens, tag_tokens, entry_id UNINDEXED
);
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, title TEXT, provider TEXT NOT NULL, model TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content TEXT NOT NULL, tool_calls TEXT, knowledge_refs TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO schema_version (version) VALUES (2);
INSERT INTO entries (id, slug, title, source, file_path, created_at, updated_at)
  VALUES ('kc_20260818_001', 'old-entry', '旧条目', 'manual', 'a.md', 't', 't');
INSERT INTO tags (name) VALUES ('redis');
INSERT INTO entry_tags (entry_id, tag_id) VALUES ('kc_20260818_001', 1);
"""


class TestMigrateV2ToV3:
    def test_drops_tag_tables_and_rebuilds_fts(self, tmp_path):
        db_path = tmp_path / "index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(V2_SCHEMA)
        conn.commit()
        conn.close()

        database = db_mod.connect(db_path)

        tables = {
            row[0]
            for row in database.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert not {"tags", "entry_tags"} & tables

        fts_columns = [
            row[1]
            for row in database.conn.execute("PRAGMA table_info(entries_fts)")
        ]
        assert "tag_tokens" not in fts_columns
        assert fts_columns[:2] == ["title_tokens", "content_tokens"]

        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION
        assert database.migrated_from == 2
        assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []

        row = database.conn.execute("SELECT id FROM entries").fetchone()
        assert row is not None

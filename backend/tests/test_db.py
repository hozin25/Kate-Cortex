import sqlite3

import pytest

from kate_cortex import db as db_mod

EXPECTED_TABLES = {
    "entries",
    "tags",
    "entry_tags",
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

    def test_records_schema_version(self, database):
        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION

    def test_reinit_is_idempotent(self, database):
        database.init_schema()
        database.init_schema()
        version = database.conn.execute("SELECT version FROM schema_version").fetchone()
        assert version[0] == db_mod.SCHEMA_VERSION

    def test_entries_rejects_invalid_type(self, database):
        with pytest.raises(sqlite3.IntegrityError):
            database.conn.execute(
                "INSERT INTO entries (id, slug, title, type, source, file_path,"
                " created_at, updated_at) VALUES ('x','x','x','snippet','manual','x','t','t')"
            )

    def test_entries_rejects_invalid_source(self, database):
        with pytest.raises(sqlite3.IntegrityError):
            database.conn.execute(
                "INSERT INTO entries (id, slug, title, type, source, file_path,"
                " created_at, updated_at) VALUES ('x','x','x','note','web','x','t','t')"
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

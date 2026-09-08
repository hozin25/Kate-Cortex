"""IMP-7：长对话增量摘要压缩"""

import sqlite3

import pytest

from kate_cortex.chat.service import ChatService
from kate_cortex.chat.summarizer import (
    SUMMARY_THRESHOLD_ROUNDS,
    ensure_summary,
)
from kate_cortex.db import connect
from kate_cortex.providers.base import Done, TextDelta
from kate_cortex.providers.fake import FakeProvider


@pytest.fixture
def chat_service(tmp_path):
    db = connect(tmp_path / "index.sqlite")
    return ChatService(db.conn)


def _seed_rounds(chat_service, n: int) -> str:
    session = chat_service.create_session("glm", "glm-4.7-flash")
    for i in range(n):
        chat_service.append_message(session.id, "user", f"问题 {i}")
        chat_service.append_message(session.id, "assistant", f"回答 {i}")
    return session.id


class TestEnsureSummary:
    def test_triggers_once_and_caches(self, chat_service):
        session_id = _seed_rounds(chat_service, SUMMARY_THRESHOLD_ROUNDS + 5)
        provider = FakeProvider(script=[TextDelta(text="这是摘要"), Done()])
        first = ensure_summary(chat_service, provider, session_id)
        assert first == "这是摘要"
        assert len(provider.calls) == 1
        # 缓存：溢出轮未增加，不再调用
        assert ensure_summary(chat_service, provider, session_id) == "这是摘要"
        assert len(provider.calls) == 1
        stored, until = chat_service.get_summary(session_id)
        assert stored == "这是摘要" and until

    def test_new_overflow_re_summarizes_with_old_summary(self, chat_service):
        session_id = _seed_rounds(chat_service, SUMMARY_THRESHOLD_ROUNDS + 5)
        provider = FakeProvider(script=[TextDelta(text="摘要一"), Done()])
        ensure_summary(chat_service, provider, session_id)
        for i in range(8):  # 新增 8 轮，溢出窗口再次出现
            chat_service.append_message(session_id, "user", f"新问题 {i}")
            chat_service.append_message(session_id, "assistant", f"新回答 {i}")
        second = ensure_summary(chat_service, provider, session_id)
        assert second == "摘要一"  # 单轮脚本循环回放
        assert len(provider.calls) == 2
        # 增量合并：第二次请求里包含旧摘要
        prompt = provider.calls[1]["messages"][0]["content"]
        assert "摘要一" in prompt and "此前对话的摘要" in prompt

    def test_below_threshold_no_call(self, chat_service):
        session_id = _seed_rounds(chat_service, 10)
        provider = FakeProvider(script=[TextDelta(text="x"), Done()])
        assert ensure_summary(chat_service, provider, session_id) is None
        assert len(provider.calls) == 0

    def test_provider_failure_degrades_to_old_summary(self, chat_service):
        session_id = _seed_rounds(chat_service, SUMMARY_THRESHOLD_ROUNDS + 5)
        ok = FakeProvider(script=[TextDelta(text="旧摘要"), Done()])
        ensure_summary(chat_service, ok, session_id)
        boom = FakeProvider(script=[RuntimeError("boom")])
        assert ensure_summary(chat_service, boom, session_id) == "旧摘要"

    def test_summary_injected_into_system_prompt(self, chat_service):
        from kate_cortex.chat.prompts import build_system_prompt

        prompt = build_system_prompt(conversation_summary="早期聊过 Redis 连接池")
        assert "## 对话背景" in prompt and "Redis 连接池" in prompt

    def test_migration_v5_to_v6(self, tmp_path):
        """v5 库（conversations 无 summary 列）打开后自动迁移出 v6 列"""
        db_path = tmp_path / "index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            "CREATE TABLE schema_version (version INTEGER NOT NULL);"
            "INSERT INTO schema_version VALUES (5);"
            "CREATE TABLE conversations ("
            " id TEXT PRIMARY KEY, title TEXT, provider TEXT NOT NULL,"
            " model TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
            "INSERT INTO conversations VALUES"
            " ('c1', NULL, 'glm', 'm', '2026-01-01', '2026-01-01');"
        )
        conn.commit()
        conn.close()
        db = connect(db_path)
        cols = {
            r[1] for r in db.conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        assert {"summary", "summarized_until"} <= cols
        assert db.conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0] == 1
        db.close()

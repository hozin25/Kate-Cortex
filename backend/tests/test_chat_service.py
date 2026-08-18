import pytest

from kate_cortex.chat.service import ChatService, SessionNotFound


@pytest.fixture
def service(env):
    from kate_cortex import db as db_mod

    database = db_mod.connect(env.db_path)
    return ChatService(database.conn)


class TestSessions:
    def test_create_session_generates_id(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")

        assert session.id.startswith("kc_conv_")
        assert session.provider == "deepseek"
        assert session.model == "deepseek-chat"
        assert session.title is None

    def test_rename_session(self, service):
        session = service.create_session(provider="glm", model="glm-4-flash")

        renamed = service.rename_session(session.id, "新标题")

        assert renamed.title == "新标题"

    def test_rename_missing_raises(self, service):
        with pytest.raises(SessionNotFound):
            service.rename_session("kc_conv_xxx", "t")

    def test_delete_session_removes_messages(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")
        service.append_message(session.id, "user", "你好")
        service.append_message(session.id, "assistant", "你好，有什么可以帮你？")

        service.delete_session(session.id)

        assert service.get_session(session.id) is None
        assert service.list_messages(session.id) == []

    def test_list_sessions_ordered_by_recency_with_preview(self, service):
        first = service.create_session(provider="deepseek", model="deepseek-chat")
        second = service.create_session(provider="deepseek", model="deepseek-chat")
        service.append_message(first.id, "user", "第一条会话的消息内容")
        service.append_message(second.id, "user", "第二条会话的消息内容")

        sessions = service.list_sessions()

        assert [s.id for s in sessions] == [second.id, first.id]
        assert sessions[0].preview == "第二条会话的消息内容"


class TestMessages:
    def test_append_message_stores_and_returns(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")

        message = service.append_message(session.id, "user", "记住这个结论")

        assert message.role == "user"
        assert message.content == "记住这个结论"
        assert service.list_messages(session.id)[0].id == message.id

    def test_messages_ordered_by_time(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")
        service.append_message(session.id, "user", "一")
        service.append_message(session.id, "assistant", "二")
        service.append_message(session.id, "user", "三")

        contents = [m.content for m in service.list_messages(session.id)]

        assert contents == ["一", "二", "三"]

    def test_tool_calls_and_refs_stored_as_json(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")

        message = service.append_message(
            session.id,
            "assistant",
            "已保存",
            tool_calls=[{"id": "call_1", "function": {"name": "save_knowledge"}}],
            knowledge_refs=["kc_20260818_001"],
        )

        stored = service.list_messages(session.id)[0]
        assert stored.tool_calls == message.tool_calls
        assert stored.knowledge_refs == ["kc_20260818_001"]

    def test_append_message_touches_session(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")
        before = service.get_session(session.id).updated_at

        service.append_message(session.id, "user", "hi")

        assert service.get_session(session.id).updated_at >= before


class TestAutoTitle:
    def test_first_message_sets_title_truncated_to_20_chars(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat")

        service.ensure_title(session.id, "这是一段特别长的首条消息用来测试自动标题截断逻辑的行为")

        assert service.get_session(session.id).title == "这是一段特别长的首条消息用来测试自动标题"

    def test_existing_title_not_overwritten(self, service):
        session = service.create_session(provider="deepseek", model="deepseek-chat", title="已有标题")

        service.ensure_title(session.id, "新消息")

        assert service.get_session(session.id).title == "已有标题"

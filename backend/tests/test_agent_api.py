import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.chat.agent import MAX_TOOL_ROUNDS
from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, TextDelta, ToolCallDelta
from kate_cortex.providers.fake import FakeProvider

from test_chat_api import parse_sse


def tool_call_deltas(call_id, name, args: dict) -> list:
    return [
        ToolCallDelta(index=0, id=call_id, name=name, arguments=json.dumps(args, ensure_ascii=False))
    ]


SAVE_ARGS = {
    "title": "连接池配置要点",
    "collections": ["编程"],
    "content_markdown": "使用 pool_pre_ping 避免断连。",
}
SUGGEST_ARGS = {
    "title": "选 SQLite 的理由",
    "collections": ["选型复盘"],
    "content_markdown": "单机个人应用，零运维，够用。",
}
MEMORY_ARGS = {
    "title": "感冒了",
    "content": "8月30日感冒，在吃感冒灵，注意保暖",
    "keywords": ["感冒", "健康", "保暖", "出行"],
    "importance": 4,
}
RECALL_ARGS = {
    "query": "周末想去户外玩",
    "keywords": ["出行", "健康"],
}


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    test_client = TestClient(app)
    test_client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": "sk-test"}},
    )
    return test_client


def start_session(client) -> str:
    return client.post("/api/chat/sessions", json={"provider": "deepseek"}).json()["id"]


def chat(client, session_id, content="记一下", rag=False):
    return client.post(
        f"/api/chat/sessions/{session_id}/chat",
        json={"content": content, "rag_enabled": rag},
    )


class TestSaveKnowledgeFlow:
    def test_tool_call_persists_entry_and_streams_events(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "save_knowledge", SAVE_ARGS) + [Done("tool_calls")],
                [TextDelta("已保存为知识条目。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        resp = chat(client, session_id)
        events = parse_sse(resp.text)
        names = [name for name, _ in events]

        assert names == ["citations", "tool_result", "delta", "done"]
        tool_result = next(data for name, data in events if name == "tool_result")
        assert tool_result["title"] == "连接池配置要点"
        assert tool_result["collections"] == ["编程"]
        assert tool_result["entry_id"].startswith("kc_")

        entries = client.get("/api/entries").json()
        assert entries["total"] == 1
        entry = client.get(f"/api/entries/{tool_result['entry_id']}").json()
        assert entry["source"] == "chat"
        assert entry["conversation_id"] == session_id

        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[1]["content"] == "已保存为知识条目。"
        assert messages[1]["tool_calls"][0]["function"]["name"] == "save_knowledge"

    def test_text_before_tool_call_streams_then_saves(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                [TextDelta("好的，我来总结保存。")]
                + tool_call_deltas("call_1", "save_knowledge", SAVE_ARGS)
                + [Done("tool_calls")],
                [TextDelta("完成。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id).text)
        names = [name for name, _ in events]

        assert names == ["citations", "delta", "tool_result", "delta", "done"]


class TestSuggestSaveFlow:
    def test_suggest_event_without_persist(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "suggest_save", SUGGEST_ARGS) + [Done("tool_calls")],
                [TextDelta("这段讨论值得保存，已生成建议卡片。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="继续聊").text)
        names = [name for name, _ in events]

        assert names == ["citations", "suggest", "delta", "done"]
        suggest = next(data for name, data in events if name == "suggest")
        assert suggest["title"] == "选 SQLite 的理由"
        assert suggest["preview"].startswith("单机个人应用")

        assert client.get("/api/entries").json()["total"] == 0

    def test_user_confirms_via_entries_api(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "suggest_save", SUGGEST_ARGS) + [Done("tool_calls")],
                [TextDelta("已生成建议。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake
        chat(client, session_id, content="继续聊")

        resp = client.post(
            "/api/entries",
            json={
                "title": "选 SQLite 的理由",
                "collections": ["选型复盘"],
                "content": "单机个人应用，零运维，够用。",
                "source": "chat",
                "conversation_id": session_id,
            },
        )

        assert resp.status_code == 201
        assert resp.json()["conversation_id"] == session_id


class TestAgentLoopEdges:
    def test_multiple_tool_calls_in_one_round(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(index=0, id="c1", name="save_knowledge", arguments=json.dumps(SAVE_ARGS)),
                    ToolCallDelta(index=1, id="c2", name="suggest_save", arguments=json.dumps(SUGGEST_ARGS)),
                    Done("tool_calls"),
                ],
                [TextDelta("两个动作都完成了。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id).text)
        names = [name for name, _ in events]

        assert names == ["citations", "tool_result", "suggest", "delta", "done"]
        assert client.get("/api/entries").json()["total"] == 1

    def test_tool_round_limit_stops_at_max(self, client):
        session_id = start_session(client)
        endless_tool = tool_call_deltas("call_loop", "suggest_save", SUGGEST_ARGS) + [Done("tool_calls")]
        fake = FakeProvider(rounds=[endless_tool])
        client.app.state.provider_factory = lambda name, model=None: fake

        resp = chat(client, session_id)
        events = parse_sse(resp.text)
        names = [name for name, _ in events]

        suggest_count = names.count("suggest")
        assert suggest_count == MAX_TOOL_ROUNDS
        assert names[-1] == "done"

    def test_malformed_tool_args_feed_error_back(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(index=0, id="c1", name="save_knowledge", arguments="{bad json"),
                    Done("tool_calls"),
                ],
                [TextDelta("参数出错了，我再试一次。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id).text)
        names = [name for name, _ in events]

        assert "delta" in names
        assert names[-1] == "done"
        assert client.get("/api/entries").json()["total"] == 0
        assert fake.calls[1]["messages"][-1]["role"] == "tool"
        assert "bad json" in fake.calls[1]["messages"][-1]["content"] or "解析" in fake.calls[1]["messages"][-1]["content"]

    def test_tools_spec_passed_to_provider(self, client):
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("ok"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        chat(client, session_id)

        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert tool_names == [
            "save_knowledge",
            "suggest_save",
            "export_markdown",
            "save_memory",
            "recall_memory",
            "install_mcp",
            "remove_mcp",
        ]

    def test_memory_disabled_hides_memory_tools(self, client):
        client.put("/api/settings", json={"memory_enabled": False})
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("ok"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        chat(client, session_id)

        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert tool_names == [
            "save_knowledge",
            "suggest_save",
            "export_markdown",
            "install_mcp",
            "remove_mcp",
        ]


class TestMemoryFlow:
    def seed_memory(self, client) -> str:
        resp = client.post(
            "/api/entries",
            json={
                "title": "感冒了",
                "collections": ["记忆"],
                "content": "8月30日感冒，在吃感冒灵，注意保暖",
                "source": "chat",
                "keywords": ["感冒", "健康", "保暖", "出行"],
                "importance": 4,
            },
        )
        return resp.json()["id"]

    def test_save_memory_streams_event_and_persists(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "save_memory", MEMORY_ARGS) + [Done("tool_calls")],
                [TextDelta("多喝水多休息，祝早日康复。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="我感冒了").text)
        names = [name for name, _ in events]

        assert names == ["citations", "memory_saved", "delta", "done"]
        saved = next(data for name, data in events if name == "memory_saved")
        assert saved["title"] == "感冒了"
        assert saved["replaced"] is False
        assert saved["keywords"] == ["感冒", "健康", "保暖", "出行"]

        entry = client.get(f"/api/entries/{saved['entry_id']}").json()
        assert entry["collections"] == ["记忆"]
        assert entry["keywords"] == ["感冒", "健康", "保暖", "出行"]
        assert entry["importance"] == 4
        assert entry["conversation_id"] == session_id

    def test_resident_memory_injected_into_system_prompt(self, client):
        entry_id = self.seed_memory(client)
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("记得保暖。"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="周末出去玩").text)

        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert "## 近期记忆" in system_prompt
        assert entry_id in system_prompt
        assert "注意保暖" in system_prompt
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert "save_memory" in tool_names and "recall_memory" in tool_names
        assert next(name for name, _ in events) == "citations"

    def test_resident_injection_off_when_disabled(self, client):
        self.seed_memory(client)
        client.put("/api/settings", json={"memory_enabled": False})
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("好。"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        chat(client, session_id, content="周末出去玩")

        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert "## 近期记忆" not in system_prompt
        assert "注意保暖" not in system_prompt

    def test_recall_memory_streams_refs_and_feeds_tool_result(self, client):
        entry_id = self.seed_memory(client)
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "recall_memory", RECALL_ARGS) + [Done("tool_calls")],
                [TextDelta("你最近感冒，出门记得保暖。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="周末想出去玩").text)
        names = [name for name, _ in events]

        assert names == ["citations", "memory_refs", "delta", "done"]
        refs = next(data for name, data in events if name == "memory_refs")
        assert refs["memories"][0]["entry_id"] == entry_id
        assert refs["memories"][0]["title"] == "感冒了"

        tool_msg = fake.calls[1]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert entry_id in tool_msg["content"]

    def test_recall_without_hit_emits_no_event(self, client):
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas("call_1", "recall_memory", {"keywords": ["做饭"]})
                + [Done("tool_calls")],
                [TextDelta("没想起什么相关的事。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="怎么做红烧肉").text)
        names = [name for name, _ in events]

        assert names == ["citations", "delta", "done"]
        tool_msg = fake.calls[1]["messages"][-1]
        assert "没有找到相关记忆" in tool_msg["content"]

    def test_save_memory_with_replaces_updates_existing(self, client):
        entry_id = self.seed_memory(client)
        session_id = start_session(client)
        fake = FakeProvider(
            rounds=[
                tool_call_deltas(
                    "call_1",
                    "save_memory",
                    {
                        "title": "感冒已痊愈",
                        "content": "9月2日感冒好了",
                        "keywords": ["感冒", "健康"],
                        "replaces_entry_id": entry_id,
                    },
                )
                + [Done("tool_calls")],
                [TextDelta("好的，已更新。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="我感冒好了").text)

        saved = next(data for name, data in events if name == "memory_saved")
        assert saved["replaced"] is True
        assert saved["entry_id"] == entry_id
        assert client.get("/api/entries").json()["total"] == 1
        assert client.get(f"/api/entries/{entry_id}").json()["title"] == "感冒已痊愈"


class TestRagIntegration:
    def test_rag_on_injects_knowledge_and_citations(self, client):
        client.post(
            "/api/entries",
            json={
                "title": "连接池调优方案",
                "content": "max_size 设为 20，pool_pre_ping 开启。",
                "source": "manual",
            },
        )
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("根据你的笔记……"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        resp = chat(client, session_id, content="连接池怎么调优", rag=True)
        events = parse_sse(resp.text)

        citations = next(data for name, data in events if name == "citations")
        assert citations["entries"][0]["title"] == "连接池调优方案"

        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert system_prompt.startswith("你是")
        assert "max_size 设为 20" in system_prompt

        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert messages[1]["knowledge_refs"] == [citations["entries"][0]["id"]]

    def test_rag_off_keeps_prompt_clean(self, client):
        client.post(
            "/api/entries",
            json={
                "title": "连接池调优方案",
                "content": "max_size 设为 20。",
                "source": "manual",
            },
        )
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("直接回答。"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(chat(client, session_id, content="连接池怎么调优", rag=False).text)

        citations = next(data for name, data in events if name == "citations")
        assert citations["entries"] == []
        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert "max_size" not in system_prompt
        assert "## 用户知识库参考" not in system_prompt

    def test_rag_defaults_to_global_setting(self, client):
        client.put("/api/settings", json={"rag_default": False})
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("hi"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        chat(client, session_id, content="随便聊聊", rag=None)

        assert "## 用户知识库参考" not in fake.calls[0]["messages"][0]["content"]

    def test_profile_injected_even_when_rag_off(self, client):
        client.post(
            "/api/entries",
            json={
                "title": "用户教育背景",
                "collections": ["个人信息"],
                "content": "用户是软件工程专业的学生。",
                "source": "manual",
            },
        )
        client.post(
            "/api/entries",
            json={
                "title": "连接池调优方案",
                "content": "max_size 设为 20。",
                "source": "manual",
            },
        )
        session_id = start_session(client)
        fake = FakeProvider(rounds=[[TextDelta("你是软件工程学生。"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        events = parse_sse(
            chat(client, session_id, content="我的身份是什么", rag=False).text
        )

        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert "## 用户档案" in system_prompt
        assert "软件工程专业的学生" in system_prompt
        assert "max_size" not in system_prompt
        assert "## 用户知识库参考" not in system_prompt
        citations = next(data for name, data in events if name == "citations")
        assert citations["entries"] == []

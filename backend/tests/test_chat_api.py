import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, TextDelta
from kate_cortex.providers.fake import FakeProvider


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    test_client = TestClient(app)
    test_client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": "sk-test", "glm": "sk-test"}},
    )
    return test_client


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        event = next(line[len("event: ") :] for line in lines if line.startswith("event: "))
        data = next(line[len("data: ") :] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


class TestSessionApi:
    def test_create_list_patch_delete(self, client):
        created = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        )
        assert created.status_code == 201, created.text
        session = created.json()
        assert session["id"].startswith("kc_conv_")

        listed = client.get("/api/chat/sessions").json()
        assert listed[0]["id"] == session["id"]

        patched = client.patch(
            f"/api/chat/sessions/{session['id']}", json={"title": "项目讨论"}
        )
        assert patched.status_code == 200
        assert patched.json()["title"] == "项目讨论"

        assert client.delete(f"/api/chat/sessions/{session['id']}").status_code == 204
        assert client.get("/api/chat/sessions").json() == []

    def test_create_rejects_unknown_provider(self, client):
        resp = client.post(
            "/api/chat/sessions", json={"provider": "openai", "model": "gpt-4"}
        )
        assert resp.status_code == 422

    def test_switch_model_keeps_provider(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()

        resp = client.patch(
            f"/api/chat/sessions/{session['id']}", json={"model": "deepseek-reasoner"}
        )

        assert resp.status_code == 200
        assert resp.json()["provider"] == "deepseek"
        assert resp.json()["model"] == "deepseek-reasoner"

    def test_switch_provider_resolves_default_model(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()

        resp = client.patch(
            f"/api/chat/sessions/{session['id']}", json={"provider": "glm"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "glm"
        # 全新默认 provider=glm → 直接取默认模型 glm-4.7-flash
        assert body["model"] == "glm-4.7-flash"

    def test_switch_provider_without_key_400(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()

        resp = client.patch(
            f"/api/chat/sessions/{session['id']}", json={"provider": "siliconflow"}
        )

        assert resp.status_code == 400
        assert "siliconflow" in resp.json()["detail"]

    def test_patch_empty_body_422(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()

        resp = client.patch(f"/api/chat/sessions/{session['id']}", json={})

        assert resp.status_code == 422

    def test_models_catalog_marks_key_and_free(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()["providers"]}

        assert providers["glm"]["has_key"] is True
        assert providers["siliconflow"]["has_key"] is False
        glm_models = {m["model"]: m for m in providers["glm"]["models"]}
        assert glm_models["glm-4.7-flash"]["free"] is True
        assert glm_models["glm-4.5"]["free"] is False

    def test_messages_endpoint(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()
        resp = client.get(f"/api/chat/sessions/{session['id']}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_session_404(self, client):
        assert client.get("/api/chat/sessions/kc_conv_none/messages").status_code == 404


class TestChatManagement:
    """对话管理基本操作：重新生成 / 编辑重发 / 删除消息"""

    def start_session(self, client) -> dict:
        return client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()

    def send(self, client, session_id, content):
        return client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": content, "rag_enabled": False},
        )

    def messages_of(self, client, session_id):
        return client.get(f"/api/chat/sessions/{session_id}/messages").json()

    def test_regenerate_replaces_last_reply(self, client):
        session = self.start_session(client)
        fake = FakeProvider(
            rounds=[
                [TextDelta("第一版回复"), Done("stop")],
                [TextDelta("第二版回复"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model: fake

        self.send(client, session["id"], "你好")
        resp = client.post(f"/api/chat/sessions/{session['id']}/regenerate", json={})

        assert resp.status_code == 200
        events = parse_sse(resp.text)
        assert [name for name, _ in events][-1] == "done"
        messages = self.messages_of(client, session["id"])
        # 用户消息不重复，旧回复被替换
        assert [(m["role"], m["content"]) for m in messages] == [
            ("user", "你好"),
            ("assistant", "第二版回复"),
        ]

    def test_regenerate_removes_only_trailing_replies(self, client):
        session = self.start_session(client)
        fake = FakeProvider(script=[TextDelta("回复"), Done("stop")])
        client.app.state.provider_factory = lambda name, model: fake
        self.send(client, session["id"], "第一问")
        self.send(client, session["id"], "第二问")

        resp = client.post(f"/api/chat/sessions/{session['id']}/regenerate", json={})

        assert resp.status_code == 200
        roles = [(m["role"], m["content"]) for m in self.messages_of(client, session["id"])]
        assert roles == [
            ("user", "第一问"),
            ("assistant", "回复"),
            ("user", "第二问"),
            ("assistant", "回复"),  # 重新生成的新回复
        ]

    def test_regenerate_without_user_message_404(self, client):
        session = self.start_session(client)
        assert (
            client.post(f"/api/chat/sessions/{session['id']}/regenerate", json={}).status_code
            == 404
        )

    def test_resend_updates_content_and_truncates(self, client):
        session = self.start_session(client)
        fake = FakeProvider(
            rounds=[
                [TextDelta("答A"), Done("stop")],
                [TextDelta("答B"), Done("stop")],
                [TextDelta("答C"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model: fake
        self.send(client, session["id"], "第一问")
        self.send(client, session["id"], "第二问")
        first_user_id = self.messages_of(client, session["id"])[0]["id"]

        resp = client.post(
            f"/api/chat/sessions/{session['id']}/messages/{first_user_id}/resend",
            json={"content": "改后的问题"},
        )

        assert resp.status_code == 200
        assert parse_sse(resp.text)[-1][0] == "done"
        messages = self.messages_of(client, session["id"])
        # 原消息原地更新，其后全部截断，新回复基于新内容
        assert [(m["role"], m["content"]) for m in messages] == [
            ("user", "改后的问题"),
            ("assistant", "答C"),
        ]

    def test_resend_rejects_assistant_message(self, client):
        session = self.start_session(client)
        fake = FakeProvider(script=[TextDelta("答"), Done("stop")])
        client.app.state.provider_factory = lambda name, model: fake
        self.send(client, session["id"], "你好")
        assistant_id = self.messages_of(client, session["id"])[1]["id"]

        resp = client.post(
            f"/api/chat/sessions/{session['id']}/messages/{assistant_id}/resend",
            json={"content": "改"},
        )

        assert resp.status_code == 400

    def test_resend_missing_message_404(self, client):
        session = self.start_session(client)
        assert (
            client.post(
                f"/api/chat/sessions/{session['id']}/messages/nope/resend",
                json={"content": "x"},
            ).status_code
            == 404
        )

    def test_delete_message(self, client):
        session = self.start_session(client)
        fake = FakeProvider(script=[TextDelta("答"), Done("stop")])
        client.app.state.provider_factory = lambda name, model: fake
        self.send(client, session["id"], "你好")
        messages = self.messages_of(client, session["id"])

        resp = client.delete(f"/api/chat/sessions/{session['id']}/messages/{messages[1]['id']}")

        assert resp.status_code == 204
        remaining = self.messages_of(client, session["id"])
        assert [m["role"] for m in remaining] == ["user"]

    def test_delete_message_of_other_session_404(self, client):
        session_a = self.start_session(client)
        session_b = self.start_session(client)
        fake = FakeProvider(script=[TextDelta("答"), Done("stop")])
        client.app.state.provider_factory = lambda name, model: fake
        self.send(client, session_a["id"], "你好")
        message_id = self.messages_of(client, session_a["id"])[0]["id"]

        # 用 B 会话的路径删 A 会话的消息 → 404（会话归属校验）
        resp = client.delete(f"/api/chat/sessions/{session_b['id']}/messages/{message_id}")

        assert resp.status_code == 404


class TestSseChat:
    def test_full_stream_flow(self, client, env):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()
        fake = FakeProvider(
            [TextDelta("你好"), TextDelta("，用户"), Done("stop")]
        )
        client.app.state.provider_factory = lambda name, model: fake

        resp = client.post(
            f"/api/chat/sessions/{session['id']}/chat",
            json={"content": "介绍一下你自己", "rag_enabled": False},
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(resp.text)

        assert events[0] == ("citations", {"entries": []})
        deltas = [data["text"] for name, data in events if name == "delta"]
        assert deltas == ["你好", "，用户"]
        done = [data for name, data in events if name == "done"][0]
        assert done["message_id"].startswith("kc_msg_")

        messages = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[1]["content"] == "你好，用户"

        title = client.get("/api/chat/sessions").json()[0]["title"]
        assert title == "介绍一下你自己"

    def test_upstream_error_sends_error_event_and_skips_persist(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "glm", "model": "glm-4-flash"}
        ).json()
        fake = FakeProvider([TextDelta("半截"), RuntimeError("upstream boom")])
        client.app.state.provider_factory = lambda name, model: fake

        resp = client.post(
            f"/api/chat/sessions/{session['id']}/chat",
            json={"content": "hi", "rag_enabled": False},
        )

        events = parse_sse(resp.text)
        names = [name for name, _ in events]
        assert "error" in names
        assert "done" not in names

        messages = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
        assert [m["role"] for m in messages] == ["user"]

    def test_chat_missing_session_404(self, client):
        resp = client.post(
            "/api/chat/sessions/kc_conv_none/chat",
            json={"content": "hi", "rag_enabled": False},
        )
        assert resp.status_code == 404

    def test_create_without_api_key_returns_400(self, client):
        client.put("/api/settings", json={"provider_keys": {}})

        resp = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        )

        assert resp.status_code == 400
        assert "API key" in resp.json()["detail"]

    def test_history_passed_to_provider(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()
        fake = FakeProvider([TextDelta("好"), Done("stop")])
        client.app.state.provider_factory = lambda name, model: fake

        client.post(
            f"/api/chat/sessions/{session['id']}/chat",
            json={"content": "第一轮", "rag_enabled": False},
        )
        client.post(
            f"/api/chat/sessions/{session['id']}/chat",
            json={"content": "第二轮", "rag_enabled": False},
        )

        last_call = fake.calls[-1]
        roles = [m["role"] for m in last_call["messages"]]
        assert roles == ["system", "user", "assistant", "user"]


class TestSettingsApi:
    def test_get_defaults(self, env):
        fresh = TestClient(
            create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
        )
        resp = fresh.get("/api/settings").json()
        assert resp["default_provider"] == "glm"
        assert resp["default_model"] == "glm-4.7-flash"
        assert resp["rag_default"] is True
        assert resp["provider_keys"] == {}

    def test_update_settings_roundtrip(self, client):
        resp = client.put(
            "/api/settings",
            json={"provider_keys": {"deepseek": "sk-123"}, "rag_default": False},
        )
        assert resp.status_code == 200

        refreshed = client.get("/api/settings").json()
        assert refreshed["provider_keys"]["deepseek"] == "sk-123"
        assert refreshed["rag_default"] is False

    def test_update_rejects_unknown_provider_key(self, client):
        resp = client.put(
            "/api/settings", json={"provider_keys": {"openai": "sk-1"}}
        )
        assert resp.status_code == 422


class TestProviderTest:
    def test_provider_connectivity_ok(self, client):
        client.put("/api/settings", json={"provider_keys": {"deepseek": "sk-123"}})
        fake = FakeProvider([TextDelta("pong"), Done("stop")])
        client.app.state.provider_factory = lambda name, model=None: fake

        resp = client.post("/api/providers/test", json={"provider": "deepseek"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["reply"] == "pong"

    def test_provider_failure_returns_502(self, client):
        client.put("/api/settings", json={"provider_keys": {"glm": "sk-123"}})
        fake = FakeProvider([RuntimeError("auth failed")])
        client.app.state.provider_factory = lambda name, model=None: fake

        resp = client.post("/api/providers/test", json={"provider": "glm"})

        assert resp.status_code == 502
        assert resp.json()["ok"] is False

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

    def test_messages_endpoint(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek", "model": "deepseek-chat"}
        ).json()
        resp = client.get(f"/api/chat/sessions/{session['id']}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_session_404(self, client):
        assert client.get("/api/chat/sessions/kc_conv_none/messages").status_code == 404


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
        assert resp["default_provider"] == "deepseek"
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

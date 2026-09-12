"""自定义 agent：CRUD / 校验 / `/名称` 引用解析 / 对话链路注入（AGENTS_PLAN.md）"""

import pytest
from fastapi.testclient import TestClient

from kate_cortex.agents import resolve_agent, strip_agent_token
from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, TextDelta
from kate_cortex.providers.fake import FakeProvider

from test_chat_api import parse_sse


@pytest.fixture
def client(env):
    return TestClient(create_app(Config(vault_path=env.vault_path, db_path=env.db_path)))


@pytest.fixture
def chat_client(env):
    """带 deepseek key 的客户端：走完整 chat 链路断言 system prompt / provider 覆盖"""
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    test_client = TestClient(app)
    test_client.put("/api/settings", json={"provider_keys": {"deepseek": "sk-test"}})
    return test_client


def create(client, **overrides):
    payload = {"name": "翻译官", "description": "中英互译", "prompt": "你是资深中英互译。"}
    payload.update(overrides)
    return client.post("/api/agents", json=payload)


class TestAgentCrud:
    def test_create_and_list(self, client):
        resp = create(client)
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["id"].startswith("kc_agent_")
        assert agent["name"] == "翻译官"
        assert agent["enabled"] is True
        assert agent["provider"] is None and agent["model"] is None

        agents = client.get("/api/agents").json()["agents"]
        assert [a["name"] for a in agents] == ["翻译官"]

    def test_create_with_model_pair(self, client):
        agent = create(client, provider="glm-coding", model="glm-5.3").json()
        assert agent["provider"] == "glm-coding"
        assert agent["model"] == "glm-5.3"

    def test_duplicate_name_409_case_insensitive(self, client):
        assert create(client).status_code == 201
        assert create(client).status_code == 409
        assert create(client, name="翻译官 ").status_code == 409  # 尾随空格 strip 后同名

        latin = create(client, name="Coder", prompt="p")
        assert latin.status_code == 201
        assert create(client, name="coder", prompt="p").status_code == 409

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": "有空格 名称"},
            {"name": "a" * 33},
            {"name": "名字/带斜杠"},
            {"name": "医生!", "prompt": "p"},
            {"prompt": ""},
            {"prompt": "长" * 4001},
            {"description": "长" * 61},
            {"provider": "glm"},
            {"provider": "unknown-provider", "model": "m"},
            {"provider": "不存在的", "model": "m"},
        ],
    )
    def test_invalid_fields_422(self, client, overrides):
        assert create(client, **overrides).status_code == 422

    def test_update_fields(self, client):
        agent = create(client).json()

        updated = client.patch(
            f"/api/agents/{agent['id']}",
            json={"description": "口译+笔译", "provider": "glm", "model": "glm-4.7-flash"},
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "口译+笔译"
        assert updated.json()["model"] == "glm-4.7-flash"

        disabled = client.patch(f"/api/agents/{agent['id']}", json={"enabled": False})
        assert disabled.json()["enabled"] is False

        renamed = client.patch(f"/api/agents/{agent['id']}", json={"name": "译员"})
        assert renamed.json()["name"] == "译员"

    def test_update_name_to_taken_409(self, client):
        create(client)
        other = create(client, name="写作助手", prompt="你是写作助手。").json()
        resp = client.patch(f"/api/agents/{other['id']}", json={"name": "翻译官"})
        assert resp.status_code == 409

    def test_update_provider_only_422_and_unknown_id_404(self, client):
        agent = create(client).json()
        assert (
            client.patch(f"/api/agents/{agent['id']}", json={"provider": "glm"}).status_code
            == 422
        )
        assert client.patch("/api/agents/kc_agent_nope", json={"enabled": False}).status_code == 404
        assert client.patch("/api/agents/kc_agent_nope", json={}).status_code == 422

    def test_delete_then_404(self, client):
        agent = create(client).json()
        assert client.delete(f"/api/agents/{agent['id']}").status_code == 204
        assert client.get("/api/agents").json()["agents"] == []
        assert client.delete(f"/api/agents/{agent['id']}").status_code == 404

    def test_disabled_agent_still_stored_but_not_resolved(self, client):
        create(client)
        agent = client.get("/api/agents").json()["agents"][0]
        client.patch(f"/api/agents/{agent['id']}", json={"enabled": False})
        assert resolve_agent("/翻译官 你好", client.get("/api/agents").json()["agents"]) is None


class TestResolveAgent:
    def make_agents(self):
        return [
            {"id": "a1", "name": "翻译官", "enabled": True, "provider": None, "model": None},
            {"id": "a2", "name": "Coder", "enabled": True, "provider": None, "model": None},
            {"id": "a3", "name": "停用的", "enabled": False, "provider": None, "model": None},
        ]

    def test_hit_with_space_and_eol(self):
        agents = self.make_agents()
        assert resolve_agent("/翻译官 你好", agents)["id"] == "a1"
        assert resolve_agent("/翻译官", agents)["id"] == "a1"
        assert resolve_agent("/coder fix this", agents)["id"] == "a2"
        assert resolve_agent("/CODER fix", agents)["id"] == "a2"  # 大小写不敏感

    def test_miss_cases(self):
        agents = self.make_agents()
        assert resolve_agent("/翻译官你好", agents) is None  # 无空格收尾不算引用
        assert resolve_agent("/不存在的 你好", agents) is None
        assert resolve_agent("/停用的 你好", agents) is None  # 停用回落默认 Kate
        assert resolve_agent("看 https://example.com/x 文档", agents) is None
        assert resolve_agent("", agents) is None
        assert resolve_agent("/ 空token", agents) is None
        assert resolve_agent("/翻译官", None) is None

    def test_strip_agent_token(self):
        assert strip_agent_token("/翻译官 你好") == "你好"
        assert strip_agent_token("/翻译官") == ""
        assert strip_agent_token("没有前缀的消息") == "没有前缀的消息"


class TestAgentChatInjection:
    """`/名称` 前缀 → system prompt 角色段 + 请求级模型覆盖（AGENTS_PLAN.md §3.2-§3.4）"""

    @staticmethod
    def make_translator(client, **overrides):
        payload = {
            "name": "翻译官",
            "description": "中英互译",
            "prompt": "你是资深中英互译，只输出译文。",
        }
        payload.update(overrides)
        resp = client.post("/api/agents", json=payload)
        assert resp.status_code == 201
        return resp.json()

    @staticmethod
    def install_fake(client, text="Hello."):
        """注入 FakeProvider 并记录每次 provider_factory 收到的 (provider, model)"""
        fake = FakeProvider(rounds=[[TextDelta(text), Done("stop")]])
        recorded = []

        def factory(name, model=None):
            recorded.append((name, model))
            return fake

        client.app.state.provider_factory = factory
        return fake, recorded

    @staticmethod
    def start_session(client) -> str:
        return client.post("/api/chat/sessions", json={"provider": "deepseek"}).json()["id"]

    def test_agent_prompt_injected_tools_kept_title_stripped(self, chat_client):
        self.make_translator(chat_client)
        fake, recorded = self.install_fake(chat_client)
        session_id = self.start_session(chat_client)

        resp = chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 你好，世界", "rag_enabled": False},
        )
        assert resp.status_code == 200
        parse_sse(resp.text)

        system_prompt = fake.calls[0]["messages"][0]["content"]
        assert "## 当前角色：翻译官" in system_prompt
        assert "只输出译文" in system_prompt
        assert "## 工具使用规则" in system_prompt  # 工具能力不裁剪
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert "save_knowledge" in tool_names and "recall_memory" in tool_names
        assert recorded[-1][0] == "deepseek"  # 未指定模型 → 用会话模型

        messages = chat_client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert messages[0]["content"] == "/翻译官 你好，世界"  # 前缀保留落库
        session = next(
            s
            for s in chat_client.get("/api/chat/sessions").json()
            if s["id"] == session_id
        )
        assert session["title"] == "你好，世界"  # 标题剥掉前缀

    def test_no_prefix_keeps_prompt_clean(self, chat_client):
        self.make_translator(chat_client)
        fake, _ = self.install_fake(chat_client)
        session_id = self.start_session(chat_client)

        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "普通消息", "rag_enabled": False},
        )

        assert "当前角色" not in fake.calls[0]["messages"][0]["content"]

    def test_non_matching_prefix_falls_back(self, chat_client):
        self.make_translator(chat_client)
        fake, _ = self.install_fake(chat_client)
        session_id = self.start_session(chat_client)

        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/不存在的 你好", "rag_enabled": False},
        )

        assert "当前角色" not in fake.calls[0]["messages"][0]["content"]

    def test_disabled_agent_falls_back(self, chat_client):
        agent = self.make_translator(chat_client)
        chat_client.patch(f"/api/agents/{agent['id']}", json={"enabled": False})
        fake, _ = self.install_fake(chat_client)
        session_id = self.start_session(chat_client)

        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 你好", "rag_enabled": False},
        )

        assert "当前角色" not in fake.calls[0]["messages"][0]["content"]

    def test_model_override_without_key_400(self, chat_client):
        self.make_translator(chat_client, provider="glm", model="glm-4.7-flash")
        session_id = self.start_session(chat_client)  # deepseek 有 key，glm 没有

        resp = chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 你好", "rag_enabled": False},
        )

        assert resp.status_code == 400
        assert "glm" in resp.json()["detail"]

    def test_model_override_reaches_provider(self, chat_client):
        chat_client.put(
            "/api/settings",
            json={"provider_keys": {"deepseek": "sk-test", "glm": "sk-glm"}},
        )
        self.make_translator(chat_client, provider="glm", model="glm-4.7-flash")
        _, recorded = self.install_fake(chat_client)
        session_id = self.start_session(chat_client)

        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 你好", "rag_enabled": False},
        )

        assert recorded[-1] == ("glm", "glm-4.7-flash")  # 请求级覆盖，不改会话
        session = next(
            s
            for s in chat_client.get("/api/chat/sessions").json()
            if s["id"] == session_id
        )
        assert (session["provider"], session["model"]) == ("deepseek", session["model"])

    def test_regenerate_reapplies_agent(self, chat_client):
        self.make_translator(chat_client)
        self.install_fake(chat_client)
        session_id = self.start_session(chat_client)
        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 你好", "rag_enabled": False},
        )

        fake2, _ = self.install_fake(chat_client, text="Hello again.")
        resp = chat_client.post(
            f"/api/chat/sessions/{session_id}/regenerate", json={"rag_enabled": False}
        )
        assert resp.status_code == 200
        parse_sse(resp.text)

        assert "## 当前角色：翻译官" in fake2.calls[0]["messages"][0]["content"]

    def test_resend_prefix_controls_agent(self, chat_client):
        self.make_translator(chat_client)
        self.install_fake(chat_client)
        session_id = self.start_session(chat_client)
        chat_client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "/翻译官 hello", "rag_enabled": False},
        )
        user_msg_id = chat_client.get(
            f"/api/chat/sessions/{session_id}/messages"
        ).json()[0]["id"]

        # 去掉前缀 → 回落默认 Kate
        fake2, _ = self.install_fake(chat_client, text="plain.")
        chat_client.post(
            f"/api/chat/sessions/{session_id}/messages/{user_msg_id}/resend",
            json={"content": "hello", "keep_images": False, "rag_enabled": False},
        )
        assert "当前角色" not in fake2.calls[0]["messages"][0]["content"]

        # 带回前缀 → agent 再次生效
        fake3, _ = self.install_fake(chat_client, text="translated.")
        chat_client.post(
            f"/api/chat/sessions/{session_id}/messages/{user_msg_id}/resend",
            json={
                "content": "/翻译官 hello",
                "keep_images": False,
                "rag_enabled": False,
            },
        )
        assert "## 当前角色：翻译官" in fake3.calls[0]["messages"][0]["content"]

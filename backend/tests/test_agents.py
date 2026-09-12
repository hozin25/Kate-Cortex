"""自定义 agent：CRUD / 校验 / `/名称` 引用解析（AGENTS_PLAN.md §2 §3.1 §3.3）"""

import pytest
from fastapi.testclient import TestClient

from kate_cortex.agents import resolve_agent, strip_agent_token
from kate_cortex.config import Config
from kate_cortex.main import create_app


@pytest.fixture
def client(env):
    return TestClient(create_app(Config(vault_path=env.vault_path, db_path=env.db_path)))


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

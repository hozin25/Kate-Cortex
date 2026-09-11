"""MCP 接入测试：多服务管理路由 / 命名空间工具 / agent 集成 / 会话内安装（全 mock 不出网）"""

import json

import pytest
from fastapi.testclient import TestClient
from mcp import types

from kate_cortex import mcp_registry
from kate_cortex.config import Config
from kate_cortex.db import connect as db_connect
from kate_cortex.main import create_app
from kate_cortex.mcp_client import (
    _result_text,
    _to_openai_tool,
    mcp_tool_name,
    parse_mcp_tool_name,
    to_namespaced_tools,
)
from kate_cortex.providers.base import Done, TextDelta, ToolCallDelta
from kate_cortex.providers.fake import FakeProvider
from kate_cortex.settings import SettingsService

from test_chat_api import parse_sse

MCP_URL = "https://mcp.example.com/mcp?key=k"

AMAP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "maps_text_search",
            "description": "关键词搜索 POI",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string"},
                    "city": {"type": "string"},
                },
                "required": ["keywords"],
            },
        },
    }
]


@pytest.fixture(autouse=True)
def clean_status_cache(monkeypatch):
    """状态缓存是模块级全局，逐测试清空防止串扰"""
    monkeypatch.setattr(mcp_registry, "_STATUS", {})


def make_client(env) -> TestClient:
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    client = TestClient(app)
    client.put("/api/settings", json={"provider_keys": {"deepseek": "sk-test"}})
    return client


def add_server(
    client: TestClient,
    monkeypatch,
    name: str = "amap",
    url: str = MCP_URL,
    tools: list = AMAP_TOOLS,
) -> dict:
    """走真实路由接入一个服务（list_tools 已 mock），返回响应体"""
    monkeypatch.setattr("kate_cortex.mcp_client.list_mcp_tools", lambda u: tools)
    resp = client.post("/api/mcp/servers", json={"name": name, "url": url})
    assert resp.status_code == 201, resp.text
    return resp.json()


def start_session(client: TestClient) -> str:
    return client.post("/api/chat/sessions", json={"provider": "deepseek"}).json()["id"]


class TestToolConversion:
    def test_to_openai_tool(self):
        tool = types.Tool(
            name="maps_text_search",
            description="关键词搜索 POI",
            input_schema={
                "type": "object",
                "properties": {"keywords": {"type": "string"}},
            },
        )
        converted = _to_openai_tool(tool)

        assert converted["type"] == "function"
        assert converted["function"]["name"] == "maps_text_search"
        assert converted["function"]["description"] == "关键词搜索 POI"
        assert converted["function"]["parameters"]["properties"] == {
            "keywords": {"type": "string"}
        }

    def test_to_openai_tool_without_schema(self):
        tool = types.Tool(
            name="no_args", input_schema={"type": "object", "properties": {}}
        )
        converted = _to_openai_tool(tool)

        assert converted["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }

    def test_to_openai_tool_missing_schema_falls_back(self):
        from types import SimpleNamespace

        converted = _to_openai_tool(
            SimpleNamespace(name="x", description=None, input_schema=None)
        )

        assert converted["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }


class TestNamespacing:
    def test_roundtrip(self):
        namespaced = to_namespaced_tools(AMAP_TOOLS, "amap")
        assert namespaced[0]["function"]["name"] == "mcp__amap__maps_text_search"
        # 描述与参数保持原样
        assert namespaced[0]["function"]["description"] == "关键词搜索 POI"

        assert parse_mcp_tool_name("mcp__amap__maps_text_search") == (
            "amap",
            "maps_text_search",
        )

    def test_parse_non_mcp_and_malformed(self):
        assert parse_mcp_tool_name("save_knowledge") is None
        assert parse_mcp_tool_name("mcp__only-id") is None
        assert parse_mcp_tool_name("mcp____tool") is None

    def test_tool_name_with_double_underscore_still_parses(self):
        name = mcp_tool_name("svc", "a__b")
        assert parse_mcp_tool_name(name) == ("svc", "a__b")


class TestServerRoutes:
    def test_add_and_list_with_status(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch, name="amap")

        body = client.get("/api/mcp/servers").json()
        assert len(body["servers"]) == 1
        server = body["servers"][0]
        assert server["id"] == "amap"
        assert server["name"] == "amap"
        assert server["url"] == MCP_URL
        assert server["enabled"] is True
        # 添加即实测过，状态缓存里已是可用
        assert server["status"]["ok"] is True
        assert server["status"]["tool_count"] == 1

        # 设置里也可见（GET /api/settings 透出 mcp_servers）
        settings = client.get("/api/settings").json()
        assert settings["mcp_servers"][0]["id"] == "amap"

    def test_add_validates_url_scheme(self, env, monkeypatch):
        client = make_client(env)
        resp = client.post(
            "/api/mcp/servers", json={"name": "amap", "url": "ftp://x"}
        )
        assert resp.status_code == 400
        assert "http" in resp.json()["detail"]
        assert client.get("/api/mcp/servers").json()["servers"] == []

    def test_add_connection_failure_persists_nothing(self, env, monkeypatch):
        client = make_client(env)

        def boom(url):
            raise ConnectionError("连接超时")

        monkeypatch.setattr("kate_cortex.mcp_client.list_mcp_tools", boom)
        resp = client.post("/api/mcp/servers", json={"name": "amap", "url": MCP_URL})
        assert resp.status_code == 400
        assert "连接失败" in resp.json()["detail"]
        assert client.get("/api/mcp/servers").json()["servers"] == []

    def test_add_without_tools_rejected(self, env, monkeypatch):
        client = make_client(env)
        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda u: []
        )
        resp = client.post("/api/mcp/servers", json={"name": "amap", "url": MCP_URL})
        assert resp.status_code == 400
        assert "未提供任何工具" in resp.json()["detail"]

    def test_add_same_url_is_idempotent(self, env, monkeypatch):
        client = make_client(env)
        first = add_server(client, monkeypatch, name="amap")
        second = add_server(client, monkeypatch, name="高德")

        servers = client.get("/api/mcp/servers").json()["servers"]
        assert len(servers) == 1
        assert second["id"] == first["id"] == "amap"

    def test_chinese_name_falls_back_to_ascii_id(self, env, monkeypatch):
        client = make_client(env)
        server = add_server(client, monkeypatch, name="高德地图")
        assert server["id"] == "mcp"

    def test_id_dedup(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch, name="amap", url=MCP_URL)
        other = add_server(
            client, monkeypatch, name="amap", url="https://mcp.other.com/mcp"
        )
        assert other["id"] == "amap-2"

    def test_delete(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)

        assert client.delete("/api/mcp/servers/amap").status_code == 204
        assert client.get("/api/mcp/servers").json()["servers"] == []
        assert client.delete("/api/mcp/servers/amap").status_code == 404

    def test_patch_enabled(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)

        body = client.patch("/api/mcp/servers/amap", json={"enabled": False}).json()
        assert body["enabled"] is False
        assert client.get("/api/mcp/servers").json()["servers"][0]["enabled"] is False

    def test_test_endpoint(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)

        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools",
            lambda u: (_ for _ in ()).throw(RuntimeError("TLS 握手失败")),
        )
        body = client.post("/api/mcp/servers/amap/test").json()
        assert body["ok"] is False
        assert "连接失败" in body["message"]
        # 失败状态被缓存，设置页能看到「不可用」
        status = client.get("/api/mcp/servers").json()["servers"][0]["status"]
        assert status["ok"] is False

        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda u: AMAP_TOOLS
        )
        body = client.post("/api/mcp/servers/amap/test").json()
        assert body["ok"] is True
        assert body["tools"] == ["maps_text_search"]

    def test_test_unknown_server_404(self, env):
        client = make_client(env)
        assert client.post("/api/mcp/servers/ghost/test").status_code == 404


class TestAgentIntegration:
    def test_namespaced_tools_merged_and_dispatched(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)

        forwarded: dict = {}

        def fake_call(url, name, args):
            forwarded.update({"url": url, "name": name, "args": args})
            return json.dumps(
                {"pois": [{"name": "西湖", "address": "杭州市龙井路1号"}]},
                ensure_ascii=False,
            )

        monkeypatch.setattr("kate_cortex.mcp_client.call_mcp_tool", fake_call)

        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="mcp__amap__maps_text_search",
                        arguments=json.dumps(
                            {"keywords": "景点", "city": "杭州"}, ensure_ascii=False
                        ),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("## 杭州一日游\n\n- **西湖**：杭州市龙井路1号"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "帮我排一个杭州一日游", "rag_enabled": False},
        )
        names = [name for name, _ in parse_sse(resp.text)]

        # MCP 工具结果以纯文本回传模型，不产生独立 SSE 事件
        assert names == ["citations", "delta", "done"]

        # 工具表 = 本地 7 个 + 命名空间化的 MCP 工具
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert tool_names[:5] == [
            "save_knowledge",
            "suggest_save",
            "export_markdown",
            "save_memory",
            "recall_memory",
        ]
        assert "install_mcp" in tool_names
        assert "remove_mcp" in tool_names
        assert "mcp__amap__maps_text_search" in tool_names

        # 命名空间名反解回真实工具名 + 原端点调用
        assert forwarded["url"] == MCP_URL
        assert forwarded["name"] == "maps_text_search"
        assert forwarded["args"]["city"] == "杭州"

        # 工具结果原文喂回模型
        tool_msg = fake.calls[1]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert "西湖" in tool_msg["content"]

        # system prompt 注入 MCP 使用规则与接入管理规则
        system = fake.calls[0]["messages"][0]["content"]
        assert "外部实时工具" in system
        assert "install_mcp" in system

        # 会话消息持久化了 MCP 工具调用
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert (
            messages[1]["tool_calls"][0]["function"]["name"]
            == "mcp__amap__maps_text_search"
        )

    def test_server_disabled_excludes_tools(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)
        client.patch("/api/mcp/servers/amap", json={"enabled": False})

        fake = FakeProvider(rounds=[[TextDelta("好"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake
        session_id = start_session(client)
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "随便聊聊", "rag_enabled": False},
        )

        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert "mcp__amap__maps_text_search" not in tool_names
        # 使用规则不注入，但接入管理规则常驻（随时可以装新的）
        system = fake.calls[0]["messages"][0]["content"]
        assert "外部实时工具" not in system
        assert "install_mcp" in system

    def test_unreachable_server_degrades_with_notice(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)

        def boom(url):
            raise ConnectionError("连接超时")

        monkeypatch.setattr("kate_cortex.mcp_client.list_mcp_tools", boom)

        fake = FakeProvider(rounds=[[TextDelta("凭常识回答"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "北京有什么好玩的", "rag_enabled": False},
        )
        events = parse_sse(resp.text)
        names = [name for name, _ in events]

        assert names == ["mcp_notice", "citations", "delta", "done"]
        notice = next(data for name, data in events if name == "mcp_notice")
        assert "连接失败" in notice["message"]
        assert "amap" in notice["message"]

        # 降级：无 MCP 工具、无使用提示词，对话照常进行
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert "mcp__amap__maps_text_search" not in tool_names
        assert "外部实时工具" not in fake.calls[0]["messages"][0]["content"]

        # 失败状态同步到设置页可见的状态缓存
        status = client.get("/api/mcp/servers").json()["servers"][0]["status"]
        assert status["ok"] is False


class TestInstallInChat:
    def _fake_provider(self):
        return FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="install_mcp",
                        arguments=json.dumps(
                            {"name": "高德地图", "url": MCP_URL}, ensure_ascii=False
                        ),
                    ),
                    Done("tool_calls"),
                ],
                [
                    ToolCallDelta(
                        index=0,
                        id="c2",
                        name="mcp__mcp__maps_text_search",
                        arguments=json.dumps({"keywords": "景点"}, ensure_ascii=False),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("已接入并查到西湖。"), Done("stop")],
            ]
        )

    def test_install_mcp_persists_and_tools_available_same_turn(
        self, env, monkeypatch
    ):
        client = make_client(env)
        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda u: AMAP_TOOLS
        )
        monkeypatch.setattr(
            "kate_cortex.mcp_client.call_mcp_tool",
            lambda url, name, args: "西湖（杭州市龙井路1号）",
        )
        fake = self._fake_provider()
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "帮我接入高德地图 MCP：https://mcp.example.com/mcp?key=k", "rag_enabled": False},
        )
        events = parse_sse(resp.text)
        names = [name for name, _ in events]

        # 前端收到 mcp_changed 提示（toast 告知接入成功）
        assert "mcp_changed" in names
        changed = next(data for name, data in events if name == "mcp_changed")
        assert changed["ok"] is True
        assert "高德地图" in changed["message"]

        # install 后工具表当轮即刷新（第 2 轮生成可见命名空间工具）
        round2_tools = [t["function"]["name"] for t in fake.calls[1]["tools"]]
        assert "mcp__mcp__maps_text_search" in round2_tools

        # 模型拿到了安装成功的摘要（含命名空间工具清单）
        # round2 的消息序列：… assistant(install 调用) → tool(install 结果) →
        # assistant(检索调用) → tool(检索结果)
        install_result_msg = fake.calls[1]["messages"][-3]
        assert install_result_msg["role"] == "tool"
        assert "mcp__mcp__maps_text_search" in install_result_msg["content"]

        # 配置持久化：对话结束后设置与设置页都能看到，且状态可用
        servers = client.get("/api/mcp/servers").json()["servers"]
        assert len(servers) == 1
        assert servers[0]["name"] == "高德地图"
        assert servers[0]["status"]["ok"] is True

        # 会话消息持久化了 install 调用
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert messages[1]["tool_calls"][0]["function"]["name"] == "install_mcp"

    def test_install_failure_informs_model_without_persisting(self, env, monkeypatch):
        client = make_client(env)

        def boom(url):
            raise ConnectionError("连接超时")

        monkeypatch.setattr("kate_cortex.mcp_client.list_mcp_tools", boom)
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="install_mcp",
                        arguments=json.dumps(
                            {"name": "amap", "url": MCP_URL}, ensure_ascii=False
                        ),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("抱歉，接入失败了。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "接入高德 MCP", "rag_enabled": False},
        )

        # 模型收到失败原因，可以如实转告用户
        tool_msg = fake.calls[1]["messages"][-1]
        assert "连接失败" in tool_msg["content"]

        # 没落任何配置
        assert client.get("/api/mcp/servers").json()["servers"] == []

    def test_remove_mcp(self, env, monkeypatch):
        client = make_client(env)
        add_server(client, monkeypatch)
        monkeypatch.setattr(
            "kate_cortex.mcp_client.call_mcp_tool",
            lambda url, name, args: (_ for _ in ()).throw(AssertionError("不应调用")),
        )
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="remove_mcp",
                        arguments=json.dumps({"id": "amap"}),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("已移除高德地图。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "移除高德地图", "rag_enabled": False},
        )
        events = parse_sse(resp.text)
        changed = [data for name, data in events if name == "mcp_changed"]
        assert changed and changed[0]["ok"] is True

        assert client.get("/api/mcp/servers").json()["servers"] == []

        # 模型收到移除确认
        assert "已移除" in fake.calls[1]["messages"][-1]["content"]

    def test_unknown_tool_no_longer_forwarded(self, env, monkeypatch):
        """历史行为：未知工具名转发到 MCP 端点；多服务下必须显式 mcp__ 前缀"""
        client = make_client(env)
        add_server(client, monkeypatch)

        def no_call(url, name, args):
            raise AssertionError("未知工具不应转发到 MCP")

        monkeypatch.setattr("kate_cortex.mcp_client.call_mcp_tool", no_call)
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(index=0, id="c1", name="not_a_real_tool", arguments="{}"),
                    Done("tool_calls"),
                ],
                [TextDelta("好的。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "随便", "rag_enabled": False},
        )

        assert "未知工具" in fake.calls[1]["messages"][-1]["content"]


class TestLegacyMigration:
    def test_mcp_url_migrated_to_servers(self, env):
        db = db_connect(env.db_path)
        settings = SettingsService(db.conn)
        settings.update({"mcp_url": MCP_URL})

        assert settings.migrate_mcp_url() is True
        servers = settings.get_all()["mcp_servers"]
        assert len(servers) == 1
        assert servers[0]["url"] == MCP_URL
        assert servers[0]["enabled"] is True
        # 旧键删除，幂等
        assert settings.migrate_mcp_url() is False
        assert settings.get_all().get("mcp_url") is None

    def test_existing_servers_not_overwritten(self, env):
        db = db_connect(env.db_path)
        settings = SettingsService(db.conn)
        settings.update(
            {"mcp_servers": [{"id": "amap", "name": "amap", "url": MCP_URL, "enabled": True}]}
        )
        settings.update({"mcp_url": "https://old.example.com/mcp"})

        assert settings.migrate_mcp_url() is False
        assert len(settings.get_all()["mcp_servers"]) == 1

    def test_settings_put_rejects_mcp_url(self, env):
        client = make_client(env)
        resp = client.put("/api/settings", json={"mcp_url": MCP_URL})
        assert resp.status_code == 422

"""MCP 接入测试：工具表转换 / 结果抽取 / agent 集成 / 连通性端点（全 mock 不出网）"""

import json

import pytest
from fastapi.testclient import TestClient
from mcp import types

from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.mcp_client import _result_text, _to_openai_tool
from kate_cortex.providers.base import Done, TextDelta, ToolCallDelta
from kate_cortex.providers.fake import FakeProvider

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


def make_client(env, mcp_url: str | None = MCP_URL) -> TestClient:
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    client = TestClient(app)
    client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": "sk-test"}, "mcp_url": mcp_url},
    )
    return client


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


class TestResultExtraction:
    def test_text_content(self):
        result = types.CallToolResult(
            content=[
                types.TextContent(type="text", text='{"pois": ["西湖"]}'),
                types.TextContent(type="text", text="共 1 条"),
            ]
        )
        assert _result_text(result) == '{"pois": ["西湖"]}\n共 1 条'

    def test_structured_content_fallback(self):
        result = types.CallToolResult(
            content=[], structured_content={"count": 2, "city": "杭州"}
        )
        assert json.loads(_result_text(result)) == {"count": 2, "city": "杭州"}

    def test_error_without_content(self):
        result = types.CallToolResult(content=[], is_error=True)
        assert _result_text(result) == "工具执行出错，无返回内容"


class TestAgentIntegration:
    def test_mcp_tools_merged_and_unknown_call_forwarded(self, env, monkeypatch):
        client = make_client(env)
        seen_urls: list[str] = []
        monkeypatch.setattr(
            "kate_cortex.routes.chat.list_mcp_tools",
            lambda url: seen_urls.append(url) or AMAP_TOOLS,
        )

        forwarded: dict = {}

        def fake_call(url, name, args):
            forwarded.update({"url": url, "name": name, "args": args})
            return json.dumps(
                {"pois": [{"name": "西湖", "address": "杭州市龙井路1号"}]},
                ensure_ascii=False,
            )

        monkeypatch.setattr("kate_cortex.chat.agent.call_mcp_tool", fake_call)

        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="maps_text_search",
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

        # 工具表 = 本地 5 个 + MCP 工具
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert tool_names[:5] == [
            "save_knowledge",
            "suggest_save",
            "export_markdown",
            "save_memory",
            "recall_memory",
        ]
        assert "maps_text_search" in tool_names

        # 未知本地工具名的调用转发到了配置的 MCP 端点
        assert seen_urls == [MCP_URL]
        assert forwarded["url"] == MCP_URL
        assert forwarded["name"] == "maps_text_search"
        assert forwarded["args"]["city"] == "杭州"

        # 工具结果原文喂回模型
        tool_msg = fake.calls[1]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert "西湖" in tool_msg["content"]

        # system prompt 注入 MCP 使用规则
        assert "外部实时工具" in fake.calls[0]["messages"][0]["content"]

        # 会话消息持久化了 MCP 工具调用
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert messages[1]["tool_calls"][0]["function"]["name"] == "maps_text_search"

    def test_mcp_unreachable_degrades_with_notice(self, env, monkeypatch):
        client = make_client(env)

        def boom(url):
            raise ConnectionError("连接超时")

        monkeypatch.setattr("kate_cortex.routes.chat.list_mcp_tools", boom)

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

        # 降级：无 MCP 工具、无 MCP 提示词，对话照常进行
        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert "maps_text_search" not in tool_names
        assert "外部实时工具" not in fake.calls[0]["messages"][0]["content"]

    def test_no_mcp_configured_keeps_local_only_tools(self, env):
        client = make_client(env, mcp_url=None)
        fake = FakeProvider(rounds=[[TextDelta("好"), Done("stop")]])
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = start_session(client)
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "随便聊聊", "rag_enabled": False},
        )

        tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
        assert tool_names == [
            "save_knowledge",
            "suggest_save",
            "export_markdown",
            "save_memory",
            "recall_memory",
        ]
        assert "外部实时工具" not in fake.calls[0]["messages"][0]["content"]


class TestMcpSettingsAndEndpoint:
    def test_mcp_url_roundtrip(self, env):
        client = make_client(env, mcp_url=None)

        assert client.get("/api/settings").json()["mcp_url"] is None

        client.put("/api/settings", json={"mcp_url": MCP_URL})
        assert client.get("/api/settings").json()["mcp_url"] == MCP_URL

        # 空字符串表示停用（null 会被后端 exclude_none 忽略）
        client.put("/api/settings", json={"mcp_url": ""})
        assert client.get("/api/settings").json()["mcp_url"] == ""

    def test_test_endpoint_without_url(self, env):
        client = make_client(env, mcp_url=None)
        body = client.post("/api/mcp/test").json()
        assert body["ok"] is False
        assert "未配置" in body["message"]

    def test_test_endpoint_reports_tools(self, env, monkeypatch):
        client = make_client(env)
        monkeypatch.setattr(
            "kate_cortex.routes.mcp.list_mcp_tools", lambda url: AMAP_TOOLS
        )
        body = client.post("/api/mcp/test").json()
        assert body["ok"] is True
        assert body["tools"] == ["maps_text_search"]
        assert "1 个工具" in body["message"]

    def test_test_endpoint_connection_failure(self, env, monkeypatch):
        client = make_client(env)

        def boom(url):
            raise RuntimeError("TLS 握手失败")

        monkeypatch.setattr("kate_cortex.routes.mcp.list_mcp_tools", boom)
        body = client.post("/api/mcp/test").json()
        assert body["ok"] is False
        assert "连接失败" in body["message"]

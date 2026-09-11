"""MCP 客户端：Streamable HTTP 接入外部工具服务（如高德地图 MCP Server）。

对同步 agent loop 暴露同步接口，每次调用建立独立连接（连接开销远小于
常驻事件循环的复杂度）；协议握手、SSE 流解析交给官方 mcp SDK。
mcp_url 形如 https://mcp.amap.com/mcp?key=xxx（key 直接拼在 URL 上）。
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

CONNECT_TIMEOUT_S = 15.0
CALL_TIMEOUT_S = 60.0


def list_mcp_tools(mcp_url: str) -> list[dict]:
    """拉取 MCP server 工具清单，转成 OpenAI function-calling 工具表"""
    return asyncio.run(_list_tools(mcp_url))


def call_mcp_tool(mcp_url: str, name: str, arguments: dict) -> str:
    """调用 MCP 工具，返回喂回模型的文本（工具原文，不二次加工）"""
    return asyncio.run(_call_tool(mcp_url, name, arguments))


async def _list_tools(mcp_url: str) -> list[dict]:
    async with _open_session(mcp_url) as session:
        result = await session.list_tools()
    return [_to_openai_tool(tool) for tool in result.tools]


async def _call_tool(mcp_url: str, name: str, arguments: dict) -> str:
    async with _open_session(mcp_url) as session:
        result = await session.call_tool(name, arguments or {})
    return _result_text(result)


@asynccontextmanager
async def _open_session(mcp_url: str) -> AsyncIterator[ClientSession]:
    async with streamable_http_client(mcp_url) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=CALL_TIMEOUT_S
        ) as session:
            await session.initialize()
            yield session


def _to_openai_tool(tool: types.Tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def to_namespaced_tools(openai_tools: list[dict], server_id: str) -> list[dict]:
    """工具名加 mcp__<服务id>__ 前缀：多服务接入时避免不同 server 的工具重名，
    同时让模型能从工具名识别所属服务（id 不含 __，可无损反解）"""
    namespaced = []
    for tool in openai_tools:
        fn = dict(tool["function"])
        fn["name"] = mcp_tool_name(server_id, fn["name"])
        namespaced.append({"type": "function", "function": fn})
    return namespaced


def mcp_tool_name(server_id: str, tool_name: str) -> str:
    return f"mcp__{server_id}__{tool_name}"


def parse_mcp_tool_name(name: str) -> tuple[str, str] | None:
    """mcp__<id>__<tool> → (id, tool)；非 MCP 前缀返回 None"""
    if not name.startswith("mcp__"):
        return None
    server_id, sep, tool_name = name[len("mcp__") :].partition("__")
    if not sep or not server_id or not tool_name:
        return None
    return server_id, tool_name


def _result_text(result: types.CallToolResult) -> str:
    texts = [
        block.text for block in result.content if isinstance(block, types.TextContent)
    ]
    if texts:
        return "\n".join(texts)
    if result.structured_content:
        return json.dumps(result.structured_content, ensure_ascii=False)
    if result.is_error:
        return "工具执行出错，无返回内容"
    return "工具无返回内容"

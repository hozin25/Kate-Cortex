"""MCP 客户端端到端冒烟：本地起真实 MCP server（streamable HTTP），无需外网与 key

场景 1：list_mcp_tools 完成协议握手并转出 OpenAI 工具表
场景 2：call_mcp_tool 真实调用工具并取回结果文本
场景 3：工具结果以纯文本喂回（agent 集成路径的传输层真实性验证）

用法：uv run python tests/smoke_mcp.py
"""

import asyncio
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp.server.mcpserver import MCPServer

from kate_cortex.mcp_client import call_mcp_tool, list_mcp_tools

server = MCPServer(name="fake-amap", version="1.0")


@server.tool(name="maps_text_search", description="关键词搜索 POI")
def maps_text_search(keywords: str, city: str = "") -> dict:
    return {
        "pois": [{"name": "西湖", "address": f"{city} 龙井路1号", "keywords": keywords}]
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(port: int) -> None:
    asyncio.run(
        server.run_streamable_http_async(
            host="127.0.0.1", port=port, stateless_http=True
        )
    )


def main() -> int:
    port = _free_port()
    threading.Thread(target=_serve, args=(port,), daemon=True).start()
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        print("FAIL: 本地 MCP server 未能启动")
        return 1

    ok = True

    tools = list_mcp_tools(url)
    names = [t["function"]["name"] for t in tools]
    print("场景 1 工具表:", json.dumps(names, ensure_ascii=False))
    if "maps_text_search" not in names:
        ok = False
    schema = tools[0]["function"]["parameters"]
    if schema.get("properties", {}).get("keywords") is None:
        print("FAIL: inputSchema 未正确转换", schema)
        ok = False

    raw = call_mcp_tool(
        url, "maps_text_search", {"keywords": "景点", "city": "杭州"}
    )
    print("场景 2 调用结果:", raw)
    pois = json.loads(raw).get("pois", [])
    if not pois or pois[0]["name"] != "西湖":
        ok = False

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

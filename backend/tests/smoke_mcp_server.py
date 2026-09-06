"""MCP 服务端冒烟：真实 stdio 握手 + 工具调用（模拟 Claude Code 接入）

流程：临时 vault 播种一条知识 → 以子进程方式启动 kate-cortex-mcp →
initialize → list_tools → search_knowledge / save_knowledge → 校验落盘。

用法：uv run python tests/smoke_mcp_server.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def seed_vault(vault: Path) -> None:
    from kate_cortex.config import Config
    from kate_cortex.db import connect as db_connect
    from kate_cortex.search import Search
    from kate_cortex.storage import Storage

    database = db_connect(vault / "index.sqlite")
    storage = Storage(
        config=Config(vault_path=vault, db_path=vault / "index.sqlite"),
        db=database,
        search=Search(database.conn),
    )
    storage.create_entry(
        title="Redis pipeline 踩坑",
        source="manual",
        content="pipeline 事务模式下不返回结果，改用 watch。",
    )


async def run_smoke(vault: Path) -> bool:
    params = StdioServerParameters(
        command="uv",
        args=["run", "kate-cortex-mcp"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={
            **os.environ,
            "KATE_VAULT_PATH": str(vault),
            "KATE_DB_PATH": str(vault / "index.sqlite"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"  服务端: {info.server_info.name} v{info.server_info.version}")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"  工具: {names}")
            expected = [
                "search_knowledge",
                "get_entry",
                "save_knowledge",
                "list_collections",
                "recall_memory",
                "save_memory",
            ]
            assert names == expected, f"工具清单不符: {names}"

            result = await session.call_tool(
                "search_knowledge", {"query": "pipeline 事务", "limit": 3}
            )
            print(f"  search 命中: {[c.text[:60] for c in result.content]}")
            assert not result.is_error

            saved = await session.call_tool(
                "save_knowledge",
                {
                    "title": "MCP 冒烟总结",
                    "content_markdown": "stdio 链路验证通过。",
                    "collections": [],
                },
            )
            print(f"  save 结果: {[c.text for c in saved.content]}")
            assert not saved.is_error
    return True


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="kate-smoke-mcp-"))
    vault = workdir / "vault"
    vault.mkdir()
    seed_vault(vault)
    print("\n场景：stdio 握手 + 工具调用")
    ok = asyncio.run(run_smoke(vault))
    mds = list(vault.rglob("*.md"))
    print(f"  vault 内 md: {[m.name for m in mds]}")
    assert any("mcp-mao-yan" in m.name for m in mds), "save_knowledge 未落盘"
    print("\n总结:", {"stdio_smoke": ok})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

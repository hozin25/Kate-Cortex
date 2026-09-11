"""MCP 接入管理 skill：install_mcp / remove_mcp。

让用户在对话里说「帮我接入 XX 的 MCP」即可由 Kate 完成验证 + 落盘，
无需手动去设置页填端点；接入结果实时同步到设置页的状态展示。
所有连接性校验都在 mcp_registry.install_server 里完成——失败不落任何配置，
模型只会拿到失败原因，不会产生「装好了」的错觉。
"""

_INSTALL_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "服务名，2-12 字（如「高德地图」）。用英文短名（如 amap、github）"
                "则它同时作为工具前缀，可读性更好"
            ),
        },
        "url": {
            "type": "string",
            "description": (
                "MCP Streamable HTTP 端点完整 URL（含 key/参数），"
                "如 https://mcp.amap.com/mcp?key=xxx。只能来自用户提供或官方文档，"
                "严禁猜测编造"
            ),
        },
    },
    "required": ["name", "url"],
}

_REMOVE_PARAMS = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "要移除的服务 id（install_mcp 返回值；或工具前缀 mcp__<id>__ 中的 id）",
        },
    },
    "required": ["id"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "install_mcp",
            "description": (
                "接入一个外部 MCP 服务（地图、天气、搜索、GitHub 等提供 "
                "Streamable HTTP 端点的服务）：验证连通后保存，其工具即刻可用。"
                "用户想加工具/接外部服务/给了 MCP 端点和 key 时调用。"
            ),
            "parameters": _INSTALL_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_mcp",
            "description": "移除一个已接入的外部 MCP 服务（id 见 install_mcp 结果或工具前缀）",
            "parameters": _REMOVE_PARAMS,
        },
    },
]


def install_mcp(mcp, args: dict) -> dict:
    result = mcp.install(args.get("name", ""), args.get("url", ""))
    if result.get("ok"):
        result["message"] = (
            f"已接入《{result['name']}》，{result['tool_count']} 个工具可用"
        )
    return result


def remove_mcp(mcp, args: dict) -> dict:
    result = mcp.remove(str(args.get("id", "")).strip())
    if result.get("ok"):
        result["message"] = f"已移除外部服务《{result['name']}》"
    return result

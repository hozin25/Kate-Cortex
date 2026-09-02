"""MCP 工具服务连通性测试"""

from fastapi import APIRouter, Request

from ..mcp_client import list_mcp_tools

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/test")
def test_mcp(request: Request):
    mcp_url = (
        (request.app.state.settings_service.get_all().get("mcp_url") or "").strip()
    )
    if not mcp_url:
        return {"ok": False, "message": "未配置 MCP 服务地址"}
    try:
        tools = list_mcp_tools(mcp_url)
    except Exception as exc:
        return {"ok": False, "message": f"连接失败: {exc}"}
    names = [t["function"]["name"] for t in tools]
    if not names:
        return {"ok": False, "message": "连接成功，但服务未提供任何工具", "tools": []}
    return {
        "ok": True,
        "message": f"已发现 {len(names)} 个工具: {', '.join(names[:6])}"
        + ("…" if len(names) > 6 else ""),
        "tools": names,
    }

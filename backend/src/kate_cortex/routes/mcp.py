"""MCP 服务管理：多服务接入（CRUD）+ 连通性测试。

服务列表存 settings["mcp_servers"]；每次添加 / 手动测试都会真实走一遍
list_tools 并刷新状态缓存，设置页与对话内 install_mcp 共用这套状态。
"""

from fastapi import APIRouter, HTTPException, Request

from ..mcp_registry import (
    McpInstallError,
    check_server,
    get_server,
    install_server,
    load_servers,
    remove_server,
    set_server_enabled,
    status_of,
)
from ..models import McpServerCreate, McpServerUpdate
from ..multiuser import get_services

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _server_out(server: dict) -> dict:
    return {**server, "status": status_of(server["id"])}


@router.get("/servers")
def list_servers(request: Request):
    servers = load_servers(get_services(request).settings_service)
    return {"servers": [_server_out(s) for s in servers]}


@router.post("/servers", status_code=201)
def add_server(payload: McpServerCreate, request: Request):
    """添加服务：先真实连接验证（list_tools），失败返回 400 且不落配置"""
    try:
        server, raw_tools = install_server(
            get_services(request).settings_service, payload.name, payload.url
        )
    except McpInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _server_out(server) | {"tool_count": len(raw_tools)}


@router.patch("/servers/{server_id}")
def update_server(server_id: str, payload: McpServerUpdate, request: Request):
    settings_service = get_services(request).settings_service
    try:
        if payload.enabled is not None:
            set_server_enabled(settings_service, server_id, payload.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="未接入该服务")
    server = get_server(settings_service, server_id)
    return _server_out(server)


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(server_id: str, request: Request):
    try:
        remove_server(get_services(request).settings_service, server_id)
    except McpInstallError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/servers/{server_id}/test")
def test_server(server_id: str, request: Request):
    """连通性测试：结果统一 200 + {ok, message}（测试不通过不是传输层错误）"""
    server = get_server(get_services(request).settings_service, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="未接入该服务")
    return check_server(server)

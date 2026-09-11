"""MCP 服务注册表：多服务配置持久化 + 连通状态缓存 + 会话内运行时。

多服务模型（取代旧的单 mcp_url）：settings["mcp_servers"] = [
    {"id": "amap", "name": "高德地图", "url": "https://…?key=…", "enabled": true}, …
]
id 是 [a-z0-9_-] 短标识，用作工具名前缀 mcp__<id>__<tool>；可见名 name 随意。

状态缓存（_status）记录每个服务最近一次 list_tools 的结果（对话开始、
设置页检测、install_mcp 都会刷新），设置页据此展示可用 / 不可用。

McpContext 是单次对话的运行时：持有当前已启用服务的命名空间工具表，
agent loop 每轮从 tool_defs() 重建工具列表——install_mcp 成功后新服务
的工具当轮即可被模型调用。
"""

import ipaddress
import logging
import os
import re
import socket
from datetime import datetime
from urllib.parse import urlsplit

from . import mcp_client
from .config import is_multiuser
from .mcp_client import parse_mcp_tool_name

logger = logging.getLogger(__name__)

# 工具名总长上限 128（OpenAI/Anthropic 规范），5(mcp__)+24(id)+2(__) 留足余量
MAX_SERVERS = 10
ID_MAX_LEN = 24


class McpInstallError(Exception):
    """install_mcp / 手动添加的校验失败（消息直接展示给用户与模型）"""


def assert_public_endpoint(url: str) -> None:
    """多用户服务器上禁止把 MCP 指向内网（SSRF：模型可被网页内容诱导，
    让服务器代为访问内网服务）。单用户本机形态默认不启用——接 localhost
    的本地 MCP server 是合法场景；KATE_MCP_ALLOW_PRIVATE=1 可强制关闭"""
    if os.environ.get("KATE_MCP_ALLOW_PRIVATE") == "1" or not is_multiuser():
        return
    host = urlsplit(url).hostname
    if not host:
        raise McpInstallError("URL 缺少主机名")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise McpInstallError(f"域名解析失败: {exc}") from exc
    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise McpInstallError(f"不允许接入内网地址: {host}")


# ---------------------------------------------------------------- 状态缓存

_STATUS: dict[str, dict] = {}


def record_status(server_id: str, ok: bool, message: str, tool_names: list[str]) -> None:
    _STATUS[server_id] = {
        "ok": ok,
        "message": message,
        "tool_count": len(tool_names),
        "tools": tool_names[:20],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def status_of(server_id: str) -> dict | None:
    return _STATUS.get(server_id)


def check_server(server: dict) -> dict:
    """实测一个服务（list_tools），刷新状态缓存并返回状态"""
    try:
        assert_public_endpoint(server["url"])
        tools = [t["function"]["name"] for t in mcp_client.list_mcp_tools(server["url"])]
    except Exception as exc:
        message = f"连接失败: {exc}"
        record_status(server["id"], ok=False, message=message, tool_names=[])
        return {"ok": False, "message": message, "tool_count": 0, "tools": []}
    message = (
        f"已发现 {len(tools)} 个工具: {', '.join(tools[:6])}"
        + ("…" if len(tools) > 6 else "")
    )
    record_status(server["id"], ok=True, message=message, tool_names=tools)
    return {"ok": True, "message": message, "tool_count": len(tools), "tools": tools}


# ---------------------------------------------------------------- 配置持久化

def load_servers(settings_service) -> list[dict]:
    """读取并归一化 mcp_servers：剔除残缺行、id 去重、保序"""
    raw = settings_service.get_all().get("mcp_servers") or []
    servers: list[dict] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        server = {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "enabled": bool(item.get("enabled", True)),
        }
        if not server["id"] or not server["url"]:
            continue
        if server["id"] in seen_ids:
            continue
        seen_ids.add(server["id"])
        servers.append(server)
    return servers


def save_servers(settings_service, servers: list[dict]) -> None:
    settings_service.update({"mcp_servers": servers})


def get_server(settings_service, server_id: str) -> dict | None:
    return next(
        (s for s in load_servers(settings_service) if s["id"] == server_id), None
    )


def install_server(
    settings_service, name: str, url: str
) -> tuple[dict, list[dict]]:
    """校验端点真实可用后落盘；返回 (server, OpenAI 风格工具定义列表)。

    连接失败 / 无工具直接抛 McpInstallError，不写任何配置——保证设置里的
    服务都经过验证。url 已存在时幂等：视为重新验证同一服务。"""
    name = (name or "").strip()
    url = (url or "").strip()
    if not name:
        raise McpInstallError("缺少服务名称")
    if not url.startswith(("http://", "https://")):
        raise McpInstallError("URL 必须以 http:// 或 https:// 开头")
    assert_public_endpoint(url)

    servers = load_servers(settings_service)
    if len(servers) >= MAX_SERVERS and not any(s["url"] == url for s in servers):
        raise McpInstallError(f"最多接入 {MAX_SERVERS} 个服务")

    try:
        raw_tools = mcp_client.list_mcp_tools(url)
    except Exception as exc:
        raise McpInstallError(f"连接失败: {exc}") from exc
    if not raw_tools:
        raise McpInstallError("端点连接成功，但未提供任何工具")
    tool_names = [t["function"]["name"] for t in raw_tools]

    existing = next((s for s in servers if s["url"] == url), None)
    if existing is not None:
        if not existing["enabled"]:
            # 重新接入 = 同时恢复启用
            existing = set_server_enabled(settings_service, existing["id"], True)
        record_status(
            existing["id"],
            ok=True,
            message=_tool_summary_message(tool_names),
            tool_names=tool_names,
        )
        return existing, raw_tools

    server = {
        "id": _unique_id(name, servers),
        "name": name,
        "url": url,
        "enabled": True,
    }
    save_servers(settings_service, [*servers, server])
    record_status(
        server["id"],
        ok=True,
        message=_tool_summary_message(tool_names),
        tool_names=tool_names,
    )
    return server, raw_tools


def remove_server(settings_service, server_id: str) -> dict:
    servers = load_servers(settings_service)
    target = next((s for s in servers if s["id"] == server_id), None)
    if target is None:
        raise McpInstallError(f"未接入该服务: {server_id}")
    save_servers(settings_service, [s for s in servers if s["id"] != server_id])
    _STATUS.pop(server_id, None)
    return target


def set_server_enabled(settings_service, server_id: str, enabled: bool) -> dict:
    servers = load_servers(settings_service)
    target = next((s for s in servers if s["id"] == server_id), None)
    if target is None:
        raise KeyError(server_id)
    target = {**target, "enabled": enabled}
    save_servers(
        settings_service,
        [target if s["id"] == server_id else s for s in servers],
    )
    return target


def _tool_summary_message(tool_names: list[str]) -> str:
    return (
        f"已发现 {len(tool_names)} 个工具: {', '.join(tool_names[:6])}"
        + ("…" if len(tool_names) > 6 else "")
    )


def _unique_id(name: str, servers: list[dict]) -> str:
    base = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-_")[:ID_MAX_LEN] or "mcp"
    taken = {s["id"] for s in servers}
    if base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


# ---------------------------------------------------------------- 会话内运行时

class McpContext:
    """单次对话的 MCP 运行时：已启用服务的命名空间工具表 + 同轮安装/移除。

    install/remove 直接改设置并同步内存状态，agent loop 下一轮的
    tools = 基础工具 + tool_defs() 即拿到新工具表。"""

    def __init__(self, settings_service):
        self.settings_service = settings_service
        self._servers: dict[str, dict] = {}
        self._tools: dict[str, list[dict]] = {}
        self.failures: list[str] = []

    @classmethod
    def load(cls, settings_service) -> "McpContext":
        """拉取所有已启用服务的工具表；失败的服务记入 failures（由调用方
        合并成一条 mcp_notice），不阻断对话"""
        ctx = cls(settings_service)
        for server in load_servers(settings_service):
            if not server["enabled"]:
                continue
            try:
                assert_public_endpoint(server["url"])
                raw = mcp_client.list_mcp_tools(server["url"])
            except Exception as exc:
                ctx.failures.append(f"{server['name']}: {exc}")
                record_status(server["id"], ok=False, message=f"连接失败: {exc}", tool_names=[])
                continue
            names = [t["function"]["name"] for t in raw]
            ctx._servers[server["id"]] = server
            ctx._tools[server["id"]] = mcp_client.to_namespaced_tools(raw, server["id"])
            record_status(server["id"], ok=True, message=_tool_summary_message(names), tool_names=names)
        return ctx

    @property
    def has_tools(self) -> bool:
        return bool(self._tools)

    def tool_defs(self) -> list[dict]:
        return [tool for tools in self._tools.values() for tool in tools]

    def dispatch(self, tool_name: str, arguments: dict) -> str:
        parsed = parse_mcp_tool_name(tool_name)
        if parsed is None:
            raise ValueError(f"不是外部工具: {tool_name}")
        server_id, real_name = parsed
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"未接入该外部服务: {server_id}")
        return mcp_client.call_mcp_tool(server["url"], real_name, arguments)

    def install(self, name: str, url: str) -> dict:
        try:
            server, raw_tools = install_server(self.settings_service, name, url)
        except McpInstallError as exc:
            return {"ok": False, "message": str(exc)}
        if server["id"] not in self._servers:
            self._servers[server["id"]] = server
            self._tools[server["id"]] = mcp_client.to_namespaced_tools(
                raw_tools, server["id"]
            )
        return {
            "ok": True,
            "id": server["id"],
            "name": server["name"],
            "tool_count": len(raw_tools),
            # 模型侧给命名空间全名，下一步可直接照抄调用
            "tools": [
                mcp_client.mcp_tool_name(server["id"], t["function"]["name"])
                for t in raw_tools[:15]
            ],
            "note": "已保存到设置，重启后仍生效；这些工具本轮对话即可直接调用",
        }

    def remove(self, server_id: str) -> dict:
        try:
            target = remove_server(self.settings_service, server_id)
        except McpInstallError as exc:
            return {"ok": False, "message": str(exc)}
        self._servers.pop(server_id, None)
        self._tools.pop(server_id, None)
        return {"ok": True, "id": server_id, "name": target["name"]}

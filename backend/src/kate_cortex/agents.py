"""自定义 agent：settings["agents"] 存储与 `/名称` 引用解析（AGENTS_PLAN.md）。

agent = system prompt 角色段 + 可选请求级模型覆盖，不裁剪工具能力；列表经
/api/agents 管理（对齐 /api/mcp/servers 的先例），多用户云端版随每用户独立
SQLite 天然隔离。引用前缀保留在消息里：历史可见，regenerate/resend 天然继承。
"""

import re
import uuid
from datetime import datetime

from .settings import KNOWN_PROVIDERS

# 名称与引用 token 同规则：单 token（无空白、无 /），中英文/数字/连字符/下划线
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff-]{1,32}$")
# 消息开头的引用前缀；(?=\s|$) 要求名称后是空格或结尾，「/医生你好」不算引用
AGENT_TOKEN = re.compile(r"^/([A-Za-z0-9_\u4e00-\u9fff-]{1,32})(?=\s|$)")

MAX_DESCRIPTION = 60
MAX_PROMPT = 4000


class AgentValidationError(ValueError):
    """字段格式不合法（路由映射 422）"""


class AgentNameTaken(ValueError):
    """名称与已有 agent 重复，大小写不敏感（路由映射 409）"""


def list_agents(settings_service) -> list[dict]:
    # get_all 未持久化时回落 DEFAULTS 的可变列表，浅拷贝防调用方原地修改污染默认值
    return [dict(a) for a in settings_service.get_all()["agents"]]


def create_agent(settings_service, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    provider = (payload.get("provider") or "").strip() or None
    model = (payload.get("model") or "").strip() or None
    _validate(name, description, prompt, provider, model)
    agents = list_agents(settings_service)
    _ensure_name_free(agents, name)
    agent = {
        "id": f"kc_agent_{uuid.uuid4().hex[:8]}",
        "name": name,
        "description": description,
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "enabled": True,
        "created_at": _now(),
    }
    save_agents(settings_service, [*agents, agent])
    return agent


def update_agent(settings_service, agent_id: str, patch: dict) -> dict:
    agents = list_agents(settings_service)
    for index, agent in enumerate(agents):
        if agent["id"] != agent_id:
            continue
        merged = {**agent}
        for key in ("name", "description", "prompt"):
            if key in patch:
                merged[key] = (patch[key] or "").strip()
        for key in ("provider", "model"):
            if key in patch:
                merged[key] = (patch[key] or "").strip() or None
        if "enabled" in patch:
            merged["enabled"] = bool(patch["enabled"])
        _validate(
            merged["name"], merged["description"], merged["prompt"],
            merged["provider"], merged["model"],
        )
        _ensure_name_free([a for a in agents if a["id"] != agent_id], merged["name"])
        agents[index] = merged
        save_agents(settings_service, agents)
        return merged
    raise KeyError(agent_id)


def delete_agent(settings_service, agent_id: str) -> None:
    agents = list_agents(settings_service)
    remaining = [a for a in agents if a["id"] != agent_id]
    if len(remaining) == len(agents):
        raise KeyError(agent_id)
    save_agents(settings_service, remaining)


def resolve_agent(content: str, agents: list[dict]) -> dict | None:
    """content 以 `/名称` 开头且命中 enabled 的 agent 时返回它，否则 None。
    已删除/已停用/改名的旧前缀一律回落默认 Kate；名称大小写不敏感。"""
    match = AGENT_TOKEN.match(content or "")
    if match is None:
        return None
    token = match.group(1).casefold()
    for agent in agents or []:
        if agent.get("enabled", True) and agent["name"].casefold() == token:
            return agent
    return None


def strip_agent_token(content: str) -> str:
    """去掉开头的 `/名称` 引用前缀（无前缀则原样返回），供标题生成剥前缀用"""
    return AGENT_TOKEN.sub("", content or "", count=1).lstrip()


def save_agents(settings_service, agents: list[dict]) -> None:
    settings_service.update({"agents": agents})


def _validate(name: str, description: str, prompt: str, provider, model) -> None:
    if not AGENT_NAME_PATTERN.match(name):
        raise AgentValidationError("名称需为 1-32 位中文、英文、数字、连字符或下划线（不含空格与 /）")
    if len(description) > MAX_DESCRIPTION:
        raise AgentValidationError(f"描述最长 {MAX_DESCRIPTION} 字")
    if not prompt:
        raise AgentValidationError("提示词不能为空")
    if len(prompt) > MAX_PROMPT:
        raise AgentValidationError(f"提示词最长 {MAX_PROMPT} 字")
    if (provider or model) and not (provider and model):
        raise AgentValidationError("指定模型时 provider 与 model 必须同时提供（留空则跟随会话模型）")
    if provider and provider not in KNOWN_PROVIDERS:
        raise AgentValidationError(f"未知 provider: {provider}")


def _ensure_name_free(agents: list[dict], name: str) -> None:
    folded = name.casefold()
    for agent in agents:
        if agent["name"].casefold() == folded:
            raise AgentNameTaken(f"已有同名 agent「{agent['name']}」，换个名字吧")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")

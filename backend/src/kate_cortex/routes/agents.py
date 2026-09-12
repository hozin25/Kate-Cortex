"""自定义 agent 管理：CRUD（AGENTS_PLAN.md §3.1）。

存储于 settings["agents"]（与 mcp_servers 同构）；字段格式校验映射 422、
重名映射 409、不存在映射 404。调用方（对话链路）用 agents.resolve_agent
解析消息前缀。
"""

from fastapi import APIRouter, HTTPException, Request

from ..agents import (
    AgentNameTaken,
    AgentValidationError,
    create_agent,
    delete_agent,
    list_agents,
    update_agent,
)
from ..models import AgentCreate, AgentUpdate
from ..multiuser import get_services

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def get_agents(request: Request):
    return {"agents": list_agents(get_services(request).settings_service)}


@router.post("", status_code=201)
def add_agent(payload: AgentCreate, request: Request):
    try:
        return create_agent(get_services(request).settings_service, payload.model_dump())
    except AgentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AgentNameTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/{agent_id}")
def patch_agent(agent_id: str, payload: AgentUpdate, request: Request):
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=422, detail="至少提供一个可更新字段")
    try:
        return update_agent(get_services(request).settings_service, agent_id, data)
    except KeyError:
        raise HTTPException(status_code=404, detail="未找到该 agent")
    except AgentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AgentNameTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/{agent_id}", status_code=204)
def remove_agent(agent_id: str, request: Request):
    try:
        delete_agent(get_services(request).settings_service, agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="未找到该 agent")

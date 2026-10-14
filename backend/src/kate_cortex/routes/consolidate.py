"""记忆巩固端点（CONSOLIDATE_PLAN.md §5）：状态 / 分批整理 / 提案处置 / 撤销合并"""

from fastapi import APIRouter, HTTPException, Request

from ..consolidator import ConsolidateError, consolidate_pass, duplicate_pairs
from ..models import (
    ConsolidateRunIn,
    ConsolidateStatusOut,
    ProposalAcceptIn,
    ProposalOut,
)
from ..multiuser import get_services
from ..providers.base import ProviderError
from ..storage import EntryNotFound, StorageError

router = APIRouter(prefix="/consolidate", tags=["consolidate"])


@router.get("/status", response_model=ConsolidateStatusOut)
def consolidate_status(request: Request):
    services = get_services(request)
    settings = services.settings_service.get_all()
    proposals: list[dict] = settings.get("consolidation_proposals") or []
    judged: list[dict] = settings.get("consolidation_judged") or []
    vector_available = bool(
        services.storage.vectors is not None and services.storage.vectors.available
    )
    candidates = (
        len(duplicate_pairs(services.storage, proposals, judged))
        if vector_available
        else 0
    )
    return {
        "consolidated_at": settings.get("consolidated_at"),
        "report": settings.get("consolidation_report"),
        "proposals": proposals,
        "candidates": candidates,
        "vector_available": vector_available,
    }


@router.post("/run")
def consolidate_run(payload: ConsolidateRunIn, request: Request):
    """一轮整理（规则引擎 + ≤limit 对 LLM 判定 + 画像提案）。remaining>0 时
    前端继续调用；provider 失败 400 供前端停止循环"""
    services = get_services(request)
    settings = services.settings_service.get_all()
    try:
        provider = services.provider_factory(settings["default_provider"])
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        result = consolidate_pass(
            services.storage, services.settings_service, provider, limit=payload.limit
        )
    except ConsolidateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/proposals/{proposal_id}/accept", response_model=list[ProposalOut])
def accept_proposal(proposal_id: str, payload: ProposalAcceptIn, request: Request):
    services = get_services(request)
    proposals = _proposals(services.settings_service)
    proposal = _take(proposals, proposal_id)
    storage = services.storage
    try:
        if proposal["kind"] == "conflict":
            keep = payload.keep if payload.keep in ("a", "b") else "b"
            drop = proposal["b"] if keep == "a" else proposal["a"]
            storage.delete_entry(drop["id"])
        elif proposal["kind"] == "profile_update":
            entry = storage.get_entry(proposal["target_id"])
            if entry is None:
                raise HTTPException(status_code=410, detail="目标档案条目已不存在")
            storage.update_entry(
                proposal["target_id"],
                title=proposal.get("title") or entry.title,
                content=proposal["content"],
            )
        elif proposal["kind"] == "profile_create":
            storage.create_entry(
                title=proposal["title"],
                content=proposal["content"],
                source="manual",
                collections=["个人信息"],
                importance=3,
            )
        else:
            raise HTTPException(status_code=422, detail=f"未知提案类型: {proposal['kind']}")
    except (EntryNotFound, StorageError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _save_proposals(services, proposals)
    return proposals


@router.delete("/proposals/{proposal_id}", response_model=list[ProposalOut])
def dismiss_proposal(proposal_id: str, request: Request):
    services = get_services(request)
    proposals = _proposals(services.settings_service)
    _take(proposals, proposal_id)
    _save_proposals(services, proposals)
    return proposals


@router.post("/undo/{entry_id}")
def undo_merge(entry_id: str, request: Request):
    """撤销合并：从 .trash 恢复被合并的原条目（合并产物保留，可手动删除）"""
    try:
        entry = get_services(request).storage.restore_entry(entry_id)
    except (EntryNotFound, StorageError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"entry_id": entry.id, "slug": entry.slug, "title": entry.title}


def _proposals(settings_service) -> list[dict]:
    return settings_service.get_all().get("consolidation_proposals") or []


def _save_proposals(services, proposals: list[dict]) -> None:
    services.settings_service.update({"consolidation_proposals": proposals})


def _take(proposals: list[dict], proposal_id: str) -> dict:
    for index, proposal in enumerate(proposals):
        if proposal.get("id") == proposal_id:
            return proposals.pop(index)
    raise HTTPException(status_code=404, detail="提案不存在或已处理")

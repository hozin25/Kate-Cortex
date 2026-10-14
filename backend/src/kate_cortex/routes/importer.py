from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..enrich import EnrichError, enrich_batch
from ..importer import ImportError_, import_obsidian, import_vault
from ..models import EnrichIn, EnrichOut
from ..multiuser import get_services
from ..providers.base import ProviderError

router = APIRouter(tags=["import"])


class VaultImportIn(BaseModel):
    source_dir: str
    dry_run: bool = False
    merge_keys: bool = True


class ObsidianImportIn(BaseModel):
    source_dir: str
    tags_as_collections: bool = True
    dry_run: bool = False


@router.post("/import/vault")
def vault_import(payload: VaultImportIn, request: Request):
    try:
        report = import_vault(
            get_services(request).storage,
            get_services(request).settings_service,
            payload.source_dir,
            dry_run=payload.dry_run,
            merge_keys=payload.merge_keys,
        )
    except ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report.as_dict()


@router.post("/import/obsidian")
def obsidian_import(payload: ObsidianImportIn, request: Request):
    try:
        report = import_obsidian(
            get_services(request).storage,
            payload.source_dir,
            tags_as_collections=payload.tags_as_collections,
            dry_run=payload.dry_run,
        )
    except ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report.as_dict()


@router.post("/import/enrich", response_model=EnrichOut)
def import_enrich(payload: EnrichIn, request: Request):
    """分批加工 import 条目（IMPORT_ENRICH_PLAN.md）：前端循环调用直到 done。
    provider 走默认会话模型；构建或调用失败 400，前端据此停止循环并提示"""
    services = get_services(request)
    settings = services.settings_service.get_all()
    try:
        provider = services.provider_factory(settings["default_provider"])
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        result = enrich_batch(services.storage, provider, limit=payload.limit)
    except EnrichError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result.as_dict()

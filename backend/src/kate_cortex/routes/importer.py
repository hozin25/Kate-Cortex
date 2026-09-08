from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..importer import ImportError_, import_obsidian, import_vault

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
            request.app.state.storage,
            request.app.state.settings_service,
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
            request.app.state.storage,
            payload.source_dir,
            tags_as_collections=payload.tags_as_collections,
            dry_run=payload.dry_run,
        )
    except ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report.as_dict()

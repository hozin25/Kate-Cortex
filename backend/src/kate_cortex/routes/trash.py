"""回收站端点：列表 / 恢复（复用 entries restore）/ 彻底删除"""

from fastapi import APIRouter, HTTPException, Request

from ..models import TrashOut
from ..storage import EntryNotFound

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get("", response_model=list[TrashOut])
def list_trash(request: Request):
    return [TrashOut(**vars(t)) for t in request.app.state.storage.list_trash()]


@router.delete("/{entry_id}", status_code=200)
def purge_trashed(entry_id: str, request: Request):
    try:
        removed = request.app.state.storage.purge_trashed(entry_id)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"purged": removed}

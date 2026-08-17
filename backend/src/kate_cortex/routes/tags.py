from fastapi import APIRouter, HTTPException, Request

from ..models import TagOut
from ..storage import EntryNotFound

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
def list_tags(request: Request):
    rows = request.app.state.storage.list_tags()
    return [TagOut(name=name, count=count) for name, count in rows]


@router.delete("/{name}", status_code=204)
def delete_tag(name: str, request: Request):
    try:
        request.app.state.storage.delete_tag(name)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))

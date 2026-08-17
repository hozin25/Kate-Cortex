from fastapi import APIRouter, HTTPException, Request

from ..models import EntryCreate, EntryListOut, EntryOut, EntrySummaryOut, EntryUpdate
from ..storage import EntryNotFound, StorageError

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", status_code=201, response_model=EntryOut)
def create_entry(payload: EntryCreate, request: Request):
    try:
        entry = request.app.state.storage.create_entry(**payload.model_dump())
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EntryOut(**vars(entry))


@router.get("", response_model=EntryListOut)
def list_entries(
    request: Request,
    type: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    items, total = request.app.state.storage.list_entries(
        type=type, tag=tag, q=q, limit=limit, offset=offset
    )
    return EntryListOut(
        items=[EntrySummaryOut(**vars(item)) for item in items], total=total
    )


@router.get("/{id_or_slug}", response_model=EntryOut)
def get_entry(id_or_slug: str, request: Request):
    entry = request.app.state.storage.get_entry(id_or_slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    return EntryOut(**vars(entry))


@router.put("/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: str, payload: EntryUpdate, request: Request):
    try:
        entry = request.app.state.storage.update_entry(
            entry_id, **payload.model_dump(exclude_none=True)
        )
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EntryOut(**vars(entry))


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: str, request: Request):
    try:
        request.app.state.storage.delete_entry(entry_id)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{entry_id}/restore", response_model=EntryOut)
def restore_entry(entry_id: str, request: Request):
    try:
        entry = request.app.state.storage.restore_entry(entry_id)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return EntryOut(**vars(entry))


@router.get("/{entry_id}/links", response_model=list[EntrySummaryOut])
def entry_links(entry_id: str, request: Request):
    if request.app.state.storage.get_entry(entry_id) is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    backlinks = request.app.state.storage.backlinks(entry_id)
    return [EntrySummaryOut(**vars(item)) for item in backlinks]

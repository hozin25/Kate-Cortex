from fastapi import APIRouter, HTTPException, Request

from ..models import CollectionCreate, CollectionOut, CollectionRename
from ..multiuser import get_services
from ..storage import (
    CollectionExists,
    CollectionNotFound,
    ProtectedCollection,
    StorageError,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionOut])
def list_collections(request: Request):
    rows = get_services(request).storage.list_collections()
    return [CollectionOut(name=name, count=count) for name, count in rows]


@router.post("", status_code=201, response_model=CollectionOut)
def create_collection(payload: CollectionCreate, request: Request):
    try:
        get_services(request).storage.create_collection(payload.name)
    except CollectionExists as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CollectionOut(name=payload.name.strip(), count=0)


@router.put("/{name}", response_model=CollectionOut)
def rename_collection(name: str, payload: CollectionRename, request: Request):
    storage = get_services(request).storage
    try:
        count = storage.rename_collection(name, payload.name)
    except CollectionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CollectionExists as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ProtectedCollection as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CollectionOut(name=payload.name.strip(), count=count)


@router.delete("/{name}", status_code=204)
def delete_collection(name: str, request: Request):
    try:
        get_services(request).storage.delete_collection(name)
    except CollectionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProtectedCollection as exc:
        raise HTTPException(status_code=409, detail=str(exc))

from fastapi import APIRouter, Request

from ..models import ReindexOut
from ..multiuser import get_services

router = APIRouter(tags=["system"])


@router.post("/sync", response_model=ReindexOut)
def reindex(request: Request):
    report, indexed = get_services(request).storage.reindex()
    return ReindexOut(
        indexed=indexed,
        unindexed_before=report.unindexed,
        missing_files=report.missing_files,
    )

from fastapi import APIRouter, Request

from ..models import ReindexOut

router = APIRouter(tags=["system"])


@router.post("/sync", response_model=ReindexOut)
def reindex(request: Request):
    report, indexed = request.app.state.storage.reindex()
    return ReindexOut(
        indexed=indexed,
        unindexed_before=report.unindexed,
        missing_files=report.missing_files,
    )

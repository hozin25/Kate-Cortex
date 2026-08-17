from fastapi import APIRouter

from .. import __version__

router = APIRouter(tags=["system"])

APP_NAME = "kate-cortex"


@router.get("/health")
def health():
    return {"app": APP_NAME, "version": __version__}

from fastapi import APIRouter

from .. import __version__
from ..config import is_multiuser

router = APIRouter(tags=["system"])

APP_NAME = "kate-cortex"


@router.get("/health")
def health():
    # mode 供前端判断是否需要登录流程（单用户/Vercel 试用 → 免登录直通）
    return {
        "app": APP_NAME,
        "version": __version__,
        "mode": "multiuser" if is_multiuser() else "single",
    }

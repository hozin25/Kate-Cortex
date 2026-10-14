"""每日简报端点（BRIEFING_PLAN.md §2）：失败 400 由前端静默降级"""

from fastapi import APIRouter, HTTPException, Request

from ..briefing import BriefingError, get_briefing
from ..models import BriefingOut
from ..multiuser import get_services
from ..providers.base import ProviderError

router = APIRouter(tags=["briefing"])


@router.get("/briefing", response_model=BriefingOut)
def briefing(request: Request, refresh: bool = False):
    services = get_services(request)
    settings = services.settings_service.get_all()
    if not settings.get("memory_enabled", True):
        from ..briefing import static_briefing

        return {**static_briefing(), "cached": False}
    try:
        provider = services.provider_factory(settings["default_provider"])
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return get_briefing(
            services.storage, services.settings_service, provider, refresh=refresh
        )
    except BriefingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

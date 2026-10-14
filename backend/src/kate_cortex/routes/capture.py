"""全局速记端点（CAPTURE_PLAN.md / BUTLER_PLAN P3）：桌面一键闪记的落库口。

正文即记忆：手动建条 + 单条 LLM 加工（keywords/importance/合集）一气呵成。
加工是 best-effort——provider 缺 key 或输出异常时条目照常入库，响应里如实
标注 enriched=false，绝不因加工失败丢内容。
"""

from fastapi import APIRouter, HTTPException, Request

from ..enrich import EnrichError, enrich_one
from ..models import CaptureIn, CaptureOut
from ..multiuser import get_services
from ..providers.base import ProviderError

router = APIRouter(tags=["capture"])

TITLE_MAX_CHARS = 40


@router.post("/capture", response_model=CaptureOut)
def capture(payload: CaptureIn, request: Request):
    services = get_services(request)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="速记内容不能为空")
    title = next((line.strip() for line in text.splitlines() if line.strip()), "")[
        :TITLE_MAX_CHARS
    ]
    entry = services.storage.create_entry(
        title=title or "速记", source="manual", content=text
    )

    settings = services.settings_service.get_all()
    try:
        provider = services.provider_factory(settings["default_provider"])
    except ProviderError as exc:
        return CaptureOut(
            entry_id=entry.id,
            slug=entry.slug,
            title=entry.title,
            enriched=False,
            hint=str(exc),
        )
    try:
        # get_entry 重读：确保加工的是已落盘的完整条目
        fresh = services.storage.get_entry(entry.id)
        if fresh is None:
            return CaptureOut(
                entry_id=entry.id, slug=entry.slug, title=entry.title, enriched=False
            )
        item, reason = enrich_one(services.storage, provider, fresh)
    except EnrichError as exc:
        return CaptureOut(
            entry_id=entry.id,
            slug=entry.slug,
            title=entry.title,
            enriched=False,
            hint=str(exc),
        )
    if item is None:
        return CaptureOut(
            entry_id=entry.id,
            slug=entry.slug,
            title=entry.title,
            enriched=False,
            hint=reason,
        )
    return CaptureOut(
        entry_id=item.entry_id,
        slug=entry.slug,
        title=item.title,
        enriched=True,
        keywords=item.keywords,
        importance=item.importance,
        collection=item.collection,
    )

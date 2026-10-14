"""每日简报（BRIEFING_PLAN.md / BUTLER_PLAN P2）：管家的主动开口。

从「记忆+个人信息」生成当日简报（到期日程/跟进事项/主动建议），同日缓存，
无记忆或记忆关闭时走静态问候不调 LLM。只能引用给定条目——宁缺勿编。
"""

import json
import logging
from datetime import datetime

from .chat.memory import MEMORY_COLLECTION
from .providers.base import Done, TextDelta
from .storage import PROFILE_COLLECTION

logger = logging.getLogger(__name__)

CACHE_KEY = "briefing_cache"
MEMORIES_CAP = 30
PROFILE_CAP = 6
ITEMS_CAP = 6

_KINDS = ("due", "followup", "tip")

_STATIC_GREETING = "主人在。今天有什么吩咐？"

_WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


class BriefingError(Exception):
    """简报生成失败（LLM 调用/输出不可用），路由转 400"""


def get_briefing(storage, settings_service, provider, *, refresh: bool = False) -> dict:
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    cache = settings_service.get_all().get(CACHE_KEY) or {}
    if not refresh and cache.get("date") == today and cache.get("payload"):
        return {**cache["payload"], "cached": True}
    payload = _build(storage, provider, today)
    settings_service.update({CACHE_KEY: {"date": today, "payload": payload}})
    return {**payload, "cached": False}


def static_briefing() -> dict:
    return {
        "date": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "greeting": _STATIC_GREETING,
        "items": [],
    }


def _build(storage, provider, today: str) -> dict:
    context = _memory_context(storage)
    if not context:
        return {**static_briefing(), "date": today}
    weekday = _WEEKDAYS[datetime.now().astimezone().weekday()]
    prompt = _PROMPT.format(today=today, weekday=weekday, context=context)
    data = _parse(_call_llm(provider, prompt))
    known = set(context["ids"])
    items = []
    for item in (data.get("items") or [])[:ITEMS_CAP]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = item.get("kind")
        entry_id = item.get("entry_id")
        items.append(
            {
                "kind": kind if kind in _KINDS else "followup",
                "text": text,
                "entry_id": entry_id if entry_id in known else None,
            }
        )
    return {
        "date": today,
        "greeting": str(data.get("greeting") or "").strip() or _STATIC_GREETING,
        "items": items,
    }


def _memory_context(storage) -> dict | None:
    memories, ids = [], []
    for name, cap in ((PROFILE_COLLECTION, PROFILE_CAP), (MEMORY_COLLECTION, MEMORIES_CAP)):
        count = 0
        for entry in _collection_entries(storage, name):
            if count >= cap:
                break
            memories.append(f"- [{entry.id}] {entry.title}：{entry.content[:120]}")
            ids.append(entry.id)
            count += 1
    if not memories:
        return None
    return {"lines": "\n".join(memories), "ids": ids}


def _collection_entries(storage, collection: str):
    summaries, _ = storage.list_entries(collection=collection, limit=50)
    out = []
    for summary in summaries:
        try:
            entry = storage.get_entry(summary.id)
        except Exception:
            continue
        if entry is not None:
            out.append(entry)
    return out


def _call_llm(provider, prompt: str) -> str:
    parts: list[str] = []
    try:
        for event in provider.chat_stream([{"role": "user", "content": prompt}], tools=None):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, Done):
                break
    except Exception as exc:
        raise BriefingError(f"LLM 调用失败：{exc}") from exc
    return "".join(parts)


def _parse(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise BriefingError("LLM 输出中没有 JSON 对象")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BriefingError(f"LLM 输出无法解析：{exc}") from exc


_PROMPT = """你是主人的私人管家 Kate。今天是 {today}（{weekday}）。请根据主人的
记忆条目生成一份简短的今日简报：值得今天知道的事。

条目格式：[条目id] 标题：内容

只输出一个 JSON 对象，不要解释、不要 markdown 代码块：
{{"greeting": "一句话向主人问早/问候", "items": [{{"kind": "due|followup|tip", "text": "一句话", "entry_id": "条目id"}}]}}

要求：
- due：今天或近日到期/已过期的日程（复诊、缴费、聚会、截止）；没有就不输出 due；
- followup：正在进行、值得跟进或提醒注意的事（如「感冒刚好，注意保暖」）；
- tip：至多 1 条，基于记忆的主动建议，没有可省略；
- text 每条不超过 40 字，语气像管家一样干练体贴，不堆砌、不寒暄；
- entry_id 必须原样来自下方列表；严禁编造列表里没有的事；
- 总条数不超过 6 条；一条合适的都没有就输出空 items。

## 主人的记忆条目
{context}"""

"""导入加工流水线（IMPORT_ENRICH_PLAN.md / BUTLER_PLAN P0）

给 source=import 且缺 keywords/importance 的条目补元数据：逐条调 LLM 生成
缺失字段，经 storage.update_entry 双写（md/DB/FTS/向量四路同步）。拉取式
分批（enrich_batch 每次加工一小批即返回），前端循环调用直到 remaining=0
——无后台线程、幂等可续跑、失败重跑无副作用。重复只标记不合并（与
save_memory 同阈值），合并决策留给 P1 巩固引擎。
"""

import json
import logging
from dataclasses import dataclass, field

from .chat.memory import MEMORY_COLLECTION
from .providers.base import Done, TextDelta
from .storage import PROFILE_COLLECTION

logger = logging.getLogger(__name__)

# 与 skills/memory.py 的 DUPLICATE_SIMILARITY 同阈值
DUPLICATE_SIMILARITY = 0.80
CONTENT_TRUNCATE = 1200  # 提示词里的正文截断：关键词提取够用
DEDUP_QUERY_TRUNCATE = 400
MAX_KEYWORDS = 8

# 系统合集不参与自动归档建议：「记忆」是自动记忆的生活事实（长文混入会污染
# 常驻注入），「个人信息」是档案核心认知——两者只能由 save_memory/用户手动管理
NO_SUGGEST_COLLECTIONS = frozenset({MEMORY_COLLECTION, PROFILE_COLLECTION})

# 幂等选取：已有哪个就补哪个，绝不覆盖已有值（手动/chat 来源不碰——
# 用户手写的空字段是「没填」不是「要补」）
_PENDING_WHERE = (
    "source = 'import' AND (keywords IS NULL OR keywords = '' OR importance IS NULL)"
)


class EnrichError(Exception):
    """中止整批的错误（provider 构建失败/流式调用抛错），路由转 400"""


@dataclass
class EnrichedItem:
    entry_id: str
    title: str
    keywords: list[str]
    importance: int | None
    collection: str | None
    duplicates: list[dict] = field(default_factory=list)


@dataclass
class EnrichBatchResult:
    processed: int = 0
    remaining: int = 0
    enriched: list[EnrichedItem] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # 「slug：原因」，可重试

    def as_dict(self) -> dict:
        return {
            "processed": self.processed,
            "remaining": self.remaining,
            "done": self.remaining == 0,
            "enriched": [
                {
                    "entry_id": item.entry_id,
                    "title": item.title,
                    "keywords": item.keywords,
                    "importance": item.importance,
                    "collection": item.collection,
                    "duplicates": item.duplicates,
                }
                for item in self.enriched
            ],
            "skipped": self.skipped,
        }


def pending_count(storage) -> int:
    row = storage.conn.execute(
        f"SELECT COUNT(*) FROM entries WHERE {_PENDING_WHERE}"
    ).fetchone()
    return row[0]


def enrich_batch(storage, provider, limit: int = 8) -> EnrichBatchResult:
    """加工最多 limit 条待处理条目。provider 失败中止整批（EnrichError）；
    单条 LLM 输出不可用只跳过该条，下次调用重试。"""
    result = EnrichBatchResult()
    ids = [
        row["id"]
        for row in storage.conn.execute(
            f"SELECT id FROM entries WHERE {_PENDING_WHERE}"
            " ORDER BY created_at, id LIMIT ?",
            (limit,),
        ).fetchall()
    ]
    for entry_id in ids:
        try:
            entry = storage.get_entry(entry_id)
        except Exception as exc:
            result.skipped.append(f"{entry_id}：条目文件缺失（{exc}）")
            continue
        item, reason = enrich_one(storage, provider, entry)
        if item is None:
            result.skipped.append(f"{entry.slug}：{reason}")
            continue
        result.enriched.append(item)
        result.processed += 1

    result.remaining = pending_count(storage)
    return result


def enrich_one(storage, provider, entry) -> tuple[EnrichedItem | None, str | None]:
    """加工单条：补齐缺失的 keywords/importance/合集并标记疑似重复。

    返回 (结果, 跳过原因)——provider 失败向上抛 EnrichError（批量场景中止
    整批、capture 场景降级为未加工）；输出不可用返回 (None, 原因) 可重试，
    已写入的部分保留。"""
    need_keywords = not entry.keywords
    need_importance = entry.importance is None
    need_collection = not entry.collections
    prompt = _build_prompt(
        entry,
        need_keywords,
        need_importance,
        need_collection,
        [
            name
            for name, _count in storage.list_collections()
            if name not in NO_SUGGEST_COLLECTIONS
        ],
    )
    try:
        output = _call_llm(provider, prompt)
    except EnrichError:
        raise
    except Exception as exc:
        raise EnrichError(f"LLM 调用失败：{exc}") from exc

    keywords: list[str] | None = None
    importance: int | None = None
    collection: str | None = None
    pending_skip: list[str] = []
    try:
        data = _parse_llm_json(output)
    except (ValueError, json.JSONDecodeError) as exc:
        return None, f"LLM 输出无法解析（{exc}）"
    if need_keywords:
        try:
            keywords = _clean_keywords(data.get("keywords"))
        except ValueError:
            pending_skip.append("keywords 无法解析")
    if need_importance:
        try:
            importance = _clean_importance(data.get("importance"))
        except (TypeError, ValueError):
            pending_skip.append("importance 无法解析")
    if need_collection:
        collection = _clean_collection(data.get("collection"))

    update_kwargs: dict = {}
    if keywords is not None:
        update_kwargs["keywords"] = keywords
    if importance is not None:
        update_kwargs["importance"] = importance
    if collection and need_collection:
        # 只有无合集条目才采纳建议；已有 tags 的条目合集不动（tags 已是
        # 用户的组织意图，避免 LLM 噪声合集覆盖）
        update_kwargs["collections"] = [collection]
    if update_kwargs:
        try:
            storage.update_entry(entry.id, **update_kwargs)
        except Exception as exc:
            return None, f"写回失败（{exc}）"

    # 任一请求字段仍缺失（如 importance 解析失败）→ 记 skipped 待重试；
    # 已写回的部分保留（下批只补剩下的）
    if pending_skip:
        return None, "、".join(pending_skip)

    return (
        EnrichedItem(
            entry_id=entry.id,
            title=entry.title,
            keywords=keywords if keywords is not None else entry.keywords,
            importance=importance if importance is not None else entry.importance,
            collection=collection,
            duplicates=_find_duplicates(storage, entry),
        ),
        None,
    )


def _build_prompt(
    entry,
    need_keywords: bool,
    need_importance: bool,
    need_collection: bool,
    collection_names: list[str],
) -> str:
    format_fields: list[str] = []
    requirements: list[str] = []
    if need_keywords:
        format_fields.append('"keywords": ["…"]')
        requirements.append(
            "- keywords：3-8 个场景触发词——将来聊到/搜到什么话题时应该想起这条内容，"
            "做同义词与场景联想，不限于文中原词；用条目主要语言"
        )
    if need_importance:
        format_fields.append('"importance": 3')
        requirements.append(
            "- importance：1-5 整数。随手收藏 1-2，日常参考资料 3，"
            "对生活有实际影响的（健康/日程/重要偏好/花费）4-5"
        )
    if need_collection:
        format_fields.append('"collection": "…"')
        requirements.append(
            "- collection：从现有合集列表中选一个最贴题的；"
            "确实都不合适才起新名（≤6 字）；拿不准给空字符串；"
            "「记忆」「个人信息」是系统合集，严禁选择"
        )
    return (
        "你在给个人知识库的一条导入条目生成检索元数据。只输出一个 JSON 对象，"
        "不要解释、不要 markdown 代码块。\n\n"
        f"条目标题：{entry.title}\n"
        f"条目正文：\n{entry.content[:CONTENT_TRUNCATE]}\n\n"
        "现有合集列表："
        + (", ".join(collection_names) if collection_names else "（空）")
        + "\n\n输出格式：\n{"
        + ", ".join(format_fields)
        + "}\n字段要求：\n"
        + "\n".join(requirements)
    )


def _call_llm(provider, prompt: str) -> str:
    parts: list[str] = []
    for event in provider.chat_stream([{"role": "user", "content": prompt}], tools=None):
        if isinstance(event, TextDelta):
            parts.append(event.text)
        elif isinstance(event, Done):
            break
    return "".join(parts)


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("输出中没有 JSON 对象")
    return json.loads(text[start : end + 1])


def _clean_keywords(raw) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("keywords 不是列表")
    items = [str(item).strip() for item in raw if str(item).strip()]
    if not items:
        raise ValueError("keywords 为空")
    return list(dict.fromkeys(items))[:MAX_KEYWORDS]


def _clean_importance(raw) -> int:
    value = int(raw)
    return max(1, min(5, value))


def _clean_collection(raw) -> str | None:
    if raw is None:
        return None
    name = str(raw).strip()
    return name or None


def _find_duplicates(storage, entry) -> list[dict]:
    """cos ≥0.80 的既有条目（排除自身）。只标记不合并；向量不可用静默跳过"""
    if storage.vectors is None:
        return []
    text = f"{entry.title}\n\n{entry.content[:DEDUP_QUERY_TRUNCATE]}"
    try:
        hits = storage.vectors.query(text, limit=3)
    except Exception:
        return []
    duplicates: list[dict] = []
    for hit in hits:
        if hit.entry_id == entry.id:
            continue
        other = storage.get_entry(hit.entry_id)
        if other is None:
            continue
        similarity = 1.0 - hit.distance
        if similarity >= DUPLICATE_SIMILARITY:
            duplicates.append(
                {
                    "entry_id": hit.entry_id,
                    "title": other.title,
                    "similarity": round(similarity, 3),
                }
            )
        if len(duplicates) >= 2:
            break
    return duplicates

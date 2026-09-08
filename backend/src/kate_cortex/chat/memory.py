"""记忆召回：常驻注入（近期/重要）+ 关键词打分检索（DESIGN.md §记忆机制）

与 RAG（FTS 全文库字面检索）区分：记忆是「记忆」合集里的原子生活事实，
跨话题关联（问「出去玩」想起「感冒」）无法靠字面命中，靠的是保存时 LLM
生成的场景关键词——save_memory 与 recall_memory 两端都由模型产出同一
话题空间里的关键词，关键词重合即语义关联。
"""

from dataclasses import dataclass
from datetime import datetime

import logging

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "记忆"
LIST_LIMIT = 500  # 个人规模上限，超出按 created_at 截断（list_entries 默认排序）
RESIDENT_LIMIT = 5
RECALL_LIMIT = 3
SNIPPET_MAX_CHARS = 200

# 打分权重：关键词重合是主信号，重要性与新近度是加权项
KEYWORD_WEIGHT = 3.0
IMPORTANCE_WEIGHT = 0.5
WEEK_BONUS = 2.0
MONTH_BONUS = 1.0
RRF_K = 60  # 关键词/向量双通道排名融合常数（同 chat/rag.py）


@dataclass
class MemorySnippet:
    entry_id: str
    title: str
    content: str
    keywords: list[str]
    importance: int
    created_at: str


def list_memories(storage) -> list[MemorySnippet]:
    summaries, _ = storage.list_entries(
        collection=MEMORY_COLLECTION, limit=LIST_LIMIT
    )
    memories = []
    for summary in summaries:
        try:
            entry = storage.get_entry(summary.id)
        except Exception:
            entry = None  # md 文件缺失/损坏的条目跳过，不拖垮召回
        if entry is None:
            continue
        memories.append(
            MemorySnippet(
                entry_id=entry.id,
                title=entry.title,
                content=entry.content.strip(),
                keywords=entry.keywords,
                importance=entry.importance or 3,
                created_at=entry.created_at,
            )
        )
    return memories


def resident_memories(storage, limit: int = RESIDENT_LIMIT) -> list[MemorySnippet]:
    """常驻注入：按 (importance, created_at) 降序取前 N 条。确定性命中
    「昨天感冒→今天提醒保暖」这类近期事项，不依赖模型自觉调用检索"""
    memories = sorted(
        list_memories(storage),
        key=lambda m: (m.importance, m.created_at),
        reverse=True,
    )
    return memories[:limit]


def recall(
    storage, query_keywords: list[str], limit: int = RECALL_LIMIT
) -> list[MemorySnippet]:
    """打分检索：只有与检索词产生关联的记忆才返回（零重合不返回），
    排序兼顾关键词重合数、重要性与新近度。

    向量可用时增加语义通道（IMP-8）：检索词拼接文本嵌入后按「记忆」合集
    过滤，与关键词排名 RRF 融合——零词面重合的跨话题召回（问「出去玩」
    想起「感冒」）不再只赌 keywords。"""
    terms = [t.strip() for t in query_keywords if t and t.strip()]
    if not terms:
        return []
    now = datetime.now().astimezone()
    scored = [
        (score, m)
        for m in list_memories(storage)
        if (score := _score(m, terms, now)) > 0
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    vector_ranked = _vector_channel(storage, terms)
    if not vector_ranked:
        return [m for _, m in scored[:limit]]

    # RRF 融合（同 chat/rag.py 思路）：关键词与向量两路排名倒数求和
    scores: dict[str, float] = {}
    for rank, (_, m) in enumerate(scored):
        scores[m.entry_id] = scores.get(m.entry_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, m in enumerate(vector_ranked):
        scores[m.entry_id] = scores.get(m.entry_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    by_id = {m.entry_id: m for m in list_memories(storage)}
    fused = sorted(scores, key=scores.get, reverse=True)
    return [by_id[entry_id] for entry_id in fused[:limit] if entry_id in by_id]


def _vector_channel(storage, terms: list[str], limit: int = 8) -> list[MemorySnippet]:
    """向量语义通道：嵌入检索词 → 过滤出「记忆」合集条目。失败静默返回空"""
    if storage.vectors is None:
        return []
    try:
        hits = storage.vectors.query(" ".join(terms), limit=limit)
    except Exception as exc:
        logger.warning("记忆向量检索失败，退化为纯关键词打分: %s", exc)
        return []
    memories = []
    for hit in hits:
        entry = storage.get_entry(hit.entry_id)
        if entry is None or MEMORY_COLLECTION not in entry.collections:
            continue
        memories.append(
            MemorySnippet(
                entry_id=entry.id,
                title=entry.title,
                content=entry.content.strip(),
                keywords=entry.keywords,
                importance=entry.importance or 3,
                created_at=entry.created_at,
            )
        )
    return memories


def _score(memory: MemorySnippet, terms: list[str], now: datetime) -> float:
    """纯函数便于单测：关键词重合(×3) + importance(×0.5) + 新近度加成"""
    overlap = sum(1 for term in terms if _matches(term, memory))
    if overlap == 0:
        return 0.0
    score = overlap * KEYWORD_WEIGHT + memory.importance * IMPORTANCE_WEIGHT
    score += _recency_bonus(memory.created_at, now)
    return score


def _matches(term: str, memory: MemorySnippet) -> bool:
    """检索词与记忆的关联判定：命中 keywords（含包含关系，如「感冒」对
    「感冒药」）、标题或正文均算"""
    haystacks = [memory.keywords, [memory.title], [memory.content]]
    return any(
        term in text or text in term
        for fields in haystacks
        for text in fields
        if text
    )


def _recency_bonus(created_at: str, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=now.tzinfo)
    days = (now - created).days
    if days < 7:
        return WEEK_BONUS
    if days < 30:
        return MONTH_BONUS
    return 0.0

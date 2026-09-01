"""RAG 检索：FTS + 向量双通道 RRF 融合 → 截断注入（DESIGN.md §7、VECTOR_SEARCH_PLAN.md §5）

FTS 负责字面精确命中（代码/报错/API 名），向量负责同义改写召回
（问「身份」命中「学生」）。两通道排名用 RRF 融合：分数量纲不可比，
排名倒数融合免归一化。向量不可用时自动退化为纯 FTS（v4 行为）。
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TOP_K = 3
CANDIDATES = TOP_K * 2  # 每通道候选数，融合后取 top
RRF_K = 60  # Reciprocal Rank Fusion 常数
SNIPPET_MAX_CHARS = 500

PROFILE_COLLECTION = "个人信息"
PROFILE_LIMIT = 3


@dataclass
class KnowledgeSnippet:
    entry_id: str
    title: str
    slug: str
    content: str


def retrieve(storage, query: str, limit: int = TOP_K) -> list[KnowledgeSnippet]:
    fts_hits = storage.search.query(query, limit=CANDIDATES)
    vec_hits = []
    if storage.vectors is not None:
        try:
            vec_hits = storage.vectors.query(query, limit=CANDIDATES)
        except Exception as exc:
            # 嵌入网络故障不拖垮对话，本轮退化为纯 FTS
            logger.warning("向量检索失败，本轮退化为纯 FTS: %s", exc)

    scores: dict[str, float] = {}
    for rank, hit in enumerate(fts_hits):
        scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + _rrf(rank)
    for rank, hit in enumerate(vec_hits):
        scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + _rrf(rank)

    snippets = []
    ranked = sorted(scores, key=scores.get, reverse=True)
    for entry_id in ranked[:limit]:
        entry = storage.get_entry(entry_id)
        if entry is None:
            continue
        snippets.append(
            KnowledgeSnippet(
                entry_id=entry.id,
                title=entry.title,
                slug=entry.slug,
                content=entry.content[:SNIPPET_MAX_CHARS],
            )
        )
    return snippets


def _rrf(rank: int) -> float:
    """rank 从 0 起，1/(K+rank+1)：双通道同时命中的条目得分叠加"""
    return 1.0 / (RRF_K + rank + 1)


def user_profile(storage) -> list[KnowledgeSnippet]:
    """「个人信息」合集的条目，按创建时间取前 N 条。向量检索落地后画像问题
    已可语义召回，但常驻注入保留：画像类问题（我是谁/做什么的）高频且必须
    确定命中，不赌检索（DESIGN §7）"""
    summaries, _ = storage.list_entries(
        collection=PROFILE_COLLECTION, limit=PROFILE_LIMIT
    )
    snippets = []
    for summary in summaries:
        entry = storage.get_entry(summary.id)
        if entry is None:
            continue
        snippets.append(
            KnowledgeSnippet(
                entry_id=entry.id,
                title=entry.title,
                slug=entry.slug,
                content=entry.content[:SNIPPET_MAX_CHARS],
            )
        )
    return snippets

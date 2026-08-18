"""RAG 检索：jieba → FTS5 top3 → 截断注入（DESIGN.md §7）"""

from dataclasses import dataclass

TOP_K = 3
SNIPPET_MAX_CHARS = 500

PROFILE_TAG = "个人信息"
PROFILE_LIMIT = 3


@dataclass
class KnowledgeSnippet:
    entry_id: str
    title: str
    slug: str
    content: str


def retrieve(storage, query: str, limit: int = TOP_K) -> list[KnowledgeSnippet]:
    snippets = []
    for hit in storage.search.query(query, limit=limit):
        entry = storage.get_entry(hit.entry_id)
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


def user_profile(storage) -> list[KnowledgeSnippet]:
    """tag=个人信息 的条目，按更新时间取前 N 条——FTS 无法跨同义改写召回
    （问「身份」但条目里只有「学生」），用户画像靠常驻注入兜底（DESIGN §7）"""
    summaries, _ = storage.list_entries(tag=PROFILE_TAG, limit=PROFILE_LIMIT)
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

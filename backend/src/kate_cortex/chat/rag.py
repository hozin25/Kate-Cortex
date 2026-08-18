"""RAG 检索：jieba → FTS5 top3 → 截断注入（DESIGN.md §7）"""

from dataclasses import dataclass

TOP_K = 3
SNIPPET_MAX_CHARS = 500


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

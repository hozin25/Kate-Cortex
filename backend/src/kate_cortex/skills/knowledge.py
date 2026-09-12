"""知识收集 skill：save_knowledge / suggest_save / search_knowledge（DESIGN.md §6）"""

import jieba

PREVIEW_CHARS = 200
SEARCH_TOP_K = 3
SEARCH_SNIPPET_CHARS = 500

_PARAMS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "知识标题（简洁，可中文）"},
        "collections": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "建议收录进的合集名称，只能从系统提示「知识库合集」小节列出的"
                "已有合集中选择；没有合适的合集则不传此参数"
            ),
        },
        "content_markdown": {
            "type": "string",
            "description": "总结后的正文 markdown。聚焦当前讨论主题，保留结论/方法/代码，剔除寒暄与过程。",
        },
    },
    "required": ["title", "content_markdown"],
}

SEARCH_PARAMS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "检索词，关键词空格分隔，如「布洛芬 退烧 用法用量」",
        },
    },
    "required": ["query"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_knowledge",
            "description": (
                "总结当前对话中的有价值内容并存入知识库。"
                "当用户明确要求记下、保存、沉淀某段讨论时调用。"
            ),
            "parameters": _PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_save",
            "description": (
                "当对话中出现值得长期保留的结论、方法或决策（即使用户没要求），"
                "调用此工具生成保存建议，交由用户确认。不要在用户没确认前真正保存。"
            ),
            "parameters": _PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "检索用户的知识库（含药品说明书等专业语料）。回答具体药品、疾病、"
                "症状等专业问题前先检索并引用条目标题作依据；检索不到就如实说明，"
                "严禁编造。"
            ),
            "parameters": SEARCH_PARAMS,
        },
    },
]


def save_knowledge(storage, args: dict, conversation_id: str) -> dict:
    entry = storage.create_entry(
        title=args["title"],
        source="chat",
        content=args["content_markdown"],
        collections=args.get("collections") or [],
        conversation_id=conversation_id,
    )
    return {
        "entry_id": entry.id,
        "slug": entry.slug,
        "title": entry.title,
        "collections": entry.collections,
    }


def suggest_save(args: dict) -> dict:
    return {
        "title": args["title"],
        "collections": args.get("collections") or [],
        "preview": args["content_markdown"][:PREVIEW_CHARS],
    }


def search_knowledge(storage, args: dict) -> dict:
    """对话内检索知识库（FTS+向量 RRF 融合，与开场 RAG 同一套），结果只回传
    模型作引用依据，不单独推 SSE 事件（引用体现在回复文本里）。
    模型拼的查询常是「药品名 + 关注点」，AND 语义缺一个词就全空——空结果时
    退化按单词条检索合并（如「布洛芬」单独命中），保证工具召回率。"""
    query = (args.get("query") or "").strip()
    from ..chat.rag import retrieve

    snippets = retrieve(storage, query, limit=SEARCH_TOP_K)
    if not snippets:
        merged: dict[str, object] = {}
        for token in _significant_tokens(query):
            for snippet in retrieve(storage, token, limit=SEARCH_TOP_K):
                merged.setdefault(snippet.entry_id, snippet)
        snippets = list(merged.values())[:SEARCH_TOP_K]
    return {
        "query": query,
        "results": [
            {
                "title": s.title,
                "slug": s.slug,
                "excerpt": s.content[:SEARCH_SNIPPET_CHARS],
            }
            for s in snippets
        ],
    }


def _significant_tokens(query: str) -> list[str]:
    from ..search import STOPWORDS

    tokens = []
    for token in jieba.cut(query):
        if token in STOPWORDS or not any(ch.isalnum() for ch in token):
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:6]

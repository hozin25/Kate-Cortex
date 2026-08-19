"""知识收集 skill：save_knowledge / suggest_save（DESIGN.md §6）"""

PREVIEW_CHARS = 200

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

"""知识收集 skill：save_knowledge / suggest_save（DESIGN.md §6）"""

PREVIEW_CHARS = 200

_PARAMS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "知识标题（简洁，可中文）"},
        "type": {
            "type": "string",
            "enum": ["note", "clip", "decision", "howto"],
            "description": "知识类型",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "标签，3~5 个，小写",
        },
        "content_markdown": {
            "type": "string",
            "description": "总结后的正文 markdown。聚焦当前讨论主题，保留结论/方法/代码，剔除寒暄与过程。",
        },
    },
    "required": ["title", "type", "tags", "content_markdown"],
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
        type=args["type"],
        tags=args.get("tags") or [],
        source="chat",
        content=args["content_markdown"],
        conversation_id=conversation_id,
    )
    return {
        "entry_id": entry.id,
        "slug": entry.slug,
        "title": entry.title,
        "type": entry.type,
        "tags": entry.tags,
    }


def suggest_save(args: dict) -> dict:
    return {
        "title": args["title"],
        "type": args["type"],
        "tags": args.get("tags") or [],
        "preview": args["content_markdown"][:PREVIEW_CHARS],
    }

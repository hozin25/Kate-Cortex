"""记忆 skill：save_memory / recall_memory（DESIGN.md §记忆机制）

save_memory 是自动路径（append-only）：模型判断对话中出现耐久个人事实
即调用，无需用户要求；旧记忆过时时通过 replaces_entry_id 显式更新而非
擅自改写。keywords 是召回的桥梁——两端（保存与检索）都由模型生成同一
话题空间的场景词。
"""

from ..chat.memory import MEMORY_COLLECTION, recall as recall_memories

_SAVE_PARAMS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "记忆标题，简短（如「感冒了」）"},
        "content": {
            "type": "string",
            "description": (
                "一句话原子事实，只记一个事实，保留关键细节（时间、程度、"
                "注意事项），如「8月30日感冒，在吃感冒灵，医生叮嘱注意保暖」"
            ),
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-8 个场景触发词：将来聊到什么话题时应该想起这条记忆"
                "（记感冒可写：感冒/健康/保暖/出行/天气），是日后召回的关键"
            ),
        },
        "importance": {
            "type": "integer",
            "description": "重要性 1-5，默认 3；影响日常生活的健康问题、近期重要日程应给 4-5",
        },
        "replaces_entry_id": {
            "type": "string",
            "description": (
                "可选。要更新的旧记忆 entry_id（来自「近期记忆」或 recall_memory "
                "结果），用于旧事实已变化时覆盖更新（如感冒已痊愈），而不是新建重复记忆"
            ),
        },
    },
    "required": ["title", "content", "keywords"],
}

_RECALL_PARAMS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "用户当前需求的一句话概述（如「周末想去户外玩」）",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-6 个检索关键词：从用户当前话题提炼，并联想可能相关的场景"
                "（问「出去玩」可查：出行/健康/天气/装备）"
            ),
        },
    },
    "required": ["keywords"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "自动记住关于用户本人的耐久事实（健康状况、行程计划、稳定偏好、"
                "重要生活事件、进行中的事）。无需用户要求，判断出现即调用；"
                "用户明确说「记住」时也用本工具。与 save_knowledge 的区别："
                "那是知识沉淀，这是用户的生活记忆。"
            ),
            "parameters": _SAVE_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "检索与用户当前话题相关的记忆。回答涉及用户个人生活的问题"
                "（健康、出行、计划、偏好、近况）前先调用，再结合结果回答。"
            ),
            "parameters": _RECALL_PARAMS,
        },
    },
]


def save_memory(storage, args: dict, conversation_id: str) -> dict:
    keywords = [str(k) for k in args.get("keywords") or []]
    importance = args.get("importance") or 3
    replaces = args.get("replaces_entry_id")
    if replaces:
        entry = storage.update_entry(
            replaces,
            title=args["title"],
            content=args["content"],
            collections=[MEMORY_COLLECTION],
            keywords=keywords,
            importance=importance,
        )
    else:
        entry = storage.create_entry(
            title=args["title"],
            source="chat",
            content=args["content"],
            collections=[MEMORY_COLLECTION],
            conversation_id=conversation_id,
            keywords=keywords,
            importance=importance,
        )
    return {
        "entry_id": entry.id,
        "slug": entry.slug,
        "title": entry.title,
        "keywords": entry.keywords,
        "replaced": bool(replaces),
    }


def recall_memory(storage, args: dict) -> dict:
    hits = recall_memories(storage, args.get("keywords") or [])
    return {
        "query": args.get("query", ""),
        "memories": [
            {
                "entry_id": m.entry_id,
                "title": m.title,
                "content": m.content,
                "keywords": m.keywords,
                "created_at": m.created_at,
            }
            for m in hits
        ],
    }

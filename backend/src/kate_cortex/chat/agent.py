"""agent loop：流式生成 → tool_call 执行 → 结果回传 → 二次生成（DESIGN.md §6.2）"""

import json
from typing import Iterator

from ..mcp_client import call_mcp_tool
from ..providers.base import TextDelta, ToolCallAccumulator, ToolCallDelta
from ..skills.export import TOOLS as EXPORT_TOOLS
from ..skills.export import export_markdown
from ..skills.knowledge import TOOLS as KNOWLEDGE_TOOLS
from ..skills.knowledge import save_knowledge, suggest_save
from ..skills.memory import TOOLS as MEMORY_TOOLS
from ..skills.memory import recall_memory, save_memory
from .prompts import build_system_prompt

# 一次对话内「生成→工具→再生成」的最大轮数；旅游规划等场景需要
# 反复搜索 POI + 路线规划，8 轮才够排出多日行程
MAX_TOOL_ROUNDS = 8


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def run_agent_chat(
    *,
    provider,
    storage,
    chat_service,
    session_id: str,
    history: list[dict],
    rag_snippets: list,
    profile_snippets: list | None = None,
    collection_names: list[str] | None = None,
    memory_snippets: list | None = None,
    conversation_summary: str | None = None,
    memory_enabled: bool = False,
    mcp_tools: list[dict] | None = None,
    mcp_url: str | None = None,
    export_dir: str | None = None,
) -> Iterator[str]:
    system_prompt = build_system_prompt(
        rag_snippets=rag_snippets,
        profile_snippets=profile_snippets,
        collections=collection_names,
        memory_snippets=memory_snippets,
        conversation_summary=conversation_summary,
        mcp_enabled=bool(mcp_tools),
    )
    messages = [{"role": "system", "content": system_prompt}, *history]
    tools = [
        *KNOWLEDGE_TOOLS,
        *EXPORT_TOOLS,
        *(MEMORY_TOOLS if memory_enabled else []),
        *(mcp_tools or []),
    ]
    knowledge_refs = [s.entry_id for s in rag_snippets]
    executed_tools: list[dict] = []
    all_text: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        parts: list[str] = []
        accumulator = ToolCallAccumulator()
        try:
            for event in provider.chat_stream(messages, tools=tools):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
                    yield sse("delta", {"text": event.text})
                elif isinstance(event, ToolCallDelta):
                    accumulator.add(event)
        except Exception as exc:
            yield sse("error", {"message": f"上游错误: {exc}"})
            return

        all_text.extend(parts)
        tool_calls = accumulator.build()
        if not tool_calls:
            break

        messages.append(
            {"role": "assistant", "content": "".join(parts), "tool_calls": tool_calls}
        )
        for call in tool_calls:
            result = _execute_tool(
                call, storage, session_id, executed_tools, mcp_url, export_dir
            )
            if isinstance(result, dict):
                event = _sse_event(call["function"]["name"], result)
                if event:
                    yield sse(event, result)
                result = _tool_summary(call, result)
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result}
            )

    message = chat_service.append_message(
        session_id,
        "assistant",
        "".join(all_text),
        tool_calls=executed_tools or None,
        knowledge_refs=knowledge_refs or None,
    )
    yield sse("done", {"message_id": message.id})


def _execute_tool(
    call: dict,
    storage,
    session_id: str,
    executed_tools: list[dict],
    mcp_url: str | None = None,
    export_dir: str | None = None,
) -> dict | str:
    name = call["function"]["name"]
    executed_tools.append(call)
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError as exc:
        return f"工具参数 JSON 解析失败: {exc}"

    try:
        if name == "save_knowledge":
            return save_knowledge(storage, args, conversation_id=session_id)
        if name == "suggest_save":
            return suggest_save(args)
        if name == "export_markdown":
            return export_markdown(args, export_dir=export_dir)
        if name == "save_memory":
            return save_memory(storage, args, conversation_id=session_id)
        if name == "recall_memory":
            return recall_memory(storage, args)
        if mcp_url:
            return call_mcp_tool(mcp_url, name, args)
        return f"未知工具: {name}"
    except Exception as exc:
        return f"工具执行失败: {exc}"


def _sse_event(name: str, result: dict) -> str | None:
    """工具结果对应的 SSE 事件；返回 None 表示无需推给前端
    （如 recall 无命中，避免空噪音）"""
    if name == "save_memory":
        return "memory_saved"
    if name == "recall_memory":
        return "memory_refs" if result.get("memories") else None
    if name == "export_markdown":
        return "file_saved"
    if "entry_id" in result:
        return "tool_result"
    return "suggest"


def _tool_summary(call: dict, result: dict) -> str:
    name = call["function"]["name"]
    if name == "save_memory":
        action = "已更新记忆" if result.get("replaced") else "已记住"
        return f"{action}《{result['title']}》(id={result['entry_id']})"
    if name == "recall_memory":
        memories = result.get("memories") or []
        if not memories:
            return "没有找到相关记忆"
        return "找到相关记忆: " + "；".join(
            f"《{m['title']}》(id={m['entry_id']}) {m['content']}" for m in memories
        )
    if name == "export_markdown":
        return f"已导出《{result['title']}》到 {result['file_path']}"
    if "entry_id" in result:
        return f"已保存知识条目《{result['title']}》(id={result['entry_id']})"
    return "已展示保存建议卡片，等待用户确认，未写入知识库"

"""agent loop：流式生成 → tool_call 执行 → 结果回传 → 二次生成（DESIGN.md §6.2）"""

import json
from typing import Iterator

from ..providers.base import TextDelta, ToolCallAccumulator, ToolCallDelta
from ..skills.knowledge import TOOLS, save_knowledge, suggest_save
from .prompts import build_system_prompt

MAX_TOOL_ROUNDS = 3


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
) -> Iterator[str]:
    system_prompt = build_system_prompt(
        rag_snippets=rag_snippets, profile_snippets=profile_snippets
    )
    messages = [{"role": "system", "content": system_prompt}, *history]
    knowledge_refs = [s.entry_id for s in rag_snippets]
    executed_tools: list[dict] = []
    all_text: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        parts: list[str] = []
        accumulator = ToolCallAccumulator()
        try:
            for event in provider.chat_stream(messages, tools=TOOLS):
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
            result = _execute_tool(call, storage, session_id, executed_tools)
            if isinstance(result, dict):
                event = "tool_result" if "entry_id" in result else "suggest"
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
    call: dict, storage, session_id: str, executed_tools: list[dict]
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
        return f"未知工具: {name}"
    except Exception as exc:
        return f"工具执行失败: {exc}"


def _tool_summary(call: dict, result: dict) -> str:
    if "entry_id" in result:
        return f"已保存知识条目《{result['title']}》(id={result['entry_id']})"
    return "已展示保存建议卡片，等待用户确认，未写入知识库"

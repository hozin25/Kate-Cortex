"""anthropic SDK 兼容 Provider：GLM 编程套餐专用（Anthropic Messages 协议）

智谱把编程套餐权益绑定在 Anthropic 兼容端点上（/api/anthropic），不走
v4 经典 API 的按量余额——同一个 key 在 v4 端点报 1113。协议差异集中在
两处：消息结构（system 独立参数、tool_use/tool_result 内容块、角色必须
交替）与工具 schema（input_schema），在此归一化到项目的 OpenAI 风格
StreamEvent 管线，agent loop 无感知。
"""

import json
import re
from typing import Iterator

import anthropic

from .base import BaseProvider, Done, StreamEvent, TextDelta, ToolCallDelta

_DATA_URL_RE = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.DOTALL)

# Anthropic stop_reason → OpenAI finish_reason
_STOP_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


def to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI 消息（system/user/assistant+tool_calls/tool）→ (system, messages)。

    - tool 角色 → user 角色的 tool_result 内容块
    - 相邻同角色消息合并为一条（多个 tool 结果、工具结果后紧跟用户追问）
    - 空 assistant 消息丢弃（无 text 且无 tool_calls 时不产生空块）
    - user content 为多模态分块列表时逐块转换（text / image_url data URL）
    """
    system_parts: list[str] = []
    converted: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(content)
        elif role == "user":
            if isinstance(content, list):
                converted.append(
                    {"role": "user", "content": _anthropic_user_blocks(content)}
                )
            else:
                converted.append({"role": "user", "content": [{"type": "text", "text": content}]})
        elif role == "assistant":
            blocks: list[dict] = []
            if content:
                blocks.append({"type": "text", "text": content})
            for call in msg.get("tool_calls") or []:
                function = call.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "input": args,
                    }
                )
            if blocks:
                converted.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id") or "",
                            "content": content,
                        }
                    ],
                }
            )

    merged: list[dict] = []
    for msg in converted:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] = [*merged[-1]["content"], *msg["content"]]
        else:
            merged.append(msg)
    return "\n\n".join(system_parts), merged


def _anthropic_user_blocks(parts: list[dict]) -> list[dict]:
    """OpenAI 多模态分块 → Anthropic 内容块。image_url 仅支持 data URL
    （附件均由本地读回，无外链场景）；无法解析的块跳过不中断"""
    blocks: list[dict] = []
    for part in parts:
        ptype = part.get("type")
        if ptype == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif ptype == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            block = _data_url_to_image_block(url)
            if block is not None:
                blocks.append(block)
    return blocks or [{"type": "text", "text": ""}]


def _data_url_to_image_block(url: str) -> dict | None:
    match = _DATA_URL_RE.match(url.strip())
    if match is None:
        return None
    media_type = match.group(1).lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    # SDK 只要求字符串，无需在此真正解码
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": match.group(2),
        },
    }


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """OpenAI function 工具 → Anthropic 工具（parameters → input_schema）"""
    converted = []
    for tool in tools:
        function = tool.get("function") or {}
        converted.append(
            {
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "input_schema": function.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return converted


class AnthropicCompatProvider(BaseProvider):
    base_url: str = ""
    max_tokens: int = 8192

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model)
        self._client_factory = lambda: anthropic.Anthropic(
            base_url=self.base_url, api_key=self.api_key
        )

    def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> Iterator[StreamEvent]:
        system, converted = to_anthropic_messages(messages)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted,
            "stream": True,
            # glm-5.3 等推理模型默认输出 thinking 块：聊天场景直接关闭，
            # 避免 UI 长时间无正文且烧输出 token
            "thinking": {"type": "disabled"},
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
            kwargs["tool_choice"] = {"type": "auto"}

        finish_reason: str | None = None
        client = self._client_factory()
        try:
            stream = client.messages.create(**kwargs)
            for event in stream:
                etype = getattr(event, "type", "")
                if etype == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", "") == "tool_use":
                        yield ToolCallDelta(
                            index=event.index, id=block.id, name=block.name
                        )
                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", "")
                    if dtype == "text_delta":
                        yield TextDelta(delta.text)
                    elif dtype == "input_json_delta":
                        yield ToolCallDelta(
                            index=event.index, arguments=delta.partial_json
                        )
                    # thinking_delta / signature_delta：关闭思考后不出现，防御性跳过
                elif etype == "message_delta":
                    raw = event.delta.stop_reason
                    finish_reason = _STOP_REASONS.get(raw, raw)
        finally:
            client.close()
        yield Done(finish_reason)

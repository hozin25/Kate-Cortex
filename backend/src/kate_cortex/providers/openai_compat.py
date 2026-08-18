"""openai SDK 兼容 Provider 公共实现：DeepSeek / GLM 共用"""

from typing import Iterator

from openai import OpenAI

from .base import BaseProvider, Done, StreamEvent, TextDelta, ToolCallDelta


class OpenAICompatProvider(BaseProvider):
    base_url: str = ""

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model)
        self._client_factory = lambda: OpenAI(
            base_url=self.base_url, api_key=self.api_key
        )

    def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> Iterator[StreamEvent]:
        client = self._client_factory()
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        finish_reason: str | None = None
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = choice.delta
            if delta is None:
                continue
            if delta.content:
                yield TextDelta(delta.content)
            for tool_call in delta.tool_calls or []:
                function = tool_call.function
                yield ToolCallDelta(
                    index=tool_call.index,
                    id=tool_call.id,
                    name=function.name if function and function.name else None,
                    arguments=(
                        function.arguments
                        if function and function.arguments
                        else ""
                    ),
                )
            if choice.finish_reason:
                finish_reason = choice.finish_reason
        yield Done(finish_reason)

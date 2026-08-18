"""Provider 抽象与流事件归一化（DESIGN.md §5）"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallDelta:
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


@dataclass
class Done:
    finish_reason: str | None = None


StreamEvent = TextDelta | ToolCallDelta | Done


class ProviderError(Exception):
    """provider 构造或调用前的本地校验错误（如缺 API key）"""


class BaseProvider(ABC):
    name: str = "base"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> Iterator[StreamEvent]:
        """流式对话。yield 归一化的 StreamEvent，最后必有 Done。"""


@dataclass
class _PartialToolCall:
    id: str | None = None
    name: str | None = None
    arguments: list[str] = field(default_factory=list)


class ToolCallAccumulator:
    """把 ToolCallDelta 增量流聚合成 OpenAI tool_calls 完整结构。

    DeepSeek / GLM 的流式 tool_calls 只在首个片段带 id 与 name，
    后续片段仅携带 index + arguments 增量，在此集中拼接。
    """

    def __init__(self):
        self._partials: dict[int, _PartialToolCall] = {}

    def add(self, delta: ToolCallDelta) -> None:
        partial = self._partials.setdefault(delta.index, _PartialToolCall())
        if delta.id:
            partial.id = delta.id
        if delta.name:
            partial.name = delta.name
        if delta.arguments:
            partial.arguments.append(delta.arguments)

    def build(self) -> list[dict]:
        calls = []
        for index in sorted(self._partials):
            partial = self._partials[index]
            calls.append(
                {
                    "id": partial.id or f"tool_{index}",
                    "type": "function",
                    "function": {
                        "name": partial.name or "",
                        "arguments": "".join(partial.arguments),
                    },
                }
            )
        return calls

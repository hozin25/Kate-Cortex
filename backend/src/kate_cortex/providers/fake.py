"""脚本化回放的假 Provider：测试基石"""

from typing import Iterator

from .base import BaseProvider, StreamEvent


class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, script: list[StreamEvent | Exception]):
        super().__init__(api_key="fake-key", model="fake-model")
        self.script = script
        self.calls: list[dict] = []

    def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> Iterator[StreamEvent]:
        self.calls.append({"messages": messages, "tools": tools})
        for item in self.script:
            if isinstance(item, Exception):
                raise item
            yield item

"""脚本化回放的假 Provider：测试基石。

- script：单轮脚本，每次调用循环回放
- rounds：多轮脚本（agent loop 二次生成场景），按调用次序逐轮消费，耗尽后循环最后一轮
"""

from typing import Iterator

from .base import BaseProvider, StreamEvent


class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, script: list | None = None, rounds: list[list] | None = None):
        super().__init__(api_key="fake-key", model="fake-model")
        if rounds is not None:
            self.rounds = rounds
        elif script is not None:
            self.rounds = [script]
        else:
            self.rounds = [[]]
        self._round_index = 0
        self.calls: list[dict] = []

    def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> Iterator[StreamEvent]:
        self.calls.append({"messages": messages, "tools": tools})
        index = min(self._round_index, len(self.rounds) - 1)
        self._round_index += 1
        for item in self.rounds[index]:
            if isinstance(item, Exception):
                raise item
            yield item

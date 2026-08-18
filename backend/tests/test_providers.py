from types import SimpleNamespace
from typing import Any

from kate_cortex.providers.base import (
    Done,
    TextDelta,
    ToolCallAccumulator,
    ToolCallDelta,
)
from kate_cortex.providers.deepseek import DeepSeekProvider
from kate_cortex.providers.glm import GLMProvider
from kate_cortex.providers.openai_compat import OpenAICompatProvider


def chunk(content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def tool_call(index, id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, function=function)


def make_provider(chunks: list[Any]) -> OpenAICompatProvider:
    provider = DeepSeekProvider(api_key="sk-test", model="deepseek-chat")
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: iter(chunks))
        )
    )
    provider._client_factory = lambda: fake_client
    return provider


class TestToolCallAccumulator:
    def test_assembles_split_arguments(self):
        acc = ToolCallAccumulator()
        acc.add(ToolCallDelta(index=0, id="call_1", name="save_knowledge", arguments='{"tit'))
        acc.add(ToolCallDelta(index=0, arguments='le": "数据库"}'))

        built = acc.build()

        assert built == [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "save_knowledge", "arguments": '{"title": "数据库"}'},
            }
        ]

    def test_multiple_tool_calls_interleaved_by_index(self):
        acc = ToolCallAccumulator()
        acc.add(ToolCallDelta(index=0, id="call_a", name="save_knowledge", arguments="{"))
        acc.add(ToolCallDelta(index=1, id="call_b", name="suggest_save", arguments="{"))
        acc.add(ToolCallDelta(index=0, arguments="}"))
        acc.add(ToolCallDelta(index=1, arguments="}"))

        built = acc.build()

        assert [call["id"] for call in built] == ["call_a", "call_b"]
        assert built[0]["function"]["arguments"] == "{}"

    def test_generates_fallback_id_when_missing(self):
        acc = ToolCallAccumulator()
        acc.add(ToolCallDelta(index=0, name="save_knowledge", arguments="{}"))

        built = acc.build()

        assert built[0]["id"] == "tool_0"

    def test_empty_returns_empty_list(self):
        assert ToolCallAccumulator().build() == []


class TestProviderNormalization:
    def test_text_deltas_pass_through(self):
        provider = make_provider(
            [
                chunk(content="你好"),
                chunk(content="，世界"),
                chunk(finish_reason="stop"),
            ]
        )

        events = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert events == [TextDelta("你好"), TextDelta("，世界"), Done("stop")]

    def test_tool_call_deltas_normalized(self):
        provider = make_provider(
            [
                chunk(
                    tool_calls=[
                        tool_call(0, id="call_1", name="save_knowledge", arguments='{"a')
                    ]
                ),
                chunk(tool_calls=[tool_call(0, arguments=': 1}')]),
                chunk(finish_reason="tool_calls"),
            ]
        )

        events = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert events[:2] == [
            ToolCallDelta(index=0, id="call_1", name="save_knowledge", arguments='{"a'),
            ToolCallDelta(index=0, arguments=": 1}"),
        ]
        assert events[-1] == Done("tool_calls")

    def test_chunk_without_choices_is_skipped(self):
        provider = make_provider(
            [SimpleNamespace(choices=[]), chunk(content="ok"), chunk(finish_reason="stop")]
        )

        events = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert events == [TextDelta("ok"), Done("stop")]

    def test_tools_kwarg_passed_through(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return iter([chunk(content="ok"), chunk(finish_reason="stop")])

        provider = DeepSeekProvider(api_key="sk-test", model="deepseek-chat")
        provider._client_factory = lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        tools = [{"type": "function", "function": {"name": "save_knowledge"}}]

        list(provider.chat_stream([{"role": "user", "content": "hi"}], tools=tools))

        assert captured["tools"] == tools
        assert captured["stream"] is True
        assert captured["tool_choice"] == "auto"


class TestProviderClasses:
    def test_deepseek_base_url(self):
        provider = DeepSeekProvider(api_key="sk", model="deepseek-chat")
        assert provider.name == "deepseek"
        assert provider.base_url == "https://api.deepseek.com/v1"

    def test_glm_base_url(self):
        provider = GLMProvider(api_key="sk", model="glm-4-flash")
        assert provider.name == "glm"
        assert provider.base_url == "https://open.bigmodel.cn/api/paas/v4"

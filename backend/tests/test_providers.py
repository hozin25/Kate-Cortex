from types import SimpleNamespace
from typing import Any

from kate_cortex.providers import DEFAULT_MODELS, REGISTRY
from kate_cortex.providers.anthropic_compat import (
    to_anthropic_messages,
    to_anthropic_tools,
)
from kate_cortex.providers.base import (
    Done,
    TextDelta,
    ToolCallAccumulator,
    ToolCallDelta,
)
from kate_cortex.providers.deepseek import DeepSeekProvider
from kate_cortex.providers.glm import GLMProvider
from kate_cortex.providers.glm_coding import GLMCodingProvider
from kate_cortex.providers.modelscope import ModelScopeProvider
from kate_cortex.providers.openai_compat import OpenAICompatProvider
from kate_cortex.providers.siliconflow import SiliconFlowProvider


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
        provider = GLMProvider(api_key="sk", model="glm-4.7-flash")
        assert provider.name == "glm"
        assert provider.base_url == "https://open.bigmodel.cn/api/paas/v4"

    def test_siliconflow_base_url(self):
        provider = SiliconFlowProvider(api_key="sk", model="Qwen/Qwen3-8B")
        assert provider.name == "siliconflow"
        assert provider.base_url == "https://api.siliconflow.cn/v1"

    def test_modelscope_base_url(self):
        provider = ModelScopeProvider(
            api_key="ms-xxx", model="Qwen/Qwen3-235B-A22B-Instruct-2507"
        )
        assert provider.name == "modelscope"
        assert provider.base_url == "https://api-inference.modelscope.cn/v1"

    def test_registry_defaults_are_free_tier(self):
        assert REGISTRY.keys() >= {"deepseek", "glm", "glm-coding", "siliconflow", "modelscope"}
        assert DEFAULT_MODELS["glm"] == "glm-4.7-flash"
        assert DEFAULT_MODELS["siliconflow"] == "Qwen/Qwen3-8B"
        assert DEFAULT_MODELS["modelscope"] == "Qwen/Qwen3-235B-A22B-Instruct-2507"


def make_siliconflow_provider(model: str, captured: dict) -> SiliconFlowProvider:
    provider = SiliconFlowProvider(api_key="sk-test", model=model)

    def fake_create(**kwargs):
        captured.update(kwargs)
        return iter([chunk(content="ok"), chunk(finish_reason="stop")])

    provider._client_factory = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    return provider


class TestSiliconFlowThinkingSwitch:
    """混合推理 Qwen3 默认开思考、思考文本会污染流式正文，须显式关闭；
    Instruct/Thinking 专版与非 Qwen 模型不认 enable_thinking，不能传"""

    def test_hybrid_qwen3_disables_thinking(self):
        captured: dict = {}
        provider = make_siliconflow_provider("Qwen/Qwen3-8B", captured)

        list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert captured["extra_body"] == {"enable_thinking": False}

    def test_hybrid_qwen3_moe_disables_thinking(self):
        captured: dict = {}
        provider = make_siliconflow_provider("Qwen/Qwen3-30B-A3B", captured)

        list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert captured["extra_body"] == {"enable_thinking": False}

    def test_instruct_variant_omits_flag(self):
        captured: dict = {}
        provider = make_siliconflow_provider(
            "Qwen/Qwen3-235B-A22B-Instruct-2507", captured
        )

        list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert "extra_body" not in captured

    def test_non_qwen_model_omits_flag(self):
        captured: dict = {}
        provider = make_siliconflow_provider("deepseek-ai/DeepSeek-V3", captured)

        list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert "extra_body" not in captured


def block_start(index, block_type, **fields):
    return SimpleNamespace(
        type="content_block_start",
        index=index,
        content_block=SimpleNamespace(type=block_type, **fields),
    )


def text_delta(index, text):
    return SimpleNamespace(
        type="content_block_delta",
        index=index,
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def json_delta(index, fragment):
    return SimpleNamespace(
        type="content_block_delta",
        index=index,
        delta=SimpleNamespace(type="input_json_delta", partial_json=fragment),
    )


def thinking_delta(index, text):
    return SimpleNamespace(
        type="content_block_delta",
        index=index,
        delta=SimpleNamespace(type="thinking_delta", thinking=text),
    )


def message_delta(stop_reason):
    return SimpleNamespace(
        type="message_delta", delta=SimpleNamespace(stop_reason=stop_reason)
    )


def make_anthropic_provider(events: list[Any], captured: dict | None = None):
    provider = GLMCodingProvider(api_key="sk-test", model="glm-5.3")

    def fake_create(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return iter(events)

    provider._client_factory = lambda: SimpleNamespace(
        messages=SimpleNamespace(create=fake_create), close=lambda: None
    )
    return provider


class TestAnthropicMessageConversion:
    def test_system_extracted_and_tool_calls_mapped(self):
        system, messages = to_anthropic_messages(
            [
                {"role": "system", "content": "你是 Kate"},
                {"role": "user", "content": "记一下"},
                {
                    "role": "assistant",
                    "content": "好的",
                    "tool_calls": [
                        {
                            "id": "toolu_1",
                            "type": "function",
                            "function": {
                                "name": "save_memory",
                                "arguments": '{"title": "感冒"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "toolu_1",
                    "content": "已记住",
                },
            ]
        )

        assert system == "你是 Kate"
        assert [m["role"] for m in messages] == ["user", "assistant", "user"]
        assert messages[1]["content"] == [
            {"type": "text", "text": "好的"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "save_memory",
                "input": {"title": "感冒"},
            },
        ]
        assert messages[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "已记住"}
        ]

    def test_consecutive_user_roles_merged(self):
        system, messages = to_anthropic_messages(
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
            ]
        )

        assert [m["role"] for m in messages] == ["user"]
        assert len(messages[0]["content"]) == 2

    def test_empty_assistant_dropped_and_bad_json_becomes_empty_input(self):
        system, messages = to_anthropic_messages(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": ""},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "t1",
                            "function": {"name": "recall_memory", "arguments": "{bad"},
                        }
                    ],
                },
            ]
        )

        assert [m["role"] for m in messages] == ["user", "assistant"]
        tool_use = messages[1]["content"][0]
        assert tool_use["input"] == {}

    def test_tool_schema_conversion(self):
        converted = to_anthropic_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "save_memory",
                        "description": "记住",
                        "parameters": {
                            "type": "object",
                            "properties": {"title": {"type": "string"}},
                        },
                    },
                }
            ]
        )

        assert converted == [
            {
                "name": "save_memory",
                "description": "记住",
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                },
            }
        ]


class TestAnthropicStreamNormalization:
    def test_text_and_thinking_deltas(self):
        provider = make_anthropic_provider(
            [
                thinking_delta(0, "让我想想"),
                text_delta(1, "你好"),
                message_delta("end_turn"),
            ]
        )

        events = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert events == [TextDelta("你好"), Done("stop")]

    def test_tool_use_stream_accumulates_via_existing_accumulator(self):
        provider = make_anthropic_provider(
            [
                text_delta(0, "我来记一下。"),
                block_start(1, "tool_use", id="toolu_9", name="save_memory"),
                json_delta(1, '{"title": "感'),
                json_delta(1, '冒"}'),
                message_delta("tool_use"),
            ]
        )

        events = list(
            provider.chat_stream([{"role": "user", "content": "我感冒了"}])
        )

        accumulator = ToolCallAccumulator()
        for event in events:
            if isinstance(event, ToolCallDelta):
                accumulator.add(event)

        assert accumulator.build() == [
            {
                "id": "toolu_9",
                "type": "function",
                "function": {"name": "save_memory", "arguments": '{"title": "感冒"}'},
            }
        ]
        assert events[-1] == Done("tool_calls")

    def test_request_kwargs(self):
        captured: dict = {}
        provider = make_anthropic_provider([message_delta("end_turn")], captured)

        list(
            provider.chat_stream(
                [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "hi"},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "save_memory",
                            "description": "d",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        )

        assert captured["system"] == "sys"
        assert captured["max_tokens"] == provider.max_tokens
        assert captured["thinking"] == {"type": "disabled"}
        assert captured["tool_choice"] == {"type": "auto"}
        assert captured["tools"][0]["input_schema"] == {"type": "object", "properties": {}}

    def test_glm_coding_base_url(self):
        provider = GLMCodingProvider(api_key="sk", model="glm-5.3")
        assert provider.name == "glm-coding"
        assert provider.base_url == "https://open.bigmodel.cn/api/anthropic"

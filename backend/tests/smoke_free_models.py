"""真 API 冒烟：免费档模型走 OpenAI 兼容端点的文本流 + 工具调用流式归一化

覆盖三家免费方案：
- glm-4.7-flash（智谱，完全免费）：key 用 GLM_KEY
- Qwen/Qwen3-8B（硅基流动免费档，验证 enable_thinking=False 生效）：key 用 SILICONFLOW_KEY
- Qwen/Qwen3-235B-A22B-Instruct-2507（魔搭每日 2000 次免费）：key 用 MODELSCOPE_KEY

只测配置了 key 的 provider，跑法：
    uv run python tests/smoke_free_models.py
"""

import os
import sys

sys.path.insert(0, "src")

from kate_cortex.providers.base import Done, TextDelta, ToolCallAccumulator, ToolCallDelta
from kate_cortex.providers.glm import GLMProvider
from kate_cortex.providers.modelscope import ModelScopeProvider
from kate_cortex.providers.siliconflow import SiliconFlowProvider
from kate_cortex.skills.knowledge import TOOLS as KNOWLEDGE_TOOLS
from kate_cortex.skills.memory import TOOLS as MEMORY_TOOLS

CASES = [
    ("glm-4.7-flash", GLMProvider, "GLM_KEY", "glm-4.7-flash"),
    ("siliconflow", SiliconFlowProvider, "SILICONFLOW_KEY", "Qwen/Qwen3-8B"),
    (
        "modelscope",
        ModelScopeProvider,
        "MODELSCOPE_KEY",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
    ),
]

MESSAGES = [
    {
        "role": "system",
        "content": "你是 Kate，用户的个人助手。出现用户健康事实必须调用 save_memory。",
    },
    {"role": "user", "content": "我感冒了，有点流鼻涕，吃什么药？"},
]

for label, cls, env, model in CASES:
    key = os.environ.get(env)
    if not key:
        print(f"=== {label}：未设置 {env}，跳过 ===\n")
        continue
    provider = cls(api_key=key, model=model)

    print(f"=== {label} / {model} ===")
    print("--- 1) 纯文本流 ---")
    events = list(
        provider.chat_stream([{"role": "user", "content": "用一句话介绍你自己"}])
    )
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    done = [e for e in events if isinstance(e, Done)]
    joined = "".join(texts)
    print(f"think_leak={'<think>' in joined} text={joined[:120]!r} "
          f"done={[d.finish_reason for d in done]}")

    print("--- 2) 工具调用流（记忆场景） ---")
    acc = ToolCallAccumulator()
    text_parts = []
    done_reasons = []
    try:
        for ev in provider.chat_stream(MESSAGES, tools=[*KNOWLEDGE_TOOLS, *MEMORY_TOOLS]):
            if isinstance(ev, TextDelta):
                text_parts.append(ev.text)
            elif isinstance(ev, ToolCallDelta):
                acc.add(ev)
            elif isinstance(ev, Done):
                done_reasons.append(ev.finish_reason)
    except Exception as exc:
        print(f"上游错误: {exc}\n")
        continue

    joined = "".join(text_parts)
    print(f"done={done_reasons} think_leak={'<think>' in joined}")
    print(f"text={joined[:120]!r}")
    for call in acc.build():
        print(f"tool_call: {call['function']['name']} args={call['function']['arguments'][:200]}")
    print()

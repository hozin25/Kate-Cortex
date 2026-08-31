"""真 API 冒烟：glm-5.3 走 Anthropic 端点的文本流 + 工具调用流式归一化"""

import os
import sys

sys.path.insert(0, "src")

from kate_cortex.providers.base import Done, TextDelta, ToolCallAccumulator, ToolCallDelta
from kate_cortex.providers.glm_coding import GLMCodingProvider
from kate_cortex.skills.memory import TOOLS as MEMORY_TOOLS
from kate_cortex.skills.knowledge import TOOLS as KNOWLEDGE_TOOLS

KEY = os.environ["GLM_KEY"]
provider = GLMCodingProvider(api_key=KEY, model="glm-5.3")

print("=== 1) 纯文本流 ===")
events = list(provider.chat_stream([{"role": "user", "content": "用一句话介绍你自己"}]))
texts = [e.text for e in events if isinstance(e, TextDelta)]
done = [e for e in events if isinstance(e, Done)]
print(f"text={"".join(texts)!r} done={[d.finish_reason for d in done]}")

print("\n=== 2) 工具调用流（记忆场景） ===")
acc = ToolCallAccumulator()
text_parts = []
done_reasons = []
for ev in provider.chat_stream(
    [
        {"role": "system", "content": "你是 Kate，用户的个人助手。出现用户健康事实必须调用 save_memory。"},
        {"role": "user", "content": "我感冒了，有点流鼻涕，吃什么药？"},
    ],
    tools=[*KNOWLEDGE_TOOLS, *MEMORY_TOOLS],
):
    if isinstance(ev, TextDelta):
        text_parts.append(ev.text)
    elif isinstance(ev, ToolCallDelta):
        acc.add(ev)
    elif isinstance(ev, Done):
        done_reasons.append(ev.finish_reason)

print(f"done={done_reasons}")
print(f"text={"".join(text_parts)[:120]!r}")
for call in acc.build():
    print(f"tool_call: {call['function']['name']} args={call['function']['arguments'][:200]}")

"""硅基流动 Provider：免费档 Qwen3 / GLM 等开源模型（OpenAI 兼容）

与 embedding 的硅基流动共用一个账号，但 key 各自独立配置
（chat 走 provider_keys["siliconflow"]，embedding 走 embedding_api_key）。
"""

import re

from .openai_compat import OpenAICompatProvider

# 混合推理模型（Qwen3-8B / Qwen3-30B-A3B / Qwen3-32B …）支持 enable_thinking，
# 且默认开启思考模式——思考文本会混入流式 content，干扰 agent loop 的正文与
# tool_calls 拼接，故一律显式关闭。Instruct/Thinking 专版与非 Qwen 模型不认
# 该参数（传了会 400），按模型名排除。
_HYBRID_THINKING_RE = re.compile(r"Qwen3(?:\.\d)?-\d+B-A\d+B$|Qwen3-\d+B$")


class SiliconFlowProvider(OpenAICompatProvider):
    name = "siliconflow"
    base_url = "https://api.siliconflow.cn/v1"

    def _request_kwargs(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        kwargs = super()._request_kwargs(messages, tools)
        model_id = self.model.split("/")[-1]
        if _HYBRID_THINKING_RE.match(model_id):
            kwargs["extra_body"] = {"enable_thinking": False}
        return kwargs

"""魔搭 ModelScope Provider：每日 2000 次免费推理 API（OpenAI 兼容）

模型 ID 带组织前缀（如 Qwen/Qwen3-235B-A22B-Instruct-2507），
6 万+ 开源模型可白嫖，key 为魔搭个人中心的 SDK Token（ms-…）。
"""

from .openai_compat import OpenAICompatProvider


class ModelScopeProvider(OpenAICompatProvider):
    name = "modelscope"
    base_url = "https://api-inference.modelscope.cn/v1"

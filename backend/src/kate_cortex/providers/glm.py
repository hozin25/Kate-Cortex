from .openai_compat import OpenAICompatProvider


class GLMProvider(OpenAICompatProvider):
    name = "glm"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    # GLM-4.6+ 支持 "thinking": {"type": ...} 轮级开关（5.3/5.3-Flash 强制开）
    supports_thinking_param = True

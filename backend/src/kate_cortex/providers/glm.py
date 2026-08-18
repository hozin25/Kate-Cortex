from .openai_compat import OpenAICompatProvider


class GLMProvider(OpenAICompatProvider):
    name = "glm"
    base_url = "https://open.bigmodel.cn/api/paas/v4"

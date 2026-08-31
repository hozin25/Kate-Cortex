from .anthropic_compat import AnthropicCompatProvider


class GLMCodingProvider(AnthropicCompatProvider):
    """GLM 编程套餐：Anthropic 协议端点，glm-5.3 等模型走套餐额度"""

    name = "glm-coding"
    base_url = "https://open.bigmodel.cn/api/anthropic"

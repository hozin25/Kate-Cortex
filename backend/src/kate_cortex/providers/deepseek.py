from .openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com/v1"

"""Provider 注册表与工厂：按 settings 构建 provider 实例"""

from .base import BaseProvider, ProviderError
from .deepseek import DeepSeekProvider
from .glm import GLMProvider

REGISTRY: dict[str, type[BaseProvider]] = {
    "deepseek": DeepSeekProvider,
    "glm": GLMProvider,
}

DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "glm": "glm-4-flash",
}


class ProviderFactory:
    def __init__(self, settings_service):
        self._settings_service = settings_service

    def __call__(self, name: str, model: str | None = None) -> BaseProvider:
        if name not in REGISTRY:
            raise ProviderError(f"未知 provider: {name}")
        settings = self._settings_service.get_all()
        api_key = settings["provider_keys"].get(name)
        if not api_key:
            raise ProviderError(f"未配置 {name} 的 API key，请先到设置页填写")
        if not model:
            model = (
                settings["default_model"]
                if settings["default_provider"] == name
                else DEFAULT_MODELS[name]
            )
        return REGISTRY[name](api_key=api_key, model=model)


def create_provider(name: str, api_key: str, model: str) -> BaseProvider:
    if name not in REGISTRY:
        raise ProviderError(f"未知 provider: {name}")
    return REGISTRY[name](api_key=api_key, model=model)

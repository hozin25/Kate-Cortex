"""Provider 注册表与工厂：按 settings 构建 provider 实例"""

from .base import BaseProvider, ProviderError
from .deepseek import DeepSeekProvider
from .glm import GLMProvider
from .glm_coding import GLMCodingProvider
from .modelscope import ModelScopeProvider
from .siliconflow import SiliconFlowProvider

REGISTRY: dict[str, type[BaseProvider]] = {
    "deepseek": DeepSeekProvider,
    "glm": GLMProvider,
    "glm-coding": GLMCodingProvider,
    "siliconflow": SiliconFlowProvider,
    "modelscope": ModelScopeProvider,
}

DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "glm": "glm-4.7-flash",  # 智谱免费档（glm-4.5-flash 已于 2026-01 下线）
    "glm-coding": "glm-5.3",
    "siliconflow": "Qwen/Qwen3-8B",  # 硅基流动免费档
    "modelscope": "Qwen/Qwen3-235B-A22B-Instruct-2507",  # 魔搭每日 2000 次免费
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


def vision_supported(provider: str, model: str) -> bool:
    """该 provider/模型能否接收图片。glm-coding 的 glm-5.3 原生多模态；
    其余按模型命名判断——名称分段含独立 v/VL 段（glm-4v-plus、Qwen-VL…）
    视为视觉模型，deepseek-chat 与纯文本档（glm-4-flash / Qwen3-8B）不支持"""
    if provider == "glm-coding":
        return True
    if provider == "deepseek":
        return False
    return any("v" in segment for segment in model.lower().split("-"))

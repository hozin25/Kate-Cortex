"""Provider 注册表与工厂：按 settings 构建 provider 实例"""

import re

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

# 对话内模型切换的可选目录（label 为展示名，free 标注免费档）；
# 不在目录里的 model 仍可经设置页自定义使用
MODEL_CATALOG: dict[str, list[dict]] = {
    "glm": [
        {"model": "glm-4.7-flash", "label": "GLM-4.7-Flash", "free": True},
        {"model": "glm-4-flash-250414", "label": "GLM-4-Flash", "free": True},
        {"model": "glm-4.5", "label": "GLM-4.5 旗舰", "free": False},
    ],
    "glm-coding": [
        {"model": "glm-5.3", "label": "GLM-5.3", "free": False},
        {"model": "glm-5.1", "label": "GLM-5.1", "free": False},
    ],
    "siliconflow": [
        {"model": "Qwen/Qwen3-8B", "label": "Qwen3-8B", "free": True},
        {"model": "Qwen/Qwen3-30B-A3B", "label": "Qwen3-30B-A3B", "free": True},
        {
            "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
            "label": "Qwen3-Coder-30B",
            "free": True,
        },
    ],
    "modelscope": [
        {
            "model": "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "label": "Qwen3-235B",
            "free": True,
        },
        {
            "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
            "label": "Qwen3-30B",
            "free": True,
        },
        {"model": "deepseek-ai/DeepSeek-V3", "label": "DeepSeek-V3", "free": True},
    ],
    "deepseek": [
        {"model": "deepseek-chat", "label": "DeepSeek-Chat", "free": False},
        {"model": "deepseek-reasoner", "label": "DeepSeek-Reasoner", "free": False},
    ],
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


# 视觉模型的命名段：可选版本号 + v / vl 收尾（4v、4.5v、vl），精确匹配
# 避免 DeepSeek-V3 这类「含 v 但非视觉」的误判
_VISION_SEGMENT_RE = re.compile(r"(\d+(\.\d+)?)?v(l)?")


def vision_supported(provider: str, model: str) -> bool:
    """该 provider/模型能否接收图片。glm-coding 的 glm-5.x 原生多模态；
    deepseek 纯文本；其余按模型命名判断——glm-4v-plus、Qwen-…-VL-…、
    glm-4.5v 等含独立 v/vl 段视为视觉模型，v3 之类的版本号不算"""
    if provider == "glm-coding":
        return True
    if provider == "deepseek":
        return False
    model_id = model.split("/")[-1]
    return any(
        _VISION_SEGMENT_RE.fullmatch(segment)
        for segment in model_id.lower().split("-")
    )

from fastapi import APIRouter, HTTPException, Request

from ..models import ProviderTestIn, SettingsOut, SettingsUpdate
from ..providers import (
    DEFAULT_MODELS,
    MODEL_CATALOG,
    REGISTRY,
    create_provider,
    vision_supported,
)
from ..providers.base import Done, ProviderError, TextDelta

router = APIRouter(tags=["settings"])


@router.get("/models")
def list_models(request: Request):
    """对话内模型切换的目录：按注册表顺序给出各 provider 的模型与 key 配置
    状态；vision 由 vision_supported 现算（与发图拦截同一判定）"""
    keys = request.app.state.settings_service.get_all()["provider_keys"]
    return {
        "providers": [
            {
                "name": name,
                "has_key": bool(keys.get(name)),
                "models": [
                    {**m, "vision": vision_supported(name, m["model"])}
                    for m in MODEL_CATALOG.get(name, [])
                ],
            }
            for name in REGISTRY
        ]
    }


@router.get("/settings", response_model=SettingsOut)
def get_settings(request: Request):
    result = request.app.state.settings_service.get_all()
    # 诚实化：返回实际生效路径（config 决定），而非从不生效的存储值
    result["vault_path"] = str(request.app.state.storage.vault)
    return result


@router.put("/settings", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, request: Request):
    try:
        updated = request.app.state.settings_service.update(
            payload.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    updated["vault_path"] = str(request.app.state.storage.vault)
    return updated


@router.post("/providers/test")
def test_provider(payload: ProviderTestIn, request: Request):
    """连通性测试：结果统一 200 + {ok, message}（测试不通过不是传输层错误，
    且 message 会直接展示给用户）。带 key/model 时测的是设置页未保存的草稿。"""
    settings = request.app.state.settings_service.get_all()
    try:
        if payload.key:
            model = payload.model or (
                settings["default_model"]
                if settings["default_provider"] == payload.provider
                else None
            )
            provider = create_provider(
                payload.provider, payload.key, model or DEFAULT_MODELS[payload.provider]
            )
        else:
            provider = request.app.state.provider_factory(payload.provider)
    except ProviderError as exc:
        return {"ok": False, "message": str(exc)}

    parts: list[str] = []
    try:
        for event in provider.chat_stream([{"role": "user", "content": "ping"}]):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, Done):
                break
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "model": provider.model, "reply": "".join(parts)[:200]}

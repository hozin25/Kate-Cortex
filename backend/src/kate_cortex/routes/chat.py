"""会话与 SSE 流式对话端点（DESIGN.md §4.2）"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..attachments import (
    AttachmentError,
    image_refs,
    save_data_urls,
    strip_images,
    to_data_url,
)
from ..chat.agent import run_agent_chat, sse as sse_event
from ..chat.memory import resident_memories
from ..chat.rag import retrieve, user_profile
from ..chat.service import SessionNotFound
from ..chat.summarizer import KEEP_ROUNDS, ensure_summary
from ..mcp_registry import McpContext
from ..models import (
    ChatRegenerate,
    ChatRequest,
    ChatResend,
    MessageOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)
from ..multiuser import get_services
from ..providers import DEFAULT_MODELS, vision_supported
from ..providers.base import ProviderError

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_ROUNDS = KEEP_ROUNDS  # 最近 N 轮原文；更早的由 summarizer 压缩（IMP-7）


@router.post("/sessions", status_code=201, response_model=SessionOut)
def create_session(payload: SessionCreate, request: Request):
    settings = get_services(request).settings_service.get_all()
    if not settings["provider_keys"].get(payload.provider):
        raise HTTPException(
            status_code=400,
            detail=f"未配置 {payload.provider} 的 API key，请先到设置页填写",
        )
    model = payload.model or (
        settings["default_model"]
        if settings["default_provider"] == payload.provider
        else DEFAULT_MODELS[payload.provider]
    )
    session = get_services(request).chat_service.create_session(
        payload.provider, model, payload.title
    )
    return SessionOut(**vars(session))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(request: Request):
    sessions = get_services(request).chat_service.list_sessions()
    return [SessionOut(**vars(s)) for s in sessions]


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session(session_id: str, payload: SessionUpdate, request: Request):
    """重命名 / 切换模型。切 provider 时按与创建会话相同的规则解析默认模型"""
    chat_service = get_services(request).chat_service
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=422, detail="至少提供 title / provider / model 之一")

    if "provider" in data or "model" in data:
        provider = data.get("provider", session.provider)
        model = data.get("model")
        settings = get_services(request).settings_service.get_all()
        if not settings["provider_keys"].get(provider):
            raise HTTPException(
                status_code=400,
                detail=f"未配置 {provider} 的 API key，请先到设置页填写",
            )
        if model is None:
            model = (
                settings["default_model"]
                if settings["default_provider"] == provider
                else DEFAULT_MODELS[provider]
            )
        session = chat_service.set_session_model(session_id, provider, model)

    if "title" in data:
        session = chat_service.rename_session(session_id, data["title"])
    return SessionOut(**vars(session))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request):
    try:
        get_services(request).chat_service.delete_session(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: str, request: Request):
    if get_services(request).chat_service.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = get_services(request).chat_service.list_messages(session_id)
    return [MessageOut(**vars(m)) for m in messages]


@router.post("/sessions/{session_id}/chat")
def chat(session_id: str, payload: ChatRequest, request: Request):
    chat_service = get_services(request).chat_service
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not payload.content.strip() and not payload.images:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    settings = get_services(request).settings_service.get_all()
    rag_enabled = (
        payload.rag_enabled if payload.rag_enabled is not None else settings["rag_default"]
    )
    memory_enabled = settings.get("memory_enabled", True)
    export_dir = (settings.get("export_dir") or "").strip() or None

    # 多模态：图片落盘 vault/attachments/，content 以 markdown 引用携带（本地可追溯）
    content = payload.content
    if payload.images:
        if not vision_supported(session.provider, session.model):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"当前模型 {session.provider}/{session.model} 不支持图片，"
                    "请切换到带「视觉」标注的模型（如 GLM 编程套餐 glm-5.3）"
                ),
            )
        try:
            rels = save_data_urls(get_services(request).storage.vault, payload.images)
        except AttachmentError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        content = content + "\n\n" + "\n".join(f"![图片]({rel})" for rel in rels)

    vision = vision_supported(session.provider, session.model)
    chat_service.append_message(session_id, "user", content)
    chat_service.ensure_title(session_id, strip_images(content))
    history = _history_messages(
        chat_service, session_id, get_services(request).storage.vault, vision
    )

    return StreamingResponse(
        _stream_response(
            request,
            session,
            history,
            rag_content=content,
            rag_enabled=rag_enabled,
            memory_enabled=memory_enabled,
            export_dir=export_dir,
        ),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/regenerate")
def regenerate(session_id: str, payload: ChatRegenerate, request: Request):
    """重新生成：删除最后一条用户消息之后的回复，重新流式生成（不重复落用户消息）"""
    chat_service = get_services(request).chat_service
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    last_user = chat_service.last_message_of_role(session_id, "user")
    if last_user is None:
        raise HTTPException(status_code=404, detail="没有可重新生成的消息")

    settings = get_services(request).settings_service.get_all()
    chat_service.delete_messages_after(session_id, last_user.id)
    history = _history_messages(
        chat_service,
        session_id,
        get_services(request).storage.vault,
        vision_supported(session.provider, session.model),
    )
    return StreamingResponse(
        _stream_response(
            request,
            session,
            history,
            rag_content=last_user.content,
            rag_enabled=(
                payload.rag_enabled
                if payload.rag_enabled is not None
                else settings["rag_default"]
            ),
            memory_enabled=settings.get("memory_enabled", True),
            export_dir=(settings.get("export_dir") or "").strip() or None,
        ),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/messages/{message_id}/resend")
def resend(session_id: str, message_id: str, payload: ChatResend, request: Request):
    """编辑用户消息并重发：原地更新内容，删除其后所有消息，重新流式生成"""
    chat_service = get_services(request).chat_service
    message = chat_service.get_message(message_id)
    if message is None or message.conversation_id != session_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.role != "user":
        raise HTTPException(status_code=400, detail="仅支持编辑用户消息")
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    content = payload.content
    if payload.keep_images:
        refs = image_refs(message.content)
        if refs:
            content = content + "\n\n" + "\n".join(f"![图片]({rel})" for rel in refs)

    settings = get_services(request).settings_service.get_all()
    chat_service.update_message(message_id, content)
    chat_service.delete_messages_after(session_id, message_id)
    history = _history_messages(
        chat_service,
        session_id,
        get_services(request).storage.vault,
        vision_supported(session.provider, session.model),
    )
    return StreamingResponse(
        _stream_response(
            request,
            session,
            history,
            rag_content=content,
            rag_enabled=(
                payload.rag_enabled
                if payload.rag_enabled is not None
                else settings["rag_default"]
            ),
            memory_enabled=settings.get("memory_enabled", True),
            export_dir=(settings.get("export_dir") or "").strip() or None,
        ),
        media_type="text/event-stream",
    )


@router.delete("/sessions/{session_id}/messages/{message_id}", status_code=204)
def delete_message(session_id: str, message_id: str, request: Request):
    chat_service = get_services(request).chat_service
    message = chat_service.get_message(message_id)
    if message is None or message.conversation_id != session_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    chat_service.delete_message(message_id)


def _stream_response(
    request: Request,
    session,
    history: list[dict],
    *,
    rag_content: str,
    rag_enabled: bool,
    memory_enabled: bool,
    export_dir: str | None,
):
    """chat / regenerate / resend 共用的 SSE 生成器：RAG 检索 → citations →
    agent loop（结束后由 run_agent_chat 落库 assistant 消息）"""
    chat_service = get_services(request).chat_service
    session_id = session.id

    def generate():
        try:
            provider = get_services(request).provider_factory(
                session.provider, session.model
            )
        except ProviderError as exc:
            yield sse_event("error", {"message": str(exc)})
            return

        snippets = (
            retrieve(get_services(request).storage, strip_images(rag_content))
            if rag_enabled
            else []
        )
        # 长对话摘要（IMP-7）：溢出轮压缩为背景注入 system prompt；失败降级硬截断
        conversation_summary = ensure_summary(chat_service, provider, session_id)
        profile = user_profile(get_services(request).storage)
        memories = (
            resident_memories(get_services(request).storage) if memory_enabled else []
        )
        # 逐个服务拉工具表（带 mcp__<id>__ 前缀）；失败的服务降级并合并成一条通知
        mcp = McpContext.load(get_services(request).settings_service)
        if mcp.failures:
            yield sse_event(
                "mcp_notice",
                {
                    "message": "外部工具服务连接失败（"
                    + "；".join(mcp.failures)
                    + "），本次回答没有这些服务的实时数据"
                },
            )
        yield sse_event(
            "citations",
            {
                "entries": [
                    {"id": s.entry_id, "title": s.title, "slug": s.slug}
                    for s in snippets
                ]
            },
        )
        yield from run_agent_chat(
            provider=provider,
            storage=get_services(request).storage,
            chat_service=chat_service,
            session_id=session_id,
            history=history,
            rag_snippets=snippets,
            profile_snippets=profile,
            collection_names=[
                name for name, _ in get_services(request).storage.list_collections()
            ],
            memory_snippets=memories,
            conversation_summary=conversation_summary,
            memory_enabled=memory_enabled,
            mcp=mcp,
            export_dir=export_dir,
        )

    return generate()


def _history_messages(
    chat_service, session_id: str, vault=None, vision: bool = False
) -> list[dict]:
    """历史 → LLM 消息。含图片引用的 user 消息在视觉模型下展开为
    OpenAI 多模态分块（image_url data URL），否则降级为 [图片] 占位文本"""
    messages = [
        m
        for m in chat_service.list_messages(session_id)
        if m.role in ("user", "assistant")
    ]
    recent = messages[-(HISTORY_ROUNDS * 2) :]
    result: list[dict] = []
    for m in recent:
        refs = image_refs(m.content)
        if m.role == "user" and refs and vision and vault is not None:
            parts: list[dict] = [{"type": "text", "text": strip_images(m.content)}]
            for rel in refs:
                try:
                    parts.append(
                        {"type": "image_url", "image_url": {"url": to_data_url(vault, rel)}}
                    )
                except OSError:
                    continue  # 附件文件缺失时跳过，不中断对话
            result.append({"role": "user", "content": parts})
        else:
            result.append({"role": m.role, "content": strip_images(m.content)})
    return result

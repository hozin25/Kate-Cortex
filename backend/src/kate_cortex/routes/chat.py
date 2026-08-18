"""会话与 SSE 流式对话端点（DESIGN.md §4.2）"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..chat.agent import run_agent_chat, sse as sse_event
from ..chat.rag import retrieve
from ..chat.service import SessionNotFound
from ..models import ChatRequest, MessageOut, SessionCreate, SessionOut, SessionRename
from ..providers import DEFAULT_MODELS
from ..providers.base import ProviderError

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_ROUNDS = 20


@router.post("/sessions", status_code=201, response_model=SessionOut)
def create_session(payload: SessionCreate, request: Request):
    settings = request.app.state.settings_service.get_all()
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
    session = request.app.state.chat_service.create_session(
        payload.provider, model, payload.title
    )
    return SessionOut(**vars(session))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(request: Request):
    sessions = request.app.state.chat_service.list_sessions()
    return [SessionOut(**vars(s)) for s in sessions]


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def rename_session(session_id: str, payload: SessionRename, request: Request):
    try:
        session = request.app.state.chat_service.rename_session(
            session_id, payload.title
        )
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionOut(**vars(session))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request):
    try:
        request.app.state.chat_service.delete_session(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: str, request: Request):
    if request.app.state.chat_service.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = request.app.state.chat_service.list_messages(session_id)
    return [MessageOut(**vars(m)) for m in messages]


@router.post("/sessions/{session_id}/chat")
def chat(session_id: str, payload: ChatRequest, request: Request):
    chat_service = request.app.state.chat_service
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    settings = request.app.state.settings_service.get_all()
    rag_enabled = (
        payload.rag_enabled if payload.rag_enabled is not None else settings["rag_default"]
    )

    chat_service.append_message(session_id, "user", payload.content)
    chat_service.ensure_title(session_id, payload.content)
    history = _history_messages(chat_service, session_id)

    def generate():
        try:
            provider = request.app.state.provider_factory(
                session.provider, session.model
            )
        except ProviderError as exc:
            yield sse_event("error", {"message": str(exc)})
            return

        snippets = (
            retrieve(request.app.state.storage, payload.content) if rag_enabled else []
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
            storage=request.app.state.storage,
            chat_service=chat_service,
            session_id=session_id,
            history=history,
            rag_snippets=snippets,
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


def _history_messages(chat_service, session_id: str) -> list[dict]:
    messages = [
        m
        for m in chat_service.list_messages(session_id)
        if m.role in ("user", "assistant")
    ]
    recent = messages[-(HISTORY_ROUNDS * 2) :]
    return [{"role": m.role, "content": m.content} for m in recent]

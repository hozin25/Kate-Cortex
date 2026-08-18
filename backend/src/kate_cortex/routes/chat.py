"""会话与 SSE 流式对话端点（DESIGN.md §4.2）"""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..chat.service import SessionNotFound
from ..models import ChatRequest, MessageOut, SessionCreate, SessionOut, SessionRename
from ..providers import DEFAULT_MODELS
from ..providers.base import Done, ProviderError, TextDelta

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_ROUNDS = 20


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    chat_service.append_message(session_id, "user", payload.content)
    chat_service.ensure_title(session_id, payload.content)

    def generate():
        yield sse_event("citations", {"entries": []})
        try:
            provider = request.app.state.provider_factory(
                session.provider, session.model
            )
        except ProviderError as exc:
            yield sse_event("error", {"message": str(exc)})
            return

        history = _history_messages(chat_service, session_id)
        parts: list[str] = []
        try:
            for event in provider.chat_stream(history):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
                    yield sse_event("delta", {"text": event.text})
        except Exception as exc:
            yield sse_event("error", {"message": f"上游错误: {exc}"})
            return

        message = chat_service.append_message(
            session_id, "assistant", "".join(parts)
        )
        yield sse_event("done", {"message_id": message.id})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _history_messages(chat_service, session_id: str) -> list[dict]:
    messages = [
        m
        for m in chat_service.list_messages(session_id)
        if m.role in ("user", "assistant")
    ]
    recent = messages[-(HISTORY_ROUNDS * 2) :]
    return [{"role": m.role, "content": m.content} for m in recent]

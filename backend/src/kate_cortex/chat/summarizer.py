"""长对话增量摘要（IMP-7，DESIGN §13 风险表 v0.2 项）

超过阈值的旧轮次压缩成 ≤500 字「对话背景」注入 system prompt，
最近 20 轮保持原文。增量合并（旧摘要 + 新溢出轮一起交给 LLM），
会话内缓存（summarized_until 未推进就不重复调用）。任何失败都
降级为硬截断（现有行为），绝不阻塞对话。
"""

import logging

from ..providers.base import Done, TextDelta

logger = logging.getLogger(__name__)

# 与 routes/chat.py 的 HISTORY_ROUNDS 保持一致：最近 20 轮原文保留
KEEP_ROUNDS = 20
# user/assistant 轮数超过该值才触发摘要（成本控制：仅长会话付费）
SUMMARY_THRESHOLD_ROUNDS = 30
SUMMARY_MAX_CHARS = 500

_SUMMARY_INSTRUCTION = (
    "请把以下对话内容压缩成不超过 500 字的中文摘要，保留：讨论的主题与结论、"
    "关键决策、涉及的人名/项目名/数字、尚未解决的问题。剔除寒暄与过程细节。"
    "直接输出摘要正文，不要任何前后缀说明。"
)


def ensure_summary(chat_service, provider, session_id: str) -> str | None:
    """必要时生成/更新会话摘要，返回当前可用的摘要（无则 None）。

    幂等且吞错：provider 失败、消息为空等一切异常都返回旧摘要。"""
    try:
        return _ensure_summary(chat_service, provider, session_id)
    except Exception as exc:
        logger.warning("会话摘要生成失败，降级为硬截断: %s", exc)
        try:
            return chat_service.get_summary(session_id)[0]
        except Exception:
            return None


def _ensure_summary(chat_service, provider, session_id: str) -> str | None:
    summary, until = chat_service.get_summary(session_id)
    messages = [
        m for m in chat_service.list_messages(session_id) if m.role in ("user", "assistant")
    ]
    rounds = len(messages) // 2
    if rounds <= SUMMARY_THRESHOLD_ROUNDS:
        return summary

    # 溢出轮 = summarized_until 之后、且不在最近 KEEP_ROUNDS 轮窗口内的消息
    after = [m for m in messages if not until or m.created_at > until]
    overflow = after[: max(0, len(after) - KEEP_ROUNDS * 2)]
    if not overflow:
        return summary  # 缓存命中：已摘要覆盖到最新可覆盖位置

    transcript = "\n".join(f"{m.role}: {m.content[:800]}" for m in overflow)
    prompt = (
        (f"此前对话的摘要：\n{summary}\n\n" if summary else "")
        + _SUMMARY_INSTRUCTION
        + "\n\n对话内容：\n"
        + transcript
    )
    parts: list[str] = []
    for event in provider.chat_stream(
        [{"role": "user", "content": prompt}], tools=None
    ):
        if isinstance(event, TextDelta):
            parts.append(event.text)
        elif isinstance(event, Done):
            break
    new_summary = "".join(parts).strip()[: SUMMARY_MAX_CHARS * 2]
    if not new_summary:
        return summary
    chat_service.set_summary(session_id, new_summary, overflow[-1].created_at)
    return new_summary

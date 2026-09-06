"""聊天图片附件：data URL 落盘 + markdown 引用解析（多模态输入，DESIGN §4.2）

图片存 vault/attachments/YYYY/MM/，消息 content 以 markdown 图片引用携带
（本地优先、可追溯、SQLite 无需迁移）；发往 LLM 时再解析回多模态内容块。
"""

import base64
import binascii
import re
from datetime import datetime
from pathlib import Path

ATTACHMENT_DIR = "attachments"
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# glm-5.3 / glm-4v 系列支持的图片类型（OpenAI 与 Anthropic 协议一致）
ALLOWED_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# ![任意](attachments/相对路径)
IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\((attachments/[^)\s]+)\)")

_DATA_URL_RE = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.DOTALL)


class AttachmentError(Exception):
    """附件非法（类型/大小/格式）——路由层转 400"""


def save_data_urls(vault: Path, data_urls: list[str]) -> list[str]:
    """批量落盘，返回 vault 相对 posix 路径列表（顺序与输入一致）"""
    if len(data_urls) > MAX_IMAGES:
        raise AttachmentError(f"单条消息最多 {MAX_IMAGES} 张图片")
    now = datetime.now()
    rel_dir = f"{ATTACHMENT_DIR}/{now.strftime('%Y/%m')}"
    saved: list[str] = []
    for index, data_url in enumerate(data_urls, start=1):
        media_type, raw = _parse_data_url(data_url)
        ext = ALLOWED_MEDIA.get(media_type)
        if ext is None:
            raise AttachmentError(f"不支持的图片类型: {media_type}（支持 png/jpeg/webp/gif）")
        if len(raw) > MAX_IMAGE_BYTES:
            raise AttachmentError(f"图片超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB 上限")
        try:
            payload = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AttachmentError("图片 base64 解码失败") from exc
        rel_path = f"{rel_dir}/{now.strftime('%Y%m%d%H%M%S')}-{now.microsecond:06d}-{index}{ext}"
        target = vault / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        saved.append(rel_path)
    return saved


def image_refs(content: str) -> list[str]:
    """提取 content 里全部附件相对路径（按出现顺序）"""
    return IMAGE_REF_RE.findall(content)


def strip_images(content: str) -> str:
    """把图片引用替换为 [图片] 占位——LLM 文本部分与 FTS/RAG 检索用"""
    return IMAGE_REF_RE.sub("[图片]", content)


def to_data_url(vault: Path, rel_path: str) -> str:
    """附件文件读回 data URL（构建 LLM 多模态内容块用）"""
    ext = Path(rel_path).suffix.lower()
    media_type = next((m for m, e in ALLOWED_MEDIA.items() if e == ext), "image/png")
    payload = base64.b64encode((vault / rel_path).read_bytes()).decode()
    return f"data:{media_type};base64,{payload}"


def _parse_data_url(data_url: str) -> tuple[str, str]:
    if not data_url.startswith("data:"):
        raise AttachmentError("图片格式错误：仅支持 data URL（base64）")
    match = _DATA_URL_RE.match(data_url.strip())
    if match is None:
        raise AttachmentError("图片 data URL 解析失败")
    return match.group(1).lower(), match.group(2)

"""附件静态服务：GET /api/attachments/{相对路径}（渲染进程 <img> 直连）"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..attachments import ALLOWED_MEDIA

router = APIRouter(prefix="/attachments", tags=["attachments"])

_MEDIA_BY_EXT = {ext: media for media, ext in ALLOWED_MEDIA.items()}


@router.get("/{rel_path:path}")
def get_attachment(rel_path: str, request: Request):
    base = (request.app.state.storage.vault / "attachments").resolve()
    # markdown 引用自带 attachments/ 前缀，前端可直接拼 api/{引用}，此处容错剥离
    if rel_path.startswith("attachments/"):
        rel_path = rel_path[len("attachments/") :]
    target = (base / rel_path).resolve()
    # 防目录穿越：解析后的绝对路径必须仍在 attachments 目录内
    if base not in target.parents:
        raise HTTPException(status_code=404, detail="附件不存在")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="附件不存在")
    media_type = _MEDIA_BY_EXT.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type)

"""向量索引状态、重建与三维投影端点（VECTOR_SEARCH_PLAN.md §6 / VECTOR_GRAPH_PLAN.md §3）"""

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    EmbeddingRebuildOut,
    EmbeddingStatusOut,
    ProjectionOut,
    ProjectionPointOut,
)
from ..multiuser import get_services
from ..projection import ProjectionResult

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get("/status", response_model=EmbeddingStatusOut)
def embedding_status(request: Request):
    index = get_services(request).vector_index
    if index is None:
        # sqlite-vec 扩展不可用：功能整体缺席，前端据此禁用区块
        return EmbeddingStatusOut(available=False, indexed=0, total=_total(request))
    indexed, total = index.status()
    return EmbeddingStatusOut(available=index.available, indexed=indexed, total=total)


@router.post("/rebuild", response_model=EmbeddingRebuildOut)
def embedding_rebuild(request: Request):
    index = get_services(request).vector_index
    if index is None:
        raise HTTPException(status_code=503, detail="向量扩展不可用（sqlite-vec 未加载）")
    if not index.available:
        raise HTTPException(status_code=502, detail="未配置 GLM API key，无法生成向量")
    result = index.rebuild(get_services(request).storage)
    indexed, total = index.status()
    return EmbeddingRebuildOut(indexed=indexed, total=total, failed=result.failed)


@router.get("/projection", response_model=ProjectionOut)
def embedding_projection(request: Request):
    return _projection_response(request)


@router.post("/projection/refresh", response_model=ProjectionOut)
def embedding_projection_refresh(request: Request):
    return _projection_response(request, refresh=True)


def _projection_response(request: Request, refresh: bool = False) -> ProjectionOut:
    """vec 扩展缺失 → available=false（对齐 status 的 200+available 语义，
    前端据此渲染空态而非报错）"""
    if get_services(request).vector_index is None or get_services(request).projection is None:
        return ProjectionOut(
            available=False, method="unavailable", n=0, computed_ms=0, points=[]
        )
    result: ProjectionResult = get_services(request).projection.get(refresh=refresh)
    return ProjectionOut(
        available=True,
        method=result.method,
        n=result.n,
        computed_ms=result.computed_ms,
        points=[
            ProjectionPointOut(
                entry_id=p.entry_id,
                title=p.title,
                collections=p.collections,
                source=p.source,
                x=p.x,
                y=p.y,
                z=p.z,
            )
            for p in result.points
        ],
    )


def _total(request: Request) -> int:
    row = get_services(request).db.conn.execute("SELECT COUNT(*) FROM entries").fetchone()
    return row[0]

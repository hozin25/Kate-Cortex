"""FastAPI 应用入口：uvicorn kate_cortex.main:app --port 1738"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .chat.service import ChatService
from .config import Config, load_config
from .db import connect as db_connect
from .providers import ProviderFactory
from .providers.embedding import make_embedder_factory
from .projection import ProjectionCache
from .search import Search
from .settings import SettingsService
from .storage import Storage
from .vectors import VectorIndex

logger = logging.getLogger(__name__)

APP_NAME = "kate-cortex"
# dev 期渲染进程由 vite 提供，端口可能被占用而顺延（5173/5174/…），按正则放行；
# 远程部署（Vercel 等）经 KATE_ALLOWED_ORIGINS 追加放行源（逗号分隔，支持 *）
RENDERER_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra_origins = os.environ.get("KATE_ALLOWED_ORIGINS", "")
RENDERER_ORIGINS += [o.strip() for o in _extra_origins.split(",") if o.strip()]
RENDERER_ORIGIN_RE = r"https?://(localhost|127\.0\.0\.1):\d+"

# 鉴权豁免：health 供 sidecar 就绪探测与「端口被占时识别本应用」，必须开放
AUTH_EXEMPT_PATHS = ("/api/health",)


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title=APP_NAME, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=RENDERER_ORIGINS,
        allow_origin_regex=RENDERER_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 本地 API 鉴权：绑定 127.0.0.1 只挡外网，挡不住本机其他进程读 key/删库。
    # Electron sidecar（阶段 5）启动时生成一次性随机 token 经环境变量注入；
    # 未设置则不启用（当前 dev 手动 uv run 的既有工作流不变）
    api_token = os.environ.get("KATE_API_TOKEN") or None
    app.state.api_token = api_token
    if api_token:
        app.middleware("http")(make_auth_middleware(api_token))
    database = db_connect(config.db_path)
    settings_service = SettingsService(database.conn)
    vector_index = (
        VectorIndex(database.conn, make_embedder_factory(settings_service))
        if database.vec_enabled
        else None
    )
    projection = (
        ProjectionCache(database.conn, settings_service.get_all)
        if database.vec_enabled
        else None
    )
    storage = Storage(
        config=config,
        db=database,
        search=Search(database.conn),
        vectors=vector_index,
    )
    _run_startup_migrations(database, storage, settings_service)
    app.state.config = config
    app.state.db = database
    app.state.storage = storage
    app.state.chat_service = ChatService(database.conn)
    app.state.settings_service = settings_service
    app.state.provider_factory = ProviderFactory(app.state.settings_service)
    app.state.vector_index = vector_index
    app.state.projection = projection

    from .routes import (
        attachments,
        chat,
        collections,
        embeddings,
        entries,
        health,
        importer,
        mcp,
        settings,
        sync,
        trash,
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(entries.router, prefix="/api")
    app.include_router(collections.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(embeddings.router, prefix="/api")
    app.include_router(mcp.router, prefix="/api")
    app.include_router(importer.router, prefix="/api")
    app.include_router(attachments.router, prefix="/api")
    app.include_router(trash.router, prefix="/api")
    return app


def make_auth_middleware(api_token: str):
    """校验 X-Kate-Token 头 / Bearer / ?api_token=（供 <img> 等无法带头的场景）"""

    async def verify_token(request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path.startswith(AUTH_EXEMPT_PATHS):
            return await call_next(request)
        header = request.headers.get("x-kate-token")
        if not header:
            bearer = request.headers.get("authorization") or ""
            header = bearer[7:] if bearer.lower().startswith("bearer ") else None
        provided = header or request.query_params.get("api_token")
        if provided != api_token:
            return JSONResponse(status_code=401, content={"detail": "未授权：本地 API 需要有效 token"})
        return await call_next(request)

    return verify_token


def _run_startup_migrations(database, storage, settings_service) -> None:
    """存量「个人信息」tag → 合集迁移（幂等，每次启动跑）；
    v3 迁移当天 FTS 被重建为空表，需从 md 真相源全量重灌一次；
    历史明文 API key 就地加密；回收站超期文件清理"""
    storage.migrate_profile_to_collection()
    if database.migrated_from is not None and database.migrated_from < 3:
        storage.reindex()
    reencrypted = settings_service.encrypt_existing_secrets()
    if reencrypted:
        logger.info("已将 %d 项历史明文凭据重写为 DPAPI 密文", reencrypted)
    purged = storage.cleanup_trash()
    if purged:
        logger.info("回收站清理：%d 个超期文件已删除", purged)


app = create_app()

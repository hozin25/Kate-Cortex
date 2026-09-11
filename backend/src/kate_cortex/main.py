"""FastAPI 应用入口：uvicorn kate_cortex.main:app --port 1738

双模式（config.is_multiuser）：
- 单用户（默认，桌面/dev/Vercel）：启动时装配一套全局服务到 app.state，
  可选 KATE_API_TOKEN 本地令牌鉴权
- 多用户（KATE_DATA_DIR 已设置）：不打开任何单用户数据库，会话中间件按
  cookie 鉴权并注入该用户的服务集（multiuser.py），可选托管前端静态文件
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import UsersStore
from .chat.service import ChatService
from .config import Config, is_multiuser, load_config
from .db import connect as db_connect
from .multiuser import UserRegistry, make_session_middleware
from .providers import ProviderFactory
from .providers.embedding import make_embedder_factory
from .projection import ProjectionCache
from .search import Search
from .settings import SettingsService
from .storage import Storage, initialize_storage
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
    app = FastAPI(title=APP_NAME, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=RENDERER_ORIGINS,
        allow_origin_regex=RENDERER_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.api_token = os.environ.get("KATE_API_TOKEN") or None

    if is_multiuser():
        _wire_multiuser(app)
    else:
        _wire_single_user(app, config or load_config())

    _include_routers(app)
    if is_multiuser():
        # mount 在路由之后注册：/api 先匹配到 API 路由，其余路径走静态文件
        _mount_frontend(app)
    return app


def _wire_single_user(app: FastAPI, config: Config) -> None:
    # 本地 API 鉴权：绑定 127.0.0.1 只挡外网，挡不住本机其他进程读 key/删库。
    # Electron sidecar（阶段 5）启动时生成一次性随机 token 经环境变量注入；
    # 未设置则不启用（当前 dev 手动 uv run 的既有工作流不变）
    if app.state.api_token:
        app.middleware("http")(make_auth_middleware(app.state.api_token))
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
    initialize_storage(database, storage, settings_service)
    app.state.config = config
    app.state.db = database
    app.state.storage = storage
    app.state.chat_service = ChatService(database.conn)
    app.state.settings_service = settings_service
    app.state.provider_factory = ProviderFactory(settings_service)
    app.state.vector_index = vector_index
    app.state.projection = projection


def _wire_multiuser(app: FastAPI) -> None:
    data_dir = Path(os.environ["KATE_DATA_DIR"])
    users_store = UsersStore(data_dir / "users.sqlite")
    registry = UserRegistry(data_dir)
    app.state.users_store = users_store
    app.state.registry = registry
    app.middleware("http")(make_session_middleware(users_store, registry))
    _warm_jieba()
    if not os.environ.get("KATE_SECRET_KEY"):
        logger.warning(
            "多用户模式未设置 KATE_SECRET_KEY，用户 API Key 将明文存储在服务器磁盘"
        )


def _include_routers(app: FastAPI) -> None:
    from .routes import (
        attachments,
        auth,
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
    app.include_router(auth.router, prefix="/api")
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


def _mount_frontend(app: FastAPI) -> None:
    """托管前端静态产物（KATE_FRONTEND_DIR）。应用用 hash 路由，深链恒为
    /#/…，服务端只需 / 命中 index.html，无需 SPA rewrite"""
    frontend_dir = os.environ.get("KATE_FRONTEND_DIR")
    if frontend_dir and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="web")
        logger.info("已托管前端静态文件: %s", frontend_dir)


def _warm_jieba() -> None:
    """jieba 词典在首次分词时惰性加载（秒级），提前到启动避免首个请求卡顿"""
    try:
        import jieba

        jieba.initialize()
    except Exception as exc:  # pragma: no cover - 分词器缺失不应阻断启动
        logger.warning("jieba 预热失败: %s", exc)


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


app = create_app()

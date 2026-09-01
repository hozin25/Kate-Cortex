"""FastAPI 应用入口：uvicorn kate_cortex.main:app --port 1738"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .chat.service import ChatService
from .config import Config, load_config
from .db import connect as db_connect
from .providers import ProviderFactory
from .providers.embedding import GLMEmbedder, SiliconFlowEmbedder
from .projection import ProjectionCache
from .search import Search
from .settings import SettingsService
from .storage import Storage
from .vectors import VectorIndex

APP_NAME = "kate-cortex"
# dev 期渲染进程由 vite 提供，端口可能被占用而顺延（5173/5174/…），按正则放行
RENDERER_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
RENDERER_ORIGIN_RE = r"https?://(localhost|127\.0\.0\.1):\d+"


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
    database = db_connect(config.db_path)
    settings_service = SettingsService(database.conn)
    vector_index = (
        VectorIndex(database.conn, _make_embedder_factory(settings_service))
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
    _run_startup_migrations(database, storage)
    app.state.config = config
    app.state.db = database
    app.state.storage = storage
    app.state.chat_service = ChatService(database.conn)
    app.state.settings_service = settings_service
    app.state.provider_factory = ProviderFactory(app.state.settings_service)
    app.state.vector_index = vector_index
    app.state.projection = projection

    from .routes import chat, collections, embeddings, entries, health, settings, sync

    app.include_router(health.router, prefix="/api")
    app.include_router(entries.router, prefix="/api")
    app.include_router(collections.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(embeddings.router, prefix="/api")
    return app


def _make_embedder_factory(settings_service):
    """每次调用时从 settings 解析 embedding provider（后配 key 免重启）：
    siliconflow 用独立 embedding_api_key；glm 为空时回退复用 provider key。
    缺 key 返回 None → 向量检索降级为纯 FTS"""

    def factory() -> GLMEmbedder | SiliconFlowEmbedder | None:
        settings = settings_service.get_all()
        provider = settings.get("embedding_provider", "glm")
        model = settings.get("embedding_model")
        api_key = settings.get("embedding_api_key")
        if provider == "siliconflow":
            if not api_key:
                return None
            return SiliconFlowEmbedder(api_key=api_key, model=model)
        if not api_key:
            api_key = settings.get("provider_keys", {}).get("glm")
        if not api_key:
            return None
        return GLMEmbedder(api_key=api_key, model=model)

    return factory


def _run_startup_migrations(database, storage) -> None:
    """存量「个人信息」tag → 合集迁移（幂等，每次启动跑）；
    v3 迁移当天 FTS 被重建为空表，需从 md 真相源全量重灌一次"""
    storage.migrate_profile_to_collection()
    if database.migrated_from is not None and database.migrated_from < 3:
        storage.reindex()


app = create_app()

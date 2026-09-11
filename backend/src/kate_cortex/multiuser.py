"""多用户运行时：每用户惰性构建一套完整服务并缓存，会话中间件按 cookie 路由。

数据布局：<KATE_DATA_DIR>/users/<user_id>/vault/（含 index.sqlite）。
构建逻辑与单用户 create_app 的装配完全一致（依赖按连接/路径绑定，无全局态，
见 DESIGN.md §多用户），首次构建跑一次启动迁移。缓存 LRU 上限 64——
超出时逐出最久未用用户并关闭其连接；个人部署量级下「正在使用的用户被
逐出」可忽略，若放大部署需改为引用计数淘汰。
"""

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from .auth import SESSION_COOKIE, UsersStore
from .chat.service import ChatService
from .config import Config
from .db import Database, connect as db_connect
from .providers import ProviderFactory
from .providers.embedding import make_embedder_factory
from .projection import ProjectionCache
from .search import Search
from .settings import SettingsService
from .storage import Storage, initialize_storage
from .vectors import VectorIndex

logger = logging.getLogger(__name__)

REGISTRY_MAX_USERS = 64


@dataclass
class UserServices:
    """一个用户的全部后端服务（与单用户 app.state 同名字段，路由无感切换）"""

    config: Config
    db: Database
    storage: Storage
    chat_service: ChatService
    settings_service: SettingsService
    provider_factory: ProviderFactory
    vector_index: VectorIndex | None
    projection: ProjectionCache | None

    def close(self) -> None:
        self.db.close()


def build_user_services(data_dir: Path, user_id: str) -> UserServices:
    user_dir = data_dir / "users" / user_id
    config = Config(
        vault_path=user_dir / "vault", db_path=user_dir / "vault" / "index.sqlite"
    )
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
        config=config, db=database, search=Search(database.conn), vectors=vector_index
    )
    initialize_storage(database, storage, settings_service)
    return UserServices(
        config=config,
        db=database,
        storage=storage,
        chat_service=ChatService(database.conn),
        settings_service=settings_service,
        provider_factory=ProviderFactory(settings_service),
        vector_index=vector_index,
        projection=projection,
    )


class UserRegistry:
    """user_id → UserServices 的进程内 LRU 缓存"""

    def __init__(self, data_dir: Path, max_users: int = REGISTRY_MAX_USERS):
        self._data_dir = data_dir
        self._max_users = max_users
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, UserServices] = OrderedDict()

    def get(self, user_id: str) -> UserServices:
        # 构建放锁内：首次构建是唯一慢路径（建目录 + schema 初始化），
        # 个人部署量级下串行化可接受，换不来「构建中重复构建/关闭在用连接」的竞态
        with self._lock:
            services = self._cache.get(user_id)
            if services is None:
                services = build_user_services(self._data_dir, user_id)
                self._cache[user_id] = services
                logger.info("已加载用户服务: %s", user_id)
            else:
                self._cache.move_to_end(user_id)
            while len(self._cache) > self._max_users:
                _, evicted = self._cache.popitem(last=False)
                logger.info("逐出用户服务缓存: %s", evicted.config.vault_path.parent.name)
                evicted.close()
            return services


def make_session_middleware(users_store: UsersStore, registry: UserRegistry):
    """cookie 会话鉴权 + 每请求用户服务注入（request.state.svc）。
    仅多用户模式注册；/api/health、/api/auth/* 与非 /api 路径（静态资源）放行"""

    async def session_middleware(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api"):
            return await call_next(request)
        if path.startswith(("/api/health", "/api/auth/")):
            return await call_next(request)
        token = request.cookies.get(SESSION_COOKIE)
        user = users_store.resolve_session(token) if token else None
        if user is None:
            return JSONResponse(
                status_code=401, content={"detail": "未登录或登录已过期"}
            )
        request.state.user_id = user["id"]
        request.state.svc = registry.get(user["id"])
        return await call_next(request)

    return session_middleware


def get_services(request: Request):
    """路由取服务集的唯一入口：多用户模式由中间件注入，单用户模式回落 app.state
    （两者字段同名：storage / chat_service / settings_service / provider_factory /
    vector_index / projection / db / config）"""
    services = getattr(request.state, "svc", None)
    if services is not None:
        return services
    return request.app.state

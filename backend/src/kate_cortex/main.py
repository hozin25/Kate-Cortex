"""FastAPI 应用入口：uvicorn kate_cortex.main:app --port 1738"""

from fastapi import FastAPI

from . import __version__
from .config import Config, load_config
from .db import connect as db_connect
from .search import Search
from .storage import Storage

APP_NAME = "kate-cortex"


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title=APP_NAME, version=__version__)
    database = db_connect(config.db_path)
    storage = Storage(config=config, db=database, search=Search(database.conn))
    app.state.config = config
    app.state.db = database
    app.state.storage = storage

    from .routes import entries, health, sync, tags

    app.include_router(health.router, prefix="/api")
    app.include_router(entries.router, prefix="/api")
    app.include_router(tags.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    return app


app = create_app()

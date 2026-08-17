"""运行配置：vault / db 路径与服务地址，环境变量可覆盖（IMPLEMENTATION_PLAN 0.1 拍板）"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1738
APP_DIR_NAME = "Kate-Cortex"


@dataclass(frozen=True)
class Config:
    vault_path: Path
    db_path: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


def load_config() -> Config:
    vault = Path(os.environ.get("KATE_VAULT_PATH") or _default_vault())
    db_path = Path(os.environ.get("KATE_DB_PATH") or vault / "index.sqlite")
    host = os.environ.get("KATE_HOST") or DEFAULT_HOST
    port = int(os.environ.get("KATE_PORT") or DEFAULT_PORT)
    return Config(vault_path=vault, db_path=db_path, host=host, port=port)


def _default_vault() -> Path:
    if os.environ.get("KATE_PACKAGED") == "1" or getattr(sys, "frozen", False):
        return Path.home() / APP_DIR_NAME / "vault"
    return Path(__file__).resolve().parents[3] / "vault"

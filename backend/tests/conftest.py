import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def pytest_configure():
    # main.py 模块级 app 在 import 时用默认路径建连接，重定向到会话临时目录避免污染 dev vault
    session_tmp = Path(tempfile.mkdtemp(prefix="kate-cortex-test-"))
    os.environ["KATE_VAULT_PATH"] = str(session_tmp / "vault")
    os.environ["KATE_DB_PATH"] = str(session_tmp / "index.sqlite")

import kate_cortex.db as db_mod
from kate_cortex.config import Config, load_config
from kate_cortex.search import Search
from kate_cortex.storage import Storage


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("KATE_VAULT_PATH", str(vault))
    monkeypatch.setenv("KATE_DB_PATH", str(tmp_path / "index.sqlite"))
    monkeypatch.delenv("KATE_PACKAGED", raising=False)
    return Config(vault_path=vault, db_path=tmp_path / "index.sqlite")


@pytest.fixture
def storage(env):
    database = db_mod.connect(env.db_path)
    return Storage(config=env, db=database, search=Search(database.conn))


@pytest.fixture
def seeded(storage):
    first = storage.create_entry(
        title="Redis pipeline 事务模式踩坑",
        source="manual",
        content="pipeline 事务模式下不返回结果。\n\n相关：[[fastapi-middleware-she-ji]]\n",
        collections=["编程"],
    )
    second = storage.create_entry(
        title="FastAPI middleware 设计",
        source="manual",
        content="middleware 执行顺序与依赖注入。",
    )
    return storage, first, second

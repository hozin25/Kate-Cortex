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
from kate_cortex.providers.embedding import FakeEmbedder
from kate_cortex.search import Search
from kate_cortex.storage import Storage
from kate_cortex.vectors import VectorIndex

# 语义簇（向量检索验收配置）：跨词面场景属同一生活语境，纯 FTS 无法互相召回
SEMANTIC_CLUSTERS = {
    "生活健康": ["感冒", "保暖", "健康", "出行", "出去玩", "天气"],
    "编程": ["redis", "python", "fastapi", "连接池", "中间件"],
}


class FailingEmbedder:
    """embed 一律抛错，验证写入路径不被网络故障阻断"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding boom")


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
def vector_storage(env):
    """带向量索引的 Storage：FakeEmbedder 按语义簇生成确定性向量"""
    database = db_mod.connect(env.db_path)
    index = VectorIndex(
        database.conn, lambda: FakeEmbedder(clusters=SEMANTIC_CLUSTERS)
    )
    storage = Storage(
        config=env, db=database, search=Search(database.conn), vectors=index
    )
    return storage, index


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

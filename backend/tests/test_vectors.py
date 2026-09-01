"""VectorIndex 与 storage 写路径挂钩（VECTOR_SEARCH_PLAN.md §4）"""

from conftest import SEMANTIC_CLUSTERS, FailingEmbedder
from kate_cortex.chat.rag import retrieve  # noqa: F401  # 确保 rag 导入无循环依赖
from kate_cortex.db import connect as db_connect
from kate_cortex.providers.embedding import FakeEmbedder
from kate_cortex.search import Search
from kate_cortex.storage import Storage
from kate_cortex.vectors import BackfillResult, VectorIndex


def make_plain_storage(env) -> Storage:
    """无向量索引的 Storage（v4 行为）"""
    database = db_connect(env.db_path)
    return Storage(config=env, db=database, search=Search(database.conn))


class TestStorageHooks:
    def test_create_entry_indexes_vector(self, vector_storage):
        storage, index = vector_storage
        storage.create_entry(title="感冒护理", source="manual", content="注意保暖多喝热水")

        assert index.status() == (1, 1)
        hits = index.query("感冒了怎么办")
        assert hits and hits[0].entry_id.startswith("kc_")

    def test_update_entry_reindexes_vector(self, vector_storage):
        storage, index = vector_storage
        entry = storage.create_entry(title="旧标题", source="manual", content="内容")
        storage.update_entry(entry.id, title="新标题", content="新内容")

        assert index.status() == (1, 1)
        assert index.query("新标题")[0].entry_id == entry.id

    def test_delete_entry_removes_vector(self, vector_storage):
        storage, index = vector_storage
        entry = storage.create_entry(title="待删除", source="manual", content="内容")
        storage.delete_entry(entry.id)

        assert index.status() == (0, 0)

    def test_restore_entry_reindexes_vector(self, vector_storage):
        storage, index = vector_storage
        entry = storage.create_entry(title="可恢复", source="manual", content="内容")
        storage.delete_entry(entry.id)
        storage.restore_entry(entry.id)

        assert index.status() == (1, 1)

    def test_reindex_clears_vectors_without_reembedding(self, vector_storage):
        storage, index = vector_storage
        storage.create_entry(title="条目", source="manual", content="内容")
        storage.reindex()

        # 只清不嵌（重嵌走显式 rebuild，避免隐式 API 费用）
        assert index.status() == (0, 1)

    def test_embedder_failure_does_not_block_create(self, env):
        database = db_connect(env.db_path)
        index = VectorIndex(database.conn, lambda: FailingEmbedder())
        storage = Storage(
            config=env, db=database, search=Search(database.conn), vectors=index
        )

        entry = storage.create_entry(title="标题", source="manual", content="内容")

        assert entry.id.startswith("kc_")
        assert index.status() == (0, 1)

    def test_missing_key_degrades_to_noop(self, env):
        database = db_connect(env.db_path)
        index = VectorIndex(database.conn, lambda: None)
        storage = Storage(
            config=env, db=database, search=Search(database.conn), vectors=index
        )

        entry = storage.create_entry(title="标题", source="manual", content="内容")

        assert not index.available
        assert index.query("任意") == []
        assert index.status() == (0, 1)
        assert storage.get_entry(entry.id) is not None


class TestBackfill:
    def test_backfill_fills_missing_and_is_idempotent(self, env):
        plain = make_plain_storage(env)
        plain.create_entry(title="感冒护理", source="manual", content="注意保暖")
        plain.create_entry(title="Redis 笔记", source="manual", content="pipeline")
        database = plain.db
        index = VectorIndex(
            database.conn, lambda: FakeEmbedder(clusters=SEMANTIC_CLUSTERS)
        )

        result = index.backfill(plain)

        assert result == BackfillResult(2, 0)
        assert index.status() == (2, 2)
        assert index.backfill(plain) == BackfillResult(0, 0)

    def test_backfill_counts_entry_with_missing_md_as_failed(self, env):
        plain = make_plain_storage(env)
        entry = plain.create_entry(title="孤儿", source="manual", content="内容")
        (plain.vault / entry.file_path).unlink()
        index = VectorIndex(
            plain.db.conn, lambda: FakeEmbedder(clusters=SEMANTIC_CLUSTERS)
        )

        result = index.backfill(plain)

        assert result == BackfillResult(0, 1)

    def test_backfill_without_key_returns_zero(self, env):
        plain = make_plain_storage(env)
        plain.create_entry(title="条目", source="manual", content="内容")
        index = VectorIndex(plain.db.conn, lambda: None)

        assert index.backfill(plain) == BackfillResult(0, 0)
        assert index.status() == (0, 1)

    def test_rebuild_clears_then_reembeds(self, env):
        plain = make_plain_storage(env)
        plain.create_entry(title="感冒护理", source="manual", content="注意保暖")
        index = VectorIndex(
            plain.db.conn, lambda: FakeEmbedder(clusters=SEMANTIC_CLUSTERS)
        )
        index.backfill(plain)

        result = index.rebuild(plain)

        assert result == BackfillResult(1, 0)
        assert index.status() == (1, 1)


class TestQuery:
    def test_same_cluster_ranks_before_other_cluster(self, vector_storage):
        storage, index = vector_storage
        near = storage.create_entry(title="感冒护理", source="manual", content="注意保暖")
        storage.create_entry(title="Redis 笔记", source="manual", content="pipeline 事务")

        hits = index.query("感冒了要注意什么")

        assert hits[0].entry_id == near.id

    def test_query_without_vectors_returns_empty(self, env):
        plain = make_plain_storage(env)
        plain.create_entry(title="条目", source="manual", content="内容")
        index = VectorIndex(plain.db.conn, lambda: None)

        assert index.query("条目") == []

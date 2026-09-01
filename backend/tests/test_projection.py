"""三维投影（VECTOR_GRAPH_PLAN.md §5）：降维质量 / 签名缓存 / 阈值分派

簇分离用例刻意用 4 簇 × 12 条：实测 2 簇小样本下 3D t-SNE 会退化为
「两团点在球壳上互绕」（调试记录见 VECTOR_GRAPH_PLAN.md §2），真实个人库
的主题数远多于 2，4 簇是对真实形态的保守模拟。
"""

import math

import pytest

from kate_cortex.db import connect as db_connect
from kate_cortex.projection import ProjectionCache
from kate_cortex.providers.embedding import FakeEmbedder
from kate_cortex.search import Search
from kate_cortex.storage import Storage
from kate_cortex.vectors import VectorIndex

# 4 簇配置（keyword → 簇名，标题含 keyword 即归簇，需与 conftest 语义簇同构）
GRAPH_CLUSTERS = {
    "出行": ["天气", "出行", "旅行"],
    "编程": ["redis", "python", "fastapi"],
    "美食": ["烹饪", "美食", "食谱"],
    "生活健康": ["感冒", "保暖", "健康"],
}


@pytest.fixture
def graph_env(env):
    """Storage + VectorIndex + ProjectionCache，共享同一 FakeEmbedder 语义簇配置"""
    database = db_connect(env.db_path)
    index = VectorIndex(database.conn, lambda: FakeEmbedder(clusters=GRAPH_CLUSTERS))
    storage = Storage(
        config=env, db=database, search=Search(database.conn), vectors=index
    )
    cache = ProjectionCache(
        database.conn,
        lambda: {"embedding_provider": "glm", "embedding_model": "embedding-3"},
    )
    return storage, cache


def seed_cluster(storage, keyword: str, name: str, count: int) -> None:
    for i in range(count):
        storage.create_entry(
            title=f"{keyword}笔记{i}",
            source="manual",
            content=f"第{i}篇：关于{keyword}的场景{i}号记录。",
            collections=[name],
        )


def distance(a, b) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def mean_pairwise(group) -> float:
    pairs = [distance(a, b) for i, a in enumerate(group) for b in group[i + 1 :]]
    return sum(pairs) / len(pairs)


class TestClusterQuality:
    def test_same_cluster_points_closer_than_cross_cluster(self, graph_env):
        storage, cache = graph_env
        for name, words in GRAPH_CLUSTERS.items():
            seed_cluster(storage, words[0], name, 12)

        result = cache.get()

        assert result.method == "tsne"
        by_collection = {
            name: [p for p in result.points if name in p.collections]
            for name in GRAPH_CLUSTERS
        }
        assert all(len(g) == 12 for g in by_collection.values())

        intra = sum(
            mean_pairwise(group) for group in by_collection.values()
        ) / len(by_collection)
        cross = [
            distance(a, b)
            for i, ga in enumerate(by_collection.values())
            for gb in list(by_collection.values())[i + 1 :]
            for a in ga
            for b in gb
        ]
        inter = sum(cross) / len(cross)
        # 实测该配置下比值 ~1.6x，留安全余量
        assert inter > intra * 1.25

    def test_collections_carried_through(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 4)

        result = cache.get()

        assert all(p.collections == ["生活健康"] for p in result.points)
        assert all(p.source == "manual" for p in result.points)


class TestThresholds:
    def test_insufficient_below_three_points(self, graph_env):
        storage, cache = graph_env
        storage.create_entry(title="感冒A", source="manual", content="感冒")
        storage.create_entry(title="感冒B", source="manual", content="又感冒")

        result = cache.get()

        assert result.method == "insufficient"
        assert result.points == []

    def test_small_library_uses_pca(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 5)
        seed_cluster(storage, "redis", "编程", 5)

        result = cache.get()

        assert result.method == "pca"
        assert result.n == 10

    def test_coords_within_unit_cube(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 12)
        seed_cluster(storage, "redis", "编程", 12)

        result = cache.get()

        assert all(
            -1.0 <= v <= 1.0 for p in result.points for v in (p.x, p.y, p.z)
        )


class TestSignatureCache:
    def test_cache_hit_until_signature_changes(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 4)

        first = cache.get()
        second = cache.get()
        assert second is first

        storage.create_entry(title="redis 新条目", source="manual", content="redis")

        third = cache.get()
        assert third is not first
        assert third.n == first.n + 1

    def test_refresh_bypasses_cache(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 4)

        first = cache.get()
        refreshed = cache.get(refresh=True)

        assert refreshed is not first
        assert refreshed.n == first.n

    def test_signature_covers_embedding_provider_and_model(self, graph_env):
        storage, cache = graph_env
        seed_cluster(storage, "感冒", "生活健康", 4)
        glm = cache.get()

        switched = ProjectionCache(
            storage.conn,
            lambda: {
                "embedding_provider": "siliconflow",
                "embedding_model": "BAAI/bge-m3",
            },
        )
        other = switched.get()

        assert other is not glm
        assert other.n == glm.n

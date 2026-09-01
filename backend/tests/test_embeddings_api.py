"""/api/embeddings/*：状态与重建端点（VECTOR_SEARCH_PLAN.md §6）"""

import pytest
from fastapi.testclient import TestClient

from conftest import SEMANTIC_CLUSTERS
from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.embedding import FakeEmbedder


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    return TestClient(app)


@pytest.fixture
def embed_client(client):
    """注入 FakeEmbedder（模拟已配 glm key），避免真实出网"""
    client.app.state.vector_index.embedder_factory = lambda: FakeEmbedder(
        clusters=SEMANTIC_CLUSTERS
    )
    return client


def create_entry(client, title: str) -> dict:
    resp = client.post(
        "/api/entries", json={"title": title, "source": "manual", "content": "内容"}
    )
    assert resp.status_code == 201
    return resp.json()


class TestStatus:
    def test_reports_counts_when_available(self, embed_client):
        create_entry(embed_client, "感冒护理")
        create_entry(embed_client, "Redis 笔记")

        resp = embed_client.get("/api/embeddings/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"available": True, "indexed": 2, "total": 2}

    def test_unavailable_without_glm_key(self, client):
        create_entry(client, "条目")

        resp = client.get("/api/embeddings/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["indexed"] == 0
        assert body["total"] == 1


class TestProviderResolution:
    """settings → embedder 解析（构造不联网，只验证 key 归属与回退）"""

    def test_glm_falls_back_to_provider_key(self, client):
        client.put("/api/settings", json={"provider_keys": {"glm": "sk-glm"}})

        assert client.get("/api/embeddings/status").json()["available"] is True

    def test_glm_prefers_dedicated_embedding_key(self, client):
        client.put("/api/settings", json={"embedding_api_key": "sk-emb"})

        assert client.get("/api/embeddings/status").json()["available"] is True

    def test_siliconflow_unavailable_without_key(self, client):
        client.put(
            "/api/settings",
            json={"embedding_provider": "siliconflow", "embedding_model": "BAAI/bge-m3"},
        )

        body = client.get("/api/embeddings/status").json()
        assert body["available"] is False

    def test_siliconflow_available_with_key(self, client):
        client.put(
            "/api/settings",
            json={
                "embedding_provider": "siliconflow",
                "embedding_model": "BAAI/bge-m3",
                "embedding_api_key": "sk-sf-test",
            },
        )

        body = client.get("/api/embeddings/status").json()
        assert body["available"] is True

    def test_siliconflow_ignores_glm_key(self, client):
        client.put("/api/settings", json={"provider_keys": {"glm": "sk-glm"}})
        client.put("/api/settings", json={"embedding_provider": "siliconflow"})

        body = client.get("/api/embeddings/status").json()
        assert body["available"] is False

    def test_unknown_embedding_provider_rejected(self, client):
        resp = client.put("/api/settings", json={"embedding_provider": "openai"})

        assert resp.status_code == 422


class TestRebuild:
    def test_rebuild_indexes_all_entries(self, client):
        # 先无 key 创建（未建向量），再注入 FakeEmbedder 重建
        create_entry(client, "感冒护理")
        create_entry(client, "Redis 笔记")
        client.app.state.vector_index.embedder_factory = lambda: FakeEmbedder(
            clusters=SEMANTIC_CLUSTERS
        )

        resp = client.post("/api/embeddings/rebuild")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"indexed": 2, "total": 2, "failed": 0}
        assert client.get("/api/embeddings/status").json()["indexed"] == 2

    def test_rebuild_is_idempotent(self, embed_client):
        create_entry(embed_client, "条目")
        first = embed_client.post("/api/embeddings/rebuild").json()

        assert first["indexed"] == 1

    def test_rebuild_without_key_returns_502(self, client):
        resp = client.post("/api/embeddings/rebuild")

        assert resp.status_code == 502


class TestProjection:
    """三维投影端点（VECTOR_GRAPH_PLAN.md §3）：vec 缺失降级 / 点集结构 / 刷新"""

    def test_unavailable_without_vector_index(self, client):
        client.app.state.vector_index = None
        client.app.state.projection = None

        resp = client.get("/api/embeddings/projection")

        assert resp.status_code == 200
        assert resp.json() == {
            "available": False,
            "method": "unavailable",
            "n": 0,
            "computed_ms": 0,
            "points": [],
        }

    def test_insufficient_with_single_entry(self, embed_client):
        create_entry(embed_client, "感冒护理")

        body = embed_client.get("/api/embeddings/projection").json()

        assert body["available"] is True
        assert body["method"] == "insufficient"
        assert body["n"] == 0
        assert body["points"] == []

    def test_projection_returns_point_cloud(self, embed_client):
        for i in range(12):
            create_entry(embed_client, f"感冒护理{i}")
            create_entry(embed_client, f"Redis 笔记{i}")

        body = embed_client.get("/api/embeddings/projection").json()

        assert body["available"] is True
        assert body["method"] == "tsne"
        assert body["n"] == 24
        assert len(body["points"]) == 24
        point = body["points"][0]
        assert {"entry_id", "title", "collections", "source", "x", "y", "z"} <= set(
            point
        )
        assert all(-1.0 <= point[k] <= 1.0 for k in ("x", "y", "z"))

    def test_refresh_recomputes(self, embed_client):
        for i in range(12):
            create_entry(embed_client, f"感冒护理{i}")
            create_entry(embed_client, f"Redis 笔记{i}")
        first = embed_client.get("/api/embeddings/projection").json()

        resp = embed_client.post("/api/embeddings/projection/refresh")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["n"] == first["n"]
        assert body["computed_ms"] >= 0

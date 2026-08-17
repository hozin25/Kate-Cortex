import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    return TestClient(app)


def create(client, **overrides):
    payload = dict(
        title="Redis pipeline 事务模式踩坑",
        type="howto",
        tags=["redis", "bug"],
        source="manual",
        content="pipeline 事务模式下不返回结果。",
    )
    payload.update(overrides)
    resp = client.post("/api/entries", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestHealth:
    def test_returns_app_identity(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["app"] == "kate-cortex"
        assert "version" in resp.json()


class TestEntryCrud:
    def test_create_chinese_title_writes_vault_file(self, client, env):
        entry = create(client)

        assert entry["id"].startswith("kc_")
        assert entry["slug"] == "redis-pipeline-shi-wu-mo-shi-cai-keng"
        assert entry["type"] == "howto"
        assert entry["tags"] == ["redis", "bug"]

        md_file = env.vault_path / entry["file_path"]
        assert md_file.is_file()
        text = md_file.read_text(encoding="utf-8")
        assert "title: Redis pipeline 事务模式踩坑" in text
        assert "pipeline 事务模式下不返回结果。" in text

    def test_create_rejects_unknown_type(self, client):
        resp = client.post(
            "/api/entries", json={"title": "t", "type": "snippet", "tags": []}
        )
        assert resp.status_code == 422

    def test_get_by_id_and_slug(self, client):
        entry = create(client)

        by_id = client.get(f"/api/entries/{entry['id']}")
        by_slug = client.get(f"/api/entries/{entry['slug']}")

        assert by_id.status_code == 200
        assert by_id.json()["id"] == entry["id"]
        assert by_slug.status_code == 200
        assert by_slug.json()["id"] == entry["id"]

    def test_get_missing_returns_404(self, client):
        assert client.get("/api/entries/nope").status_code == 404

    def test_list_with_type_and_tag_filter(self, client):
        create(client)
        create(client, title="读书笔记", type="note", tags=["reading"])

        by_type = client.get("/api/entries", params={"type": "note"})
        by_tag = client.get("/api/entries", params={"tag": "redis"})

        assert by_type.json()["total"] == 1
        assert by_type.json()["items"][0]["title"] == "读书笔记"
        assert by_tag.json()["total"] == 1
        assert by_tag.json()["items"][0]["title"] == "Redis pipeline 事务模式踩坑"

    def test_update_entry(self, client):
        entry = create(client)

        resp = client.put(
            f"/api/entries/{entry['id']}",
            json={"title": "改标题", "tags": ["redis", "pipeline"]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "改标题"
        assert body["slug"] == entry["slug"]
        assert body["tags"] == ["redis", "pipeline"]


class TestSearch:
    def test_search_chinese_keyword(self, client):
        create(client)

        resp = client.get("/api/entries", params={"q": "事务模式"})

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["slug"] == "redis-pipeline-shi-wu-mo-shi-cai-keng"

    def test_search_no_match(self, client):
        create(client)
        resp = client.get("/api/entries", params={"q": "量子纠缠"})
        assert resp.json()["total"] == 0


class TestSoftDelete:
    def test_delete_then_get_404_then_restore(self, client):
        entry = create(client)

        assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
        assert client.get(f"/api/entries/{entry['id']}").status_code == 404

        restored = client.post(f"/api/entries/{entry['id']}/restore")

        assert restored.status_code == 200
        assert restored.json()["title"] == entry["title"]
        assert client.get(f"/api/entries/{entry['id']}").status_code == 200

    def test_restore_missing_returns_404(self, client):
        assert client.post("/api/entries/kc_19990101_001/restore").status_code == 404

    def test_restore_conflict_returns_409(self, client, env):
        import shutil

        entry = create(client)
        src = env.vault_path / entry["file_path"]
        dst = env.vault_path / ".trash" / entry["file_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(src), str(dst))

        resp = client.post(f"/api/entries/{entry['id']}/restore")

        assert resp.status_code == 409


class TestLinks:
    def test_backlinks_endpoint(self, client):
        first = create(client)
        second = create(
            client,
            title="FastAPI middleware 设计",
            type="note",
            tags=["fastapi"],
            content=f"参考 [[{first['slug']}]]。",
        )

        resp = client.get(f"/api/entries/{first['id']}/links")

        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()] == [second["id"]]

    def test_links_missing_entry_404(self, client):
        assert client.get("/api/entries/nope/links").status_code == 404


class TestTags:
    def test_list_tags_with_counts(self, client):
        create(client)
        create(client, title="另一条", type="note", tags=["redis"])

        resp = client.get("/api/tags")

        tags = {item["name"]: item["count"] for item in resp.json()}
        assert tags == {"bug": 1, "redis": 2}

    def test_delete_tag_updates_entries(self, client):
        entry = create(client)

        resp = client.delete("/api/tags/redis")

        assert resp.status_code == 204
        refreshed = client.get(f"/api/entries/{entry['id']}").json()
        assert refreshed["tags"] == ["bug"]

    def test_delete_missing_tag_404(self, client):
        assert client.delete("/api/tags/nope").status_code == 404


class TestSync:
    def test_sync_reindexes_external_file(self, client, env):
        entry = create(client)
        orphan_dir = env.vault_path / "2026" / "08"
        orphan_dir.mkdir(parents=True, exist_ok=True)
        (orphan_dir / "20260818-099-wai-bu.md").write_text(
            "---\n"
            "id: kc_20260818_099\n"
            "slug: wai-bu\n"
            "title: 外部笔记\n"
            "type: note\n"
            "tags: []\n"
            "source: import\n"
            "created_at: 2026-08-18T09:00:00+08:00\n"
            "updated_at: 2026-08-18T09:00:00+08:00\n"
            "---\n"
            "外部手动放入的内容。\n",
            encoding="utf-8",
        )

        resp = client.post("/api/sync")

        assert resp.status_code == 200
        body = resp.json()
        assert body["indexed"] == 2
        assert "kc_20260818_099" in body["unindexed_before"]
        found = client.get("/api/entries/wai-bu")
        assert found.status_code == 200
        assert found.json()["title"] == "外部笔记"
        assert client.get(f"/api/entries/{entry['id']}").status_code == 200

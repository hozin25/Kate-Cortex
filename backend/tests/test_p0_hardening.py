"""P0 加固验收：凭据静态加密 / 本地 API 鉴权 / vault_path 诚实化 / 回收站补全"""

import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.security import decrypt_secret
from kate_cortex.settings import SettingsService


def raw_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    return TestClient(app)


class TestSecretsAtRest:
    def test_provider_keys_encrypted_in_database(self, client):
        client.put("/api/settings", json={"provider_keys": {"deepseek": "sk-at-rest-1"}})

        stored = raw_setting(client.app.state.db.conn, "provider_keys")

        assert decrypt_secret(stored["deepseek"]) == "sk-at-rest-1"  # 可解密还原
        if sys.platform == "win32":
            assert "sk-at-rest-1" not in json.dumps(stored)  # 明文不落盘

    def test_embedding_key_encrypted_in_database(self, client):
        client.put("/api/settings", json={"embedding_api_key": "sk-emb-at-rest"})

        stored = raw_setting(client.app.state.db.conn, "embedding_api_key")

        assert decrypt_secret(stored) == "sk-emb-at-rest"
        if sys.platform == "win32":
            assert "sk-emb-at-rest" not in json.dumps(stored)

    def test_api_roundtrip_still_returns_plaintext_to_caller(self, client):
        client.put("/api/settings", json={"provider_keys": {"glm": "sk-rt"}})

        refreshed = client.get("/api/settings").json()

        assert refreshed["provider_keys"]["glm"] == "sk-rt"

    def test_startup_migration_encrypts_existing_plaintext(self, env):
        import sqlite3

        from kate_cortex.db import connect as db_connect

        database = db_connect(env.db_path)
        service = SettingsService(database.conn)
        with database.conn:
            database.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('provider_keys', ?)",
                (json.dumps({"deepseek": "sk-legacy-plain"}),),
            )

        changed = service.encrypt_existing_secrets()

        assert changed == 1
        stored = raw_setting(database.conn, "provider_keys")
        assert decrypt_secret(stored["deepseek"]) == "sk-legacy-plain"
        if sys.platform == "win32":
            assert stored["deepseek"] != "sk-legacy-plain"
        assert service.encrypt_existing_secrets() == 0  # 幂等


class TestLocalApiAuth:
    @pytest.fixture
    def auth_client(self, env, monkeypatch):
        monkeypatch.setenv("KATE_API_TOKEN", "tok-abc-123")
        app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
        return TestClient(app)

    def test_missing_token_401(self, auth_client):
        assert auth_client.get("/api/entries").status_code == 401

    def test_wrong_token_401(self, auth_client):
        resp = auth_client.get("/api/entries", headers={"X-Kate-Token": "nope"})
        assert resp.status_code == 401

    def test_header_token_ok(self, auth_client):
        resp = auth_client.get("/api/entries", headers={"X-Kate-Token": "tok-abc-123"})
        assert resp.status_code == 200

    def test_bearer_token_ok(self, auth_client):
        resp = auth_client.get(
            "/api/entries", headers={"Authorization": "Bearer tok-abc-123"}
        )
        assert resp.status_code == 200

    def test_query_token_ok_for_img_tags(self, auth_client):
        resp = auth_client.get("/api/entries?api_token=tok-abc-123")
        assert resp.status_code == 200

    def test_health_open_for_sidecar_probe(self, auth_client):
        assert auth_client.get("/api/health").status_code == 200

    def test_no_token_env_keeps_dev_workflow(self, client):
        assert client.get("/api/entries").status_code == 200


class TestVaultPathHonesty:
    def test_update_rejects_vault_path(self, client):
        resp = client.put("/api/settings", json={"vault_path": "D:/somewhere"})
        assert resp.status_code == 422  # extra=forbid：明拒而非静默忽略

    def test_get_returns_active_path(self, client, env):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        assert resp.json()["vault_path"] == str(env.vault_path)

    def test_legacy_stored_vault_path_not_exposed(self, client):
        with client.app.state.db.conn:
            client.app.state.db.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('vault_path', '\"D:/dead\"')"
            )
        assert client.get("/api/settings").json()["vault_path"] != "D:/dead"


class TestTrashCompletion:
    def make_entry(self, client, title="待删除条目") -> dict:
        return client.post(
            "/api/entries", json={"title": title, "source": "manual", "content": "内容"}
        ).json()

    def test_delete_then_list_restore(self, client):
        entry = self.make_entry(client)

        assert client.delete(f"/api/entries/{entry['id']}").status_code == 204

        trashed = client.get("/api/trash").json()
        assert [t["id"] for t in trashed] == [entry["id"]]
        assert trashed[0]["title"] == "待删除条目"
        assert "deleted_at" in trashed[0]

        assert client.post(f"/api/entries/{entry['id']}/restore").status_code == 200
        assert client.get("/api/trash").json() == []
        assert client.get(f"/api/entries/{entry['id']}").status_code == 200

    def test_purge_removes_file_permanently(self, client, env):
        entry = self.make_entry(client)
        client.delete(f"/api/entries/{entry['id']}")

        resp = client.delete(f"/api/trash/{entry['id']}")

        assert resp.status_code == 200
        assert ".trash" in resp.json()["purged"]
        assert client.get("/api/trash").json() == []
        assert not any((env.vault_path / ".trash").rglob("*.md"))

    def test_purge_missing_404(self, client):
        assert client.delete("/api/trash/kc_20260101_999").status_code == 404

    def test_cleanup_removes_expired_keeps_fresh(self, client, env, storage):
        old = self.make_entry(client, "旧删除")
        new = self.make_entry(client, "新删除")
        client.delete(f"/api/entries/{old['id']}")
        client.delete(f"/api/entries/{new['id']}")

        # 把「旧删除」的 mtime 回拨 40 天
        for md in (env.vault_path / ".trash").rglob("*.md"):
            if old["slug"] in md.name:
                stamp = time.time() - 40 * 86400
                os.utime(md, (stamp, stamp))

        removed = storage.cleanup_trash()

        assert removed == 1
        remaining = client.get("/api/trash").json()
        assert [t["title"] for t in remaining] == ["新删除"]

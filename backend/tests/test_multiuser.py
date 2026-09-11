"""多用户模式测试：认证流 / 数据隔离 / 服务注册表 / SSRF 防护 / Fernet（全 mock 不出网）"""

import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex import mcp_registry
from kate_cortex.auth import (
    check_invite_code,
    hash_password,
    validate_username,
    verify_password,
)
from kate_cortex.config import is_multiuser
from kate_cortex.main import create_app

from test_mcp import AMAP_TOOLS

# 公网 IP 字面量（example.com）：SSRF 防护放行且不触发 DNS，离线确定
PUBLIC_MCP_URL = "https://93.184.216.34/mcp?key=k"


@pytest.fixture(autouse=True)
def clean_status_cache(monkeypatch):
    monkeypatch.setattr(mcp_registry, "_STATUS", {})


@pytest.fixture
def multi_env(tmp_path, monkeypatch):
    """启用多用户模式：数据目录指向测试临时目录，清掉单用户/桌面模式的凭据"""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("KATE_DATA_DIR", str(data_dir))
    for var in ("KATE_INVITE_CODE", "KATE_SECRET_KEY", "KATE_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return data_dir


def make_app(multi_env):
    return create_app()


def register(client: TestClient, username: str, password: str = "pass123", **kwargs):
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": password, **kwargs},
    )


class TestAuthFlow:
    def test_register_login_me_logout(self, multi_env):
        app = make_app(multi_env)
        client = TestClient(app)

        resp = register(client, "alice")
        assert resp.status_code == 201
        assert resp.json()["username"] == "alice"
        assert "kate_session" in resp.cookies

        # 注册即登录：me 返回当前用户
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "alice"

        # 登出后会话失效
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401

        # 重新登录恢复会话
        login = client.post(
            "/api/auth/login", json={"username": "alice", "password": "pass123"}
        )
        assert login.status_code == 200
        assert client.get("/api/auth/me").json()["username"] == "alice"

    def test_unauthenticated_api_rejected(self, multi_env):
        client = TestClient(make_app(multi_env))
        assert client.get("/api/entries").status_code == 401
        assert client.get("/api/settings").status_code == 401
        # health 豁免
        assert client.get("/api/health").status_code == 200

    def test_duplicate_username_case_insensitive(self, multi_env):
        app = make_app(multi_env)
        client = TestClient(app)
        assert register(client, "alice").status_code == 201
        assert register(client, "alice").status_code == 409
        assert register(client, "ALICE").status_code == 409

    def test_invalid_credentials_rejected(self, multi_env):
        client = TestClient(make_app(multi_env))
        # 用户名：过长/非法字符
        assert register(client, "a").status_code == 422
        assert register(client, "x" * 33).status_code == 422
        assert register(client, "空 格").status_code == 422
        # 密码过短
        assert register(client, "alice", password="12345").status_code == 422
        # 登录密码错误
        register(client, "bob")
        resp = client.post(
            "/api/auth/login", json={"username": "bob", "password": "wrong!"}
        )
        assert resp.status_code == 401

    def test_invite_code(self, multi_env, monkeypatch):
        monkeypatch.setenv("KATE_INVITE_CODE", "letmein")
        client = TestClient(make_app(multi_env))

        assert register(client, "alice").status_code == 403
        assert register(client, "alice", invite_code="wrong").status_code == 403
        assert register(client, "alice", invite_code="letmein").status_code == 201

    def test_invite_code_validation(self, monkeypatch):
        monkeypatch.delenv("KATE_INVITE_CODE", raising=False)
        assert check_invite_code(None) is None  # 未配置邀请码不需要
        assert check_invite_code("anything") is None


class TestSingleUserCompat:
    """单用户形态（桌面/dev/Vercel 试用）与新代码的兼容"""

    def test_health_reports_mode(self, multi_env, monkeypatch):
        client = TestClient(make_app(multi_env))
        assert client.get("/api/health").json()["mode"] == "multiuser"

        monkeypatch.delenv("KATE_DATA_DIR", raising=False)
        single = TestClient(create_app())
        assert single.get("/api/health").json()["mode"] == "single"

    def test_auth_routes_404_on_single_user(self, monkeypatch):
        monkeypatch.delenv("KATE_DATA_DIR", raising=False)
        client = TestClient(create_app())
        resp = client.post(
            "/api/auth/login", json={"username": "alice", "password": "pass123"}
        )
        assert resp.status_code == 404
        assert "单用户" in resp.json()["detail"]


class TestStaticHosting:
    def test_frontend_dir_served(self, multi_env, monkeypatch, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html><body>kate-web</body></html>", encoding="utf-8")
        monkeypatch.setenv("KATE_FRONTEND_DIR", str(dist))
        client = TestClient(make_app(multi_env))

        assert client.get("/").status_code == 200
        assert "kate-web" in client.get("/").text
        # API 未被遮蔽
        assert client.get("/api/health").status_code == 200


class TestUserIsolation:
    def test_entries_settings_mcp_isolated(self, multi_env, monkeypatch):
        app = make_app(multi_env)
        alice = TestClient(app)
        bob = TestClient(app)
        register(alice, "alice")
        register(bob, "bob")

        # alice 存条目、配 MCP、改设置
        alice.post(
            "/api/entries",
            json={"title": "alice 的私货", "content": "只有 alice 能看到"},
        )
        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda url: AMAP_TOOLS
        )
        resp = alice.post(
            "/api/mcp/servers", json={"name": "amap", "url": PUBLIC_MCP_URL}
        )
        assert resp.status_code == 201
        alice.put("/api/settings", json={"export_dir": "D:/alice-docs"})

        # bob 的世界是空的
        assert bob.get("/api/entries").json()["total"] == 0
        assert bob.get("/api/mcp/servers").json()["servers"] == []
        assert bob.get("/api/settings").json()["export_dir"] is None
        assert bob.get("/api/settings").json()["vault_path"] != alice.get(
            "/api/settings"
        ).json()["vault_path"]

    def test_registry_caches_services_per_user(self, multi_env):
        app = make_app(multi_env)
        client = TestClient(app)
        register(client, "alice")
        user_id = client.get("/api/auth/me").json()["id"]

        # 受保护路由触发服务构建（/api/auth/* 豁免，不构建）
        client.get("/api/settings")
        registry = app.state.registry
        assert user_id in registry._cache
        assert registry.get(user_id) is registry.get(user_id)

        # 每个用户独立的 vault 目录
        services = registry.get(user_id)
        assert multi_env in services.config.vault_path.parents
        assert user_id in services.config.vault_path.parts


class TestSsrfGuard:
    def test_private_url_rejected_in_multiuser(self, multi_env, monkeypatch):
        client = TestClient(make_app(multi_env))
        register(client, "alice")

        def no_connect(url):  # 防护应在真实连接前拦截
            raise AssertionError("不应发起连接")

        monkeypatch.setattr("kate_cortex.mcp_client.list_mcp_tools", no_connect)
        for url in (
            "http://127.0.0.1:9999/mcp",
            "http://localhost/mcp",
            "http://192.168.1.5/mcp",
            "http://[::1]/mcp",
        ):
            resp = client.post("/api/mcp/servers", json={"name": "x", "url": url})
            assert resp.status_code == 400, url
            assert "内网" in resp.json()["detail"]

    def test_public_url_passes_guard(self, multi_env, monkeypatch):
        client = TestClient(make_app(multi_env))
        register(client, "alice")
        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda url: AMAP_TOOLS
        )
        # 公网 IP 字面量：不触发 DNS，离线确定
        resp = client.post(
            "/api/mcp/servers",
            json={"name": "amap", "url": "https://93.184.216.34/mcp?key=k"},
        )
        assert resp.status_code == 201

    def test_allow_private_escape_hatch(self, multi_env, monkeypatch):
        monkeypatch.setenv("KATE_MCP_ALLOW_PRIVATE", "1")
        client = TestClient(make_app(multi_env))
        register(client, "alice")
        monkeypatch.setattr(
            "kate_cortex.mcp_client.list_mcp_tools", lambda url: AMAP_TOOLS
        )
        resp = client.post(
            "/api/mcp/servers", json={"name": "local", "url": "http://127.0.0.1:9000/mcp"}
        )
        assert resp.status_code == 201


class TestCryptoAndPrimitives:
    def test_password_hash_roundtrip(self):
        stored = hash_password("s3cret!")
        assert stored.startswith("scrypt$")
        assert verify_password("s3cret!", stored)
        assert not verify_password("wrong", stored)

    def test_username_validation(self):
        assert validate_username("小明-01") is None
        assert validate_username("a") is not None
        assert validate_username("has space") is not None

    def test_fernet_decrypt(self, monkeypatch):
        pytest.importorskip("cryptography")
        from cryptography.fernet import Fernet

        monkeypatch.setenv("KATE_SECRET_KEY", "deploy-secret")
        key = base64.urlsafe_b64encode(hashlib.sha256(b"deploy-secret").digest())
        token = (
            "fernet:"
            + Fernet(key).encrypt("sk-my-api-key".encode("utf-8")).decode("ascii")
        )
        from kate_cortex.security import decrypt_secret

        assert decrypt_secret(token) == "sk-my-api-key"

    def test_fernet_decrypt_requires_key(self, monkeypatch):
        pytest.importorskip("cryptography")
        from cryptography.fernet import Fernet

        monkeypatch.delenv("KATE_SECRET_KEY", raising=False)
        key = base64.urlsafe_b64encode(hashlib.sha256(b"k").digest())
        token = "fernet:" + Fernet(key).encrypt(b"x").decode("ascii")
        from kate_cortex.security import decrypt_secret

        with pytest.raises(RuntimeError):
            decrypt_secret(token)

    def test_is_multiuser(self, monkeypatch, tmp_path):
        monkeypatch.delenv("KATE_DATA_DIR", raising=False)
        assert is_multiuser() is False
        monkeypatch.setenv("KATE_DATA_DIR", str(tmp_path))
        assert is_multiuser() is True

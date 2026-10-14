"""全局速记端点测试（CAPTURE_PLAN.md）"""

import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, ProviderError, TextDelta
from kate_cortex.providers.fake import FakeProvider


def _enrich_round(keywords=None, importance=4, collection="灵感"):
    payload = {
        "keywords": keywords or ["速记", "灵感", "想法"],
        "importance": importance,
        "collection": collection,
    }
    return [TextDelta(json.dumps(payload, ensure_ascii=False)), Done("stop")]


@pytest.fixture
def client(env):
    return TestClient(create_app(Config(vault_path=env.vault_path, db_path=env.db_path)))


class TestCapture:
    def test_capture_creates_and_enriches_inline(self, client):
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_enrich_round()]
        )

        resp = client.post(
            "/api/capture",
            json={"text": "Monday 例会要演示新原型\n记得带上次的用户反馈笔记"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["enriched"] is True
        assert body["title"] == "Monday 例会要演示新原型"
        assert body["keywords"] == ["速记", "灵感", "想法"]
        assert body["importance"] == 4 and body["collection"] == "灵感"

        entry = client.get(f"/api/entries/{body['entry_id']}").json()
        assert entry["source"] == "manual"
        assert entry["content"].startswith("Monday 例会要演示新原型")

    def test_title_truncated_to_40_chars(self, client):
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_enrich_round()]
        )
        long_line = "超" * 60

        body = client.post("/api/capture", json={"text": f"{long_line}\n正文"}).json()

        assert body["title"] == "超" * 40

    def test_provider_missing_still_saves_entry(self, client):
        def broken(name, model=None):
            raise ProviderError("未配置 glm 的 API key")

        client.app.state.provider_factory = broken

        resp = client.post("/api/capture", json={"text": "先记下来再说"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["enriched"] is False
        assert "未配置" in body["hint"]
        assert client.get(f"/api/entries/{body['entry_id']}").status_code == 200

    def test_bad_llm_output_still_saves_entry(self, client):
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[[TextDelta("这不是 JSON"), Done("stop")]]
        )

        body = client.post("/api/capture", json={"text": "随便记点"}).json()

        assert body["enriched"] is False
        assert "无法解析" in body["hint"]
        entry = client.get(f"/api/entries/{body['entry_id']}").json()
        assert entry["title"] == "随便记点"

    def test_blank_text_rejected(self, client):
        assert client.post("/api/capture", json={"text": "   "}).status_code == 422

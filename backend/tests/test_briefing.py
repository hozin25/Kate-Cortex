"""每日简报测试（BRIEFING_PLAN.md §4）"""

import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.briefing import get_briefing, static_briefing
from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, ProviderError, TextDelta
from kate_cortex.providers.fake import FakeProvider
from kate_cortex.settings import SettingsService


def _briefing_round(entry_id="kc_1", **item_extra):
    payload = {
        "greeting": "早上好，主人。",
        "items": [
            {"kind": "due", "text": "今天 10:00 有复诊", "entry_id": entry_id},
            {"kind": "followup", "text": "感冒刚好，注意保暖", "entry_id": entry_id},
        ],
    }
    payload["items"][0].update(item_extra)
    return [TextDelta(json.dumps(payload, ensure_ascii=False)), Done("stop")]


def _memory(storage, title="复诊提醒", content="10月14日 上午去医院复诊。"):
    return storage.create_entry(
        title=title,
        source="chat",
        content=content,
        collections=["记忆"],
        keywords=["复诊", "健康"],
        importance=4,
    )


@pytest.fixture
def settings_of(storage):
    return SettingsService(storage.conn)


class TestGetBriefing:
    def test_generates_and_validates_items(self, storage, settings_of):
        entry = _memory(storage)
        fake = FakeProvider(rounds=[_briefing_round(entry_id=entry.id)])

        result = get_briefing(storage, settings_of, fake)

        assert result["greeting"] == "早上好，主人。"
        assert [i["kind"] for i in result["items"]] == ["due", "followup"]
        assert result["items"][0]["entry_id"] == entry.id
        assert result["cached"] is False
        assert len(fake.calls) == 1

    def test_unknown_entry_id_stripped(self, storage, settings_of):
        _memory(storage)
        fake = FakeProvider(rounds=[_briefing_round(entry_id="kc_not_exist")])

        result = get_briefing(storage, settings_of, fake)

        assert result["items"][0]["entry_id"] is None

    def test_same_day_cache_no_second_call(self, storage, settings_of):
        _memory(storage)
        fake = FakeProvider(rounds=[_briefing_round(), _briefing_round()])
        get_briefing(storage, settings_of, fake)

        second = get_briefing(storage, settings_of, fake)

        assert second["cached"] is True
        assert len(fake.calls) == 1

    def test_refresh_forces_regeneration(self, storage, settings_of):
        _memory(storage)
        fake = FakeProvider(rounds=[_briefing_round(), _briefing_round()])
        get_briefing(storage, settings_of, fake)

        result = get_briefing(storage, settings_of, fake, refresh=True)

        assert result["cached"] is False
        assert len(fake.calls) == 2

    def test_no_memories_static_no_llm(self, storage, settings_of):
        fake = FakeProvider(rounds=[_briefing_round()])

        result = get_briefing(storage, settings_of, fake)

        assert result == {**static_briefing(), "cached": False}
        assert len(fake.calls) == 0

    def test_llm_failure_raises(self, storage, settings_of):
        _memory(storage)
        fake = FakeProvider(rounds=[[RuntimeError("upstream boom")]])

        with pytest.raises(Exception):
            get_briefing(storage, settings_of, fake)

    def test_bad_json_raises(self, storage, settings_of):
        _memory(storage)
        fake = FakeProvider(rounds=[[TextDelta("今天没什么事"), Done("stop")]])

        with pytest.raises(Exception):
            get_briefing(storage, settings_of, fake)


class TestBriefingApi:
    @pytest.fixture
    def client(self, env):
        app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
        return TestClient(app)

    def _seed_memory(self, client):
        resp = client.post(
            "/api/entries",
            json={
                "title": "复诊提醒",
                "source": "chat",
                "content": "10月14日 上午去医院复诊。",
                "collections": ["记忆"],
                "keywords": ["复诊"],
                "importance": 4,
            },
        )
        return resp.json()["id"]

    def test_briefing_roundtrip_and_cache(self, client):
        entry_id = self._seed_memory(client)
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_briefing_round(entry_id=entry_id), _briefing_round(entry_id=entry_id)]
        )

        first = client.get("/api/briefing").json()
        assert first["cached"] is False and len(first["items"]) == 2

        second = client.get("/api/briefing").json()
        assert second["cached"] is True

        refreshed = client.get("/api/briefing", params={"refresh": "true"}).json()
        assert refreshed["cached"] is False

    def test_memory_disabled_static(self, client):
        self._seed_memory(client)
        client.put("/api/settings", json={"memory_enabled": False})
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_briefing_round()]
        )

        result = client.get("/api/briefing").json()

        assert result["items"] == []
        assert result["greeting"] == "主人在。今天有什么吩咐？"

    def test_provider_error_400(self, client):
        self._seed_memory(client)

        def broken(name, model=None):
            raise ProviderError("未配置 glm 的 API key")

        client.app.state.provider_factory = broken
        assert client.get("/api/briefing").status_code == 400

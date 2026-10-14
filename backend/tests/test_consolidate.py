"""记忆巩固引擎测试（CONSOLIDATE_PLAN.md §7）"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.consolidator import (
    ARCHIVE_COLLECTION,
    adjust_importance,
    archive_stale,
    consolidate_pass,
    log_prune_hits,
    recall_stats,
)
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, ProviderError, TextDelta
from kate_cortex.providers.fake import FakeProvider
from kate_cortex.settings import SettingsService

NOW = datetime.now().astimezone()


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _memory(storage, title="感冒了", content="感冒了，在吃感冒灵。", **kwargs):
    return storage.create_entry(
        title=title,
        source="chat",
        content=content,
        collections=kwargs.pop("collections", ["记忆"]),
        keywords=kwargs.pop("keywords", ["感冒", "健康"]),
        importance=kwargs.pop("importance", 3),
        **kwargs,
    )


def _backdate(storage, entry, days_ago: int):
    """把条目 created_at 改到 days_ago 天前（frontmatter 是事实源）"""
    found = storage.get_entry(entry.id)
    md = storage.vault / found.file_path
    md.write_text(
        md.read_text(encoding="utf-8").replace(found.created_at, _iso(days_ago)),
        encoding="utf-8",
    )


def _hits(storage, entry_id, count: int, days_ago: int = 1):
    with storage.conn:
        storage.conn.executemany(
            "INSERT INTO memory_hits (entry_id, recalled_at, source) VALUES (?, ?, ?)",
            [(entry_id, _iso(days_ago), "recall")] * count,
        )


def _judge_round(verdict="duplicate", **extra):
    payload = {
        "verdict": verdict,
        "merged_title": "日语学习：通过 N3",
        "merged_content": "2026-03 开始学日语，2026-09 通过 N3。",
        "keywords": ["日语", "学习"],
        "importance": 4,
        "reason": "同一事实的进展",
    }
    payload.update(extra)
    return [TextDelta(json.dumps(payload, ensure_ascii=False)), Done("stop")]


_PROFILE_EMPTY = [TextDelta('{"updates": [], "creates": []}'), Done("stop")]


@pytest.fixture
def settings_of(storage):
    return SettingsService(storage.conn)


class TestAdjustImportance:
    def test_promote_on_frequent_recall(self, storage):
        entry = _memory(storage, importance=3)
        _hits(storage, entry.id, count=3, days_ago=5)

        actions = adjust_importance(storage, NOW)

        assert len(actions) == 1 and actions[0]["to"] == 4
        assert storage.get_entry(entry.id).importance == 4

    def test_decay_by_staleness(self, storage):
        entry = _memory(storage, importance=4)
        _backdate(storage, entry, days_ago=120)

        actions = adjust_importance(storage, NOW)

        assert actions[0]["to"] == 2  # >90d cap 2
        entry2 = _memory(storage, title="旧事", importance=5)
        _backdate(storage, entry2, days_ago=200)
        actions = adjust_importance(storage, NOW)
        assert actions[0]["to"] == 1  # >180d cap 1

    def test_idempotent_no_repeat_write(self, storage):
        entry = _memory(storage, importance=3)
        _backdate(storage, entry, days_ago=120)

        first = adjust_importance(storage, NOW)
        second = adjust_importance(storage, NOW)

        assert first and not second  # 目标已达成，第二轮不再写

    def test_skip_entries_without_importance(self, storage):
        entry = storage.create_entry(
            title="未加工", source="import", content="x", collections=["记忆"]
        )
        assert adjust_importance(storage, NOW) == []
        assert storage.get_entry(entry.id).importance is None


class TestArchive:
    def test_stale_low_importance_archived(self, storage):
        entry = _memory(storage, importance=2)
        _backdate(storage, entry, days_ago=200)
        pre = {entry.id: 2}

        actions = archive_stale(storage, NOW, pre)

        assert [a["entry_id"] for a in actions] == [entry.id]
        archived = storage.get_entry(entry.id)
        assert ARCHIVE_COLLECTION in archived.collections
        assert "记忆" not in archived.collections

    def test_recently_important_not_archived_even_after_decay(self, storage):
        entry = _memory(storage, importance=4)
        _backdate(storage, entry, days_ago=200)
        pre = {entry.id: 4}  # 调整前重要；本轮衰减到 1 但不归档

        adjust_importance(storage, NOW)
        actions = archive_stale(storage, NOW, pre)

        assert actions == []
        assert storage.get_entry(entry.id).collections == ["记忆"]


class TestHits:
    def test_stats_and_prune(self, storage):
        entry = _memory(storage)
        _hits(storage, entry.id, count=2, days_ago=3)
        with storage.conn:
            storage.conn.execute(
                "INSERT INTO memory_hits (entry_id, recalled_at, source) VALUES (?, ?, ?)",
                (entry.id, _iso(300), "recall"),
            )

        stats = recall_stats(storage)
        assert stats[entry.id]["hits"] == 3

        pruned = log_prune_hits(storage, NOW)
        assert pruned == 1
        assert recall_stats(storage)[entry.id]["hits"] == 2


class TestConsolidatePass:
    def test_duplicate_auto_merged_and_undoable(self, vector_storage, settings_of):
        storage, _ = vector_storage
        old = storage.create_entry(
            title="感冒了",
            source="chat",
            content="2026-09-01 感冒了，在吃感冒灵，注意保暖。",
            collections=["记忆"],
            keywords=["感冒"],
            importance=3,
        )
        _backdate(storage, old, days_ago=30)
        new = storage.create_entry(
            title="感冒好了",
            source="chat",
            content="感冒已经好了，感冒灵吃完了，不用再保暖。",
            collections=["记忆"],
            keywords=["感冒"],
            importance=3,
        )
        fake = FakeProvider(rounds=[_judge_round("update"), _PROFILE_EMPTY])

        result = consolidate_pass(storage, settings_of, fake, limit=6)

        assert len(result["merged"]) == 1
        assert result["merged"][0]["trashed_id"] == new.id  # 保留较早条目
        assert result["done"] and result["remaining"] == 0
        kept = storage.get_entry(old.id)
        kept_title = json.loads(_judge_round()[0].text)["merged_title"]
        assert kept.title == kept_title
        assert kept.importance == 4
        assert "感冒" in kept.keywords and "日语" in kept.keywords
        assert storage._find_row(new.id) is None  # 较新条目已进 .trash
        report = settings_of.get_all()["consolidation_report"]
        assert report["merged"][0]["trashed_id"] == new.id

        # 撤销：恢复被合并条目
        restored = storage.restore_entry(new.id)
        assert storage.get_entry(restored.id) is not None

    def test_conflict_goes_to_proposal(self, vector_storage, settings_of):
        storage, _ = vector_storage
        a = _memory(storage, title="感冒不能喝酒", content="感冒期间绝对不能喝酒，会加重病情。")
        b = _memory(storage, title="感冒能喝酒", content="感冒了喝点酒发发汗就好了。")
        fake = FakeProvider(rounds=[_judge_round("conflict"), _PROFILE_EMPTY])

        result = consolidate_pass(storage, settings_of, fake, limit=6)

        assert result["conflicts_queued"] == 1 and result["merged"] == []
        proposals = settings_of.get_all()["consolidation_proposals"]
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal["kind"] == "conflict"
        assert {proposal["a"]["id"], proposal["b"]["id"]} == {a.id, b.id}
        assert proposal["a"]["content"] and proposal["b"]["content"]

    def test_distinct_cached_second_pass_no_pair_call(self, vector_storage, settings_of):
        storage, _ = vector_storage
        _memory(storage, title="感冒了", content="感冒了，在吃感冒灵。")
        _memory(storage, title="又感冒了", content="这次感冒比较重，继续吃感冒灵。")
        fake = FakeProvider(rounds=[_judge_round("distinct"), _PROFILE_EMPTY])
        consolidate_pass(storage, settings_of, fake, limit=6)

        fake2 = FakeProvider(rounds=[_judge_round(), _PROFILE_EMPTY])
        result = consolidate_pass(storage, settings_of, fake2, limit=6)

        assert result["merged"] == []
        # 第二轮零 LLM 调用：distinct 对已被缓存跳过，也没有新记忆触发画像维护
        assert len(fake2.calls) == 0

    def test_profile_proposal_created(self, storage, settings_of):
        _memory(storage, title="对芒果过敏", content="确诊对芒果过敏，以后要避开。")
        payload = json.dumps(
            {
                "updates": [],
                "creates": [
                    {
                        "title": "过敏原",
                        "content": "对芒果过敏（2026-09 确诊），需终身规避。",
                        "reason": "持久健康事实",
                    }
                ],
            },
            ensure_ascii=False,
        )
        fake = FakeProvider(rounds=[[TextDelta(payload), Done("stop")]])

        result = consolidate_pass(storage, settings_of, fake, limit=6)

        assert result["profile_proposals"] == 1
        proposal = settings_of.get_all()["consolidation_proposals"][-1]
        assert proposal["kind"] == "profile_create"
        # 无向量 → 配对阶段整体跳过，仍 done
        assert result["done"]


class TestConsolidateApi:
    @pytest.fixture
    def client(self, env):
        app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
        # 注入确定性向量（默认 embedder 因缺 key 不可用；配对阶段只用已存向量，不调 API）
        from kate_cortex.providers.embedding import FakeEmbedder

        app.state.storage.vectors.embedder_factory = lambda: FakeEmbedder(
            clusters={"生活健康": ["感冒", "保暖", "健康"]}
        )
        return TestClient(app)

    def _seed_pair(self, client):
        # 同语义簇的两条记忆（FakeEmbedder 簇向量 sim≈0.99）
        for title, content in [
            ("感冒了要注意保暖", "感冒了，在吃感冒灵，医生叮嘱注意保暖。"),
            ("又感冒了", "这次感冒比较重，继续吃感冒灵，注意保暖别出门。"),
        ]:
            resp = client.post(
                "/api/entries",
                json={
                    "title": title,
                    "source": "chat",
                    "content": content,
                    "collections": ["记忆"],
                    "keywords": ["感冒"],
                    "importance": 3,
                },
            )
            assert resp.status_code == 201, resp.text

    def test_status_and_run(self, client):
        self._seed_pair(client)
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_judge_round("distinct"), _PROFILE_EMPTY]
        )

        status = client.get("/api/consolidate/status").json()
        assert status["vector_available"] is True
        assert status["candidates"] == 1

        run = client.post("/api/consolidate/run", json={"limit": 6}).json()
        assert run["done"] is True
        assert run["report"]["ran_at"]

        status2 = client.get("/api/consolidate/status").json()
        assert status2["candidates"] == 0  # distinct 已缓存
        assert status2["consolidated_at"] is not None

    def test_proposal_accept_and_dismiss(self, client):
        self._seed_pair(client)
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_judge_round("conflict"), _PROFILE_EMPTY]
        )
        client.post("/api/consolidate/run", json={})

        proposal = client.get("/api/consolidate/status").json()["proposals"][0]

        # 忽略
        resp = client.delete(f"/api/consolidate/proposals/{proposal['id']}")
        assert resp.status_code == 200
        assert client.get("/api/consolidate/status").json()["proposals"] == []

        # 再造一个 conflict，accept keep="a"（保留较早，删较晚）
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_judge_round("conflict"), _PROFILE_EMPTY]
        )
        # distinct 已缓存？conflict 之前没缓存（提案被删后 pair 不在 pending，
        # 但 judged 里也没有——conflict 不进 judged，可重新判定）
        client.post("/api/consolidate/run", json={})
        proposal = client.get("/api/consolidate/status").json()["proposals"][0]
        resp = client.post(
            f"/api/consolidate/proposals/{proposal['id']}/accept", json={"keep": "a"}
        )
        assert resp.status_code == 200
        kept_id = proposal["a"]["id"]
        dropped_id = proposal["b"]["id"]
        assert client.get(f"/api/entries/{kept_id}").status_code == 200
        assert client.get(f"/api/entries/{dropped_id}").status_code == 404
        assert client.get("/api/consolidate/status").json()["proposals"] == []

    def test_undo_restore(self, client):
        resp = client.post(
            "/api/entries",
            json={"title": "待删", "source": "manual", "content": "x"},
        )
        entry_id = resp.json()["id"]
        assert client.delete(f"/api/entries/{entry_id}").status_code == 204

        undo = client.post(f"/api/consolidate/undo/{entry_id}")
        assert undo.status_code == 200
        assert client.get(f"/api/entries/{entry_id}").status_code == 200

    def test_accept_profile_create(self, client):
        from kate_cortex.consolidator import _proposal_id

        client.app.state.settings_service.update(
            {
                "consolidation_proposals": [
                    {
                        "id": _proposal_id(),
                        "kind": "profile_create",
                        "created_at": _iso(0),
                        "title": "过敏原",
                        "content": "对芒果过敏（2026-09 确诊）。",
                        "reason": "持久健康事实",
                    }
                ]
            }
        )
        proposal = client.app.state.settings_service.get_all()[
            "consolidation_proposals"
        ][0]

        resp = client.post(
            f"/api/consolidate/proposals/{proposal['id']}/accept", json={}
        )

        assert resp.status_code == 200
        profile = client.get("/api/entries", params={"collection": "个人信息"}).json()
        assert profile["total"] == 1
        assert profile["items"][0]["title"] == "过敏原"
        assert client.get("/api/consolidate/status").json()["proposals"] == []

    def test_provider_error_400(self, client):
        def broken(name, model=None):
            raise ProviderError("未配置 glm 的 API key")

        client.app.state.provider_factory = broken
        resp = client.post("/api/consolidate/run", json={})
        assert resp.status_code == 400

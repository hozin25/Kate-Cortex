"""导入加工流水线测试（IMPORT_ENRICH_PLAN.md §7）"""

import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.enrich import EnrichError, enrich_batch
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, ProviderError, TextDelta
from kate_cortex.providers.fake import FakeProvider


def _json_round(keywords=None, importance=3, collection=""):
    payload = '{"keywords": %s, "importance": %s, "collection": "%s"}' % (
        json.dumps(keywords or ["感冒", "健康", "保暖"], ensure_ascii=False),
        importance,
        collection,
    )
    return [TextDelta(payload), Done("stop")]


def _import_entry(storage, **overrides):
    payload = dict(
        title="三亚海鲜避坑攻略",
        source="import",
        content="第一市场买海鲜要盯秤，避开拉客的。十一期间人多，建议早去。",
    )
    payload.update(overrides)
    return storage.create_entry(**payload)


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    return TestClient(app)


class TestSelection:
    def test_only_pending_import_entries_processed(self, storage):
        pending = _import_entry(storage)  # import + 无字段 → 加工
        _import_entry(  # import + 字段齐全 → 不动
            storage,
            title="已有字段",
            keywords=["旅行"],
            importance=2,
        )
        manual = storage.create_entry(  # manual 来源 → 不动
            title="手动条目", source="manual", content="随手记"
        )
        fake = FakeProvider(rounds=[_json_round(collection="旅行")])

        result = enrich_batch(storage, fake, limit=10)

        assert [item.entry_id for item in result.enriched] == [pending.id]
        assert result.remaining == 0
        assert fake.calls[0]["messages"][0]["content"].startswith(
            "你在给个人知识库的一条导入条目生成检索元数据"
        )
        enriched = storage.get_entry(pending.id)
        assert enriched.keywords == ["感冒", "健康", "保暖"]
        assert enriched.importance == 3
        untouched = storage.get_entry(manual.id)
        assert untouched.keywords == []

    def test_batch_limit_and_idempotent(self, storage):
        first = _import_entry(storage, title="条目一")
        second = _import_entry(storage, title="条目二")
        third = _import_entry(storage, title="条目三")
        fake = FakeProvider(rounds=[_json_round()] * 3)

        batch1 = enrich_batch(storage, fake, limit=2)
        assert batch1.processed == 2
        assert batch1.remaining == 1

        batch2 = enrich_batch(storage, fake, limit=2)
        assert batch2.processed == 1
        assert batch2.remaining == 0 and batch2.as_dict()["done"]

        rerun = enrich_batch(storage, FakeProvider(rounds=[_json_round()]), limit=8)
        assert rerun.processed == 0 and rerun.remaining == 0 and rerun.as_dict()["done"]
        assert {first.id, second.id, third.id} <= {
            item.entry_id for item in [*batch1.enriched, *batch2.enriched]
        }

    def test_system_collections_excluded_from_suggestion(self, storage):
        # 「记忆」已存在（生活记忆合集）也不能出现在建议列表里——
        # 知识文档混进记忆合集会污染常驻注入
        storage.create_entry(
            title="已有记忆",
            source="chat",
            content="x",
            collections=["记忆"],
            keywords=["x"],
            importance=3,
        )
        entry = _import_entry(storage)
        fake = FakeProvider(rounds=[_json_round(collection="旅行")])

        enrich_batch(storage, fake, limit=8)

        prompt = fake.calls[0]["messages"][0]["content"]
        assert "现有合集列表：（空）" in prompt  # 「记忆」被过滤后列表为空
        assert "严禁选择" in prompt
        assert storage.get_entry(entry.id).collections == ["旅行"]

    def test_md_file_updated(self, storage, env):
        entry = _import_entry(storage)
        enrich_batch(storage, FakeProvider(rounds=[_json_round(importance=4)]), limit=8)
        md = (env.vault_path / storage.get_entry(entry.id).file_path).read_text(
            encoding="utf-8"
        )
        assert "importance: 4" in md
        assert "感冒" in md


class TestPartialFields:
    def test_existing_keywords_preserved_when_only_importance_missing(self, storage):
        entry = _import_entry(storage, keywords=["旅行", "美食"], importance=None)
        fake = FakeProvider(rounds=[_json_round(keywords=["不该出现"], importance=5)])

        result = enrich_batch(storage, fake, limit=8)

        assert result.processed == 1
        prompt = fake.calls[0]["messages"][0]["content"]
        assert "keywords：3-8" not in prompt
        assert "importance：1-5" in prompt
        enriched = storage.get_entry(entry.id)
        assert enriched.keywords == ["旅行", "美食"]  # 原值保留
        assert enriched.importance == 5

    def test_bad_importance_skipped_but_keywords_written(self, storage):
        entry = _import_entry(storage)
        bad = '{"keywords": ["感冒", "健康"], "importance": "重要"}'
        fake = FakeProvider(
            rounds=[
                [TextDelta(bad), Done("stop")],
                _json_round(importance=4),  # 下批只补 importance
            ]
        )

        batch1 = enrich_batch(storage, fake, limit=8)
        assert batch1.processed == 0
        assert any("importance 无法解析" in s for s in batch1.skipped)
        # keywords 已写回（部分成功），条目仍待加工（importance 缺失）
        assert storage.get_entry(entry.id).keywords == ["感冒", "健康"]
        assert batch1.remaining == 1

        batch2 = enrich_batch(storage, fake, limit=8)
        assert batch2.processed == 1
        assert "keywords：3-8" not in fake.calls[-1]["messages"][0]["content"]
        assert storage.get_entry(entry.id).importance == 4

    def test_unparseable_output_skipped_and_retryable(self, storage):
        entry = _import_entry(storage)
        fake = FakeProvider(rounds=[[TextDelta("我觉得这条挺重要的"), Done("stop")]])

        result = enrich_batch(storage, fake, limit=8)

        assert result.processed == 0
        assert result.remaining == 1
        assert any("无法解析" in s for s in result.skipped)
        assert storage.get_entry(entry.id).keywords == []


class TestCollections:
    def test_suggestion_applied_and_existing_collection_reused(self, storage):
        storage.create_collection("旅行")
        entry = _import_entry(storage)
        fake = FakeProvider(rounds=[_json_round(collection="旅行")])

        result = enrich_batch(storage, fake, limit=8)

        assert result.enriched[0].collection == "旅行"
        assert storage.get_entry(entry.id).collections == ["旅行"]
        assert storage.list_collections() == [("旅行", 1)]

    def test_new_collection_created(self, storage):
        entry = _import_entry(storage)
        enrich_batch(
            storage, FakeProvider(rounds=[_json_round(collection="美食")]), limit=8
        )
        assert storage.get_entry(entry.id).collections == ["美食"]

    def test_entry_with_collections_untouched(self, storage):
        entry = _import_entry(
            storage, keywords=["旅行"], importance=2, collections=["美食"]
        )
        _import_entry(storage)  # 让它有待加工条目，但断言对象是上面这条
        fake = FakeProvider(rounds=[_json_round(collection="旅行")])

        enrich_batch(storage, fake, limit=8)

        assert storage.get_entry(entry.id).collections == ["美食"]

    def test_no_collection_needed_when_placeholder_empty(self, storage):
        entry = _import_entry(storage)
        enrich_batch(storage, FakeProvider(rounds=[_json_round(collection="")]), limit=8)
        assert storage.get_entry(entry.id).collections == []


class TestDuplicates:
    def test_semantic_duplicate_marked_not_merged(self, vector_storage):
        storage, _index = vector_storage
        keep = storage.create_entry(
            title="感冒了要注意保暖",
            source="import",
            keywords=["感冒", "健康"],
            importance=3,
            content="感冒了，在吃感冒灵，医生叮嘱注意保暖。",
        )
        pending = _import_entry(
            storage,
            title="又感冒了",
            content="这次感冒比较重，继续吃感冒灵，注意保暖别出门。",
        )
        fake = FakeProvider(rounds=[_json_round(collection="健康")])

        result = enrich_batch(storage, fake, limit=8)

        assert result.processed == 1
        duplicates = result.enriched[0].duplicates
        assert [d["entry_id"] for d in duplicates] == [keep.id]
        # 同簇文本 0.9 簇基 + 0.1 噪声混合，相似度 ~0.99（非 1.0）
        assert duplicates[0]["similarity"] >= 0.9
        # 只标记：两条都在，未合并
        assert storage.get_entry(keep.id) is not None
        assert storage.get_entry(pending.id) is not None


class TestProviderFailure:
    def test_stream_error_aborts_batch(self, storage):
        _import_entry(storage, title="条目一")
        _import_entry(storage, title="条目二")
        fake = FakeProvider(
            rounds=[_json_round(), [RuntimeError("upstream boom")]]
        )

        with pytest.raises(EnrichError):
            enrich_batch(storage, fake, limit=8)

    def test_missing_file_skipped_not_fatal(self, storage, env):
        entry = _import_entry(storage)
        (env.vault_path / storage.get_entry(entry.id).file_path).unlink()
        result = enrich_batch(storage, FakeProvider(rounds=[[_json_round()]]), limit=8)
        assert result.processed == 0
        assert any("文件缺失" in s for s in result.skipped)


class TestEnrichApi:
    def test_enrich_loop_via_api(self, client):
        client.post(
            "/api/entries",
            json={
                "title": "三亚海鲜避坑攻略",
                "source": "import",
                "content": "第一市场买海鲜要盯秤。",
            },
        )
        client.app.state.provider_factory = lambda name, model=None: FakeProvider(
            rounds=[_json_round(importance=4, collection="旅行")]
        )

        resp = client.post("/api/import/enrich", json={"limit": 8})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["processed"] == 1 and body["done"] and body["remaining"] == 0
        item = body["enriched"][0]
        assert item["keywords"] == ["感冒", "健康", "保暖"]
        assert item["importance"] == 4 and item["collection"] == "旅行"

        # 幂等：没有待加工条目时再次调用
        resp2 = client.post("/api/import/enrich", json={})
        assert resp2.json()["processed"] == 0 and resp2.json()["done"]

    def test_default_limit_without_payload(self, client):
        client.app.state.provider_factory = lambda name, model=None: FakeProvider()
        assert client.post("/api/import/enrich", json={}).status_code == 200

    def test_provider_error_returns_400(self, client):
        def broken_factory(name, model=None):
            raise ProviderError("未配置 glm 的 API key，请先到设置页填写")

        client.app.state.provider_factory = broken_factory
        resp = client.post("/api/import/enrich", json={})
        assert resp.status_code == 400
        assert "未配置" in resp.json()["detail"]

    def test_limit_validation(self, client):
        client.app.state.provider_factory = lambda name, model=None: FakeProvider()
        assert client.post("/api/import/enrich", json={"limit": 0}).status_code == 422
        assert client.post("/api/import/enrich", json={"limit": 25}).status_code == 422


class TestEnrichSetting:
    def test_roundtrip(self, client):
        resp = client.put("/api/settings", json={"import_enrich": False})
        assert resp.status_code == 200
        assert resp.json()["import_enrich"] is False
        resp = client.put("/api/settings", json={"import_enrich": True})
        assert resp.json()["import_enrich"] is True

    def test_default_on(self, client):
        assert client.get("/api/settings").json()["import_enrich"] is True

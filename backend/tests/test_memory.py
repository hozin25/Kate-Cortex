"""记忆机制单测：打分检索 / 常驻注入 / save_memory 工具 handler"""

from datetime import datetime, timedelta

import pytest

from kate_cortex.chat.memory import (
    KEYWORD_WEIGHT,
    MEMORY_COLLECTION,
    WEEK_BONUS,
    MemorySnippet,
    _recency_bonus,
    _score,
    list_memories,
    recall,
    resident_memories,
)
from kate_cortex.skills.memory import recall_memory, save_memory


def _snippet(**overrides) -> MemorySnippet:
    defaults = dict(
        entry_id="kc_20260830_001",
        title="感冒了",
        content="8月30日感冒，在吃感冒灵，注意保暖",
        keywords=["感冒", "健康", "保暖", "出行"],
        importance=3,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    defaults.update(overrides)
    return MemorySnippet(**defaults)


def _iso(days_ago: int) -> str:
    return (
        (datetime.now().astimezone() - timedelta(days=days_ago))
        .isoformat(timespec="seconds")
    )


class TestScore:
    def test_keyword_overlap_is_main_signal(self):
        now = datetime.now().astimezone()
        fresh = _snippet(created_at=_iso(1))
        assert _score(fresh, ["出行", "健康"], now) == pytest.approx(
            2 * KEYWORD_WEIGHT + 3 * 0.5 + WEEK_BONUS
        )

    def test_zero_overlap_scores_zero(self):
        assert _score(_snippet(), ["做饭", "菜谱"], datetime.now().astimezone()) == 0.0

    def test_keyword_containment_matches(self):
        """「感冒药」能命中关键词「感冒」（包含关系双向）"""
        now = datetime.now().astimezone()
        assert _score(_snippet(), ["感冒药"], now) > 0

    def test_title_and_content_also_match(self):
        now = datetime.now().astimezone()
        no_kw = _snippet(keywords=[])
        assert _score(no_kw, ["感冒"], now) > 0

    def test_recency_bonus_boundaries(self):
        now = datetime.now().astimezone()
        assert _recency_bonus(_iso(3), now) == WEEK_BONUS
        assert _recency_bonus(_iso(10), now) == 1.0
        assert _recency_bonus(_iso(60), now) == 0.0
        assert _recency_bonus("not-a-date", now) == 0.0


class TestSaveMemoryHandler:
    def test_creates_memory_entry_in_memory_collection(self, storage):
        result = save_memory(
            storage,
            {
                "title": "感冒了",
                "content": "8月30日感冒，在吃感冒灵，注意保暖",
                "keywords": ["感冒", "健康", "保暖", "出行"],
                "importance": 4,
            },
            conversation_id="kc_conv_abc",
        )

        assert result["replaced"] is False
        assert result["keywords"] == ["感冒", "健康", "保暖", "出行"]
        entry = storage.get_entry(result["entry_id"])
        assert entry.collections == [MEMORY_COLLECTION]
        assert entry.source == "chat"
        assert entry.conversation_id == "kc_conv_abc"
        assert entry.importance == 4

    def test_defaults_importance_to_three(self, storage):
        result = save_memory(
            storage, {"title": "x", "content": "y", "keywords": ["z"]}, "kc_conv_abc"
        )
        assert storage.get_entry(result["entry_id"]).importance == 3

    def test_replaces_updates_instead_of_duplicating(self, storage):
        first = save_memory(
            storage,
            {
                "title": "感冒了",
                "content": "8月30日感冒，注意保暖",
                "keywords": ["感冒", "健康"],
            },
            "kc_conv_abc",
        )
        second = save_memory(
            storage,
            {
                "title": "感冒已痊愈",
                "content": "9月2日感冒好了",
                "keywords": ["感冒", "健康"],
                "replaces_entry_id": first["entry_id"],
            },
            "kc_conv_abc",
        )

        assert second["replaced"] is True
        assert second["entry_id"] == first["entry_id"]
        assert len(list_memories(storage)) == 1
        entry = storage.get_entry(first["entry_id"])
        assert entry.title == "感冒已痊愈"
        assert "感冒好了" in entry.content


class TestRecall:
    def test_cross_topic_recall_via_scenario_keywords(self, storage):
        """核心场景：昨天记「感冒」，今天问「出去玩」——检索词与记忆关键词
        在「出行/健康」场景空间相遇（字面无交集也能召回）"""
        save_memory(
            storage,
            {
                "title": "感冒了",
                "content": "8月30日感冒，在吃感冒灵，注意保暖",
                "keywords": ["感冒", "健康", "保暖", "出行"],
                "importance": 4,
            },
            "kc_conv_abc",
        )

        result = recall_memory(storage, {"query": "周末想去户外玩", "keywords": ["出行", "天气"]})

        assert len(result["memories"]) == 1
        assert result["memories"][0]["title"] == "感冒了"
        assert result["memories"][0]["entry_id"].startswith("kc_")

    def test_no_hit_returns_empty(self, storage):
        save_memory(
            storage,
            {"title": "感冒了", "content": "…", "keywords": ["感冒", "健康"]},
            "kc_conv_abc",
        )
        result = recall_memory(storage, {"query": "怎么做红烧肉", "keywords": ["做饭", "菜谱"]})
        assert result["memories"] == []

    def test_empty_keywords_returns_empty(self, storage):
        save_memory(
            storage, {"title": "x", "content": "y", "keywords": ["z"]}, "c"
        )
        assert recall(storage, []) == []
        assert recall(storage, ["  "]) == []

    def test_more_overlap_ranks_higher(self, storage):
        save_memory(
            storage,
            {"title": "感冒了", "content": "注意保暖", "keywords": ["感冒", "出行"]},
            "c",
        )
        save_memory(
            storage,
            {"title": "爱爬山", "content": "每月一次", "keywords": ["出行", "户外", "周末"]},
            "c",
        )

        hits = recall(storage, ["出行", "户外"])

        assert [m.title for m in hits] == ["爱爬山", "感冒了"]


class TestResidentMemories:
    def test_orders_by_importance_then_recency(self, storage):
        save_memory(
            storage,
            {"title": "小事", "content": "…", "keywords": ["a"], "importance": 1},
            "c",
        )
        save_memory(
            storage,
            {"title": "大事", "content": "…", "keywords": ["b"], "importance": 5},
            "c",
        )

        titles = [m.title for m in resident_memories(storage)]

        assert titles[0] == "大事"

    def test_limit_caps_resident_list(self, storage):
        for i in range(7):
            save_memory(
                storage,
                {"title": f"记忆{i}", "content": "…", "keywords": ["k"], "importance": 3},
                "c",
            )

        assert len(resident_memories(storage)) == 5

    def test_ignores_non_memory_entries(self, storage):
        storage.create_entry(title="普通知识", source="manual", content="与记忆无关")
        assert resident_memories(storage) == []

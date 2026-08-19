import pytest

from kate_cortex.skills.knowledge import save_knowledge, suggest_save


class TestSaveKnowledge:
    def test_creates_entry_with_chat_source_and_conversation(self, storage):
        result = save_knowledge(
            storage,
            {
                "title": "连接池配置要点",
                "collections": ["编程"],
                "content_markdown": "使用 `pool_pre_ping=True` 避免断连。",
            },
            conversation_id="kc_conv_abc",
        )

        entry = storage.get_entry(result["entry_id"])
        assert entry.source == "chat"
        assert entry.conversation_id == "kc_conv_abc"
        assert entry.collections == ["编程"]
        assert "pool_pre_ping" in entry.content
        assert result["title"] == "连接池配置要点"
        assert result["collections"] == ["编程"]

    def test_missing_required_argument_raises(self, storage):
        with pytest.raises(KeyError):
            save_knowledge(
                storage, {"collections": []}, conversation_id="kc_conv_abc"
            )

    def test_without_collections_creates_uncollected_entry(self, storage):
        result = save_knowledge(
            storage,
            {
                "title": "无合集知识",
                "content_markdown": "x",
            },
            conversation_id="kc_conv_abc",
        )

        entry = storage.get_entry(result["entry_id"])
        assert entry.collections == []
        assert storage.list_collections() == []


class TestSuggestSave:
    def test_builds_suggestion_without_persisting(self, storage):
        result = suggest_save(
            {
                "title": "值得保存的结论",
                "collections": ["编程", "复盘"],
                "content_markdown": "选 SQLite 而不是 Postgres，因为单机够用。",
            }
        )

        assert result == {
            "title": "值得保存的结论",
            "collections": ["编程", "复盘"],
            "preview": "选 SQLite 而不是 Postgres，因为单机够用。",
        }
        items, total = storage.list_entries()
        assert total == 0

    def test_preview_truncated_to_200_chars(self):
        result = suggest_save(
            {
                "title": "长文",
                "content_markdown": "字" * 500,
            }
        )
        assert len(result["preview"]) == 200

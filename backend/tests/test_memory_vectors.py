"""IMP-8：记忆保存查重（duplicate_hint）+ 向量辅助召回（跨词面命中）"""

from kate_cortex.chat.memory import recall
from kate_cortex.skills.memory import save_memory


def _save(storage, title, content, keywords):
    return save_memory(
        storage,
        {
            "title": title,
            "content": content,
            "keywords": keywords,
            "importance": 3,
        },
        conversation_id="kc_conv_test",
    )


class TestDuplicateHint:
    def test_similar_memory_hits_hint(self, vector_storage):
        storage, _ = vector_storage
        _save(storage, "感冒了", "8月30日感冒，注意保暖", ["感冒", "健康"])
        second = _save(
            storage, "生病记录", "最近着凉不舒服，要多穿点", ["保暖", "身体"]
        )
        # 同属「生活健康」语义簇 → 相似度 ≥0.80
        assert second.get("duplicate_hint") is not None
        assert second["duplicate_hint"]["entry_id"] != second["entry_id"]
        assert "replaces_entry_id" in second["note"]

    def test_different_topic_no_hint(self, vector_storage):
        storage, _ = vector_storage
        _save(storage, "感冒了", "8月30日感冒，注意保暖", ["感冒", "健康"])
        other = _save(
            storage, "Redis 踩坑", "pipeline 事务模式不返回结果", ["redis", "编程"]
        )
        assert "duplicate_hint" not in other

    def test_no_vectors_no_hint(self, storage):
        # 纯 FTS 降级路径：不查重也不报错
        result = _save(storage, "感冒了", "8月30日感冒", ["感冒"])
        assert "duplicate_hint" not in result


class TestVectorRecall:
    def test_cross_lexical_recall(self, vector_storage):
        storage, _ = vector_storage
        _save(storage, "感冒了", "8月30日感冒，注意保暖", ["感冒", "健康"])
        # 检索词零词面重合，但同属「生活健康」簇 → 向量通道召回
        hits = recall(storage, ["出去玩", "天气"])
        assert any("感冒" in m.title for m in hits)

    def test_non_memory_entries_not_recalled(self, vector_storage):
        storage, _ = vector_storage
        storage.create_entry(
            title="天气科普",
            source="manual",
            content="降温与保暖常识",
            collections=["科普"],
        )
        _save(storage, "Redis 踩坑", "pipeline 不返回结果", ["redis"])
        # 「天气」语义上命中科普条目，但它不在「记忆」合集 → 不进召回
        hits = recall(storage, ["天气"])
        assert all("科普" not in m.title for m in hits)

    def test_plain_storage_recall_unchanged(self, storage):
        _save(storage, "感冒了", "8月30日感冒，注意保暖", ["感冒", "健康"])
        hits = recall(storage, ["感冒"])
        assert [m.title for m in hits] == ["感冒了"]
        assert recall(storage, ["完全无关词"]) == []

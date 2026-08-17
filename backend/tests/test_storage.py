from datetime import datetime

import pytest

from kate_cortex.storage import StorageError


def today_prefix():
    return datetime.now().strftime("%Y%m%d")


class TestCreate:
    def test_creates_file_and_index_with_chinese_title(self, storage, env):
        entry = storage.create_entry(
            title="数据库连接池配置",
            type="note",
            tags=["python"],
            source="manual",
            content="使用 SQLAlchemy 的连接池。",
        )

        assert entry.id == f"kc_{today_prefix()}_001"
        assert entry.slug == "shu-ju-ku-lian-jie-chi-pei-zhi"
        assert entry.type == "note"
        assert entry.source == "manual"

        md_file = env.vault_path / entry.file_path
        assert md_file.is_file()
        text = md_file.read_text(encoding="utf-8")
        assert "title: 数据库连接池配置" in text
        assert "使用 SQLAlchemy 的连接池。" in text

        assert storage.get_entry(entry.id) is not None

    def test_same_day_entries_increment_sequence(self, storage):
        first = storage.create_entry(
            title="第一条", type="note", tags=[], source="manual", content="a"
        )
        second = storage.create_entry(
            title="第二条", type="note", tags=[], source="manual", content="b"
        )

        assert first.id.endswith("_001")
        assert second.id.endswith("_002")
        assert first.slug != second.slug

    def test_slug_conflict_appends_suffix(self, storage):
        first = storage.create_entry(
            title="重复标题", type="note", tags=[], source="manual", content="a"
        )
        second = storage.create_entry(
            title="重复标题", type="note", tags=[], source="manual", content="b"
        )

        assert first.slug == "chong-fu-biao-ti"
        assert second.slug == "chong-fu-biao-ti-2"

    def test_deduplicates_tags(self, storage):
        entry = storage.create_entry(
            title="标签去重", type="note", tags=["redis", "redis", "bug"],
            source="manual", content="x",
        )
        assert entry.tags == ["redis", "bug"]

    def test_rejects_unknown_type(self, storage):
        with pytest.raises(StorageError):
            storage.create_entry(
                title="t", type="snippet", tags=[], source="manual", content="x"
            )


class TestGet:
    def test_get_by_slug(self, seeded):
        storage, _, second = seeded
        found = storage.get_entry(second.slug)
        assert found is not None
        assert found.id == second.id

    def test_get_missing_returns_none(self, storage):
        assert storage.get_entry("no-such") is None


class TestList:
    def test_lists_all_with_total(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries()
        assert total == 2
        assert [item.title for item in items] == [
            "FastAPI middleware 设计",
            "Redis pipeline 事务模式踩坑",
        ]

    def test_filters_by_type(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries(type="howto")
        assert total == 1
        assert items[0].title == "Redis pipeline 事务模式踩坑"

    def test_filters_by_tag(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries(tag="fastapi")
        assert total == 1
        assert items[0].title == "FastAPI middleware 设计"

    def test_pagination(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries(limit=1, offset=1)
        assert total == 2
        assert len(items) == 1
        assert items[0].title == "Redis pipeline 事务模式踩坑"

    def test_query_matches_chinese_content(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries(q="依赖注入")
        assert total == 1
        assert items[0].title == "FastAPI middleware 设计"


class TestUpdate:
    def test_update_content_rewrites_file_and_index(self, storage, env, seeded):
        storage, first, _ = seeded

        updated = storage.update_entry(first.id, content="全新的连接池耗尽结论。")

        md_file = env.vault_path / updated.file_path
        assert "全新的连接池耗尽结论。" in md_file.read_text(encoding="utf-8")
        assert updated.updated_at >= first.updated_at
        items, _ = storage.list_entries(q="耗尽")
        assert items[0].id == first.id

    def test_update_title_keeps_slug_stable(self, seeded):
        storage, first, _ = seeded
        updated = storage.update_entry(first.id, title="改了标题")
        assert updated.slug == first.slug
        assert updated.title == "改了标题"

    def test_update_missing_entry_raises(self, storage):
        with pytest.raises(StorageError):
            storage.update_entry("kc_19990101_001", content="x")


class TestSoftDelete:
    def test_delete_moves_file_to_trash(self, storage, env, seeded):
        storage, first, _ = seeded
        original_path = env.vault_path / first.file_path

        storage.delete_entry(first.id)

        assert not original_path.is_file()
        trash_files = list((env.vault_path / ".trash").rglob("*.md"))
        assert len(trash_files) == 1
        assert storage.get_entry(first.id) is None

    def test_delete_removes_from_search(self, storage, seeded):
        storage, first, _ = seeded
        storage.delete_entry(first.id)
        items, total = storage.list_entries(q="事务模式")
        assert total == 0

    def test_restore_returns_entry_and_file(self, storage, env, seeded):
        storage, first, _ = seeded
        storage.delete_entry(first.id)

        restored = storage.restore_entry(first.id)

        assert restored.id == first.id
        assert restored.title == first.title
        assert (env.vault_path / restored.file_path).is_file()
        assert storage.get_entry(first.id) is not None

    def test_restore_unknown_raises(self, storage):
        with pytest.raises(StorageError):
            storage.restore_entry("kc_19990101_001")


class TestLinks:
    def test_backlinks_resolves_slug_to_entry(self, seeded):
        storage, first, second = seeded
        backlinks = storage.backlinks(second.id)
        assert [entry.id for entry in backlinks] == [first.id]

    def test_backlinks_empty_when_none(self, storage, seeded):
        storage, first, _ = seeded
        assert storage.backlinks(first.id) == []


class TestSync:
    def test_sync_reports_unindexed_external_file(self, storage, env, seeded):
        orphan = env.vault_path / "2026" / "08"
        orphan.mkdir(parents=True, exist_ok=True)
        (orphan / "20260818-099-manual-note.md").write_text(
            "---\n"
            "id: kc_20260818_099\n"
            "slug: manual-note\n"
            "title: 手动放的笔记\n"
            "type: note\n"
            "tags: []\n"
            "source: import\n"
            "created_at: 2026-08-18T09:00:00+08:00\n"
            "updated_at: 2026-08-18T09:00:00+08:00\n"
            "---\n"
            "外部手动创建。\n",
            encoding="utf-8",
        )

        report = storage.sync()

        assert "kc_20260818_099" in report.unindexed

    def test_reindex_picks_up_edited_file(self, storage, env, seeded):
        _, _, second = seeded
        md_file = env.vault_path / second.file_path
        md_file.write_text(
            md_file.read_text(encoding="utf-8").replace(
                "middleware 执行顺序与依赖注入。", "被外部编辑器改过的内容。"
            ),
            encoding="utf-8",
        )

        storage.reindex()

        refreshed = storage.get_entry(second.id)
        assert "被外部编辑器改过的内容。" in refreshed.content

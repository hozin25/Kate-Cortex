from datetime import datetime

import pytest

from kate_cortex.storage import (
    CollectionExists,
    CollectionNotFound,
    StorageError,
)


def today_prefix():
    return datetime.now().strftime("%Y%m%d")


class TestCreate:
    def test_creates_file_and_index_with_chinese_title(self, storage, env):
        entry = storage.create_entry(
            title="数据库连接池配置",
            source="manual",
            content="使用 SQLAlchemy 的连接池。",
        )

        assert entry.id == f"kc_{today_prefix()}_001"
        assert entry.slug == "shu-ju-ku-lian-jie-chi-pei-zhi"
        assert entry.source == "manual"
        assert entry.collections == []

        md_file = env.vault_path / entry.file_path
        assert md_file.is_file()
        text = md_file.read_text(encoding="utf-8")
        assert "title: 数据库连接池配置" in text
        assert "使用 SQLAlchemy 的连接池。" in text

        assert storage.get_entry(entry.id) is not None

    def test_same_day_entries_increment_sequence(self, storage):
        first = storage.create_entry(title="第一条", source="manual", content="a")
        second = storage.create_entry(title="第二条", source="manual", content="b")

        assert first.id.endswith("_001")
        assert second.id.endswith("_002")
        assert first.slug != second.slug

    def test_slug_conflict_appends_suffix(self, storage):
        first = storage.create_entry(title="重复标题", source="manual", content="a")
        second = storage.create_entry(title="重复标题", source="manual", content="b")

        assert first.slug == "chong-fu-biao-ti"
        assert second.slug == "chong-fu-biao-ti-2"

    def test_create_with_collections_persists_to_frontmatter(self, storage, env):
        entry = storage.create_entry(
            title="投资复盘",
            source="manual",
            content="内容",
            collections=["金融", "金融", "复盘"],
        )
        assert entry.collections == ["金融", "复盘"]

        text = (env.vault_path / entry.file_path).read_text(encoding="utf-8")
        assert "collections:" in text
        assert "- 金融" in text

    def test_rejects_unknown_source(self, storage):
        with pytest.raises(StorageError):
            storage.create_entry(title="t", source="web", content="x")


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

    def test_filters_by_collection(self, seeded):
        storage, _, _ = seeded
        items, total = storage.list_entries(collection="编程")
        assert total == 1
        assert items[0].title == "Redis pipeline 事务模式踩坑"
        assert items[0].collections == ["编程"]

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


class TestCollections:
    def test_create_list_and_duplicate(self, storage):
        storage.create_collection("金融")
        storage.create_collection("情感")

        assert storage.list_collections() == [("情感", 0), ("金融", 0)]

        with pytest.raises(CollectionExists):
            storage.create_collection("金融")
        with pytest.raises(StorageError):
            storage.create_collection("  ")

    def test_empty_collection_survives_entry_membership_clear(self, storage, seeded):
        storage, first, _ = seeded
        storage.update_entry(first.id, collections=[])

        assert ("编程", 0) in storage.list_collections()

    def test_update_entry_replaces_collections(self, storage, seeded):
        storage, first, second = seeded
        storage.create_collection("复盘")

        storage.update_entry(first.id, collections=["复盘", "编程"])
        assert storage.get_entry(first.id).collections == ["复盘", "编程"]

        storage.update_entry(first.id, collections=["复盘"])
        assert storage.get_entry(first.id).collections == ["复盘"]

        items, total = storage.list_entries(collection="编程")
        assert total == 0

    def test_rename_rewrites_member_frontmatter(self, storage, env, seeded):
        storage, first, _ = seeded

        count = storage.rename_collection("编程", "技术")

        assert count == 1
        assert storage.get_entry(first.id).collections == ["技术"]
        text = (env.vault_path / first.file_path).read_text(encoding="utf-8")
        assert "- 技术" in text and "- 编程" not in text
        assert ("技术", 1) in storage.list_collections()

    def test_rename_to_existing_name_raises(self, storage, seeded):
        storage, _, _ = seeded
        storage.create_collection("复盘")
        with pytest.raises(CollectionExists):
            storage.rename_collection("编程", "复盘")

    def test_rename_missing_raises(self, storage):
        with pytest.raises(CollectionNotFound):
            storage.rename_collection("不存在", "新名字")

    def test_delete_keeps_entries_but_clears_membership(self, storage, env, seeded):
        storage, first, _ = seeded

        count = storage.delete_collection("编程")

        assert count == 1
        entry = storage.get_entry(first.id)
        assert entry is not None
        assert entry.collections == []
        assert "collections:" not in (
            env.vault_path / entry.file_path
        ).read_text(encoding="utf-8")
        assert storage.list_collections() == []
        _, total = storage.list_entries()
        assert total == 2

    def test_delete_missing_raises(self, storage):
        with pytest.raises(CollectionNotFound):
            storage.delete_collection("不存在")


LEGACY_ENTRY_MD = """---
id: kc_20260801_001
slug: jiao-yu-bei-jing
title: 教育背景
tags:
- 个人信息
- redis
source: manual
created_at: "2026-08-01T10:00:00+08:00"
updated_at: "2026-08-01T10:00:00+08:00"
---
本科计算机专业。
"""


class TestProfileMigration:
    def _seed_legacy_entry(self, env, storage):
        md_file = env.vault_path / "2026" / "08" / "20260801-001-jiao-yu-bei-jing.md"
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(LEGACY_ENTRY_MD, encoding="utf-8")
        storage.reindex()
        return md_file

    def test_moves_profile_tag_to_collection(self, storage, env):
        md_file = self._seed_legacy_entry(env, storage)

        migrated = storage.migrate_profile_to_collection()

        assert migrated == 1
        entry = storage.get_entry("kc_20260801_001")
        assert entry is not None
        assert "个人信息" in entry.collections
        assert entry.tags == ["redis"]
        assert ("个人信息", 1) in storage.list_collections()

        text = md_file.read_text(encoding="utf-8")
        assert "- 个人信息" in text
        assert "redis" in text
        assert entry.created_at == "2026-08-01T10:00:00+08:00"
        assert entry.updated_at == "2026-08-01T10:00:00+08:00"

    def test_idempotent_rerun_returns_zero(self, storage, env):
        self._seed_legacy_entry(env, storage)
        storage.migrate_profile_to_collection()

        assert storage.migrate_profile_to_collection() == 0

    def test_untouched_without_profile_tag(self, storage, env):
        storage.create_entry(title="普通条目", source="manual", content="x")

        assert storage.migrate_profile_to_collection() == 0
        items, total = storage.list_entries()
        assert total == 1

    def test_keeps_existing_collection_membership(self, storage, env):
        md_file = self._seed_legacy_entry(env, storage)

        storage.migrate_profile_to_collection()

        entry = storage.get_entry("kc_20260801_001")
        assert entry.collections == ["个人信息"]
        assert "- 个人信息" in md_file.read_text(encoding="utf-8")

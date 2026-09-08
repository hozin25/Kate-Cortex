"""IMP-5 / IMP-10：vault 合并迁移与 Obsidian 导入"""

import json

from kate_cortex.importer import ImportError_, import_obsidian, import_vault
from kate_cortex.security import encrypt_secret


def _make_source_vault(tmp_path, with_settings: dict | None = None):
    """构造一个最小的 Kate-Cortex 源 vault（md 双写格式的子集）"""
    src = tmp_path / "src_vault"
    (src / "2026" / "01").mkdir(parents=True)
    (src / "2026" / "01" / "20260101-001-redis.md").write_text(
        "---\n"
        "id: kc_20260101_001\n"
        "slug: redis-note\n"
        "title: Redis 笔记\n"
        "source: manual\n"
        "created_at: '2026-01-01T10:00:00+08:00'\n"
        "updated_at: '2026-01-01T10:00:00+08:00'\n"
        "collections:\n- 编程\n"
        "---\n"
        "pipeline 内容，参见 [[fastapi-note]]\n",
        encoding="utf-8",
    )
    (src / "attachments" / "2026" / "01").mkdir(parents=True)
    (src / "attachments" / "2026" / "01" / "pic.png").write_bytes(b"\x89PNG fake")
    if with_settings:
        import sqlite3

        conn = sqlite3.connect(src / "index.sqlite")
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO settings VALUES ('provider_keys', ?)",
            (
                json.dumps(
                    {k: encrypt_secret(v) for k, v in with_settings.items()},
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
        conn.close()
    return src


class TestVaultImport:
    def test_import_entries_attachments_links(self, storage, tmp_path):
        src = _make_source_vault(tmp_path)
        report = import_vault(storage, None, str(src), merge_keys=False)
        assert report.dry_run is False
        assert report.imported == 1
        entry = storage.get_entry("redis-note")
        assert entry is not None
        assert entry.collections == ["编程"]
        assert (storage.vault / "attachments" / "2026" / "01" / "pic.png").is_file()
        # 源目录原样未动
        assert (src / "2026" / "01" / "20260101-001-redis.md").is_file()
        # 双链解析进 entry_links
        rows = storage.conn.execute("SELECT to_slug FROM entry_links").fetchall()
        assert [tuple(r) for r in rows] == [("fastapi-note",)]

    def test_slug_conflict_gets_suffix(self, storage, tmp_path):
        storage.create_entry(title="占位", source="manual", content="x", slug="redis-note")
        src = _make_source_vault(tmp_path)
        report = import_vault(storage, None, str(src), merge_keys=False)
        assert report.imported == 1
        assert report.slug_renamed == ["redis-note → redis-note-2"]

    def test_dry_run_writes_nothing(self, storage, tmp_path):
        src = _make_source_vault(tmp_path)
        report = import_vault(storage, None, str(src), dry_run=True, merge_keys=False)
        assert report.imported == 1 and report.attachments == 1
        assert storage.list_entries()[1] == 0
        assert not (storage.vault / "attachments").exists()

    def test_idempotent_by_entry_id(self, storage, tmp_path):
        src = _make_source_vault(tmp_path)
        import_vault(storage, None, str(src), merge_keys=False)
        report = import_vault(storage, None, str(src), merge_keys=False)
        assert report.imported == 0
        assert any("id 已存在" in s for s in report.skipped)

    def test_merge_keys_only_missing(self, storage, tmp_path):
        src = _make_source_vault(tmp_path, with_settings={"glm": "g-key", "deepseek": "d-key"})

        class FakeSettings:
            def __init__(self):
                self.current = {"provider_keys": {"glm": "existing"}}

            def get_all(self):
                return self.current

            def update(self, patch):
                self.current["provider_keys"].update(patch["provider_keys"])

        fake = FakeSettings()
        report = import_vault(storage, fake, str(src))
        assert report.keys_merged == ["deepseek"]
        assert fake.current["provider_keys"]["glm"] == "existing"  # 不覆盖

    def test_rejects_same_dir_and_missing(self, storage, tmp_path):
        import pytest

        with pytest.raises(ImportError_):
            import_vault(storage, None, str(tmp_path / "nope"))
        with pytest.raises(ImportError_):
            import_vault(storage, None, str(storage.vault))


def _make_obsidian_vault(tmp_path):
    src = tmp_path / "obs"
    notes = src / "notes"
    notes.mkdir(parents=True)
    (notes / "Go.md").write_text(
        "---\ntags:\n- 编程\naliases:\n- Golang\ncssclass: wide\n---\n"
        "# Go 语言\n\n语法简介。\n\n关联：[[Rust|锈语言]] 和 ![[go-logo.png]]\n",
        encoding="utf-8",
    )
    (notes / "Rust.md").write_text(
        "无 frontmatter 的笔记，标题靠 H1。\n\n见 [[Go]]\n",
        encoding="utf-8",
    )
    (notes / "附件目录").mkdir()
    (notes / "附件目录" / "go-logo.png").write_bytes(b"\x89PNG logo")
    return src


class TestObsidianImport:
    def test_import_full_flow(self, storage, tmp_path):
        src = _make_obsidian_vault(tmp_path)
        report = import_obsidian(storage, str(src))
        assert report.imported == 2
        assert report.links_rewritten == 2  # [[Rust|锈语言]] + [[Go]]
        assert report.attachments == 1

        go = storage.get_entry(
            next(e.id for e in storage.list_entries(limit=10)[0] if e.title == "Go 语言")
        )
        assert go is not None and go.source == "import"
        assert go.collections == ["编程"]
        assert go.title == "Go 语言"
        assert "[[rust|锈语言]]" in go.content
        assert "import-" in go.content and "go-logo.png" in go.content
        att_file = storage.vault / "attachments"
        assert any(p.name == "go-logo.png" for p in att_file.rglob("go-logo.png"))
        # Obsidian 扩展字段透传
        text = (storage.vault / go.file_path).read_text(encoding="utf-8")
        assert "aliases" in text and "Golang" in text and "cssclass" in text

        rust = storage.get_entry("rust")
        assert rust is not None and rust.title == "Rust"
        assert f"[[{go.slug}]]" in rust.content

    def test_no_frontmatter_uses_filename(self, storage, tmp_path):
        src = tmp_path / "obs2"
        src.mkdir()
        (src / "随手记.md").write_text("没有标题也没有 frontmatter\n", encoding="utf-8")
        report = import_obsidian(storage, str(src))
        assert report.imported == 1
        entry = storage.get_entry("sui-shou-ji")
        assert entry is not None and entry.title == "随手记"

    def test_dry_run_no_writes(self, storage, tmp_path):
        src = _make_obsidian_vault(tmp_path)
        report = import_obsidian(storage, str(src), dry_run=True)
        assert report.imported == 2
        assert storage.list_entries()[1] == 0
        assert not (storage.vault / "attachments").exists()

    def test_unresolved_link_left_as_is(self, storage, tmp_path):
        src = tmp_path / "obs3"
        src.mkdir()
        (src / "A.md").write_text("链接到 [[不存在]]\n", encoding="utf-8")
        report = import_obsidian(storage, str(src))
        assert report.imported == 1 and report.links_rewritten == 0
        entry = storage.get_entry("a")
        assert "[[不存在]]" in entry.content

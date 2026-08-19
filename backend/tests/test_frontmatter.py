import pytest

from kate_cortex.frontmatter import (
    EntryMeta,
    FrontmatterError,
    dump_markdown,
    parse_markdown,
    validate,
)


def make_meta(**overrides):
    base = dict(
        id="kc_20260817_001",
        slug="redis-pipeline-bug",
        title="Redis pipeline 在事务模式下不返回结果",
        tags=["redis", "bug"],
        collections=["编程"],
        source="chat",
        language="python",
        conversation="kc_conv_a1b2c3",
        created_at="2026-08-17T10:30:00+08:00",
        updated_at="2026-08-17T10:30:00+08:00",
    )
    base.update(overrides)
    return EntryMeta(**base)


class TestParse:
    def test_parses_full_frontmatter_and_content(self):
        text = (
            "---\n"
            "id: kc_20260817_001\n"
            "slug: redis-pipeline-bug\n"
            "title: Redis pipeline 在事务模式下不返回结果\n"
            "tags: [redis, bug]\n"
            "collections: [编程, 复盘]\n"
            "language: python\n"
            "source: chat\n"
            "conversation: kc_conv_a1b2c3\n"
            "created_at: 2026-08-17T10:30:00+08:00\n"
            "updated_at: 2026-08-17T10:30:00+08:00\n"
            "---\n"
            "\n"
            "正文第一段。\n"
            "\n"
            "```python\n"
            "pipe = r.pipeline(transaction=True)\n"
            "```\n"
        )

        meta, content = parse_markdown(text)

        assert meta.id == "kc_20260817_001"
        assert meta.slug == "redis-pipeline-bug"
        assert meta.title == "Redis pipeline 在事务模式下不返回结果"
        assert meta.tags == ["redis", "bug"]
        assert meta.collections == ["编程", "复盘"]
        assert meta.language == "python"
        assert meta.source == "chat"
        assert meta.conversation == "kc_conv_a1b2c3"
        assert "正文第一段。" in content
        assert "pipeline(transaction=True)" in content

    def test_ignores_legacy_type_field(self):
        text = (
            "---\n"
            "id: kc_20260817_001\n"
            "slug: redis-pipeline-bug\n"
            "title: 旧版条目\n"
            "type: howto\n"
            "source: manual\n"
            "created_at: 2026-08-17T10:30:00+08:00\n"
            "updated_at: 2026-08-17T10:30:00+08:00\n"
            "---\n"
            "正文\n"
        )

        meta, _ = parse_markdown(text)

        assert not hasattr(meta, "type")
        assert meta.collections == []

    def test_collections_accepts_single_string(self):
        text = (
            "---\n"
            "id: kc_20260817_001\n"
            "slug: some-slug\n"
            "title: 单合集\n"
            "source: manual\n"
            "collections: 金融\n"
            "created_at: 2026-08-17T10:30:00+08:00\n"
            "updated_at: 2026-08-17T10:30:00+08:00\n"
            "---\n"
            "正文\n"
        )

        meta, _ = parse_markdown(text)

        assert meta.collections == ["金融"]

    def test_tags_missing_defaults_to_empty(self):
        text = (
            "---\n"
            "id: kc_20260817_001\n"
            "slug: some-slug\n"
            "title: 无标签条目\n"
            "source: manual\n"
            "created_at: 2026-08-17T10:30:00+08:00\n"
            "updated_at: 2026-08-17T10:30:00+08:00\n"
            "---\n"
            "正文\n"
        )

        meta, _ = parse_markdown(text)

        assert meta.tags == []

    def test_raises_when_frontmatter_missing(self):
        with pytest.raises(FrontmatterError):
            parse_markdown("# 只有正文，没有 frontmatter\n")

    def test_raises_when_required_field_missing(self):
        text = (
            "---\n"
            "id: kc_20260817_001\n"
            "slug: some-slug\n"
            "---\n"
            "正文\n"
        )
        with pytest.raises(FrontmatterError):
            parse_markdown(text)


class TestValidate:
    @pytest.mark.parametrize("bad_source", ["web", "", "CHAT"])
    def test_rejects_invalid_source(self, bad_source):
        with pytest.raises(FrontmatterError):
            validate(make_meta(source=bad_source))

    def test_rejects_empty_title(self):
        with pytest.raises(FrontmatterError):
            validate(make_meta(title=""))

    def test_accepts_optional_fields_as_none(self):
        meta = make_meta(language=None, conversation=None)
        validate(meta)


class TestDump:
    def test_roundtrip_preserves_meta_and_content(self):
        meta = make_meta()
        content = "正文第一段。\n\n第二段有 [[other-entry]] 链接。\n"

        text = dump_markdown(meta, content)
        parsed_meta, parsed_content = parse_markdown(text)

        assert parsed_meta == meta
        assert parsed_content == content.strip("\n")

    def test_dumped_text_starts_with_delimiter(self):
        text = dump_markdown(make_meta(), "正文")
        assert text.startswith("---\n")
        assert "type:" not in text

    def test_roundtrip_with_none_optional_fields(self):
        meta = make_meta(language=None, conversation=None, collections=[])

        parsed_meta, _ = parse_markdown(dump_markdown(meta, "正文"))

        assert parsed_meta.language is None
        assert parsed_meta.conversation is None
        assert parsed_meta.collections == []

    def test_empty_tags_omitted_in_dump_but_nonempty_passes_through(self):
        text = dump_markdown(make_meta(tags=[]), "正文")
        assert "tags:" not in text

        text = dump_markdown(make_meta(tags=["存量标签"]), "正文")
        assert "存量标签" in text

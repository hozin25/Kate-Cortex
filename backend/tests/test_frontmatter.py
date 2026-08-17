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
        type="howto",
        tags=["redis", "bug"],
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
            "type: howto\n"
            "tags: [redis, bug]\n"
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
        assert meta.type == "howto"
        assert meta.tags == ["redis", "bug"]
        assert meta.language == "python"
        assert meta.source == "chat"
        assert meta.conversation == "kc_conv_a1b2c3"
        assert "正文第一段。" in content
        assert "pipeline(transaction=True)" in content

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
    @pytest.mark.parametrize("bad_type", ["snippet", "", "NOTE"])
    def test_rejects_invalid_type(self, bad_type):
        with pytest.raises(FrontmatterError):
            validate(make_meta(type=bad_type))

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

    def test_roundtrip_with_none_optional_fields(self):
        meta = make_meta(language=None, conversation=None)

        parsed_meta, _ = parse_markdown(dump_markdown(meta, "正文"))

        assert parsed_meta.language is None
        assert parsed_meta.conversation is None

from kate_cortex.linking import extract_links


class TestExtractLinks:
    def test_extracts_plain_slug_link(self):
        content = "参考 [[redis-pipeline-bug]] 的记录。"
        assert extract_links(content) == ["redis-pipeline-bug"]

    def test_extracts_multiple_links_in_order(self):
        content = "先看 [[alpha]]，再看 [[beta]]，最后回到 [[alpha]]。"
        assert extract_links(content) == ["alpha", "beta"]

    def test_ignores_links_inside_fenced_code_block(self):
        content = "正文 [[real-link]]\n\n```python\n# see [[code-link]]\nprint(1)\n```\n"
        assert extract_links(content) == ["real-link"]

    def test_ignores_links_inside_inline_code(self):
        content = "用 `[[not-a-link]]` 语法，但 [[real-link]] 生效。"
        assert extract_links(content) == ["real-link"]

    def test_ignores_links_inside_indented_code_block(self):
        content = "正文 [[real-link]]\n\n    这是缩进代码块 [[indented-link]]\n"
        assert extract_links(content) == ["real-link"]

    def test_link_with_display_alias_returns_slug(self):
        content = "见 [[redis-pipeline-bug|这篇笔记]]。"
        assert extract_links(content) == ["redis-pipeline-bug"]

    def test_content_without_links_returns_empty(self):
        assert extract_links("没有任何链接的内容。") == []

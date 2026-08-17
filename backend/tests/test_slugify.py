import re

from kate_cortex.slugify import slugify


class TestSlugify:
    def test_chinese_title_converts_to_pinyin(self):
        assert slugify("数据库连接池") == "shu-ju-ku-lian-jie-chi"

    def test_mixed_chinese_and_english(self):
        assert slugify("Redis pipeline 的坑") == "redis-pipeline-de-keng"

    def test_english_title_is_lowercased_and_joined(self):
        assert slugify("FastAPI Middleware Design") == "fastapi-middleware-design"

    def test_special_characters_become_separators(self):
        assert slugify("HTTP/2 & WebSocket: 实战!") == "http-2-websocket-shi-zhan"

    def test_collapses_consecutive_separators_and_trims(self):
        assert slugify("--多余--分隔符--") == "duo-yu-fen-ge-fu"

    def test_falls_back_to_timestamp_when_empty(self):
        result = slugify("!!!???")
        assert re.fullmatch(r"e\d+", result), f"expected timestamp fallback, got {result}"

    def test_falls_back_to_timestamp_when_blank(self):
        result = slugify("   ")
        assert re.fullmatch(r"e\d+", result)

    def test_long_title_is_truncated_to_max_length(self):
        result = slugify("a" * 100)
        assert len(result) <= 60

    def test_truncation_does_not_leave_trailing_separator(self):
        result = slugify("x" * 59 + "-")
        assert not result.endswith("-")
        assert len(result) <= 60

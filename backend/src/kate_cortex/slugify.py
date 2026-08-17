"""标题 → slug：中文转拼音，异常兜底时间戳（DESIGN.md §3.1）"""

import re
import time

from pypinyin import lazy_pinyin

MAX_SLUG_LENGTH = 60


def slugify(title: str, *, max_length: int = MAX_SLUG_LENGTH) -> str:
    parts = lazy_pinyin(title.strip().lower(), errors="default")
    text = "-".join(parts)
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        return f"e{time.time_ns() // 1_000_000}"
    return text[:max_length].rstrip("-")

"""`[[slug]]` 双向链接提取（DESIGN.md §3.4）"""

import re

_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def extract_links(content: str) -> list[str]:
    """提取正文中的 slug 链接，跳过代码块与行内代码，去重保序。"""
    stripped = _strip_code(content)
    seen: dict[str, None] = {}
    for match in _LINK_RE.finditer(stripped):
        slug = match.group(1).strip()
        if slug:
            seen.setdefault(slug, None)
    return list(seen)


def _strip_code(content: str) -> str:
    lines = content.split("\n")
    out: list[str] = []
    in_fence = False
    for line in lines:
        if in_fence:
            out.append("")
            if line.lstrip().startswith("```"):
                in_fence = False
            continue
        if line.lstrip().startswith("```"):
            in_fence = True
            out.append("")
            continue
        if line.startswith("    ") or line.startswith("\t"):
            out.append("")
            continue
        out.append(line)
    return _INLINE_CODE_RE.sub(" ", "\n".join(out))

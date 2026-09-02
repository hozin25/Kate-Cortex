"""文件导出 skill：export_markdown——把内容写成独立 .md 文件（DESIGN.md §6.1）。

与 save_knowledge 的区别：知识库条目带 frontmatter 且被 vault 递归索引；
导出文件是干净的独立文档，保存在 vault 之外的导出文件夹，不进索引。
"""

import re
from pathlib import Path

_PARAMS = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "文档标题，同时用作文件名（可中文，如「杭州两日游」）",
        },
        "content_markdown": {
            "type": "string",
            "description": "完整文档正文 markdown，含标题与全文，可直接作为独立文件使用",
        },
    },
    "required": ["title", "content_markdown"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "export_markdown",
            "description": (
                "把内容保存为独立的 Markdown 文件（.md），存入导出文件夹。"
                "当用户要求「保存成文件」「导出 md」「存到文件夹」「给我一份文件」时调用，"
                "而不是只在聊天里输出格式化文本。"
            ),
            "parameters": _PARAMS,
        },
    }
]

DEFAULT_DIR_NAME = "Kate-Cortex 导出"

# Windows 文件名非法字符与控制字符
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def default_export_dir() -> str:
    return str(Path.home() / "Documents" / DEFAULT_DIR_NAME)


def _safe_stem(title: str) -> str:
    stem = _ILLEGAL.sub("-", title).strip(" .-")
    return stem or "未命名"


def export_markdown(args: dict, export_dir: str | None = None) -> dict:
    target = Path(export_dir or default_export_dir())
    target.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(args["title"])
    path = target / f"{stem}.md"
    counter = 2
    while path.exists():
        path = target / f"{stem} ({counter}).md"
        counter += 1

    path.write_text(args["content_markdown"], encoding="utf-8")
    return {"title": args["title"], "file_path": str(path)}

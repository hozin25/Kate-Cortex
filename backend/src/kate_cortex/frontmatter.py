"""frontmatter 解析 / 生成 / 校验（DESIGN.md §3.2）"""

from dataclasses import dataclass

import frontmatter
import yaml

ENTRY_TYPES = frozenset({"note", "clip", "decision", "howto"})
SOURCES = frozenset({"manual", "chat", "import"})

_REQUIRED = ("id", "slug", "title", "type", "source", "created_at", "updated_at")


class FrontmatterError(ValueError):
    pass


@dataclass
class EntryMeta:
    id: str
    slug: str
    title: str
    type: str
    tags: list[str]
    source: str
    created_at: str
    updated_at: str
    language: str | None = None
    conversation: str | None = None


def parse_markdown(text: str) -> tuple[EntryMeta, str]:
    post = frontmatter.loads(text)
    fm = post.metadata
    missing = [key for key in _REQUIRED if not fm.get(key)]
    if missing:
        raise FrontmatterError(f"frontmatter 缺少必填字段: {', '.join(missing)}")

    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    meta = EntryMeta(
        id=str(fm["id"]),
        slug=str(fm["slug"]),
        title=str(fm["title"]),
        type=str(fm["type"]),
        tags=[str(tag) for tag in tags],
        source=str(fm["source"]),
        created_at=str(fm["created_at"]),
        updated_at=str(fm["updated_at"]),
        language=_optional_str(fm.get("language")),
        conversation=_optional_str(fm.get("conversation")),
    )
    validate(meta)
    return meta, post.content


def validate(meta: EntryMeta) -> None:
    if meta.type not in ENTRY_TYPES:
        raise FrontmatterError(f"type 非法: {meta.type!r}，允许值 {sorted(ENTRY_TYPES)}")
    if meta.source not in SOURCES:
        raise FrontmatterError(f"source 非法: {meta.source!r}，允许值 {sorted(SOURCES)}")
    if not meta.title.strip():
        raise FrontmatterError("title 不能为空")
    if not meta.id.strip() or not meta.slug.strip():
        raise FrontmatterError("id 与 slug 不能为空")


def dump_markdown(meta: EntryMeta, content: str) -> str:
    validate(meta)
    fm: dict = {
        "id": meta.id,
        "slug": meta.slug,
        "type": meta.type,
        "title": meta.title,
        "tags": meta.tags,
        "language": meta.language,
        "source": meta.source,
        "conversation": meta.conversation,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
    }
    fm = {key: value for key, value in fm.items() if value is not None}
    head = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    body = content.rstrip("\n")
    return f"---\n{head.rstrip('\n')}\n---\n{body}\n" if body else f"---\n{head.rstrip('\n')}\n---\n"


def _optional_str(value) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value or None

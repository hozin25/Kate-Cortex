"""frontmatter 解析 / 生成 / 校验（DESIGN.md §3.2）"""

from dataclasses import dataclass, field

import frontmatter
import yaml

SOURCES = frozenset({"manual", "chat", "import"})

_REQUIRED = ("id", "slug", "title", "source", "created_at", "updated_at")


class FrontmatterError(ValueError):
    pass


@dataclass
class EntryMeta:
    id: str
    slug: str
    title: str
    # tags 已废弃（v3 起合集为唯一组织机制）：仅透传存量文件数据，业务层不读写
    tags: list[str]
    source: str
    created_at: str
    updated_at: str
    collections: list[str] = field(default_factory=list)
    language: str | None = None
    conversation: str | None = None
    # 自动记忆（v4）：场景触发词与重要性，仅「记忆」合集条目使用，其余条目为空
    keywords: list[str] = field(default_factory=list)
    importance: int | None = None


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value]


def parse_markdown(text: str) -> tuple[EntryMeta, str]:
    post = frontmatter.loads(text)
    fm = post.metadata
    missing = [key for key in _REQUIRED if not fm.get(key)]
    if missing:
        raise FrontmatterError(f"frontmatter 缺少必填字段: {', '.join(missing)}")

    meta = EntryMeta(
        id=str(fm["id"]),
        slug=str(fm["slug"]),
        title=str(fm["title"]),
        tags=_str_list(fm.get("tags")),
        source=str(fm["source"]),
        created_at=str(fm["created_at"]),
        updated_at=str(fm["updated_at"]),
        collections=_str_list(fm.get("collections")),
        language=_optional_str(fm.get("language")),
        conversation=_optional_str(fm.get("conversation")),
        keywords=_str_list(fm.get("keywords")),
        importance=_optional_int(fm.get("importance")),
    )
    validate(meta)
    return meta, post.content


def validate(meta: EntryMeta) -> None:
    if meta.source not in SOURCES:
        raise FrontmatterError(f"source 非法: {meta.source!r}，允许值 {sorted(SOURCES)}")
    if not meta.title.strip():
        raise FrontmatterError("title 不能为空")
    if not meta.id.strip() or not meta.slug.strip():
        raise FrontmatterError("id 与 slug 不能为空")
    if meta.importance is not None and not 1 <= meta.importance <= 5:
        raise FrontmatterError(f"importance 必须在 1-5 之间: {meta.importance}")


def dump_markdown(meta: EntryMeta, content: str) -> str:
    validate(meta)
    fm: dict = {
        "id": meta.id,
        "slug": meta.slug,
        "title": meta.title,
        "tags": meta.tags,
        "collections": meta.collections,
        "language": meta.language,
        "source": meta.source,
        "conversation": meta.conversation,
        "keywords": meta.keywords,
        "importance": meta.importance,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
    }
    fm = {key: value for key, value in fm.items() if value}
    head = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    body = content.rstrip("\n")
    return f"---\n{head.rstrip('\n')}\n---\n{body}\n" if body else f"---\n{head.rstrip('\n')}\n---\n"


def _optional_str(value) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value or None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)

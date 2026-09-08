"""导入器（IMPROVEMENT_PLAN IMP-5 / IMP-10）

两个入口共用底座：
- import_vault：从另一个 Kate-Cortex vault 合并式迁移（frontmatter 完全兼容）
- import_obsidian：从 Obsidian vault 导入（tags→合集、[[链接]]→[[slug]]、附件拷贝）

安全约定：绝不修改/删除源目录；dry_run 只算报告不落盘。
"""

import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import frontmatter as fm_lib
import yaml

from .attachments import ATTACHMENT_DIR
from .frontmatter import EntryMeta, dump_markdown, parse_markdown
from .security import decrypt_secret
from .slugify import slugify
from .storage import Storage

# 源扫描统一跳过的目录/文件
SKIP_DIRS = {".trash", ".obsidian", ".git", "node_modules"}


class ImportError_(Exception):
    pass


@dataclass
class ImportReport:
    imported: int = 0
    skipped: list[str] = field(default_factory=list)  # 原因说明（含文件名）
    links_rewritten: int = 0
    attachments: int = 0
    keys_merged: list[str] = field(default_factory=list)  # 补齐的 provider 名
    slug_renamed: list[str] = field(default_factory=list)  # 冲突重命名的 slug
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
    vector_hint: bool = False  # 存在向量索引时提示重建

    def as_dict(self) -> dict:
        return {
            "imported": self.imported,
            "skipped": self.skipped,
            "links_rewritten": self.links_rewritten,
            "attachments": self.attachments,
            "keys_merged": self.keys_merged,
            "slug_renamed": self.slug_renamed,
            "warnings": self.warnings,
            "dry_run": self.dry_run,
            "vector_hint": self.vector_hint,
        }


def _scan_md(source: Path) -> list[Path]:
    files: list[Path] = []
    for md in sorted(source.rglob("*.md")):
        parts = md.relative_to(source).parts
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        files.append(md)
    return files


# ── IMP-10：Kate-Cortex vault 合并式迁移 ──


def import_vault(
    storage: Storage,
    settings_service,
    source_dir: str,
    *,
    dry_run: bool = False,
    merge_keys: bool = True,
) -> ImportReport:
    source = Path(source_dir).expanduser().resolve()
    if not source.is_dir():
        raise ImportError_(f"源目录不存在或不是目录: {source}")
    if source == storage.vault.resolve():
        raise ImportError_("源目录与当前 vault 相同，无需导入")

    report = ImportReport(dry_run=dry_run, vector_hint=storage.vectors is not None)

    # 附件目录整体合并（不覆盖已有同名文件）
    src_att = source / ATTACHMENT_DIR
    if src_att.is_dir():
        for f in src_att.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(source)
            dst = storage.vault / rel
            if dst.exists():
                continue
            report.attachments += 1
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

    for md in _scan_md(source):
        rel = md.relative_to(source)
        try:
            meta, content = parse_markdown(md.read_text(encoding="utf-8"))
        except Exception as exc:
            report.skipped.append(f"{rel}: frontmatter 解析失败（{exc}）")
            continue
        if storage._find_row(meta.id) is not None:
            report.skipped.append(f"{rel}: 条目 id 已存在（{meta.id}），跳过")
            continue
        final_slug = meta.slug
        if storage._slug_taken(meta.slug):
            final_slug = storage._unique_slug(meta.slug)
            report.slug_renamed.append(f"{meta.slug} → {final_slug}")
            meta.slug = final_slug
        # 正文里的附件引用：文件已合并拷贝，引用路径不变（同为 attachments/ 相对路径）
        if not dry_run:
            rel_path = storage._rel_path(meta.id, meta.slug)
            dst = storage.vault / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(dump_markdown(meta, content), encoding="utf-8")
            storage._write_db(meta, content, rel_path)
            if storage.vectors:
                storage.vectors.index_entry(meta.id, meta.title, content)
        report.imported += 1

    if merge_keys:
        merged = _merge_provider_keys(settings_service, source, dry_run)
        report.keys_merged = merged

    if storage.vectors is not None:
        report.warnings.append("已启用向量检索：导入条目尚未嵌入，请在设置页点击「重建索引」")
    if report.slug_renamed:
        report.warnings.append(
            f"{len(report.slug_renamed)} 个条目因 slug 冲突自动改名（见 slug_renamed）"
        )
    return report


def _merge_provider_keys(settings_service, source: Path, dry_run: bool) -> list[str]:
    """读源 settings 表解密 key，只补本库缺失的 provider（不覆盖已有）。

    DPAPI 密文只能同用户同机解密——跨机器会失败，静默跳过。"""
    db_file = source / "index.sqlite"
    if not db_file.is_file():
        return []
    try:
        raw = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        row = raw.execute(
            "SELECT value FROM settings WHERE key = 'provider_keys'"
        ).fetchone()
        embed_row = raw.execute(
            "SELECT value FROM settings WHERE key = 'embedding_api_key'"
        ).fetchone()
        raw.close()
    except sqlite3.Error:
        return []
    import json

    decrypted: dict[str, str] = {}
    try:
        for name, value in (json.loads(row[0]) if row else {}).items():
            if value:
                decrypted[name] = decrypt_secret(value)
    except Exception:
        pass
    try:
        if embed_row and embed_row[0]:
            key = decrypt_secret(json.loads(embed_row[0]))
            if key:
                decrypted.setdefault("embedding", key)
    except Exception:
        pass

    current = settings_service.get_all()
    missing = {
        name: value
        for name, value in decrypted.items()
        if name != "embedding" and value and not current["provider_keys"].get(name)
    }
    if missing and not dry_run:
        settings_service.update(
            {"provider_keys": {**current["provider_keys"], **missing}}
        )
    return sorted(missing)


# ── IMP-5：Obsidian vault 导入 ──

# ![[pic.png]] / ![[pic.png|400]]（embed）与 [[Note]] / [[Note|alias]]（链接）
_EMBED_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def import_obsidian(
    storage: Storage,
    source_dir: str,
    *,
    tags_as_collections: bool = True,
    dry_run: bool = False,
) -> ImportReport:
    source = Path(source_dir).expanduser().resolve()
    if not source.is_dir():
        raise ImportError_(f"源目录不存在或不是目录: {source}")
    if source == storage.vault.resolve():
        raise ImportError_("源目录与当前 vault 相同，无需导入")

    report = ImportReport(dry_run=dry_run, vector_hint=storage.vectors is not None)
    files = _scan_md(source)

    # 第一遍：解析 frontmatter（宽松），确定 title / slug / tags，建 文件名→slug 映射
    parsed: list[tuple[Path, dict, str]] = []
    name_to_slug: dict[str, str] = {}
    for md in files:
        post = fm_lib.loads(md.read_text(encoding="utf-8"))
        fm = dict(post.metadata)
        title = str(fm.get("title") or "").strip()
        if not title:
            m = re.search(r"^#\s+(.+)$", post.content, re.MULTILINE)
            title = m.group(1).strip() if m else ""
        if not title:
            title = md.stem
        slug = _unique_slug_in(storage, slugify(title), name_to_slug.values())
        name_to_slug.setdefault(md.stem, slug)
        parsed.append((md, {**fm, "_title": title, "_slug": slug}, post.content))

    # 附件名 → 源文件路径（vault 内任意位置）
    att_by_name: dict[str, Path] = {}
    for f in source.rglob("*"):
        if f.is_file() and f.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"
        }:
            att_by_name.setdefault(f.name, f)

    att_dir = f"{ATTACHMENT_DIR}/import-{datetime.now().strftime('%Y%m%d')}"

    # 第二遍：重写正文并落库
    for md, fm, content in parsed:
        rel = md.relative_to(source)
        title = fm["_title"]
        slug = fm["_slug"]

        def rewrite_embed(m: re.Match) -> str:
            name = Path(m.group(1).strip()).name
            src_file = att_by_name.get(name)
            if src_file is None:
                report.warnings.append(f"{rel}: 附件不存在，保留原引用 {name}")
                return m.group(0)
            report.attachments += 1
            if not dry_run:
                dst = storage.vault / att_dir / name
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst)
            return f"![]({att_dir}/{name})"

        content = _EMBED_RE.sub(rewrite_embed, content)

        link_state = {"count": 0}

        def rewrite_link(m: re.Match) -> str:
            target = Path(m.group(1).strip()).name  # [[dir/Note]] 按 Note 匹配
            alias = (m.group(2) or "").strip()
            target_slug = name_to_slug.get(target.removesuffix(".md"))
            if target_slug is None:
                report.warnings.append(f"{rel}: 链接目标不在导入范围，保留原样 [[{target}]]")
                return m.group(0)
            link_state["count"] += 1
            return f"[[{target_slug}|{alias}]]" if alias else f"[[{target_slug}]]"

        content = _LINK_RE.sub(rewrite_link, content)
        report.links_rewritten += link_state["count"]

        collections = (
            [str(t).strip() for t in _as_list(fm.get("tags")) if str(t).strip()]
            if tags_as_collections
            else []
        )
        # 其余 Obsidian 字段（aliases/date/cssclass…）原样透传，tags 收进合集后移除
        extra = {
            k: v for k, v in fm.items()
            if k not in {"_title", "_slug", "tags", "title"}
            and k not in {"id", "slug", "source", "created_at", "updated_at",
                          "collections", "language", "conversation",
                          "keywords", "importance"}
        }
        meta = EntryMeta(
            id=storage._next_id() if not dry_run else "dryrun",
            slug=slug,
            title=title,
            tags=[],
            source="import",
            created_at=str(fm.get("date") or ""),
            updated_at="",
            collections=list(dict.fromkeys(collections)),
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        meta.created_at = meta.created_at or now
        meta.updated_at = now
        if not dry_run:
            rel_path = storage._rel_path(meta.id, meta.slug)
            dst = storage.vault / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            fm_dict = _entry_fm_dict(meta) | extra
            head = yaml.safe_dump(
                fm_dict, allow_unicode=True, sort_keys=False, default_flow_style=False
            )
            dst.write_text(f"---\n{head.rstrip()}\n---\n{content}\n", encoding="utf-8")
            storage._write_db(meta, content, rel_path)
            if storage.vectors:
                storage.vectors.index_entry(meta.id, meta.title, content)
        report.imported += 1

    if storage.vectors is not None:
        report.warnings.append("已启用向量检索：导入条目尚未嵌入，请在设置页点击「重建索引」")
    report.warnings.append("重复导入不查重：同 vault 再导会生成 -2 后缀的新条目")
    return report


def _entry_fm_dict(meta: EntryMeta) -> dict:
    fm: dict = {
        "id": meta.id,
        "slug": meta.slug,
        "title": meta.title,
        "collections": meta.collections,
        "source": meta.source,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
    }
    return {k: v for k, v in fm.items() if v}


def _unique_slug_in(storage: Storage, base: str, used) -> str:
    candidate = base or "untitled"
    suffix = 2
    while storage._slug_taken(candidate) or candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):  # yaml 稀疏列表 {null: tag}
        return list(value.values())
    return list(value)

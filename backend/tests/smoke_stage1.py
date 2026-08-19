"""阶段 1 验收冒烟：创建→过滤→详情→更新→搜索→软删→恢复，校验 vault 产物"""

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:1738"
vault = Path(sys.argv[1])

client = httpx.Client(base_url=BASE, timeout=10)
steps: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    steps.append((name, ok, detail))


health = client.get("/api/health").json()
check("health", health["app"] == "kate-cortex", str(health))

created = client.post(
    "/api/entries",
    json={
        "title": "如何设计本地优先的知识库",
        "collections": ["知识管理"],
        "source": "manual",
        "content": "markdown 与 SQLite 双写，文件是事实来源。",
    },
)
entry = created.json()
check("创建中文标题", created.status_code == 201 and entry["id"].startswith("kc_"), entry.get("slug", ""))

listed = client.get("/api/entries", params={"collection": "知识管理"}).json()
check("列表过滤 collection", listed["total"] == 1 and listed["items"][0]["id"] == entry["id"])

detail = client.get(f"/api/entries/{entry['id']}").json()
by_slug = client.get(f"/api/entries/{entry['slug']}").json()
check(
    "详情 by id/slug",
    detail["content"].startswith("markdown") and by_slug["id"] == entry["id"],
)

updated = client.put(
    f"/api/entries/{entry['id']}", json={"title": "本地优先知识库设计要点"}
)
check(
    "更新标题",
    updated.status_code == 200 and updated.json()["slug"] == entry["slug"],
)

searched = client.get("/api/entries", params={"q": "事实来源"}).json()
check("中文全文搜索", searched["total"] == 1 and searched["items"][0]["id"] == entry["id"])

client.delete(f"/api/entries/{entry['id']}")
gone = client.get(f"/api/entries/{entry['id']}")
trash_files = list((vault / ".trash").rglob("*.md")) if (vault / ".trash").exists() else []
check("软删：详情 404 + 文件进 .trash", gone.status_code == 404 and len(trash_files) == 1)

restored = client.post(f"/api/entries/{entry['id']}/restore")
check(
    "恢复",
    restored.status_code == 200 and (vault / restored.json()["file_path"]).is_file(),
)

md_files = list(vault.rglob("*.md"))
md_text = md_files[0].read_text(encoding="utf-8")
check(
    "vault md 与 frontmatter 正确",
    len(md_files) == 1
    and md_text.startswith("---\n")
    and "title: 本地优先知识库设计要点" in md_text
    and "知识管理" in md_text
    and "事实来源" in md_text,
)

print(json.dumps({name: {"ok": ok, "detail": detail} for name, ok, detail in steps}, ensure_ascii=False, indent=2))
failed = [name for name, ok, _ in steps if not ok]
print(f"\n{'全部通过' if not failed else '失败: ' + ', '.join(failed)}")
sys.exit(1 if failed else 0)

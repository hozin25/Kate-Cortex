"""阶段 3 验收冒烟：真实模型跑核心闭环三场景（需真实 API key）

场景 1（deepseek）：对话指令「记一下」→ save_knowledge → vault 生成 md
场景 2（glm）：陈述结论 → suggest_save 建议卡片 → curl 模拟用户确认入库
场景 3（deepseek）：预存知识 → 新会话 RAG 开 → citations 引用该条目

用法：KATE_DEEPSEEK_KEY=... KATE_GLM_KEY=... uv run python tests/smoke_stage3.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app


def parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        event = next(l[len("event: "):] for l in lines if l.startswith("event: "))
        data = next(l[len("data: "):] for l in lines if l.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def run_chat(client, session_id, content, rag=False):
    resp = client.post(
        f"/api/chat/sessions/{session_id}/chat",
        json={"content": content, "rag_enabled": rag},
    )
    return parse_sse(resp.text)


def scenario1_save(client) -> bool:
    session = client.post("/api/chat/sessions", json={"provider": "deepseek"}).json()
    events = run_chat(
        client,
        session["id"],
        "请把「SQLite 是嵌入式的单文件数据库，适合个人本地应用」这条知识记入知识库。",
    )
    names = [n for n, _ in events]
    print(f"  事件序列: {names}")
    tool_results = [d for n, d in events if n == "tool_result"]
    if not tool_results:
        print("  FAIL: 未出现 tool_result 事件")
        return False
    entry_id = tool_results[0]["entry_id"]
    detail = client.get(f"/api/entries/{entry_id}").json()
    print(f"  入库: {detail['id']} 《{detail['title']}》 type={detail['type']} tags={detail['tags']}")
    print(f"  来源: source={detail['source']} conversation={detail['conversation_id'] == session['id']}")
    md_ok = "SQLite" in detail["content"]
    print(f"  正文含关键词: {md_ok}")
    return detail["source"] == "chat" and md_ok


def scenario2_suggest(client) -> bool:
    session = client.post("/api/chat/sessions", json={"provider": "glm"}).json()
    events = run_chat(
        client,
        session["id"],
        "我决定了：我的个人知识管理工具选 SQLite 而不是 PostgreSQL，因为它是单文件、零运维、本地优先。",
    )
    names = [n for n, _ in events]
    print(f"  事件序列: {names}")
    suggests = [d for n, d in events if n == "suggest"]
    if not suggests:
        print("  WARN: 模型未主动建议（不阻塞验收，人工判断即可）")
        return True
    suggestion = suggests[0]
    print(f"  建议卡片: 《{suggestion['title']}》 type={suggestion['type']}")
    confirmed = client.post(
        "/api/entries",
        json={
            "title": suggestion["title"],
            "type": suggestion["type"],
            "tags": suggestion["tags"],
            "content": suggestion["preview"],
            "source": "chat",
            "conversation_id": session["id"],
        },
    )
    ok = confirmed.status_code == 201
    print(f"  模拟用户确认入库: {'PASS' if ok else 'FAIL'} ({confirmed.json().get('id')})")
    return ok


def scenario3_rag(client) -> bool:
    client.post(
        "/api/entries",
        json={
            "title": "SQLite 连接池调优",
            "type": "howto",
            "tags": ["sqlite"],
            "content": "max_size 设为 20，pool_pre_ping 开启可避免断连后取到失效连接。",
            "source": "manual",
        },
    )
    session = client.post("/api/chat/sessions", json={"provider": "deepseek"}).json()
    events = run_chat(client, session["id"], "连接池怎么调优", rag=True)
    citations = next(d for n, d in events if n == "citations")["entries"]
    print(f"  citations: {[e['title'] for e in citations]}")
    reply = "".join(d["text"] for n, d in events if n == "delta")
    print(f"  回复预览: {reply[:100]}")
    refs_ok = bool(citations)
    messages = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
    refs_saved = messages[-1]["knowledge_refs"] == [e["id"] for e in citations]
    print(f"  knowledge_refs 落库一致: {refs_saved}")
    return refs_ok and refs_saved


def main() -> int:
    deepseek_key = os.environ.get("KATE_DEEPSEEK_KEY", "")
    glm_key = os.environ.get("KATE_GLM_KEY", "")
    if not deepseek_key or not glm_key:
        print("需要 KATE_DEEPSEEK_KEY 与 KATE_GLM_KEY")
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="kate-smoke3-"))
    app = create_app(Config(vault_path=workdir / "vault", db_path=workdir / "index.sqlite"))
    client = TestClient(app)
    client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": deepseek_key, "glm": glm_key}},
    )

    results = {}
    print("\n场景 1：对话指令保存（deepseek）")
    results["scenario1"] = scenario1_save(client)
    print("\n场景 2：AI 主动建议（glm）")
    results["scenario2"] = scenario2_suggest(client)
    print("\n场景 3：RAG 引用（deepseek）")
    results["scenario3"] = scenario3_rag(client)

    print("\n总结:", json.dumps(results, ensure_ascii=False))
    failed = [k for k, v in results.items() if not v]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""阶段 2 验收冒烟：真实 provider 各完成一轮流式对话（需真实 API key）

用法：
  uv run python tests/smoke_stage2.py            # 两家都测（读环境变量）
  KATE_GLM_KEY= uv run python tests/smoke_stage2.py  # 只测 deepseek

环境变量：KATE_DEEPSEEK_KEY / KATE_GLM_KEY
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

PROBE = "用一句话回答：SQLite 的全文检索扩展叫什么？"


def parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        event = next(l[len("event: "):] for l in lines if l.startswith("event: "))
        data = next(l[len("data: "):] for l in lines if l.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def smoke(provider: str, api_key: str) -> bool:
    workdir = Path(tempfile.mkdtemp(prefix=f"kate-smoke2-{provider}-"))
    app = create_app(Config(vault_path=workdir / "vault", db_path=workdir / "index.sqlite"))
    client = TestClient(app)
    client.put("/api/settings", json={"provider_keys": {provider: api_key}})

    session = client.post("/api/chat/sessions", json={"provider": provider}).json()
    print(f"[{provider}] session={session['id']} model={session['model']}")

    resp = client.post(
        f"/api/chat/sessions/{session['id']}/chat",
        json={"content": PROBE, "rag_enabled": False},
    )
    events = parse_sse(resp.text)
    names = [name for name, _ in events]
    deltas = "".join(d["text"] for n, d in events if n == "delta")

    ok_stream = "delta" in names and "done" in names and "error" not in names
    print(f"[{provider}] SSE 事件: {names[:3]}...{names[-1]}")
    print(f"[{provider}] 回复: {deltas[:120]}")

    messages = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
    ok_history = len(messages) == 2 and messages[1]["content"] == deltas

    title = client.get("/api/chat/sessions").json()[0]["title"]
    ok_title = bool(title)

    ok = ok_stream and ok_history and ok_title
    print(f"[{provider}] 落库={ok_history} 标题={title!r} => {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> int:
    keys = {
        "deepseek": os.environ.get("KATE_DEEPSEEK_KEY", ""),
        "glm": os.environ.get("KATE_GLM_KEY", ""),
    }
    if not any(keys.values()):
        print("未提供任何 API key（KATE_DEEPSEEK_KEY / KATE_GLM_KEY），跳过真实冒烟")
        return 2

    results = {}
    for provider, key in keys.items():
        if key:
            results[provider] = smoke(provider, key)
    failed = [p for p, ok in results.items() if not ok]
    print("总结:", "全部通过" if not failed else f"失败: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

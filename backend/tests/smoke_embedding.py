"""向量检索验收冒烟：真实 embedding 服务 + 混合召回（需真实 key）

场景 1：embedding 接口连通（维度/相似度合理）
场景 2：零词面重合的语义召回（「出去玩」召回「感冒保暖」条目）
场景 3：rebuild 端点全量补嵌

用法（二选一）：
  KATE_GLM_KEY=... uv run python tests/smoke_embedding.py
  KATE_SF_KEY=... uv run python tests/smoke_embedding.py   # 硅基流动免费档 bge-m3
  KATE_SF_KEY=... KATE_EMBEDDING_PROVIDER=siliconflow uv run python tests/smoke_embedding.py
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
from kate_cortex.providers.embedding import GLMEmbedder, SiliconFlowEmbedder


def resolve_provider() -> tuple[str, str, object]:
    """(provider, api_key, embedder 类)；显式指定或按可用 key 推断"""
    provider = os.environ.get("KATE_EMBEDDING_PROVIDER", "")
    glm_key = os.environ.get("KATE_GLM_KEY", "")
    sf_key = os.environ.get("KATE_SF_KEY", "")
    if not provider:
        provider = "siliconflow" if sf_key and not glm_key else "glm"
    if provider == "siliconflow":
        return "siliconflow", sf_key, SiliconFlowEmbedder
    return "glm", glm_key, GLMEmbedder


def scenario1_embed(embedder_cls, api_key: str) -> bool:
    embedder = embedder_cls(api_key=api_key)
    vectors = embedder.embed(
        ["感冒了，医生叮嘱出行注意保暖", "明天出去玩要准备什么", "Redis pipeline 事务模式"]
    )
    dims = {len(v) for v in vectors}
    life_sim = _cosine(vectors[0], vectors[1])
    cross_sim = _cosine(vectors[0], vectors[2])
    print(f"  模型: {embedder.model} 维度: {dims}（期望 {{1024}}）")
    print(f"  同域相似度(感冒↔出去玩): {life_sim:.4f}（期望 >0.4）")
    print(f"  跨域相似度(感冒↔Redis): {cross_sim:.4f}（期望 <0.4）")
    return dims == {1024} and life_sim > 0.4 and cross_sim < 0.4


def scenario2_semantic_recall(client) -> bool:
    client.post(
        "/api/entries",
        json={
            "title": "感冒护理记录",
            "content": "感冒了，医生叮嘱出行注意保暖，多喝热水。",
            "source": "manual",
        },
    )
    client.post(
        "/api/entries",
        json={
            "title": "Redis pipeline 踩坑",
            "content": "pipeline 事务模式下不返回结果，改用 watch。",
            "source": "manual",
        },
    )
    session = client.post("/api/chat/sessions", json={"provider": "glm"}).json()
    resp = client.post(
        f"/api/chat/sessions/{session['id']}/chat",
        json={"content": "明天出去玩要准备什么", "rag_enabled": True},
    )
    citations = []
    for block in resp.text.strip().split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("event: citations"):
                citations = json.loads(
                    next(
                        l[len("data: ") :]
                        for l in block.split("\n")
                        if l.startswith("data: ")
                    )
                )["entries"]
    print(f"  citations: {[e['title'] for e in citations]}")
    titles = [e["title"] for e in citations]
    return "感冒护理记录" in titles and "Redis pipeline 踩坑" not in titles[:1]


def scenario3_rebuild(client) -> bool:
    before = client.get("/api/embeddings/status").json()
    result = client.post("/api/embeddings/rebuild").json()
    after = client.get("/api/embeddings/status").json()
    print(f"  重建前: available={before['available']} indexed={before['indexed']}/{before['total']}")
    print(f"  重建结果: {result}")
    print(f"  重建后: indexed={after['indexed']}/{after['total']}")
    return after["indexed"] == after["total"] and result["failed"] == 0


def _cosine(a: list[float], b: list[float]) -> float:
    # GLM embedding-3 输出已归一化，点积即余弦相似度
    return sum(x * y for x, y in zip(a, b))


def main() -> int:
    provider, api_key, embedder_cls = resolve_provider()
    if not api_key:
        print(f"需要 {'KATE_SF_KEY' if provider == 'siliconflow' else 'KATE_GLM_KEY'}")
        return 2

    print(f"\n场景 1：embedding 接口连通（{provider}）")
    s1 = scenario1_embed(embedder_cls, api_key)

    workdir = Path(tempfile.mkdtemp(prefix="kate-smoke-emb-"))
    app = create_app(Config(vault_path=workdir / "vault", db_path=workdir / "index.sqlite"))
    client = TestClient(app)
    settings = {"embedding_provider": provider, "embedding_model": embedder_cls.default_model}
    if provider == "siliconflow":
        settings["embedding_api_key"] = api_key
    else:
        settings["provider_keys"] = {"glm": api_key}
    client.put("/api/settings", json=settings)

    print("\n场景 2：零词面重合的语义召回")
    s2 = scenario2_semantic_recall(client)
    print("\n场景 3：rebuild 全量补嵌")
    s3 = scenario3_rebuild(client)

    results = {"embed": s1, "semantic_recall": s2, "rebuild": s3}
    print("\n总结:", json.dumps(results, ensure_ascii=False))
    return 1 if [k for k, v in results.items() if not v] else 0


if __name__ == "__main__":
    sys.exit(main())

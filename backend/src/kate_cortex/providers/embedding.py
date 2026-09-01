"""Embedding 客户端：GLM embedding-3 / 硅基流动 BAAI/bge-m3（均 OpenAI 兼容）

向量混合检索用（VECTOR_SEARCH_PLAN.md §3）。key 解析见 main._make_embedder_factory：
glm 回退复用 provider key（零新配置）；siliconflow 用独立 embedding_api_key
（bge-m3 为免费档）。两家的嵌入向量空间不互通，切换 provider 后须重建索引。
"""

import random

from openai import OpenAI

EMBEDDING_BASE_URLS = {
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
}
EMBEDDING_DEFAULT_MODELS = {
    "glm": "embedding-3",
    "siliconflow": "BAAI/bge-m3",
}
EMBEDDING_DIM = 1024  # 与 entries_vec 的 float[1024] 对齐；bge-m3 原生 1024
TRUNCATE_CHARS = 1500  # GLM 单条 3072 token 上限内的安全截断（bge-m3 8K，同样覆盖）


class EmbeddingUnavailable(Exception):
    """embedding 客户端不可用（未配 key 等）——调用方据此降级，非错误"""


class _OpenAICompatEmbedder:
    name = ""
    base_url = ""
    default_model = ""
    max_batch = 64
    supports_dimensions = True

    def __init__(self, api_key: str, model: str | None = None, client_factory=None):
        self.api_key = api_key
        self.model = model or self.default_model
        self._client_factory = client_factory or (
            lambda: OpenAI(base_url=self.base_url, api_key=api_key)
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        truncated = [t[:TRUNCATE_CHARS] for t in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(truncated), self.max_batch):
            batch = truncated[start : start + self.max_batch]
            kwargs: dict = {"model": self.model, "input": batch}
            if self.supports_dimensions:
                kwargs["dimensions"] = EMBEDDING_DIM
            resp = self._client_factory().embeddings.create(**kwargs)
            data = sorted(resp.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in data)
        return vectors


class GLMEmbedder(_OpenAICompatEmbedder):
    name = "glm"
    base_url = EMBEDDING_BASE_URLS["glm"]
    default_model = "embedding-3"
    max_batch = 64  # 官方单请求 input 数组上限
    # dimensions 支持 256/512/1024/2048


class SiliconFlowEmbedder(_OpenAICompatEmbedder):
    name = "siliconflow"
    base_url = EMBEDDING_BASE_URLS["siliconflow"]
    default_model = "BAAI/bge-m3"  # 免费档；Pro/BAAI/bge-m3 为付费加速版
    max_batch = 32  # 硅基流动单请求 input 数组上限
    supports_dimensions = False  # bge-m3 固定 1024 维，不支持 dimensions 参数


class FakeEmbedder:
    """确定性测试桩：同簇文本 → 相近向量，跨簇 → 近乎正交。

    clusters 形如 {"生活健康": ["感冒", "保暖", "出去玩"], "编程": ["redis"]}，
    文本包含任一关键词即归入该簇（按字典序先命中先得）；无簇命中则退化为
    纯文本哈希向量。用于验证零词面重合下的语义召回链路。
    """

    def __init__(
        self,
        clusters: dict[str, list[str]] | None = None,
        dimensions: int = EMBEDDING_DIM,
    ):
        self.clusters = dict(sorted((clusters or {}).items()))
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        noise = _unit_vector(f"text:{text}", self.dimensions)
        cluster = self._cluster_of(text)
        if cluster is None:
            return noise
        base = _unit_vector(f"cluster:{cluster}", self.dimensions)
        blended = [0.9 * b + 0.1 * n for b, n in zip(base, noise)]
        norm = sum(x * x for x in blended) ** 0.5
        return [x / norm for x in blended]

    def _cluster_of(self, text: str) -> str | None:
        lowered = text.lower()
        for name, words in self.clusters.items():
            if any(word.lower() in lowered for word in words):
                return name
        return None


def _unit_vector(seed: str, dimensions: int) -> list[float]:
    # random.Random(str) 内部走 sha512 播种，跨进程/跨平台确定
    rng = random.Random(seed)
    raw = [rng.random() for _ in range(dimensions)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]

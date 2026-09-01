"""Embedder 客户端行为：批量切分 / dimensions 差异 / 截断 / 顺序还原（不联网）"""

from types import SimpleNamespace

from kate_cortex.providers.embedding import GLMEmbedder, SiliconFlowEmbedder


class FakeEmbeddingsAPI:
    """记录请求参数；按 index 逆序返回，验证 embed() 会重排"""

    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        data = [
            SimpleNamespace(index=i, embedding=[0.1, 0.2, 0.3, 0.4])
            for i in range(len(kwargs["input"]))
        ]
        return SimpleNamespace(data=list(reversed(data)))


def make_embedder(cls, **kwargs):
    api = FakeEmbeddingsAPI()
    embedder = cls(api_key="sk-test", client_factory=lambda: SimpleNamespace(embeddings=api), **kwargs)
    return embedder, api


class TestGLMEmbedder:
    def test_default_model_and_dimensions_param(self):
        embedder, api = make_embedder(GLMEmbedder)
        assert embedder.model == "embedding-3"

        embedder.embed(["文本"])

        assert api.calls[0]["dimensions"] == 1024
        assert api.calls[0]["model"] == "embedding-3"

    def test_batches_by_64(self):
        embedder, api = make_embedder(GLMEmbedder)

        embedder.embed([f"文本{i}" for i in range(70)])

        assert [len(c["input"]) for c in api.calls] == [64, 6]

    def test_preserves_input_order(self):
        embedder, api = make_embedder(GLMEmbedder)  # 假 API 逆序返回

        vectors = embedder.embed(["a", "b", "c"])

        assert len(vectors) == 3
        assert all(v == [0.1, 0.2, 0.3, 0.4] for v in vectors)


class TestSiliconFlowEmbedder:
    def test_default_model_and_no_dimensions_param(self):
        embedder, api = make_embedder(SiliconFlowEmbedder)
        assert embedder.model == "BAAI/bge-m3"

        embedder.embed(["文本"])

        assert "dimensions" not in api.calls[0]  # bge-m3 不支持该参数
        assert api.calls[0]["model"] == "BAAI/bge-m3"

    def test_batches_by_32(self):
        embedder, api = make_embedder(SiliconFlowEmbedder)

        embedder.embed([f"文本{i}" for i in range(40)])

        assert [len(c["input"]) for c in api.calls] == [32, 8]


class TestTruncation:
    def test_truncates_each_text_to_limit(self):
        embedder, api = make_embedder(GLMEmbedder)

        embedder.embed(["长" * 2000, "短"])

        assert len(api.calls[0]["input"][0]) == 1500
        assert api.calls[0]["input"][1] == "短"

    def test_explicit_model_overrides_default(self):
        embedder, api = make_embedder(GLMEmbedder, model="embedding-2")

        embedder.embed(["文本"])

        assert api.calls[0]["model"] == "embedding-2"

from kate_cortex.chat.prompts import build_system_prompt
from kate_cortex.chat.rag import retrieve


class TestRetrieve:
    def test_returns_top3_snippets_truncated(self, storage):
        for i in range(5):
            storage.create_entry(
                title=f"连接池调优方案 {i}",
                type="howto",
                tags=["python"],
                source="manual",
                content=f"连接池参数 max_overflow={i}。" + "细节" * 400,
            )

        snippets = retrieve(storage, "连接池 max_overflow")

        assert len(snippets) == 3
        assert all(len(s.content) <= 500 for s in snippets)
        assert all(s.entry_id.startswith("kc_") for s in snippets)
        assert snippets[0].title.startswith("连接池调优方案")

    def test_no_match_returns_empty(self, storage):
        storage.create_entry(
            title="Redis 笔记", type="note", tags=[], source="manual", content="内容"
        )
        assert retrieve(storage, "量子纠缠实验") == []


class TestBuildSystemPrompt:
    def test_contains_persona_and_tool_rules(self):
        prompt = build_system_prompt(None)
        assert "Kate" in prompt
        assert "save_knowledge" in prompt
        assert "suggest_save" in prompt

    def test_injects_knowledge_section(self, storage):
        storage.create_entry(
            title="连接池调优方案",
            type="howto",
            tags=["python"],
            source="manual",
            content="max_size 设为 20。",
        )
        snippets = retrieve(storage, "连接池调优")

        prompt = build_system_prompt(snippets)

        assert "用户知识库" in prompt
        assert "连接池调优方案" in prompt
        assert "max_size 设为 20" in prompt

    def test_no_knowledge_omits_section(self):
        prompt = build_system_prompt(None)
        assert "## 用户知识库参考" not in prompt

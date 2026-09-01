from kate_cortex.chat.prompts import build_system_prompt
from kate_cortex.chat.rag import retrieve, user_profile


class TestRetrieve:
    def test_returns_top3_snippets_truncated(self, storage):
        for i in range(5):
            storage.create_entry(
                title=f"连接池调优方案 {i}",
                source="manual",
                content=f"连接池参数 max_overflow={i}。" + "细节" * 400,
            )

        snippets = retrieve(storage, "连接池 max_overflow")

        assert len(snippets) == 3
        assert all(len(s.content) <= 500 for s in snippets)
        assert all(s.entry_id.startswith("kc_") for s in snippets)
        assert snippets[0].title.startswith("连接池调优方案")

    def test_no_match_returns_empty(self, storage):
        storage.create_entry(title="Redis 笔记", source="manual", content="内容")
        assert retrieve(storage, "量子纠缠实验") == []


class TestHybridRetrieve:
    """FTS + 向量 RRF 融合（VECTOR_SEARCH_PLAN §5）"""

    def test_semantic_recall_across_word_gap(self, vector_storage):
        """验收用例：零词面重合时必须靠向量召回（纯 FTS 下必空手而归）"""
        storage, _ = vector_storage
        storage.create_entry(
            title="感冒护理记录",
            source="manual",
            content="感冒了，医生叮嘱出行注意保暖，多喝热水。",
        )
        storage.create_entry(
            title="Redis pipeline 踩坑",
            source="manual",
            content="pipeline 事务模式下不返回结果。",
        )

        snippets = retrieve(storage, "明天出去玩要准备什么")

        assert snippets, "零词面重合，向量通道必须召回"
        assert snippets[0].title == "感冒护理记录"

    def test_rrf_boosts_dual_channel_hit(self, vector_storage):
        """FTS 与向量双通道同时命中的条目排最前"""
        storage, _ = vector_storage
        dual = storage.create_entry(
            title="出行准备清单",
            source="manual",
            content="看天气，备好衣物。",
        )
        storage.create_entry(
            title="感冒护理记录",
            source="manual",
            content="感冒了，注意保暖。",
        )

        snippets = retrieve(storage, "出行准备")

        assert snippets[0].entry_id == dual.id

    def test_vector_failure_falls_back_to_fts(self, vector_storage, monkeypatch):
        storage, index = vector_storage
        storage.create_entry(title="连接池调优", source="manual", content="max_size 20")

        def boom(text, limit=10):
            raise RuntimeError("embedding down")

        monkeypatch.setattr(index, "query", boom)

        snippets = retrieve(storage, "连接池调优")

        assert [s.title for s in snippets] == ["连接池调优"]


class TestBuildSystemPrompt:
    def test_contains_persona_and_tool_rules(self):
        prompt = build_system_prompt(None)
        assert "Kate" in prompt
        assert "save_knowledge" in prompt
        assert "suggest_save" in prompt

    def test_injects_knowledge_section(self, storage):
        storage.create_entry(
            title="连接池调优方案",
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

    def test_injects_collections_section(self):
        prompt = build_system_prompt(None, None, ["金融", "情感"])
        assert "## 知识库合集" in prompt
        assert "金融" in prompt and "情感" in prompt

    def test_no_collections_omits_section(self):
        prompt = build_system_prompt(None, None, [])
        assert "## 知识库合集" not in prompt


class TestUserProfile:
    def test_returns_only_entries_in_profile_collection(self, storage):
        storage.create_entry(
            title="用户教育背景",
            source="manual",
            content="软件工程学生。",
            collections=["个人信息"],
        )
        storage.create_entry(
            title="连接池调优",
            source="manual",
            content="max_size 设为 20。",
        )

        profile = user_profile(storage)

        assert [s.title for s in profile] == ["用户教育背景"]

    def test_prompt_contains_profile_even_without_rag(self, storage):
        storage.create_entry(
            title="用户教育背景",
            source="manual",
            content="软件工程学生。",
            collections=["个人信息"],
        )
        profile = user_profile(storage)

        prompt = build_system_prompt(None, profile)

        assert "## 用户档案" in prompt
        assert "软件工程学生" in prompt
        assert "## 用户知识库参考" not in prompt

    def test_no_profile_omits_section(self):
        prompt = build_system_prompt(None, None)
        assert "## 用户档案" not in prompt

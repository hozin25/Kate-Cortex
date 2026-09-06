"""MCP 服务端：工具函数行为 + MCPServer 注册验证（不启 stdio）"""

import asyncio

from kate_cortex.db import connect as db_connect
from kate_cortex.mcp_server import (
    TOOL_NAMES,
    create_server,
    get_entry,
    list_collections,
    recall_memory,
    save_knowledge,
    save_memory,
    search_knowledge,
)
from kate_cortex.search import Search
from kate_cortex.storage import Storage


def make_storage(env) -> Storage:
    database = db_connect(env.db_path)
    return Storage(config=env, db=database, search=Search(database.conn))


class TestSearchAndGet:
    def test_search_hits_chinese_keyword(self, env):
        storage = make_storage(env)
        storage.create_entry(
            title="Redis pipeline 踩坑", source="manual", content="事务模式不返回结果。"
        )

        results = search_knowledge(storage, "pipeline 事务")

        assert len(results) == 1
        assert results[0]["title"] == "Redis pipeline 踩坑"
        assert "entry_id" in results[0] and "slug" in results[0]

    def test_search_no_match_returns_empty(self, env):
        storage = make_storage(env)
        assert search_knowledge(storage, "量子纠缠") == []

    def test_get_entry_by_id_and_slug_with_backlinks(self, env):
        storage = make_storage(env)
        target = storage.create_entry(
            title="FastAPI middleware", source="manual", content="顺序与依赖注入。"
        )
        storage.create_entry(
            title="引用方", source="manual", content=f"参见 [[{target.slug}]]"
        )

        by_id = get_entry(storage, target.id)
        by_slug = get_entry(storage, target.slug)

        assert by_id["title"] == by_slug["title"] == "FastAPI middleware"
        # 反向链接 = 引用了本条目的「引用方」
        assert [b["title"] for b in by_id["backlinks"]] == ["引用方"]

    def test_get_entry_missing_raises(self, env):
        storage = make_storage(env)
        try:
            get_entry(storage, "nope")
            raise AssertionError("应当抛 ValueError")
        except ValueError as exc:
            assert "不存在" in str(exc)


class TestSaveAndList:
    def test_save_knowledge_marks_source_import(self, env):
        storage = make_storage(env)

        result = save_knowledge(storage, "任务总结", "修复了 pipeline 问题。", ["编程"])

        assert result["entry_id"].startswith("kc_")
        assert result["collections"] == ["编程"]
        entry = storage.get_entry(result["entry_id"])
        assert entry.source == "import"  # 外部写入打标，与 manual/chat 区分
        assert (env.vault_path / entry.file_path).is_file()

    def test_list_collections_counts(self, env):
        storage = make_storage(env)
        save_knowledge(storage, "条目一", "内容", ["编程"])
        save_knowledge(storage, "条目二", "内容", ["编程"])

        names = {c["name"]: c["count"] for c in list_collections(storage)}
        assert names["编程"] == 2


class TestMemoryTools:
    def test_save_and_recall_memory(self, env):
        storage = make_storage(env)
        save_memory(storage, "用 Windows 开发", "用户在 Windows 10 上开发", ["环境", "windows"], 4)

        result = recall_memory(storage, ["windows", "开发环境"])

        assert len(result["memories"]) == 1
        assert result["memories"][0]["importance"] == 4

    def test_recall_no_overlap_returns_empty(self, env):
        storage = make_storage(env)
        save_memory(storage, "感冒了", "注意保暖", ["健康"], 3)
        assert recall_memory(storage, ["编程", "redis"])["memories"] == []

    def test_save_memory_replace_updates_in_place(self, env):
        storage = make_storage(env)
        first = save_memory(storage, "感冒了", "8月30日感冒", ["健康"], 4)

        second = save_memory(storage, "感冒痊愈", "感冒已好", ["健康"], 2, replaces_entry_id=first["entry_id"])

        assert second["replaced"] is True
        assert second["entry_id"] == first["entry_id"]  # 原地更新不新建
        memories = recall_memory(storage, ["健康"])["memories"]
        assert [m["title"] for m in memories] == ["感冒痊愈"]

    def test_invalid_importance_rejected(self, env):
        storage = make_storage(env)
        try:
            save_memory(storage, "x", "y", ["z"], 9)
            raise AssertionError("应当抛 ValueError")
        except ValueError:
            pass


class TestServerRegistration:
    def test_registers_all_tools_with_descriptions(self, env):
        storage = make_storage(env)
        server = create_server(storage)

        tools = asyncio.run(server.list_tools())

        assert tuple(t.name for t in tools) == TOOL_NAMES
        assert all(t.description for t in tools)  # description 是 agent 调用依据，必填

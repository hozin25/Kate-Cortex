"""Kate-Cortex MCP 服务端：把知识库/记忆能力暴露给外部 AI 工具（stdio）

README「桌面端 + MCP 双形态」的服务端侧（v0.3 路线）：Claude Code / Cursor
等编码 agent 经 MCP 检索与沉淀用户的个人知识库。与 MCP 客户端
（mcp_client.py，Kate 用别人的工具）方向相反：这里是别人用你的数据。

独立进程，与 1738 HTTP 服务并存（SQLite WAL 支持多进程读写同一库）：

    uv run kate-cortex-mcp                          # 或 uv run python -m kate_cortex.mcp_server

Claude Code 接入（--project 指向后端目录）：

    claude mcp add kate-cortex -s user -- uv run --project D:\\workspace\\Kate-Cortex\\backend python -m kate_cortex.mcp_server

写入约束：只增不改（无 update/delete 工具），与记忆机制同一 append-only
原则；外部写入一律 source=import 打标，与 manual / chat 区分可追溯。
"""

from .chat.memory import MEMORY_COLLECTION, recall as recall_memories
from .chat.rag import retrieve
from .config import load_config
from .db import connect as db_connect
from .providers.embedding import make_embedder_factory
from .search import Search
from .settings import SettingsService
from .storage import Storage
from .vectors import VectorIndex

TOOL_NAMES = (
    "search_knowledge",
    "get_entry",
    "save_knowledge",
    "list_collections",
    "recall_memory",
    "save_memory",
)


def build_storage() -> Storage:
    """独立进程装配：与 main.create_app 相同的依赖链（复用 vault 与 SQLite）"""
    config = load_config()
    database = db_connect(config.db_path)
    vectors = (
        VectorIndex(database.conn, make_embedder_factory(SettingsService(database.conn)))
        if database.vec_enabled
        else None
    )
    return Storage(
        config=config, db=database, search=Search(database.conn), vectors=vectors
    )


# ── 工具实现（纯函数便于单测；MCP 层只做薄封装） ──


def search_knowledge(storage, query: str, limit: int = 5) -> list[dict]:
    """混合检索（FTS 字面 + 向量语义，与 Kate 对话同一条 RAG 链路）"""
    snippets = retrieve(storage, query, limit=limit)
    return [
        {
            "entry_id": s.entry_id,
            "title": s.title,
            "slug": s.slug,
            "content": s.content,
        }
        for s in snippets
    ]


def get_entry(storage, id_or_slug: str) -> dict:
    entry = storage.get_entry(id_or_slug)
    if entry is None:
        raise ValueError(f"条目不存在: {id_or_slug}")
    return {
        "entry_id": entry.id,
        "slug": entry.slug,
        "title": entry.title,
        "content": entry.content,
        "collections": entry.collections,
        "source": entry.source,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "backlinks": [
            {"entry_id": b.id, "title": b.title, "slug": b.slug}
            for b in storage.backlinks(entry.id)
        ],
    }


def save_knowledge(
    storage, title: str, content_markdown: str, collections: list[str] | None = None
) -> dict:
    entry = storage.create_entry(
        title=title,
        source="import",
        content=content_markdown,
        collections=collections or [],
    )
    return {
        "entry_id": entry.id,
        "slug": entry.slug,
        "title": entry.title,
        "collections": entry.collections,
    }


def list_collections(storage) -> list[dict]:
    return [{"name": name, "count": count} for name, count in storage.list_collections()]


def recall_memory(storage, keywords: list[str]) -> dict:
    hits = recall_memories(storage, keywords)
    return {
        "memories": [
            {
                "entry_id": m.entry_id,
                "title": m.title,
                "content": m.content,
                "keywords": m.keywords,
                "importance": m.importance,
                "created_at": m.created_at,
            }
            for m in hits
        ]
    }


def save_memory(
    storage,
    title: str,
    content: str,
    keywords: list[str],
    importance: int = 3,
    replaces_entry_id: str | None = None,
) -> dict:
    if not 1 <= importance <= 5:
        raise ValueError("importance 取值 1-5")
    if replaces_entry_id:
        entry = storage.update_entry(
            replaces_entry_id,
            title=title,
            content=content,
            collections=[MEMORY_COLLECTION],
            keywords=keywords,
            importance=importance,
        )
    else:
        entry = storage.create_entry(
            title=title,
            source="import",
            content=content,
            collections=[MEMORY_COLLECTION],
            keywords=keywords,
            importance=importance,
        )
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "keywords": entry.keywords,
        "replaced": bool(replaces_entry_id),
    }


# ── MCP 装配（mcp SDK 2.x：MCPServer + tool 装饰器） ──


def create_server(storage) -> "object":
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="kate-cortex",
        title="Kate-Cortex 个人知识库",
        description="个人编程知识库与用户记忆：语义检索、条目读取、知识沉淀、记忆召回",
        instructions=(
            "动手写代码前先 search_knowledge 查用户的历史踩坑与决策；"
            "任务出现值得长期保留的结论时用 save_knowledge 沉淀（合集只能从 "
            "list_collections 结果中选，没有合适的就不传）；"
            "涉及用户个人偏好/环境/近况时先 recall_memory。"
        ),
    )

    @server.tool(
        name="search_knowledge",
        description=(
            "检索用户的个人知识库（FTS 字面 + 向量语义混合）。写代码、做技术决策前"
            "先查：项目历史踩坑、选型理由、修复经验。返回条目标题与正文片段。"
        ),
    )
    def _search(query: str, limit: int = 5) -> list[dict]:
        return search_knowledge(storage, query, limit)

    @server.tool(
        name="get_entry",
        description="读取单条知识的完整内容（支持 entry_id 或 slug），含元数据与反向链接。",
    )
    def _get(id_or_slug: str) -> dict:
        return get_entry(storage, id_or_slug)

    @server.tool(
        name="save_knowledge",
        description=(
            "把有长期价值的内容沉淀进用户知识库（markdown）。适用：任务总结、"
            "踩坑结论、决策记录。collections 只能从 list_collections 结果中选，"
            "没有合适的合集可不传。"
        ),
    )
    def _save(title: str, content_markdown: str, collections: list[str] | None = None) -> dict:
        return save_knowledge(storage, title, content_markdown, collections)

    @server.tool(
        name="list_collections",
        description="列出知识库全部合集及条目数（save_knowledge 选合集前调用）。",
    )
    def _list() -> list[dict]:
        return list_collections(storage)

    @server.tool(
        name="recall_memory",
        description=(
            "召回关于用户本人的记忆（偏好、开发环境、健康、进行中的事）。"
            "keywords 传 3-6 个场景词：从当前话题提炼并联想相关场景。"
        ),
    )
    def _recall(keywords: list[str]) -> dict:
        return recall_memory(storage, keywords)

    @server.tool(
        name="save_memory",
        description=(
            "记住关于用户本人的耐久事实（稳定偏好、开发环境、重要事项）。"
            "一条只记一个原子事实，keywords 给 3-8 个场景触发词。"
            "旧事实变化时传 replaces_entry_id 覆盖更新而非新建。"
        ),
    )
    def _save_mem(
        title: str,
        content: str,
        keywords: list[str],
        importance: int = 3,
        replaces_entry_id: str | None = None,
    ) -> dict:
        return save_memory(storage, title, content, keywords, importance, replaces_entry_id)

    return server


def main() -> None:
    server = create_server(build_storage())
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

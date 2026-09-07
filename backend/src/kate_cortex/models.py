"""Pydantic 请求/响应模型"""

from typing import Literal

from pydantic import BaseModel, Field

EntrySource = Literal["manual", "chat", "import"]
ProviderName = Literal["deepseek", "glm", "glm-coding", "siliconflow", "modelscope"]
EmbeddingProviderName = Literal["glm", "siliconflow"]


class EntryCreate(BaseModel):
    title: str = Field(min_length=1)
    collections: list[str] = Field(default_factory=list)
    content: str = ""
    source: EntrySource = "manual"
    language: str | None = None
    conversation_id: str | None = None
    slug: str | None = None
    keywords: list[str] = Field(default_factory=list)
    importance: int | None = Field(default=None, ge=1, le=5)


class EntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    collections: list[str] | None = None
    language: str | None = None
    keywords: list[str] | None = None
    importance: int | None = Field(default=None, ge=1, le=5)


class EntryOut(BaseModel):
    id: str
    slug: str
    title: str
    collections: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    content: str
    file_path: str
    created_at: str
    updated_at: str
    keywords: list[str] = Field(default_factory=list)
    importance: int | None = None


class EntrySummaryOut(BaseModel):
    id: str
    slug: str
    title: str
    collections: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    created_at: str
    updated_at: str
    keywords: list[str] = Field(default_factory=list)
    importance: int | None = None


class EntryListOut(BaseModel):
    items: list[EntrySummaryOut]
    total: int


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1)


class CollectionRename(BaseModel):
    name: str = Field(min_length=1)


class CollectionOut(BaseModel):
    name: str
    count: int


class SyncReportOut(BaseModel):
    unindexed: list[str]
    missing_files: list[str]


class ReindexOut(BaseModel):
    indexed: int
    unindexed_before: list[str]
    missing_files: list[str]


class SessionCreate(BaseModel):
    provider: ProviderName
    model: str | None = None
    title: str | None = None


class SessionUpdate(BaseModel):
    """重命名 / 切换模型共用的 PATCH 载荷，三字段至少给一个"""

    title: str | None = Field(default=None, min_length=1)
    provider: ProviderName | None = None
    model: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str | None
    provider: str
    model: str
    created_at: str
    updated_at: str
    preview: str = ""


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tool_calls: list | None = None
    knowledge_refs: list | None = None
    created_at: str


class ChatRequest(BaseModel):
    content: str = ""  # 图片-only 消息允许空文本（与 images 至少有一）
    images: list[str] = Field(default_factory=list, max_length=4)  # data URL
    rag_enabled: bool | None = None


class ChatRegenerate(BaseModel):
    rag_enabled: bool | None = None


class ChatResend(BaseModel):
    """编辑用户消息并重发：content 为新文本；keep_images=True 时保留原消息的图片引用"""

    content: str = Field(min_length=1)
    rag_enabled: bool | None = None
    keep_images: bool = True


class SettingsUpdate(BaseModel):
    """extra=forbid：vault_path 等无效字段直接 422，而不是静默忽略造成
    "看似配置成功"的误导（诚实原则）"""

    model_config = {"extra": "forbid"}

    provider_keys: dict[str, str] | None = None
    default_provider: ProviderName | None = None
    default_model: str | None = None
    rag_default: bool | None = None
    memory_enabled: bool | None = None
    embedding_provider: EmbeddingProviderName | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    mcp_url: str | None = None
    export_dir: str | None = None


class SettingsOut(BaseModel):
    provider_keys: dict[str, str]
    default_provider: str
    default_model: str
    rag_default: bool
    memory_enabled: bool
    vault_path: str | None  # 当前实际生效的 vault 路径（来自 config，非存储值）
    embedding_provider: str
    embedding_model: str
    embedding_api_key: str | None
    mcp_url: str | None
    export_dir: str | None


class EmbeddingStatusOut(BaseModel):
    available: bool
    indexed: int
    total: int


class EmbeddingRebuildOut(BaseModel):
    indexed: int
    total: int
    failed: int


ProjectionMethod = Literal["tsne", "pca", "insufficient", "unavailable"]


class ProjectionPointOut(BaseModel):
    entry_id: str
    title: str
    collections: list[str]
    source: str
    x: float
    y: float
    z: float


class ProjectionOut(BaseModel):
    available: bool
    method: ProjectionMethod
    n: int
    computed_ms: int
    points: list[ProjectionPointOut]


class ProviderTestIn(BaseModel):
    provider: ProviderName


class TrashOut(BaseModel):
    id: str
    title: str
    file_path: str
    deleted_at: str

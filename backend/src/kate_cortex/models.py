"""Pydantic 请求/响应模型"""

from typing import Literal

from pydantic import BaseModel, Field

EntrySource = Literal["manual", "chat", "import"]
ProviderName = Literal["deepseek", "glm", "glm-coding"]


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


class SessionRename(BaseModel):
    title: str = Field(min_length=1)


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
    content: str = Field(min_length=1)
    rag_enabled: bool | None = None


class SettingsUpdate(BaseModel):
    provider_keys: dict[str, str] | None = None
    default_provider: ProviderName | None = None
    default_model: str | None = None
    rag_default: bool | None = None
    memory_enabled: bool | None = None
    vault_path: str | None = None


class SettingsOut(BaseModel):
    provider_keys: dict[str, str]
    default_provider: str
    default_model: str
    rag_default: bool
    memory_enabled: bool
    vault_path: str | None


class ProviderTestIn(BaseModel):
    provider: ProviderName

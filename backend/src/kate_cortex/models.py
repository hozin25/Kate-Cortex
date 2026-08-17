"""Pydantic 请求/响应模型"""

from typing import Literal

from pydantic import BaseModel, Field

EntryType = Literal["note", "clip", "decision", "howto"]
EntrySource = Literal["manual", "chat", "import"]


class EntryCreate(BaseModel):
    title: str = Field(min_length=1)
    type: EntryType
    tags: list[str] = Field(default_factory=list)
    content: str = ""
    source: EntrySource = "manual"
    language: str | None = None
    conversation_id: str | None = None
    slug: str | None = None


class EntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    type: EntryType | None = None
    language: str | None = None


class EntryOut(BaseModel):
    id: str
    slug: str
    title: str
    type: str
    tags: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    content: str
    file_path: str
    created_at: str
    updated_at: str


class EntrySummaryOut(BaseModel):
    id: str
    slug: str
    title: str
    type: str
    tags: list[str]
    source: str
    language: str | None
    conversation_id: str | None
    created_at: str
    updated_at: str


class EntryListOut(BaseModel):
    items: list[EntrySummaryOut]
    total: int


class TagOut(BaseModel):
    name: str
    count: int


class SyncReportOut(BaseModel):
    unindexed: list[str]
    missing_files: list[str]


class ReindexOut(BaseModel):
    indexed: int
    unindexed_before: list[str]
    missing_files: list[str]

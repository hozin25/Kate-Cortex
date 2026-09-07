"""对话数据层：会话 CRUD、消息追加、标题自动生成"""

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime

PREVIEW_LENGTH = 60
TITLE_LENGTH = 20


class SessionNotFound(Exception):
    pass


class MessageNotFound(Exception):
    pass


@dataclass
class Session:
    id: str
    title: str | None
    provider: str
    model: str
    created_at: str
    updated_at: str
    preview: str = ""


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    tool_calls: list | None
    knowledge_refs: list | None
    created_at: str


class ChatService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_session(
        self, provider: str, model: str, title: str | None = None
    ) -> Session:
        now = _now()
        session = Session(
            id=f"kc_conv_{uuid.uuid4().hex[:12]}",
            title=title,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO conversations (id, title, provider, model, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id, session.title, session.provider,
                    session.model, session.created_at, session.updated_at,
                ),
            )
        return session

    def get_session(self, session_id: str) -> Session | None:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (session_id,)
        ).fetchone()
        return self._to_session(row) if row else None

    def list_sessions(self, limit: int = 100) -> list[Session]:
        rows = self.conn.execute(
            "WITH last_msg AS ("
            "  SELECT conversation_id, content,"
            "    ROW_NUMBER() OVER (PARTITION BY conversation_id"
            "      ORDER BY created_at DESC, rowid DESC) AS rn"
            "  FROM messages"
            ")"
            "SELECT c.*, lm.content AS preview"
            " FROM conversations c"
            " LEFT JOIN last_msg lm ON lm.conversation_id = c.id AND lm.rn = 1"
            " ORDER BY c.updated_at DESC, c.rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._to_session(row) for row in rows]

    def rename_session(self, session_id: str, title: str) -> Session:
        if self.get_session(session_id) is None:
            raise SessionNotFound(session_id)
        with self.conn:
            self.conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), session_id),
            )
        session = self.get_session(session_id)
        assert session is not None
        return session

    def set_session_model(self, session_id: str, provider: str, model: str) -> Session:
        """对话中途切换模型：只影响之后的请求，历史消息与上下文保持连续"""
        if self.get_session(session_id) is None:
            raise SessionNotFound(session_id)
        with self.conn:
            self.conn.execute(
                "UPDATE conversations SET provider = ?, model = ? WHERE id = ?",
                (provider, model, session_id),
            )
        session = self.get_session(session_id)
        assert session is not None
        return session

    def delete_session(self, session_id: str) -> None:
        if self.get_session(session_id) is None:
            raise SessionNotFound(session_id)
        with self.conn:
            self.conn.execute("DELETE FROM conversations WHERE id = ?", (session_id,))

    def list_messages(self, session_id: str) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ?"
            " ORDER BY created_at, rowid",
            (session_id,),
        ).fetchall()
        return [self._to_message(row) for row in rows]

    def get_message(self, message_id: str) -> Message | None:
        row = self.conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        return self._to_message(row) if row else None

    def last_message_of_role(self, session_id: str, role: str) -> Message | None:
        row = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND role = ?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return self._to_message(row) if row else None

    def update_message(self, message_id: str, content: str) -> Message:
        message = self.get_message(message_id)
        if message is None:
            raise MessageNotFound(message_id)
        with self.conn:
            self.conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?", (content, message_id)
            )
        updated = self.get_message(message_id)
        assert updated is not None
        return updated

    def delete_message(self, message_id: str) -> None:
        if self.get_message(message_id) is None:
            raise MessageNotFound(message_id)
        with self.conn:
            self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def delete_messages_after(self, session_id: str, message_id: str) -> int:
        """删除该消息之后的所有消息（严格之后，不含自身）。排序键与
        list_messages 一致（created_at, rowid），返回删除条数"""
        row = self.conn.execute(
            "SELECT conversation_id, created_at, rowid FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if row is None or row["conversation_id"] != session_id:
            raise MessageNotFound(message_id)
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?"
                " AND (created_at > ? OR (created_at = ? AND rowid > ?))",
                (session_id, row["created_at"], row["created_at"], row["rowid"]),
            )
            return cursor.rowcount

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list | None = None,
        knowledge_refs: list | None = None,
    ) -> Message:
        if self.get_session(session_id) is None:
            raise SessionNotFound(session_id)
        message = Message(
            id=f"kc_msg_{uuid.uuid4().hex[:12]}",
            conversation_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            knowledge_refs=knowledge_refs,
            created_at=_now(),
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content,"
                " tool_calls, knowledge_refs, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message.id, message.conversation_id, message.role,
                    message.content,
                    _dump_json(tool_calls), _dump_json(knowledge_refs),
                    message.created_at,
                ),
            )
            self.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (message.created_at, session_id),
            )
        return message

    def ensure_title(self, session_id: str, first_message: str) -> None:
        session = self.get_session(session_id)
        if session is None or session.title:
            return
        with self.conn:
            self.conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (first_message.strip()[:TITLE_LENGTH], session_id),
            )

    def _to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            title=row["title"],
            provider=row["provider"],
            model=row["model"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            preview=(row["preview"] or "")[:PREVIEW_LENGTH] if "preview" in row.keys() else "",
        )

    def _to_message(self, row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            tool_calls=_load_json(row["tool_calls"]),
            knowledge_refs=_load_json(row["knowledge_refs"]),
            created_at=row["created_at"],
        )


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _dump_json(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _load_json(value: str | None):
    return json.loads(value) if value else None

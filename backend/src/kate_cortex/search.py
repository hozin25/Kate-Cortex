"""FTS5 + jieba 预分词中文检索（DESIGN.md §7）"""

import sqlite3
from typing import NamedTuple

import jieba


class SearchHit(NamedTuple):
    entry_id: str
    title: str | None
    snippet: str


class Search:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def tokenize(self, text: str) -> str:
        return " ".join(t for t in jieba.cut(text) if t.strip())

    def match_expr(self, keywords: str) -> str:
        tokens = [t for t in jieba.cut(keywords) if _is_word(t)]
        if not tokens:
            return ""
        return " AND ".join(f'"{t}"' for t in tokens)

    def index_entry(
        self, entry_id: str, title: str, content: str, tags: list[str]
    ) -> None:
        self.remove_entry(entry_id)
        self._conn.execute(
            "INSERT INTO entries_fts (title_tokens, content_tokens, tag_tokens, entry_id)"
            " VALUES (?, ?, ?, ?)",
            (
                self.tokenize(title),
                self.tokenize(content),
                " ".join(self.tokenize(tag) for tag in tags),
                entry_id,
            ),
        )

    def remove_entry(self, entry_id: str) -> None:
        self._conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))

    def query(self, keywords: str, limit: int = 20) -> list[SearchHit]:
        expr = self.match_expr(keywords)
        if not expr:
            return []
        rows = self._conn.execute(
            "SELECT f.entry_id, e.title, substr(f.content_tokens, 1, 120)"
            " FROM entries_fts f LEFT JOIN entries e ON e.id = f.entry_id"
            " WHERE entries_fts MATCH ?"
            " ORDER BY rank LIMIT ?",
            (expr, limit),
        ).fetchall()
        return [
            SearchHit(entry_id=row[0], title=row[1], snippet=_detokenize(row[2]))
            for row in rows
        ]


def _is_word(token: str) -> bool:
    return any(ch.isalnum() for ch in token)


def _detokenize(tokens: str | None) -> str:
    if not tokens:
        return ""
    return tokens.replace(" ", "")[:80]

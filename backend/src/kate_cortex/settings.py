"""设置读写：provider key / 默认模型 / RAG 默认 / vault 路径"""

import json
import sqlite3

DEFAULTS = {
    "provider_keys": {},
    "default_provider": "deepseek",
    "default_model": "deepseek-chat",
    "rag_default": True,
    "memory_enabled": True,
    "vault_path": None,
    "embedding_provider": "glm",  # glm | siliconflow
    "embedding_model": "embedding-3",
    "embedding_api_key": None,  # siliconflow 必填；glm 为空时回退 provider_keys["glm"]
}

KNOWN_PROVIDERS = {"deepseek", "glm", "glm-coding"}


class SettingsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_all(self) -> dict:
        result = dict(DEFAULTS)
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            result[row["key"]] = json.loads(row["value"])
        return result

    def update(self, patch: dict) -> dict:
        for provider in patch.get("provider_keys", {}):
            if provider not in KNOWN_PROVIDERS:
                raise ValueError(f"未知 provider: {provider}")
        current = self.get_all()
        merged = {**current, **{k: v for k, v in patch.items() if v is not None}}
        with self.conn:
            for key, value in merged.items():
                self.conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        return self.get_all()

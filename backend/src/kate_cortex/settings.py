"""设置读写：provider key / 默认模型 / RAG 默认 / vault 路径"""

import json
import sqlite3

DEFAULTS = {
    "provider_keys": {},
    "default_provider": "glm",  # 免费档 glm-4.7-flash 开箱即用
    "default_model": "glm-4.7-flash",
    "rag_default": True,
    "memory_enabled": True,
    "vault_path": None,
    "embedding_provider": "glm",  # glm | siliconflow
    "embedding_model": "embedding-3",
    "embedding_api_key": None,  # siliconflow 必填；glm 为空时回退 provider_keys["glm"]
    "mcp_url": None,  # MCP Streamable HTTP 端点（含 key），如高德地图；留空停用
    "export_dir": None,  # export_markdown 导出文件夹；空则用 文档\Kate-Cortex 导出
}

KNOWN_PROVIDERS = {"deepseek", "glm", "glm-coding", "siliconflow", "modelscope"}


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

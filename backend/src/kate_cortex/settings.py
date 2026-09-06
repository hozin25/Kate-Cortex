"""设置读写：provider key / 默认模型 / RAG 默认

敏感值（provider_keys 的各 key、embedding_api_key）落库前经 DPAPI 加密、
读出时解密（security.py）——对调用方完全透明。历史明文由启动迁移
encrypt_existing_secrets() 就地重写。vault 路径不存设置：实际位置由
config（环境变量/默认值）决定，GET /api/settings 返回当前生效路径。
"""

import json
import sqlite3

from .security import decrypt_secret, encrypt_secret

DEFAULTS = {
    "provider_keys": {},
    "default_provider": "glm",  # 免费档 glm-4.7-flash 开箱即用
    "default_model": "glm-4.7-flash",
    "rag_default": True,
    "memory_enabled": True,
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
            if row["key"] == "vault_path":
                continue  # 历史遗留的无效设置，不再透出
            result[row["key"]] = json.loads(row["value"])
        result["provider_keys"] = {
            name: decrypt_secret(value)
            for name, value in (result.get("provider_keys") or {}).items()
            if value
        }
        result["embedding_api_key"] = decrypt_secret(result.get("embedding_api_key"))
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
                    (key, json.dumps(self._encrypt_field(key, value), ensure_ascii=False)),
                )
        return self.get_all()

    def encrypt_existing_secrets(self) -> int:
        """启动迁移：历史明文 key 就地重写为密文（幂等，返回改写条数）"""
        changed = 0
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = 'provider_keys'"
        ).fetchone()
        if row is not None:
            keys = json.loads(row[0])
            if any(keys.values()):
                encrypted = {name: encrypt_secret(v) for name, v in keys.items()}
                if encrypted != keys:
                    with self.conn:
                        self.conn.execute(
                            "UPDATE settings SET value = ? WHERE key = 'provider_keys'",
                            (json.dumps(encrypted, ensure_ascii=False),),
                        )
                    changed += 1
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = 'embedding_api_key'"
        ).fetchone()
        if row is not None:
            stored = json.loads(row[0])
            if stored and encrypt_secret(stored) != stored:
                with self.conn:
                    self.conn.execute(
                        "UPDATE settings SET value = ? WHERE key = 'embedding_api_key'",
                        (json.dumps(encrypt_secret(stored), ensure_ascii=False),),
                    )
                changed += 1
        return changed

    @staticmethod
    def _encrypt_field(key: str, value):
        if key == "provider_keys" and isinstance(value, dict):
            return {name: encrypt_secret(v) for name, v in value.items()}
        if key == "embedding_api_key" and value:
            return encrypt_secret(value)
        return value

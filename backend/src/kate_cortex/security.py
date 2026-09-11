"""敏感值静态加密：Windows 用 DPAPI，Linux 服务器用 KATE_SECRET_KEY + Fernet。

settings 表中的 API key 以 "dpapi:"（Windows，当前 OS 用户可解密）或 "fernet:"
（服务器，KATE_SECRET_KEY 派生密钥）前缀 + base64 密文存储，防止 index.sqlite
被备份/网盘同步/拷贝时明文泄漏。非 Windows 且未配置 KATE_SECRET_KEY 时退化为
明文（本地开发环境，启动时会告警）；解密兼容历史明文值（无前缀原样返回），
启动迁移 encrypt_existing_secrets 会把明文就地重写为当前平台的密文形态。
"""

import base64
import ctypes
import hashlib
import os
import sys
from ctypes import wintypes

PREFIX_DPAPI = "dpapi:"
PREFIX_FERNET = "fernet:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1

_FERNET_PREFIXES = (PREFIX_DPAPI, PREFIX_FERNET)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _fernet():
    """KATE_SECRET_KEY（任意随机串）→ sha256 → Fernet key；未配置返回 None。
    cryptography 延迟导入：桌面 Windows 走 DPAPI 用不到它"""
    secret = os.environ.get("KATE_SECRET_KEY")
    if not secret:
        return None
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str | None) -> str | None:
    if not plain or plain.startswith(_FERNET_PREFIXES):
        return plain  # 空值与已加密值原样返回（幂等）
    if sys.platform == "win32":
        return PREFIX_DPAPI + base64.b64encode(_dpapi(True, plain.encode("utf-8"))).decode("ascii")
    fernet = _fernet()
    if fernet is not None:
        return PREFIX_FERNET + fernet.encrypt(plain.encode("utf-8")).decode("ascii")
    return plain


def decrypt_secret(stored: str | None) -> str | None:
    if not stored or not stored.startswith(_FERNET_PREFIXES):
        return stored  # 非 Windows 平台不应出现 dpapi: 密文；原样返回便于排查
    if stored.startswith(PREFIX_DPAPI):
        if sys.platform != "win32":
            return stored
        return _dpapi(False, base64.b64decode(stored[len(PREFIX_DPAPI) :])).decode("utf-8")
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("检测到 fernet: 密文但未配置 KATE_SECRET_KEY，无法解密")
    return fernet.decrypt(stored[len(PREFIX_FERNET) :].encode("ascii")).decode("utf-8")


def _dpapi(protect: bool, data: bytes) -> bytes:
    fn = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    blob_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    if not fn(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    ):
        raise OSError("DPAPI 调用失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

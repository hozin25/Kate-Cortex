"""敏感值静态加密：Windows DPAPI（CryptProtectData），仅当前 Windows 用户可解密

settings 表中的 API key 以 "dpapi:" 前缀 + base64 密文存储，防止 index.sqlite
被备份/网盘同步/拷贝时明文泄漏。非 Windows 平台退化为明文（开发环境）；
解密兼容历史明文值（无前缀原样返回），启动迁移会把明文择机重写为密文。
"""

import base64
import ctypes
import sys
from ctypes import wintypes

PREFIX = "dpapi:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def encrypt_secret(plain: str | None) -> str | None:
    if not plain or plain.startswith(PREFIX):
        return plain  # 空值与已加密值原样返回（幂等）
    if sys.platform != "win32":
        return plain
    blob = _dpapi(True, plain.encode("utf-8"))
    return PREFIX + base64.b64encode(blob).decode("ascii")


def decrypt_secret(stored: str | None) -> str | None:
    if not stored or not stored.startswith(PREFIX):
        return stored
    if sys.platform != "win32":
        return stored  # 非 Windows 平台不应出现密文；原样返回便于排查
    return _dpapi(False, base64.b64decode(stored[len(PREFIX) :])).decode("utf-8")


def _dpapi(protect: bool, data: bytes) -> bytes:
    fn = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
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

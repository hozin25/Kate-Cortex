"""多用户账号体系：users.sqlite（账号 + 会话）、scrypt 口令哈希、滑动过期会话。

仅在多用户模式（KATE_DATA_DIR 已设置）下由 main.py 装配；桌面/单用户形态
完全不触碰本模块。会话 token 只下发原文、库存 SHA256——库泄漏也拿不回
有效 cookie。过期 30 天，每次校验滑动续期。
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION_COOKIE = "kate_session"
SESSION_TTL_DAYS = 30
_RENEW_THRESHOLD = timedelta(days=1)  # 剩余不足 1 天才重写 expires_at，避免每请求写库

_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,32}$", re.UNICODE)

# scrypt 内存参数：2^14 * 8 * 128 ≈ 16MB/次，登录频率下可接受
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2**14, 8, 1, 32

_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def validate_username(username: str) -> str | None:
    """返回错误消息；None 表示合法"""
    if not _USERNAME_RE.match(username or ""):
        return "用户名需 2-32 位（中文、字母、数字、_、-）"
    return None


def validate_password(password: str) -> str | None:
    if not password or len(password) < 6 or len(password) > 128:
        return "密码需 6-128 位"
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=_DKLEN,
        )
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class UsersStore:
    """users.sqlite 的读写；单连接 + WAL，量级（个人部署的账号数）下足够"""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_USERS_SCHEMA)
        self._conn.commit()

    def register(self, username: str, password: str) -> sqlite3.Row:
        """返回新用户行；用户名重复抛 ValueError"""
        self._conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (_iso(_now()),)
        )
        user_id = f"kc_user_{secrets.token_hex(8)}"
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO users (id, username, password_hash, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (user_id, username, hash_password(password), _iso(_now())),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已被占用") from exc
        return self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    def verify_login(self, username: str, password: str) -> sqlite3.Row | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return row

    def create_session(self, user_id: str) -> tuple[str, datetime]:
        """返回 (token 明文, 过期时间)；明文只出现在 cookie，库存哈希"""
        token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=SESSION_TTL_DAYS)
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    hashlib.sha256(token.encode("ascii")).hexdigest(),
                    user_id,
                    _iso(expires),
                    _iso(_now()),
                ),
            )
        return token, expires

    def resolve_session(self, token: str) -> sqlite3.Row | None:
        """token → 用户行；顺带滑动续期并清理过期会话"""
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = self._conn.execute(
            "SELECT s.expires_at, u.* FROM sessions s"
            " JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires < _now():
            self.delete_session(token)
            return None
        if expires - _now() < _RENEW_THRESHOLD:
            with self._conn:
                self._conn.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                    (_iso(_now() + timedelta(days=SESSION_TTL_DAYS)), token_hash),
                )
        return row

    def delete_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def close(self) -> None:
        self._conn.close()


def invite_code_required() -> bool:
    return bool(os.environ.get("KATE_INVITE_CODE"))


def check_invite_code(code: str | None) -> str | None:
    """返回错误消息；None 表示通过。未配置邀请码时不需要"""
    expected = os.environ.get("KATE_INVITE_CODE")
    if not expected:
        return None
    if not code or not hmac.compare_digest(code.strip(), expected):
        return "邀请码错误"
    return None

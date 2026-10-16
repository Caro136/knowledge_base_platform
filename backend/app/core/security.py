"""安全工具：密码哈希与 JWT。

T-01 阶段先落地工具函数，T-05（认证）直接复用，避免届时改动本文件。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw_password: str) -> str:
    """生成密码哈希（bcrypt 加盐）。"""
    # bcrypt 仅处理前 72 字节，超长密码先截断，避免底层抛错
    return _pwd_context.hash(raw_password[:72])


def verify_password(raw_password: str, password_hash: str) -> bool:
    """校验密码。"""
    try:
        return _pwd_context.verify(raw_password[:72], password_hash)
    except ValueError:
        # 哈希格式异常（如脏数据）时按校验失败处理，不向上抛
        return False


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> tuple[str, int]:
    """签发 JWT。

    :return: (token, 有效期秒数)
    """
    expire_seconds = settings.JWT_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expire_seconds)).timestamp()),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expire_seconds


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 JWT，失败（过期/签名不符/格式错误）返回 None。"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

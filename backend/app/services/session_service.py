"""会话与消息存储（T-24）。

会话所有权严格绑定 ``user_id``：所有查询都带该条件，
从存储层杜绝「越权读取他人会话」的可能（FR-29 的可见范围默认取「仅本人」）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.mongo import get_db

logger = logging.getLogger(__name__)

COLLECTION = "chat_session"


def _col():
    return get_db()[COLLECTION]


def ensure_indexes() -> None:
    """创建索引（幂等，启动时调用一次）。"""
    try:
        _col().create_index([("session_id", 1)], unique=True)
        _col().create_index([("user_id", 1), ("updated_at", -1)])
    except Exception as exc:  # noqa: BLE001
        logger.warning("创建会话索引失败（不影响功能）：%s", exc)


def create_session(user_id: int, title: str | None = None) -> str:
    session_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    _col().insert_one(
        {
            "session_id": session_id,
            "user_id": user_id,
            "title": (title or "新对话")[:60],
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    return session_id


def get_session(session_id: str, user_id: int) -> dict[str, Any] | None:
    return _col().find_one({"session_id": session_id, "user_id": user_id})


def list_sessions(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """当前用户的会话列表（按最近活跃倒序）。"""
    cursor = (
        _col()
        .find({"user_id": user_id}, {"_id": 0, "session_id": 1, "title": 1, "updated_at": 1})
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [
        {
            "session_id": doc.get("session_id"),
            "title": doc.get("title") or "新对话",
            "updated_at": doc.get("updated_at"),
        }
        for doc in cursor
    ]


def append_message(session_id: str, user_id: int, message: dict[str, Any]) -> None:
    """追加一条消息并刷新会话活跃时间。"""
    message = dict(message)
    message.setdefault("created_at", datetime.now(UTC))
    _col().update_one(
        {"session_id": session_id, "user_id": user_id},
        {"$push": {"messages": message}, "$set": {"updated_at": datetime.now(UTC)}},
    )


def get_history(session_id: str, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """取最近若干条消息，供多轮上下文使用。"""
    doc = get_session(session_id, user_id)
    if not doc:
        return []
    messages = doc.get("messages") or []
    return messages[-limit:]


def update_title(session_id: str, user_id: int, title: str) -> None:
    _col().update_one(
        {"session_id": session_id, "user_id": user_id},
        {"$set": {"title": title[:60], "updated_at": datetime.now(UTC)}},
    )


def delete_session(session_id: str, user_id: int) -> bool:
    return _col().delete_one({"session_id": session_id, "user_id": user_id}).deleted_count > 0

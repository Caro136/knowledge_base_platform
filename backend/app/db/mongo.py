"""MongoDB 客户端（会话历史存储）。

会话数据形态天然是文档型（消息列表长度不定），且与关系库的平台数据无强一致性要求，
因此按 SPEC §5.4 放在 MongoDB。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

_client: Any = None


def get_client():
    """获取 MongoClient 单例（惰性创建 + 快速失败）。"""
    global _client
    if _client is None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover
            raise BizError(Code.INTERNAL_ERROR, "缺少 pymongo 依赖") from exc

        try:
            _client = MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            logger.info("MongoDB 已连接：%s/%s", settings.MONGO_URL, settings.MONGO_DB_NAME)
        except Exception as exc:  # noqa: BLE001
            _client = None
            logger.error("连接 MongoDB 失败：%s", exc)
            raise BizError(Code.INTERNAL_ERROR, f"MongoDB 不可用：{settings.MONGO_URL}") from exc
    return _client


def get_db():
    """获取会话库。"""
    return get_client()[settings.MONGO_DB_NAME]


def reset_client() -> None:
    """重置客户端（配置变更或测试使用）。"""
    global _client
    _client = None

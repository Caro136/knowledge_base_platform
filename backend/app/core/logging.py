"""结构化日志与请求上下文。

设计要点（SPEC §8 可观测性）：
- 单行 key=value 结构化输出，便于内网 grep 与后续接入采集；
- 通过 ContextVar 注入 request_id，贯穿同一请求的所有日志；
- 敏感字段脱敏由调用方负责（日志工具只提供 mask 辅助函数）。
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

from app.core.config import settings

#: 当前请求 ID（无请求上下文时为空串）
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s [%(name)s] rid=%(request_id)s %(message)s"
)


class RequestIdFilter(logging.Filter):
    """把 contextvar 中的 request_id 注入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


def _force_utf8_stdio() -> None:
    """输出被重定向时强制使用 UTF-8。

    Windows 下当 stdout 被重定向到管道/文件时，Python 会回退到系统 locale 编码
    （简体中文环境为 cp936），导致中文日志在按 UTF-8 解读的采集端显示为乱码。
    直接连接终端（isatty）时保留系统编码，以免在 GBK 代码页的控制台中反而乱码。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if getattr(stream, "isatty", lambda: False)():
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 部分环境下流不可重配置（如已被包装），忽略即可
            pass


def setup_logging() -> None:
    """初始化根日志配置（应用启动时调用一次）。"""
    _force_utf8_stdio()

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())

    # 清理既有 handler，避免 uvicorn 重复初始化导致日志翻倍
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)

    # 让 uvicorn 的访问日志沿用同一套格式
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def new_request_id() -> str:
    """生成新的请求 ID。"""
    return uuid.uuid4().hex[:16]


def set_request_id(request_id: str) -> None:
    request_id_ctx.set(request_id)


def mask(value: str | None, keep: int = 4) -> str:
    """脱敏：仅保留首尾少量字符，用于日志中输出密钥、手机号等。"""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"

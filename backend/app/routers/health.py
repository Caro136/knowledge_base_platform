"""健康检查接口。

- ``GET /healthz``：存活探针，只反映进程状态，不触碰任何外部依赖；
- ``GET /healthz/ready``：就绪探针，逐个检查关键依赖（当前为 MySQL，
  后续接入 Milvus / MongoDB / MinIO 时在此追加）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError
from app.core.response import ok
from app.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="存活探针")
def healthz() -> dict:
    return ok(
        {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": __version__,
            "env": settings.APP_ENV,
        }
    )


def _check_mysql() -> str:
    """检查 MySQL 连通性，返回 'up' 或失败原因。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "up"
    except Exception as exc:  # noqa: BLE001 - 健康检查需要捕获所有异常
        logger.warning("MySQL 健康检查失败: %s", exc)
        return f"down({type(exc).__name__})"


@router.get("/healthz/ready", summary="就绪探针")
def readyz() -> dict:
    deps = {"mysql": _check_mysql()}
    unhealthy = {name: state for name, state in deps.items() if state != "up"}
    if unhealthy:
        detail = "，".join(f"{name}={state}" for name, state in unhealthy.items())
        raise BizError(Code.INTERNAL_ERROR, f"依赖服务未就绪：{detail}")
    return ok({"status": "ready", "dependencies": deps})

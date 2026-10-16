"""路由注册入口。

新增业务模块时，在 :func:`register_routers` 中追加一行 include_router 即可，
业务路由统一挂载在 ``settings.API_PREFIX``（默认 ``/api``）之下。
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings


def register_routers(app: FastAPI) -> None:
    """注册全部路由。

    已注册：
        - /healthz, /healthz/ready          健康检查（T-01）

    待注册（按任务分解推进）：
        - /api/auth                         T-05
        - /api/user|role|dept|menu          T-06 ~ T-08
        - /api/knowledge                    T-10 ~ T-17
        - /api/chat, /internal/authz        T-19 ~ T-26
        - /api/dashboard                    T-27 ~ T-29
        - /api/precipitation                T-30 ~ T-34
    """
    from app.routers.health import router as health_router

    app.include_router(health_router)

    # 业务路由前缀预留，后续模块统一使用：
    # app.include_router(auth_router, prefix=settings.API_PREFIX)
    _ = settings.API_PREFIX

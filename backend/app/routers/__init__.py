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
        - /healthz, /healthz/ready              健康检查（T-01）
        - /api/auth/*                           登录与当前用户（T-05）
        - /api/menu/*                           菜单树与权限点（T-06）
        - /api/user/* /api/role/* /api/dept/*   组织与权限管理（T-07 / T-08）
        - /api/knowledge/*                      知识台账与导入任务（T-10 / T-11）

    待注册（按任务分解推进）：
        - /api/dashboard                        T-27 ~ T-29
        - /api/precipitation                    T-30 ~ T-34
    """
    from app.routers.auth_router import router as auth_router
    from app.routers.authz_router import router as authz_router
    from app.routers.chat_router import router as chat_router
    from app.routers.dept_router import router as dept_router
    from app.routers.health import router as health_router
    from app.routers.knowledge_router import router as knowledge_router
    from app.routers.menu_router import router as menu_router
    from app.routers.role_router import router as role_router
    from app.routers.user_router import router as user_router

    # 健康检查与内部鉴权接口不带业务前缀（内部接口路径自带 /internal）
    app.include_router(health_router)
    app.include_router(authz_router)

    api_routers = (
        auth_router,
        menu_router,
        user_router,
        role_router,
        dept_router,
        knowledge_router,
        chat_router,
    )
    for router in api_routers:
        app.include_router(router, prefix=settings.API_PREFIX)

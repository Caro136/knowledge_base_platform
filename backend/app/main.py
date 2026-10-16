"""应用入口。

职责：组装中间件 → 注册异常处理器 → 注册路由 → 托管前端产物。

启动::

    cd backend
    python -m app.main          # 或 uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import new_request_id, set_request_id, setup_logging
from app.routers import register_routers

logger = logging.getLogger(__name__)

#: SPA 兜底路由需要排除的路径前缀（API、文档、静态资源）
_NON_SPA_PREFIXES = (
    "api/",
    "internal/",
    "healthz",
    "docs",
    "redoc",
    "openapi.json",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期钩子。"""
    logger.info("=" * 68)
    logger.info("%s v%s 启动 env=%s", settings.APP_NAME, __version__, settings.APP_ENV)
    logger.info("接口前缀=%s  静态目录=%s", settings.API_PREFIX, settings.static_dir_abs)
    if settings.JWT_SECRET.startswith("change-me"):
        # 安全红线提醒：默认密钥绝不允许进入生产环境
        logger.warning("检测到默认 JWT_SECRET，上线前必须替换为随机长字符串！")
    if not settings.LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY，问答生成能力将在调用时返回 40001（T-19 之后生效）")
    logger.info("=" * 68)
    yield
    logger.info("%s 已停止", settings.APP_NAME)


def _register_request_middleware(app: FastAPI) -> None:
    """请求 ID 注入与访问日志。"""

    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or new_request_id()
        set_request_id(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 异常交由全局处理器转换，这里只补一条带耗时的错误日志
            cost_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "请求异常 %s %s cost=%.1fms", request.method, request.url.path, cost_ms
            )
            raise
        cost_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = rid
        # 健康探针与静态资源不记访问日志，避免噪音
        if not request.url.path.startswith(("/healthz", "/assets")):
            logger.info(
                "%s %s -> %s cost=%.1fms",
                request.method, request.url.path, response.status_code, cost_ms,
            )
        return response


def _mount_frontend(app: FastAPI) -> None:
    """托管前端构建产物（若已构建），并为 SPA 提供 history 模式兜底。"""
    static_dir = settings.static_dir_abs
    index_file = static_dir / "index.html"

    if not index_file.exists():
        logger.info(
            "未找到前端产物（%s），跳过静态托管；开发时请使用 Vite dev server", static_dir
        )

        @app.get("/", include_in_schema=False)
        def _root() -> JSONResponse:
            return JSONResponse(
                {
                    "code": 0,
                    "message": "后端服务运行中；前端产物尚未构建（frontend 执行 npm run build 后由本服务托管）",
                    "data": {"健康检查": "/healthz", "接口文档": "/docs"},
                }
            )

        return

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:
        # 非前端路径（API/文档）不落到 SPA，直接 404
        if full_path.startswith(_NON_SPA_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        # 命中真实静态文件（favicon、robots 等）则直接返回
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # 其余路径一律交给前端路由（history 模式）
        return FileResponse(index_file)


def create_app() -> FastAPI:
    """构建 FastAPI 应用。"""
    setup_logging()

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="知识库管理平台后端 API（依据 docs/知识库管理平台技术设计规格SPEC.md）",
        lifespan=lifespan,
    )

    # 内层：请求上下文与访问日志
    _register_request_middleware(app)

    # 外层：CORS。放在最后 add，确保异常响应同样带回 CORS 头
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    register_exception_handlers(app)
    register_routers(app)
    _mount_frontend(app)

    return app


app = create_app()


def main() -> None:
    """本地启动入口（开发用）。"""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.is_dev,
        log_config=None,  # 沿用 app.core.logging 的配置
    )


if __name__ == "__main__":
    main()

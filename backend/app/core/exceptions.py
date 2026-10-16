"""业务异常与全局异常处理器。

约定：业务代码只抛 :class:`BizError`，由处理器统一转成标准响应体，
避免在每个接口里手写 try/except 与响应拼装。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.codes import Code, default_message, http_status_of
from app.core.response import json_fail

logger = logging.getLogger(__name__)

#: 框架内置的英文默认 detail，命中时改用 codes.py 中的中文文案
_FRAMEWORK_DEFAULT_DETAILS = {
    "Not Found",
    "Method Not Allowed",
    "Internal Server Error",
}


class BizError(Exception):
    """业务异常。"""

    def __init__(
        self,
        code: int = Code.INTERNAL_ERROR,
        message: str | None = None,
        data: object | None = None,
    ) -> None:
        self.code = int(code)
        self.message = message or default_message(self.code)
        self.data = data
        super().__init__(self.message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(BizError)
    async def _handle_biz_error(_: Request, exc: BizError):
        # 业务异常属于预期内的分支，用 warning 级别，避免污染错误告警
        logger.warning("业务异常 code=%s message=%s", exc.code, exc.message)
        return json_fail(exc.code, exc.message, exc.data)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError):
        # 把 pydantic 的校验明细压缩成一句可读提示，同时保留原始明细便于排障
        details = "; ".join(
            f"{'.'.join(str(x) for x in err.get('loc', []))}: {err.get('msg', '')}"
            for err in exc.errors()
        )
        logger.warning("参数校验失败: %s", details)
        return json_fail(Code.PARAM_INVALID, f"{default_message(Code.PARAM_INVALID)}（{details}）", None)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException):
        # HTTPException 在业务代码中被明确用于表达"无权限/未登录"等语义
        code = exc.status_code
        if code == 401:
            biz_code = Code.UNAUTHENTICATED
        elif code == 403:
            biz_code = Code.NO_OPERATION_PERMISSION
        elif code == 404:
            biz_code = Code.NOT_FOUND
        else:
            biz_code = Code.INTERNAL_ERROR

        # 业务代码显式传入的 detail 优先；框架内置的英文默认文案改用统一中文提示
        raw_detail = exc.detail
        if not raw_detail or str(raw_detail) in _FRAMEWORK_DEFAULT_DETAILS:
            return json_fail(biz_code)
        return json_fail(biz_code, str(raw_detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        # 未预期异常：记录完整堆栈，但对外只暴露通用文案，不泄漏内部细节
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return json_fail(Code.INTERNAL_ERROR)


__all__ = ["BizError", "register_exception_handlers", "http_status_of"]

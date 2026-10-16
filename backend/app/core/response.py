"""统一响应包装（SPEC §6.1）。

除 SSE 与文件流外，所有接口返回 ``{"code": 0, "message": "ok", "data": ...}``。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.codes import Code, default_message

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """标准响应体。"""

    code: int = Field(default=Code.OK, description="业务错误码，0 表示成功")
    message: str = Field(default="ok", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")


def _dump(value: Any) -> Any:
    """按对外别名（camelCase）递归序列化 Pydantic 模型。"""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    return value


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """构造成功响应字典。

    显式按别名序列化，不依赖序列化器的默认行为，保证对外字段恒为 camelCase。
    """
    return {"code": Code.OK, "message": message, "data": _dump(data)}


def fail(code: int, message: str | None = None, data: Any = None) -> dict[str, Any]:
    """构造失败响应字典。"""
    return {"code": code, "message": message or default_message(code), "data": data}


def json_fail(code: int, message: str | None = None, data: Any = None) -> JSONResponse:
    """构造失败响应对象（供异常处理器使用）。"""
    from app.core.codes import http_status_of

    return JSONResponse(
        status_code=http_status_of(code),
        content=fail(code, message, data),
    )


class PageData(BaseModel, Generic[T]):
    """分页数据结构。"""

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(default=0, description="总条数")
    page: int = Field(default=1, description="当前页码，从 1 开始")
    size: int = Field(default=10, description="每页条数")


class PageQuery(BaseModel):
    """分页查询参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    size: int = Field(default=10, ge=1, le=100, description="每页条数，最大 100")

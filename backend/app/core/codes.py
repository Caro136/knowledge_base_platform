"""统一错误码体系（SPEC §6.1）。

段位划分：
    0       成功
    100xx   参数与校验
    200xx   认证与权限
    300xx   业务规则
    400xx   依赖与系统
"""

from __future__ import annotations

from enum import IntEnum


class Code(IntEnum):
    """业务错误码。"""

    OK = 0

    # ---------- 100xx 参数与校验 ----------
    PARAM_INVALID = 10001
    FILE_FORMAT_UNSUPPORTED = 10002
    FILE_TOO_LARGE = 10003
    NOT_FOUND = 10004

    # ---------- 200xx 认证与权限 ----------
    UNAUTHENTICATED = 20001
    NO_OPERATION_PERMISSION = 20002
    NO_DATA_PERMISSION = 20003
    ACCOUNT_DISABLED = 20004

    # ---------- 300xx 业务规则 ----------
    DOCUMENT_NOT_FOUND = 30001
    STATE_NOT_ALLOWED = 30002
    PARSE_FAILED = 30003
    FAQ_STATE_INVALID = 30004

    # ---------- 400xx 依赖与系统 ----------
    LLM_UNAVAILABLE = 40001
    VECTOR_DB_UNAVAILABLE = 40002
    DOC_PARSE_UNAVAILABLE = 40003
    OBJECT_STORAGE_UNAVAILABLE = 40004
    INTERNAL_ERROR = 50000


#: 错误码 → 默认 HTTP 状态码
CODE_HTTP_STATUS: dict[int, int] = {
    Code.OK: 200,
    Code.PARAM_INVALID: 400,
    Code.FILE_FORMAT_UNSUPPORTED: 400,
    Code.FILE_TOO_LARGE: 413,
    Code.NOT_FOUND: 404,
    Code.UNAUTHENTICATED: 401,
    Code.NO_OPERATION_PERMISSION: 403,
    Code.NO_DATA_PERMISSION: 403,
    Code.ACCOUNT_DISABLED: 403,
    Code.DOCUMENT_NOT_FOUND: 404,
    Code.STATE_NOT_ALLOWED: 409,
    Code.PARSE_FAILED: 422,
    Code.FAQ_STATE_INVALID: 409,
    Code.LLM_UNAVAILABLE: 503,
    Code.VECTOR_DB_UNAVAILABLE: 503,
    Code.DOC_PARSE_UNAVAILABLE: 503,
    Code.OBJECT_STORAGE_UNAVAILABLE: 503,
    Code.INTERNAL_ERROR: 500,
}

#: 错误码 → 默认提示文案
CODE_MESSAGE: dict[int, str] = {
    Code.OK: "ok",
    Code.PARAM_INVALID: "请求参数不合法",
    Code.FILE_FORMAT_UNSUPPORTED: "不支持的文件格式",
    Code.FILE_TOO_LARGE: "文件超过大小限制",
    Code.NOT_FOUND: "请求的资源不存在",
    Code.UNAUTHENTICATED: "未登录或登录状态已失效",
    Code.NO_OPERATION_PERMISSION: "缺少操作权限",
    Code.NO_DATA_PERMISSION: "无权访问该知识内容",
    Code.ACCOUNT_DISABLED: "账号已被禁用，请联系管理员",
    Code.DOCUMENT_NOT_FOUND: "知识单元不存在",
    Code.STATE_NOT_ALLOWED: "当前状态不允许该操作",
    Code.PARSE_FAILED: "文档解析失败",
    Code.FAQ_STATE_INVALID: "FAQ 当前状态不允许该操作",
    Code.LLM_UNAVAILABLE: "大模型服务暂不可用，请稍后重试",
    Code.VECTOR_DB_UNAVAILABLE: "向量检索服务暂不可用",
    Code.DOC_PARSE_UNAVAILABLE: "文档解析服务暂不可用",
    Code.OBJECT_STORAGE_UNAVAILABLE: "对象存储服务暂不可用",
    Code.INTERNAL_ERROR: "服务内部错误",
}


def default_message(code: int) -> str:
    """取错误码的默认文案，未登记则回落到内部错误文案。"""
    return CODE_MESSAGE.get(code, CODE_MESSAGE[Code.INTERNAL_ERROR])


def http_status_of(code: int) -> int:
    """取错误码对应的 HTTP 状态码，未登记则回落到 500。"""
    return CODE_HTTP_STATUS.get(code, 500)

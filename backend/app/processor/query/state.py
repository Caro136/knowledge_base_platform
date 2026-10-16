"""问答流程状态。"""

from __future__ import annotations

from typing import Any, TypedDict


class QueryState(TypedDict, total=False):
    """查询流程状态（节点间传递）。"""

    # ---------- 输入 ----------
    question: str
    user_id: int
    session_id: str
    history: list[dict[str, Any]]
    """近若干轮对话（用于多轮上下文）。"""

    # ---------- 检索与鉴权 ----------
    dense_hits: list[dict[str, Any]]
    sparse_hits: list[dict[str, Any]]
    fused_chunks: list[dict[str, Any]]
    """RRF 融合后的候选切片（未鉴权）。"""
    authorized_chunks: list[dict[str, Any]]
    """通过数据权限校验的切片。"""
    denied_doc_ids: list[str]
    """被拦截的知识单元（仅用于生成受限提示，不落库）。"""

    # ---------- 重排与上下文 ----------
    ranked_docs: list[dict[str, Any]]
    """重排并截断后的最终上下文切片。"""
    context: str
    messages: list[dict[str, str]]
    """交给大模型的完整消息列表（由 build_context 组装）。"""
    references: list[dict[str, Any]]
    """引用溯源卡片数据。"""

    # ---------- 输出标记 ----------
    has_context: bool
    permission_denied: bool
    """是否存在「有相关知识但无权访问」的情形（触发安全提示）。"""
    answer: str

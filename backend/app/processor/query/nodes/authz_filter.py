"""数据权限过滤节点（T-20，FR-24 / FR-26）。

位置：RRF 融合之后、重排之前（SPEC ADR-003）。
这样未授权切片在进入重排与 Prompt 之前就被移除，绝不进入大模型上下文。

两条安全底线：
1. **无锚点切片一律拒绝**：切片缺少 ``doc_id`` 时无法判定归属，直接丢弃，
   防止历史脏数据绕过鉴权；
2. **鉴权异常即拒绝**：由 :class:`AuthzService` 内部保证 fail-closed。
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.session import SessionLocal
from app.models import User
from app.processor.query.state import QueryState
from app.services.authz_service import AuthzService

logger = logging.getLogger(__name__)


def authz_filter_node(state: QueryState) -> QueryState:
    chunks = state.get("fused_chunks") or []
    if not chunks:
        return {"authorized_chunks": [], "denied_doc_ids": [], "permission_denied": False}

    # 第一步：丢弃没有权限锚点的切片（只可能是历史脏数据）
    anchored = [chunk for chunk in chunks if chunk.get("doc_id")]
    dropped = len(chunks) - len(anchored)
    if dropped:
        logger.warning("丢弃 %d 条缺少 doc_id 锚点的切片（无法判定权限）", dropped)

    if not anchored:
        return {"authorized_chunks": [], "denied_doc_ids": [], "permission_denied": False}

    candidate_doc_ids = list(dict.fromkeys(chunk["doc_id"] for chunk in anchored))

    # 节点在线程池中执行，使用独立会话而非请求级会话
    with SessionLocal() as db:
        user = db.get(User, state.get("user_id")) if state.get("user_id") else None
        allowed, denied = AuthzService.filter_doc_ids(db, user, candidate_doc_ids)

    allowed_set = set(allowed)
    authorized = [chunk for chunk in anchored if chunk["doc_id"] in allowed_set]

    logger.info(
        "鉴权完成：候选 %d 个知识单元 → 放行 %d / 拦截 %d（切片 %d → %d）",
        len(candidate_doc_ids), len(allowed), len(denied), len(anchored), len(authorized),
    )
    return {
        "authorized_chunks": authorized,
        "denied_doc_ids": sorted(set(denied)),
        # 存在被拦截项才需要给用户安全提示
        "permission_denied": bool(denied),
    }


def has_authorized_chunks(state: QueryState) -> str:
    """条件边：无有权切片时跳过重排，直接进入上下文组装（避免空跑精排）。"""
    return "rerank" if (state.get("authorized_chunks") or []) else "build_context"

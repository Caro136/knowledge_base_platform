"""动态数据权限鉴权引擎（T-16）。

四维 OR 判定（PRD §2.3）：
- ``global``       → 所有人可读
- ``department``   → 用户**直属部门**命中配置的部门集合
- ``role``         → 用户的**启用角色**命中配置的角色集合
- ``user``         → 用户本人命中配置的人员集合
命中任一维度即放行；**无任何权限记录 = 拒绝**。

设计取舍：
1. **fail-closed**：用户不存在、无上下文或判定过程中出现任何异常，一律返回「全部拒绝」。
   宁可少答，不可越权。
2. **实时查库而非缓存**：PRD 要求「权限规则即时生效」。实时查询天然满足该语义，
   也避免了缓存与数据库不一致的风险；随之而来的查询开销在单机规模下可忽略
   （一次批量鉴权只查一次权限表）。
3. **批量接口**：召唤候选项一次性判定，避免逐条查询造成 N+1。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PERM_DEPARTMENT,
    PERM_GLOBAL,
    PERM_ROLE,
    PERM_USER,
    KbDocPerm,
    User,
)
from app.schemas.authz import AuthzExplainOut

logger = logging.getLogger(__name__)


def user_scope(user: User) -> tuple[set[int], set[int], int]:
    """提取用户的数据权限维度：部门集合、启用角色集合、用户本人 ID。"""
    dept_ids = {user.dept_id} if user.dept_id else set()
    role_ids = user.enabled_role_ids()
    return dept_ids, role_ids, user.id


def _match_reason(row: KbDocPerm, dept_ids: set[int], role_ids: set[int], uid: int) -> str | None:
    """判断单条权限记录是否命中，命中则返回可读的原因。"""
    if row.perm_type == PERM_GLOBAL:
        return "global"
    if row.perm_type == PERM_DEPARTMENT and row.entity_id in dept_ids:
        return f"department:{row.entity_id}"
    if row.perm_type == PERM_ROLE and row.entity_id in role_ids:
        return f"role:{row.entity_id}"
    if row.perm_type == PERM_USER and row.entity_id == uid:
        return f"user:{row.entity_id}"
    return None


class AuthzService:
    """数据权限判定。"""

    @staticmethod
    def filter_doc_ids(db: Session, user: User | None, doc_ids: list[str]) -> tuple[list[str], list[str]]:
        """批量判定，返回 (allowed, denied)，两组均保持入参顺序且去重。"""
        unique = list(dict.fromkeys(doc_ids or []))
        if not unique:
            return [], []

        try:
            if user is None:
                # 无用户上下文：全部拒绝
                return [], unique

            if user.is_super:
                # 超管：全部放行
                return unique, []

            dept_ids, role_ids, uid = user_scope(user)

            rows = db.scalars(select(KbDocPerm).where(KbDocPerm.doc_id.in_(unique))).all()
            allowed_set: set[str] = set()
            for row in rows:
                if _match_reason(row, dept_ids, role_ids, uid):
                    allowed_set.add(row.doc_id)

            allowed = [doc_id for doc_id in unique if doc_id in allowed_set]
            denied = [doc_id for doc_id in unique if doc_id not in allowed_set]
            return allowed, denied

        except Exception:  # noqa: BLE001
            # 安全降级：鉴权链路出错时拒绝全部，绝不放行
            logger.exception("鉴权过程异常，安全降级为全部拒绝（候选 %d 个）", len(unique))
            return [], unique

    @staticmethod
    def can_access(db: Session, user: User | None, doc_id: str) -> bool:
        """单个知识单元是否可访问。"""
        allowed, _ = AuthzService.filter_doc_ids(db, user, [doc_id])
        return bool(allowed)

    @staticmethod
    def explain(db: Session, user: User | None, doc_id: str) -> AuthzExplainOut:
        """给出鉴权结论及原因，用于「为什么看不到」的排障与演示。"""
        if user is None:
            return AuthzExplainOut(doc_id=doc_id, allowed=False, reason="未登录或用户不存在")

        if user.is_super:
            return AuthzExplainOut(doc_id=doc_id, allowed=True, reason="超级管理员，拥有全部数据权限")

        dept_ids, role_ids, uid = user_scope(user)
        rows = db.scalars(select(KbDocPerm).where(KbDocPerm.doc_id == doc_id)).all()

        if not rows:
            return AuthzExplainOut(
                doc_id=doc_id, allowed=False, reason="该知识单元未配置任何数据权限（默认拒绝）"
            )

        matched = [reason for row in rows if (reason := _match_reason(row, dept_ids, role_ids, uid))]
        configured = sorted({f"{row.perm_type}:{row.entity_id}" for row in rows})

        if matched:
            return AuthzExplainOut(
                doc_id=doc_id, allowed=True, reason="命中授权维度：" + "、".join(matched), matched=matched
            )
        return AuthzExplainOut(
            doc_id=doc_id,
            allowed=False,
            reason="已配置权限但均未命中。已配置：" + "、".join(configured),
            matched=[],
        )

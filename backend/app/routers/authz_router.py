"""内部数据权限鉴权接口（T-16）。

对外提供「给定用户 + 候选知识单元，返回允许/拒绝列表」的能力，
供问答引擎（T-19）在检索召回复核权限时调用。

安全约束：普通用户只能查询**自己**的权限；查询他人需超级管理员。
（问答链路实际是同进程直调 :class:`AuthzService`，本接口保留是为了
满足「智能体通过权限接口访问」的架构语义，并便于独立测试与外部集成。）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.core.response import ok
from app.db.session import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.authz import AuthzFilterIn
from app.services.authz_service import AuthzService

router = APIRouter(prefix="/internal/authz", tags=["内部鉴权"])


@router.post("/filter", summary="批量数据权限鉴权")
def filter_docs(
    payload: AuthzFilterIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    target = current_user
    if payload.user_id is not None and payload.user_id != current_user.id:
        if not current_user.is_super:
            raise BizError(Code.NO_DATA_PERMISSION, "仅超级管理员可查询他人的数据权限")
        target = db.get(User, payload.user_id)
        if target is None:
            raise BizError(Code.NOT_FOUND, "目标用户不存在")

    allowed, denied = AuthzService.filter_doc_ids(db, target, payload.doc_ids)
    return ok({"allowed": allowed, "denied": denied})


@router.get("/explain/{doc_id}", summary="解释某知识单元的鉴权结论（排障用）")
def explain(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return ok(AuthzService.explain(db, current_user, doc_id))

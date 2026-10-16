"""知识沉淀接口（T-30 ~ T-33）。

三块能力：
- FAQ 挖掘与审核发布（含缓存生效控制与数据权限）
- 已发布 FAQ（供对话工作台的「常见问题」展示）
- 知识缺口清单与转建补充任务
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_permission
from app.models import User
from app.schemas.knowledge import AssignPermsIn
from app.schemas.ops import FaqAuditIn, FaqQuery, GapQuery, GapTaskIn
from app.services import faq_service, ops_service

router = APIRouter(prefix="/precipitation", tags=["知识沉淀"])


# ---------------------------------------------------------------------------
# FAQ 挖掘与审核（T-30 / T-31）
# ---------------------------------------------------------------------------


@router.get("/faq/list", summary="候选与已发布 FAQ 列表")
def list_faqs(
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None, description="pending/published/rejected；不传则不含收集中"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("faq:list")),
) -> dict:
    query = FaqQuery(keyword=keyword, status=status, page=page, size=size)
    return ok(faq_service.list_faqs(db, query))


@router.get("/faq/published", summary="已发布 FAQ（供对话工作台展示常见问题）")
def published_faqs(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    return ok(faq_service.list_published(db, user))


@router.put("/faq/{faq_id}/audit", summary="审核 FAQ：发布（写入缓存）或驳回")
def audit_faq(
    faq_id: int,
    payload: FaqAuditIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("faq:audit")),
) -> dict:
    return ok(faq_service.audit(db, faq_id, payload, user))


@router.delete("/faq/{faq_id}", summary="删除 FAQ")
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("faq:delete")),
) -> dict:
    faq_service.delete_faq(db, faq_id)
    return ok(message="删除成功")


@router.get("/faq/{faq_id}/perms", summary="查询 FAQ 的数据权限")
def faq_perms(
    faq_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("faq:audit")),
) -> dict:
    return ok(faq_service.get_faq_perms(db, faq_id))


@router.post("/faq/perms/assign", summary="分配 FAQ 数据权限（覆盖式；清空即公开）")
def assign_faq_perms(
    payload: AssignPermsIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("faq:audit")),
) -> dict:
    return ok(faq_service.assign_faq_perms(db, payload))


# ---------------------------------------------------------------------------
# 知识缺口（T-32 / T-33）
# ---------------------------------------------------------------------------


@router.get("/gap/list", summary="知识缺口清单")
def list_gaps(
    include_resolved: bool = Query(default=False, description="是否包含已处理项"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("gap:list")),
) -> dict:
    query = GapQuery(include_resolved=include_resolved, page=page, size=size)
    return ok(ops_service.list_gaps(db, query))


@router.put("/gap/{gap_id}/resolve", summary="标记缺口已解决")
def resolve_gap(
    gap_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("gap:handle")),
) -> dict:
    ops_service.resolve_gap(db, gap_id)
    return ok(message="已标记解决")


@router.post("/gap/{gap_id}/task", summary="缺口转建知识补充任务")
def create_gap_task(
    gap_id: int,
    payload: GapTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("gap:handle")),
) -> dict:
    return ok(ops_service.create_gap_task(db, gap_id, payload, user))


@router.get("/gap/tasks", summary="知识补充任务列表")
def list_gap_tasks(
    gapId: int | None = Query(default=None),  # noqa: N803 - 对外参数名
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("gap:list")),
) -> dict:
    return ok(ops_service.list_gap_tasks(db, gapId))

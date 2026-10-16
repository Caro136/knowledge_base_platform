"""运营看板接口（T-28）。

四个只读聚合接口，全部要求 ``dashboard:view`` 权限。
时间窗口通过 ``days`` 参数控制，默认 30 天（趋势默认 14 天）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_permission
from app.models import User
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["运营看板"])


@router.get("/overview", summary="总览指标（PV/UV、Token、延时、命中率、缺口数）")
def overview(
    days: int = Query(default=30, ge=1, le=365, description="统计窗口（天）"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
) -> dict:
    return ok(dashboard_service.overview(db, days))


@router.get("/trend", summary="访问趋势（按天聚合 PV / UV）")
def trend(
    days: int = Query(default=14, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
) -> dict:
    return ok(dashboard_service.trend(db, days))


@router.get("/top-questions", summary="高频提问排行")
def top_questions(
    limit: int = Query(default=10, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
) -> dict:
    return ok(dashboard_service.top_questions(db, limit, days))


@router.get("/top-docs", summary="热门知识单元排行")
def top_docs(
    limit: int = Query(default=10, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
) -> dict:
    return ok(dashboard_service.top_docs(db, limit, days))

"""部门接口（T-07）。

部门树同时被系统管理页与「知识单元数据权限配置弹窗」复用，
因此读取接口采用 require_any_permission 放行多个权限点。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_any_permission, require_permission
from app.models import User
from app.schemas.rbac import DeptIn
from app.services.rbac_service import DeptService

router = APIRouter(prefix="/dept", tags=["部门"])

#: 允许读取部门树的权限点：系统管理页、知识数据权限弹窗、FAQ 数据权限弹窗
_READ_PERMS = ("dept:list", "knowledge:perm", "faq:audit")


@router.get("/tree", summary="部门树")
def dept_tree(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    return ok(DeptService.tree(db))


@router.post("", summary="新增部门")
def create_dept(
    payload: DeptIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dept:create")),
) -> dict:
    return ok(DeptService.create(db, payload))


@router.put("/{dept_id}", summary="编辑部门")
def update_dept(
    dept_id: int,
    payload: DeptIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dept:update")),
) -> dict:
    return ok(DeptService.update(db, dept_id, payload))


@router.delete("/{dept_id}", summary="删除部门")
def delete_dept(
    dept_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dept:delete")),
) -> dict:
    DeptService.delete(db, dept_id)
    return ok(message="删除成功")

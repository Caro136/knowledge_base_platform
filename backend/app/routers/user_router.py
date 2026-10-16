"""用户账号接口（T-07）。

用户列表同样被数据权限配置弹窗复用（选择"个人可见"的授权对象），
因此读取接口放行多个权限点。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_any_permission, require_permission
from app.models import User
from app.schemas.rbac import UserIn, UserQuery
from app.services.rbac_service import UserService

router = APIRouter(prefix="/user", tags=["用户"])

_READ_PERMS = ("user:list", "knowledge:perm", "faq:audit")


@router.get("/list", summary="用户列表（分页）")
def list_users(
    keyword: str | None = Query(default=None, description="按账号/昵称模糊匹配"),
    deptId: int | None = Query(default=None, description="按部门筛选"),  # noqa: N803 - 对外参数名
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    query = UserQuery(
        keyword=keyword, dept_id=deptId, enabled=enabled, page=page, size=size
    )
    return ok(UserService.list_page(db, query))


@router.post("", summary="新增用户")
def create_user(
    payload: UserIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:create")),
) -> dict:
    return ok(UserService.create(db, payload))


@router.put("/{user_id}", summary="编辑用户")
def update_user(
    user_id: int,
    payload: UserIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("user:update")),
) -> dict:
    return ok(UserService.update(db, user_id, payload))


@router.delete("/{user_id}", summary="删除用户")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    operator: User = Depends(require_permission("user:delete")),
) -> dict:
    UserService.delete(db, user_id, operator)
    return ok(message="删除成功")

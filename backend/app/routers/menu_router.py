"""菜单与权限点接口（T-06）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import get_current_user, require_permission
from app.models import User
from app.services.rbac_service import MenuService

router = APIRouter(prefix="/menu", tags=["菜单与权限"])


@router.get("/mine", summary="当前用户菜单树（前端渲染侧边栏）")
def my_menus(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ok(MenuService.user_menu_tree(db, user))


@router.get("/tree", summary="全量菜单树（含按钮，用于角色权限分配）")
def menu_tree(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:perm")),
) -> dict:
    return ok(MenuService.full_tree(db))

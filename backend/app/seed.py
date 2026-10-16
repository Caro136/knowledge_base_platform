"""初始化脚本：建表 + 菜单权限点 + 初始超级管理员。

用法::

    cd backend
    python -m app.seed

幂等：重复执行不会产生重复数据（菜单按 perm/path 匹配，用户按 username 匹配）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import Dept, Menu, Role, User
from app.models.rbac import MENU_TYPE_BUTTON, MENU_TYPE_DIR, MENU_TYPE_MENU

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 菜单与权限点定义
# 结构：(名称, 类型, 权限标识, 路由路径, 组件路径, 图标, 子节点)
# 该清单与 SPEC §6.2 的接口权限点、PRD §2.2 的建议清单保持一致。
# --------------------------------------------------------------------------
MENU_TREE: list[dict] = [
    {
        "name": "知识管理",
        "type": MENU_TYPE_DIR,
        "icon": "Document",
        "path": "/knowledge",
        "children": [
            {
                "name": "知识单元",
                "type": MENU_TYPE_MENU,
                "perm": "knowledge:list",
                "path": "/knowledge/list",
                "component": "knowledge/List",
                "icon": "Files",
                "children": [
                    {"name": "查询", "type": MENU_TYPE_BUTTON, "perm": "knowledge:query"},
                    {"name": "导入", "type": MENU_TYPE_BUTTON, "perm": "knowledge:import"},
                    {"name": "编辑", "type": MENU_TYPE_BUTTON, "perm": "knowledge:update"},
                    {"name": "删除", "type": MENU_TYPE_BUTTON, "perm": "knowledge:delete"},
                    {"name": "数据权限", "type": MENU_TYPE_BUTTON, "perm": "knowledge:perm"},
                ],
            },
        ],
    },
    {
        "name": "AI 对话",
        "type": MENU_TYPE_MENU,
        "perm": "ai:chat",
        "path": "/chat/index",
        "component": "chat/Index",
        "icon": "ChatDotRound",
        "children": [],
    },
    {
        "name": "数据看板",
        "type": MENU_TYPE_MENU,
        "perm": "dashboard:view",
        "path": "/dashboard/index",
        "component": "dashboard/Index",
        "icon": "DataLine",
        "children": [],
    },
    {
        "name": "知识沉淀",
        "type": MENU_TYPE_DIR,
        "icon": "Refresh",
        "path": "/precipitation",
        "children": [
            {
                "name": "FAQ 审核",
                "type": MENU_TYPE_MENU,
                "perm": "faq:list",
                "path": "/precipitation/faq",
                "component": "precipitation/Faq",
                "icon": "ChatLineSquare",
                "children": [
                    {"name": "审核发布", "type": MENU_TYPE_BUTTON, "perm": "faq:audit"},
                    {"name": "删除", "type": MENU_TYPE_BUTTON, "perm": "faq:delete"},
                ],
            },
            {
                "name": "知识缺口",
                "type": MENU_TYPE_MENU,
                "perm": "gap:list",
                "path": "/precipitation/gap",
                "component": "precipitation/Gap",
                "icon": "Warning",
                "children": [
                    {"name": "转建任务", "type": MENU_TYPE_BUTTON, "perm": "gap:handle"},
                ],
            },
        ],
    },
    {
        "name": "权限管理",
        "type": MENU_TYPE_DIR,
        "icon": "Setting",
        "path": "/system",
        "children": [
            {
                "name": "用户管理",
                "type": MENU_TYPE_MENU,
                "perm": "user:list",
                "path": "/system/user",
                "component": "system/User",
                "icon": "User",
                "children": [
                    {"name": "新增", "type": MENU_TYPE_BUTTON, "perm": "user:create"},
                    {"name": "编辑", "type": MENU_TYPE_BUTTON, "perm": "user:update"},
                    {"name": "删除", "type": MENU_TYPE_BUTTON, "perm": "user:delete"},
                ],
            },
            {
                "name": "角色管理",
                "type": MENU_TYPE_MENU,
                "perm": "role:list",
                "path": "/system/role",
                "component": "system/Role",
                "icon": "Avatar",
                "children": [
                    {"name": "新增", "type": MENU_TYPE_BUTTON, "perm": "role:create"},
                    {"name": "编辑", "type": MENU_TYPE_BUTTON, "perm": "role:update"},
                    {"name": "删除", "type": MENU_TYPE_BUTTON, "perm": "role:delete"},
                    {"name": "分配权限", "type": MENU_TYPE_BUTTON, "perm": "role:perm"},
                ],
            },
            {
                "name": "部门管理",
                "type": MENU_TYPE_MENU,
                "perm": "dept:list",
                "path": "/system/dept",
                "component": "system/Dept",
                "icon": "OfficeBuilding",
                "children": [
                    {"name": "新增", "type": MENU_TYPE_BUTTON, "perm": "dept:create"},
                    {"name": "编辑", "type": MENU_TYPE_BUTTON, "perm": "dept:update"},
                    {"name": "删除", "type": MENU_TYPE_BUTTON, "perm": "dept:delete"},
                ],
            },
        ],
    },
]


def seed_menus(db: Session) -> int:
    """写入菜单与权限点，返回新建的菜单数量。"""
    created = 0

    def _upsert(nodes: list[dict], parent_id: int, order_start: int = 0) -> None:
        nonlocal created
        for index, node in enumerate(nodes):
            perm = node.get("perm")
            path = node.get("path")
            # 幂等匹配：优先按 perm，其次按 path
            stmt = select(Menu)
            if perm:
                stmt = stmt.where(Menu.perm == perm)
            elif path:
                stmt = stmt.where(Menu.path == path, Menu.parent_id == parent_id)
            else:
                stmt = stmt.where(Menu.name == node["name"], Menu.parent_id == parent_id)

            menu = db.execute(stmt).scalar_one_or_none()
            if menu is None:
                menu = Menu(
                    name=node["name"],
                    parent_id=parent_id,
                    type=node["type"],
                    perm=perm,
                    path=path,
                    component=node.get("component"),
                    icon=node.get("icon"),
                    order_no=order_start + index,
                    visible=True,
                )
                db.add(menu)
                db.flush()  # 取到自增 ID 供子节点使用
                created += 1
            _upsert(node.get("children") or [], menu.id, order_start)

    _upsert(MENU_TREE, 0)
    db.commit()
    return created


def seed_admin(db: Session) -> bool:
    """创建初始超级管理员，返回是否新建。"""
    existing = db.execute(
        select(User).where(User.username == settings.INIT_ADMIN_USERNAME)
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("超级管理员 %s 已存在，跳过", settings.INIT_ADMIN_USERNAME)
        return False

    admin = User(
        username=settings.INIT_ADMIN_USERNAME,
        password_hash=hash_password(settings.INIT_ADMIN_PASSWORD),
        nickname=settings.INIT_ADMIN_NICKNAME,
        dept_id=None,
        is_super=True,
        enabled=True,
    )
    db.add(admin)
    db.commit()
    logger.info("已创建超级管理员：%s", settings.INIT_ADMIN_USERNAME)
    return True


def seed_demo_org(db: Session) -> None:
    """创建演示用部门与角色（幂等），便于 T-05 之后快速联调鉴权。

    说明：仅用于开发/演示环境，生产环境可跳过本步骤。
    """
    if db.execute(select(Dept).where(Dept.parent_id == 0)).first() is None:
        root = Dept(name="总部", parent_id=0, order_no=0, enabled=True)
        db.add(root)
        db.flush()
        for i, name in enumerate(["财务部", "人力资源部", "客服部", "技术部"]):
            db.add(Dept(name=name, parent_id=root.id, order_no=i, enabled=True))
        logger.info("已创建演示部门树")

    if db.execute(select(Role)).first() is None:
        for code, name in [("knowledge_admin", "知识管理员"), ("normal_user", "普通用户")]:
            db.add(Role(name=name, code=code, remark="演示角色", enabled=True))
        logger.info("已创建演示角色")
    db.commit()


def main() -> None:
    setup_logging()
    logger.info("开始初始化：建表 → 菜单权限点 → 超级管理员")
    init_db()

    with SessionLocal() as db:
        created = seed_menus(db)
        logger.info("菜单权限点处理完成，新建 %d 项", created)
        seed_admin(db)
        seed_demo_org(db)

    logger.info("初始化完成。登录账号：%s", settings.INIT_ADMIN_USERNAME)


if __name__ == "__main__":
    main()

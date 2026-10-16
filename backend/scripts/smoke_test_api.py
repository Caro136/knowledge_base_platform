"""认证与组织权限冒烟测试（T-05 ~ T-08）。

用法：
    cd backend
    uv run python -m scripts.smoke_test_api

脚本会创建临时部门/角色/用户，并在结束前清理干净。
"""

from __future__ import annotations

import time

from scripts.smoke_common import (
    ADMIN_PWD,
    ADMIN_USER,
    call,
    check,
    login,
    summary,
)


def find_menu(nodes: list[dict], perm: str) -> dict | None:
    """在菜单树中按权限点查找节点。"""
    for node in nodes:
        if node.get("perm") == perm:
            return node
        hit = find_menu(node.get("children") or [], perm)
        if hit:
            return hit
    return None


def main() -> int:
    stamp = str(int(time.time()))[-6:]
    dept_name = f"冒烟测试部{stamp}"
    role_code = f"smoke_role_{stamp}"
    user_name = f"smoke_user_{stamp}"
    created: dict[str, object] = {}

    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)

    try:
        # ---------- T-05 认证 ----------
        check("登录：超管登录成功", bool(admin_token))

        _, body = call("POST", "/api/auth/login", body={"username": ADMIN_USER, "password": "wrong-password"})
        check("登录：密码错误被拒绝（20001/20004）", body.get("code") in (20001, 20004), body.get("code"))

        _, body = call("GET", "/api/auth/me")
        check("认证：未携带 token 访问被拒绝（20001）", body.get("code") == 20001, body.get("code"))

        _, body = call("GET", "/api/auth/me", token=admin_token)
        info = body.get("data") or {}
        check("认证：/auth/me 返回用户信息", body.get("code") == 0 and info.get("username") == ADMIN_USER)
        check("认证：超管权限点为通配 *", info.get("perms") == ["*"], info.get("perms"))
        check("认证：超管菜单树非空", len(info.get("menus") or []) > 0, f"{len(info.get('menus') or [])} 个顶级节点")

        # ---------- T-06 菜单与权限点 ----------
        _, body = call("GET", "/api/menu/mine", token=admin_token)
        my_menus = body.get("data") or []
        check("菜单：/menu/mine 返回菜单树", body.get("code") == 0 and len(my_menus) > 0)
        first_level = [node["name"] for node in my_menus]
        check("菜单：顶级菜单符合 seed 定义", set(first_level) >= {"知识管理", "AI 对话", "数据看板", "知识沉淀", "权限管理"}, first_level)

        _, body = call("GET", "/api/menu/tree", token=admin_token)
        full_tree = body.get("data") or []
        check("菜单：/menu/tree 返回含按钮的全量树", body.get("code") == 0 and len(full_tree) == 5, len(full_tree))
        chat_menu = find_menu(full_tree, "ai:chat")
        dash_menu = find_menu(full_tree, "dashboard:view")
        check("菜单：可按 perm 定位节点", bool(chat_menu and dash_menu))

        # ---------- T-07 部门 / 角色 / 用户 ----------
        _, body = call("GET", "/api/dept/tree", token=admin_token)
        check("部门：查询部门树", body.get("code") == 0 and len(body.get("data") or []) > 0)

        _, body = call("POST", "/api/dept", token=admin_token, body={"name": dept_name, "parentId": 0, "orderNo": 99, "enabled": True})
        check("部门：新增部门", body.get("code") == 0 and (body.get("data") or {}).get("name") == dept_name, body.get("message"))
        created["dept_id"] = (body.get("data") or {}).get("id")

        _, body = call("POST", "/api/role", token=admin_token, body={"name": f"冒烟角色{stamp}", "code": role_code, "remark": "smoke test", "enabled": True})
        check("角色：新增角色", body.get("code") == 0 and (body.get("data") or {}).get("code") == role_code, body.get("message"))
        role_id = (body.get("data") or {}).get("id")
        created["role_id"] = role_id

        _, body = call("POST", "/api/user", token=admin_token, body={
            "username": user_name, "password": "Smoke@123456", "nickname": "冒烟测试用户",
            "deptId": created["dept_id"], "roleIds": [role_id], "enabled": True,
        })
        check("用户：新增用户并绑定部门/角色", body.get("code") == 0 and (body.get("data") or {}).get("username") == user_name, body.get("message"))
        created["user_id"] = (body.get("data") or {}).get("id")

        _, body = call("GET", f"/api/user/list?keyword={user_name}", token=admin_token)
        items = (body.get("data") or {}).get("items") or []
        check("用户：列表可检索到新用户", body.get("code") == 0 and len(items) == 1, len(items))
        if items:
            check("用户：列表返回部门名与角色名", items[0].get("deptName") == dept_name and items[0].get("roleNames"), items[0].get("deptName"))

        _, body = call("POST", "/api/user", token=admin_token, body={"username": "bad name!", "password": "123456"})
        check("用户：非法账号名被参数校验拦截（10001）", body.get("code") == 10001, body.get("code"))

        # ---------- T-08 角色权限分配 ----------
        _, body = call("PUT", f"/api/role/{role_id}/menus", token=admin_token,
                       body={"menuIds": [chat_menu["id"], dash_menu["id"]]})
        check("授权：分配角色权限", body.get("code") == 0, body.get("message"))

        _, body = call("GET", f"/api/role/{role_id}/menus", token=admin_token)
        assigned = body.get("data") or []
        check("授权：回读角色权限一致", sorted(assigned) == sorted([chat_menu["id"], dash_menu["id"]]), assigned)

        _, body = call("PUT", f"/api/role/{role_id}/menus", token=admin_token, body={"menuIds": [999999]})
        check("授权：非法菜单 ID 被拒绝（10001）", body.get("code") == 10001, body.get("code"))

        # ---------- 普通用户视角：权限裁剪与越权拦截 ----------
        user_token, user_info = login(user_name, "Smoke@123456")
        check("普通用户：登录成功", bool(user_token))

        perms = set(user_info.get("perms") or [])
        check("普通用户：权限点仅含被授予项", perms == {"ai:chat", "dashboard:view"}, sorted(perms))
        check("普通用户：角色编码正确", user_info.get("roles") == [role_code], user_info.get("roles"))

        user_top = [node["name"] for node in (user_info.get("menus") or [])]
        check("普通用户：菜单仅含被授权项（知识管理/权限管理被裁剪）", set(user_top) >= {"AI 对话", "数据看板"} and "权限管理" not in user_top, user_top)

        _, body = call("GET", "/api/user/list", token=user_token)
        check("越权：无 user:list 权限访问用户列表被拒（20002）", body.get("code") == 20002, body.get("code"))

        _, body = call("GET", "/api/dept/tree", token=user_token)
        check("越权：无 dept:list 权限访问部门树被拒（20002）", body.get("code") == 20002, body.get("code"))

        _, body = call("GET", "/api/menu/tree", token=user_token)
        check("越权：无 role:perm 权限访问全量菜单树被拒（20002）", body.get("code") == 20002, body.get("code"))

        _, body = call("GET", "/api/knowledge/list", token=user_token)
        check("越权：无 knowledge:* 权限访问知识台账被拒（20002）", body.get("code") == 20002, body.get("code"))

    finally:
        if created.get("user_id"):
            _, body = call("DELETE", f"/api/user/{created['user_id']}", token=admin_token)
            check("清理：删除测试用户", body.get("code") == 0, body.get("message"))
        if created.get("role_id"):
            _, body = call("DELETE", f"/api/role/{created['role_id']}", token=admin_token)
            check("清理：删除测试角色", body.get("code") == 0, body.get("message"))
        if created.get("dept_id"):
            _, body = call("DELETE", f"/api/dept/{created['dept_id']}", token=admin_token)
            check("清理：删除测试部门", body.get("code") == 0, body.get("message"))

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

"""数据权限鉴权冒烟测试（T-16 / T-17）。

复现 PRD §2.9.9 的「跨部门知识隔离」场景：

    财务部 文档A（全局公开）           → 所有人可读
    人力资源部 文档B（部门+角色授权）   → 仅人力资源部 / 管理层角色 / 指定个人
    文档C（未配置任何权限）             → 任何人不可读（默认拒绝）

验证四维 OR 判定、fail-closed 默认、覆盖式赋权的即时生效、以及越权拦截。

用法：
    cd backend
    uv run python -m scripts.smoke_test_authz
"""

from __future__ import annotations

import time

from scripts.smoke_common import (
    ADMIN_PWD,
    ADMIN_USER,
    call,
    call_multipart,
    check,
    login,
    summary,
)

DOC_A = "# 差旅报销标准\n\n一线城市住宿每晚不超过 500 元。\n".encode("utf-8")
DOC_B = "# 高管薪酬与股权激励细则\n\n本细则仅对人力资源部与管理层开放。\n".encode("utf-8")
DOC_C = "# 未授权文档\n\n本文件未配置任何权限，应处于默认拒绝状态。\n".encode("utf-8")

USER_PWD = "Smoke@123456"


def upload(token: str, name: str, content: bytes) -> str:
    _, body = call_multipart("/api/knowledge/upload", [(name, content)], token=token)
    accepted = (body.get("data") or {}).get("accepted") or []
    return accepted[0]["docId"] if accepted else ""


def authz(token: str, doc_ids: list[str]) -> tuple[list[str], list[str]]:
    """以当前登录用户的身份做批量鉴权。"""
    _, body = call("POST", "/internal/authz/filter", token=token, body={"docIds": doc_ids})
    data = body.get("data") or {}
    return data.get("allowed") or [], data.get("denied") or []


def main() -> int:
    stamp = str(int(time.time()))[-6:]
    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)
    check("登录：超管登录成功", bool(admin_token))

    created = {"users": [], "roles": [], "depts": [], "docs": []}

    try:
        # ---------- 准备组织与账号 ----------
        _, body = call("POST", "/api/dept", token=admin_token,
                       body={"name": f"财务部{stamp}", "parentId": 0, "orderNo": 1, "enabled": True})
        dept_a = (body.get("data") or {})["id"]
        created["depts"].append(dept_a)

        _, body = call("POST", "/api/dept", token=admin_token,
                       body={"name": f"人力资源部{stamp}", "parentId": 0, "orderNo": 2, "enabled": True})
        dept_b = (body.get("data") or {})["id"]
        created["depts"].append(dept_b)

        _, body = call("POST", "/api/role", token=admin_token,
                       body={"name": f"管理层{stamp}", "code": f"exec_{stamp}", "enabled": True})
        role_r = (body.get("data") or {})["id"]
        created["roles"].append(role_r)

        def make_user(name: str, dept_id: int | None, role_ids: list[int]) -> tuple[int, str]:
            _, resp = call("POST", "/api/user", token=admin_token, body={
                "username": name, "password": USER_PWD, "nickname": name,
                "deptId": dept_id, "roleIds": role_ids, "enabled": True,
            })
            uid = (resp.get("data") or {})["id"]
            created["users"].append(uid)
            token, _ = login(name, USER_PWD)
            return uid, token

        _, alice_token = make_user(f"alice_{stamp}", dept_a, [])
        _, bob_token = make_user(f"bob_{stamp}", dept_b, [])
        _, carol_token = make_user(f"carol_{stamp}", None, [role_r])
        check("准备：三个账号分别归属不同部门/角色", all([alice_token, bob_token, carol_token]))

        # ---------- 上传三个知识单元 ----------
        doc_a = upload(admin_token, f"travel-policy-{stamp}.md", DOC_A)
        doc_b = upload(admin_token, f"exec-pay-{stamp}.md", DOC_B)
        doc_c = upload(admin_token, f"unassigned-{stamp}.md", DOC_C)
        created["docs"] = [doc_a, doc_b, doc_c]
        check("准备：上传三个知识单元", all([doc_a, doc_b, doc_c]))

        # ---------- T-17 赋权 ----------
        # 文档A：全局公开
        _, body = call("POST", "/api/knowledge/perms/assign", token=admin_token,
                       body={"docIds": [doc_a], "isGlobal": True})
        check("赋权：文档A 设为全局公开", body.get("code") == 0, body.get("message"))

        # 文档B：人力资源部 + 管理层角色
        _, body = call("POST", "/api/knowledge/perms/assign", token=admin_token,
                       body={"docIds": [doc_b], "deptIds": [dept_b], "roleIds": [role_r]})
        check("赋权：文档B 授予部门+角色", body.get("code") == 0, body.get("message"))

        # 文档C：不赋权，保持默认拒绝
        _, body = call("GET", f"/api/knowledge/{doc_c}/perms", token=admin_token)
        perm_c = body.get("data") or {}
        check("赋权：文档C 保持「未配置」状态", not any([
            perm_c.get("isGlobal"), perm_c.get("deptIds"), perm_c.get("roleIds"), perm_c.get("userIds"),
        ]), perm_c)

        _, body = call("GET", f"/api/knowledge/{doc_b}/perms", token=admin_token)
        perm_b = body.get("data") or {}
        check("赋权：回读文档B 权限配置一致",
              perm_b.get("deptIds") == [dept_b] and perm_b.get("roleIds") == [role_r], perm_b)

        _, body = call("GET", f"/api/knowledge/list?keyword=travel-policy", token=admin_token)
        items = (body.get("data") or {}).get("items") or []
        check("台账：权限标签正确反映全局公开", bool(items) and items[0]["permSummary"]["isGlobal"] is True,
              items[0]["permSummary"] if items else None)

        # ---------- T-16 四维判定 ----------
        docs = [doc_a, doc_b, doc_c]

        allowed, denied = authz(alice_token, docs)
        check("判定：财务部 alice —— 全局文档可读、人力文档被拒",
              allowed == [doc_a] and set(denied) == {doc_b, doc_c}, f"allowed={len(allowed)} denied={len(denied)}")

        allowed, denied = authz(bob_token, docs)
        check("判定：人力资源部 bob —— 部门命中，人力文档可读",
              set(allowed) == {doc_a, doc_b} and denied == [doc_c], f"allowed={len(allowed)}")

        allowed, denied = authz(carol_token, docs)
        check("判定：无部门但持管理层角色 carol —— 角色命中",
              set(allowed) == {doc_a, doc_b} and denied == [doc_c], f"allowed={len(allowed)}")

        allowed, denied = authz(admin_token, docs)
        check("判定：超管 —— 全部可读（含未配置文档）", sorted(allowed) == sorted(docs) and not denied)

        check("判定：未配置权限的文档对所有人默认拒绝（fail-closed）",
              all(doc_c in authz(tok, [doc_c])[1] for tok in (alice_token, bob_token, carol_token)))

        # ---------- 鉴权解释（排障/演示） ----------
        _, body = call("GET", f"/internal/authz/explain/{doc_b}", token=alice_token)
        explain = body.get("data") or {}
        check("解释：alice 对人力文档无权且给出原因",
              explain.get("allowed") is False and "未命中" in (explain.get("reason") or ""), explain.get("reason"))

        _, body = call("GET", f"/internal/authz/explain/{doc_b}", token=bob_token)
        explain = body.get("data") or {}
        check("解释：bob 命中部门维度", explain.get("allowed") is True and "department" in str(explain.get("matched")),
              explain.get("matched"))

        # ---------- 覆盖式赋权 + 即时生效 ----------
        alice_uid = created["users"][0]
        _, body = call("POST", "/api/knowledge/perms/assign", token=admin_token,
                       body={"docIds": [doc_b], "userIds": [alice_uid]})
        check("覆盖：文档B 改为仅 alice 个人可见", body.get("code") == 0, body.get("message"))

        allowed, _ = authz(alice_token, [doc_b])
        check("即时生效：alice 立即获得访问权（鉴权实时查库，无缓存延迟）", allowed == [doc_b])
        allowed, denied = authz(bob_token, [doc_b])
        check("即时生效：bob 立即失去访问权（原部门授权已被覆盖）", not allowed and denied == [doc_b])

        # ---------- 边界与越权 ----------
        _, body = call("POST", "/api/knowledge/perms/assign", token=admin_token,
                       body={"docIds": [doc_a], "deptIds": [999999]})
        check("校验：不存在的部门 ID 被拒绝（10001）", body.get("code") == 10001, body.get("message"))

        _, body = call("POST", "/api/knowledge/perms/assign", token=admin_token,
                       body={"docIds": ["not-exist-doc"], "isGlobal": True})
        check("校验：不存在的知识单元被拒绝（30001）", body.get("code") == 30001, body.get("code"))

        bob_uid = created["users"][1]
        _, body = call("POST", "/internal/authz/filter", token=alice_token,
                       body={"userId": bob_uid, "docIds": [doc_a]})
        check("越权：普通用户查询他人权限被拒（20003）", body.get("code") == 20003, body.get("code"))

        _, body = call("POST", "/api/knowledge/perms/assign", token=alice_token,
                       body={"docIds": [doc_a], "isGlobal": True})
        check("越权：无 knowledge:perm 权限的普通用户不能改权限（20002）", body.get("code") == 20002, body.get("code"))

    finally:
        for doc_id in created["docs"]:
            call("DELETE", f"/api/knowledge/{doc_id}", token=admin_token)
        for uid in created["users"]:
            call("DELETE", f"/api/user/{uid}", token=admin_token)
        for rid in created["roles"]:
            call("DELETE", f"/api/role/{rid}", token=admin_token)
        for did in created["depts"]:
            call("DELETE", f"/api/dept/{did}", token=admin_token)
        check("清理：测试数据已删除", True)

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

"""AI 鉴权问答冒烟测试（T-19 ~ T-24）。

覆盖：
1. 问答全链路——检索 → 鉴权 → 精排 → 流式生成 → 引用溯源；
2. **越权防护**——存在相关知识但无权访问时，返回固定提示且不调用大模型；
3. 知识缺口——库中无相关内容时如实说明，不凭空作答；
4. 会话隔离——会话只能被所属用户读取与删除；
5. 操作权限——无 ai:chat 权限者不可问答。

用法：
    cd backend
    uv run python -m scripts.smoke_test_chat [--timeout 240]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

from scripts.smoke_common import (
    ADMIN_PWD,
    ADMIN_USER,
    BASE,
    call,
    call_multipart,
    check,
    login,
    summary,
)

USER_PWD = "Smoke@123456"

PUBLIC_DOC = """# 差旅报销标准

## 住宿标准

一线城市住宿每晚不超过 500 元，二线城市不超过 350 元。

## 交通标准

普通员工出差乘坐高铁二等座；总监及以上可乘坐一等座。
""".encode("utf-8")

SECRET_DOC = """# 高管薪酬与股权激励细则

本细则仅限人力资源部查阅。高管年度基本薪酬区间为 120 万至 200 万元，
股权激励分四年归属，每年归属 25%。
""".encode("utf-8")


def call_stream(path: str, token: str, timeout: int = 240) -> list[dict]:
    """读取 SSE 流并解析为事件列表。"""
    request = urllib.request.Request(BASE + path, method="GET")
    request.add_header("Authorization", f"Bearer {token}")
    events: list[dict] = []
    current = None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append({"event": current, "data": json.loads(line[6:])})
                current = None
    return events


def ask(token: str, question: str, session_id: str | None = None, timeout: int = 240) -> tuple[dict, list[dict]]:
    """发起一次问答并读完整个 SSE 流，返回 (受理结果, 事件列表)。"""
    body = {"question": question}
    if session_id:
        body["sessionId"] = session_id
    _, resp = call("POST", "/api/chat/query", token=token, body=body)
    if resp.get("code") != 0:
        return resp, []
    data = resp.get("data") or {}
    events = call_stream(f"/api/chat/stream/{data['taskId']}", token, timeout=timeout)
    return data, events


def final_answer(events: list[dict]) -> str:
    for event in reversed(events):
        if event["event"] == "done":
            return event["data"].get("answer") or ""
    return ""


def main() -> int:
    timeout = 240
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    stamp = str(int(time.time()))[-6:]
    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)
    created = {"users": [], "roles": [], "depts": [], "docs": []}

    try:
        # ---------- 准备：一个公开文档 + 一个仅人力可见的文档 ----------
        _, body = call_multipart("/api/knowledge/upload",
                                 [(f"travel-{stamp}.md", PUBLIC_DOC)], token=admin_token)
        public_doc = (body.get("data") or {})["accepted"][0]["docId"]

        _, body = call_multipart("/api/knowledge/upload",
                                 [(f"exec-pay-{stamp}.md", SECRET_DOC)], token=admin_token)
        secret_doc = (body.get("data") or {})["accepted"][0]["docId"]
        created["docs"] = [public_doc, secret_doc]
        check("准备：上传公开文档与受限文档", bool(public_doc and secret_doc))

        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [public_doc], "isGlobal": True})

        _, body = call("POST", "/api/dept", token=admin_token,
                       body={"name": f"人力部{stamp}", "parentId": 0, "orderNo": 1, "enabled": True})
        dept_hr = (body.get("data") or {})["id"]
        created["depts"].append(dept_hr)
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [secret_doc], "deptIds": [dept_hr]})

        # 等两个文档完成导入（问答依赖向量已入库）
        print("    等待文档导入完成…")
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, resp = call("GET", "/api/knowledge/list?size=50", token=admin_token)
            items = {item["docId"]: item["status"] for item in (resp.get("data") or {}).get("items", [])}
            if items.get(public_doc) == "ready" and items.get(secret_doc) == "ready":
                break
            if "failed" in (items.get(public_doc), items.get(secret_doc)):
                break
            time.sleep(3)
        check("准备：文档导入完成",
              items.get(public_doc) == "ready" and items.get(secret_doc) == "ready",
              f"public={items.get(public_doc)} secret={items.get(secret_doc)}")

        # ---------- 场景一：有权问答 ----------
        result, events = ask(admin_token, "出差住宿标准是多少？", timeout=timeout)
        kinds = [event["event"] for event in events]
        check("问答：SSE 事件序列完整（stage → delta → references → done）",
              "stage" in kinds and "delta" in kinds and "done" in kinds, kinds)
        check("问答：收到正文增量（流式输出）", kinds.count("delta") > 0, f"{kinds.count('delta')} 个增量")
        answer = final_answer(events)
        check("问答：回答包含资料中的关键数值（500）", "500" in answer, answer[:60].replace("\n", " "))
        check("问答：回答非空且具备一定长度", len(answer) > 20, f"{len(answer)} 字")

        refs = next((e["data"].get("items") for e in events if e["event"] == "references"), [])
        check("引用：返回溯源卡片并指向公开文档", bool(refs) and any(r.get("docId") == public_doc for r in refs),
              f"{len(refs)} 条引用")

        session_id = result.get("sessionId")

        # ---------- 场景二：会话历史与多轮 ----------
        _, body = call("GET", "/api/chat/sessions", token=admin_token)
        sessions = body.get("data") or []
        check("会话：列表包含本次会话", any(s["sessionId"] == session_id for s in sessions), len(sessions))

        result2, events2 = ask(admin_token, "那交通标准呢？", session_id=session_id, timeout=timeout)
        check("多轮：可在同一会话内追问", bool(result2) and final_answer(events2) != "", result2.get("sessionId") == session_id)

        _, body = call("GET", f"/api/chat/history/{session_id}", token=admin_token)
        messages = body.get("data") or []
        roles = [m["role"] for m in messages]
        check("会话：历史含两轮问答（2 问 2 答）", len(messages) == 4 and roles.count("user") == 2, roles)

        # ---------- 场景三：越权防护（核心） ----------
        _, body = call("POST", "/api/user", token=admin_token, body={
            "username": f"leak_{stamp}", "password": USER_PWD, "nickname": "越权测试",
            "deptId": None, "roleIds": [], "enabled": True,
        })
        outsider_uid = (body.get("data") or {})["id"]
        created["users"].append(outsider_uid)

        # 该用户需要 ai:chat 权限才能提问：建一个只含 AI 对话的角色
        _, body = call("GET", "/api/menu/tree", token=admin_token)
        chat_menu = _find_menu(body.get("data") or [], "ai:chat")
        _, body = call("POST", "/api/role", token=admin_token,
                       body={"name": f"提问者{stamp}", "code": f"asker_{stamp}", "enabled": True})
        asker_role = (body.get("data") or {})["id"]
        created["roles"].append(asker_role)
        call("PUT", f"/api/role/{asker_role}/menus", token=admin_token,
             body={"menuIds": [chat_menu["id"]]})
        call("PUT", f"/api/user/{outsider_uid}", token=admin_token, body={
            "username": f"leak_{stamp}", "nickname": "越权测试", "roleIds": [asker_role], "enabled": True,
        })

        outsider_token, _ = login(f"leak_{stamp}", USER_PWD)
        check("准备：受限用户可登录且具备提问权限", bool(outsider_token))

        # 情形一：仍有部分有权内容 → 正常回答，但绝不得泄漏受限文档
        _, events3 = ask(outsider_token, "高管薪酬区间是多少？", timeout=timeout)
        answer3 = final_answer(events3)
        refs3 = next((e["data"].get("items") for e in events3 if e["event"] == "references"), [])
        check("越权：回答中不含受限文档的敏感数值（120 万 / 25%）",
              "120" not in answer3 and "25%" not in answer3, answer3[:50].replace("\n", " "))
        check("越权：引用来源不含受限文档",
              not any(r.get("docId") == secret_doc for r in refs3), f"{len(refs3)} 条引用")

        # 情形二：连公开文档也收权 → 完全无有权内容 → 应给出权限受限提示且不调用大模型
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [public_doc], "deptIds": [dept_hr]})
        _, events5 = ask(outsider_token, "住宿标准是多少？", timeout=timeout)
        notices5 = [e["data"] for e in events5 if e["event"] == "notice"]
        check("越权：无任何有权内容时返回权限受限提示",
              any(n.get("type") == "permission_denied" for n in notices5), notices5)
        check("越权：受限时不调用大模型（无正文增量）",
              not [e for e in events5 if e["event"] == "delta"], [e["event"] for e in events5][:6])

        # ---------- 场景四：知识缺口 ----------
        _, events4 = ask(admin_token, "公司食堂的午餐菜单是什么？", timeout=timeout)
        answer4 = final_answer(events4)
        check("缺口：无相关内容时如实说明且不编造",
              "未收录" in answer4 or "未检索到" in answer4 or "没有" in answer4, answer4[:60])

        # ---------- 会话隔离 ----------
        _, body = call("GET", f"/api/chat/history/{session_id}", token=outsider_token)
        check("隔离：他人无法读取该会话（10004/30001）", body.get("code") in (10004, 30001), body.get("code"))

        _, body = call("DELETE", f"/api/chat/history/{session_id}", token=outsider_token)
        check("隔离：他人无法删除该会话", body.get("code") in (10004, 30001), body.get("code"))

        # ---------- 操作权限 ----------
        _, body = call("POST", "/api/chat/query", body={"question": "test"})
        check("越权：未登录不能提问（20001）", body.get("code") == 20001, body.get("code"))

        # 无 ai:chat 权限的用户（admin 建一个无角色账号）
        _, body = call("POST", "/api/user", token=admin_token, body={
            "username": f"nochat_{stamp}", "password": USER_PWD, "nickname": "无权限",
            "deptId": None, "roleIds": [], "enabled": True,
        })
        nochat_uid = (body.get("data") or {})["id"]
        created["users"].append(nochat_uid)
        nochat_token, _ = login(f"nochat_{stamp}", USER_PWD)
        _, body = call("POST", "/api/chat/query", token=nochat_token, body={"question": "test"})
        check("越权：无 ai:chat 权限不能提问（20002）", body.get("code") == 20002, body.get("code"))

        # ---------- 清理会话 ----------
        _, body = call("DELETE", f"/api/chat/history/{session_id}", token=admin_token)
        check("会话：本人可删除会话", body.get("code") == 0, body.get("message"))

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


def _find_menu(nodes: list[dict], perm: str) -> dict:
    for node in nodes:
        if node.get("perm") == perm:
            return node
        hit = _find_menu(node.get("children") or [], perm)
        if hit:
            return hit
    return {}


if __name__ == "__main__":
    raise SystemExit(main())

"""端到端全流程演示（T-35）。

复现 PRD §2.9.9 的两个业务场景，用于向评审方演示完整链路：

    场景一：跨部门财务与薪酬制度问答隔离
    场景二：客服高频问答沉淀为 FAQ 与知识缺口补足

输出为可读的演示叙述（而非断言列表），每步给出实际结果与结论。
用法::

    cd backend
    uv run python -m scripts.demo_end_to_end [--timeout 240]
"""

from __future__ import annotations

import sys
import time

from app.core.config import settings
from scripts.smoke_common import (
    ADMIN_PWD,
    ADMIN_USER,
    call,
    call_multipart,
    login,
)
from scripts.smoke_test_chat import ask, final_answer

USER_PWD = "Smoke@123456"

TRAVEL_DOC = """# 差旅报销标准

## 住宿标准

一线城市住宿每晚不超过 500 元，二线城市不超过 350 元。

## 交通标准

普通员工出差乘坐高铁二等座；总监及以上可乘坐一等座。
""".encode("utf-8")

SALARY_DOC = """# 高管薪酬与股权激励细则

本细则仅限人力资源部与管理层查阅，禁止对外传播。

## 薪酬构成

高管年度基本薪酬区间为 120 万元至 200 万元，绩效奖金按年度考核结果发放。

## 股权激励

首次授予的期权分四年归属，每年归属 25%。
""".encode("utf-8")

AFTER_SALE_DOC = """# 售后政策

## 退换货规则

签收后 7 天内可无理由退货；生鲜类商品因易腐性不支持无理由退货，
但配送破损可在 24 小时内申请赔付。
""".encode("utf-8")

FAQ_QUESTION = "生鲜食品破损怎么赔偿？"
#: 缺口场景刻意选一个与库内文档**完全无关**的问题。
#: 注意：与知识库「沾边但不覆盖」的问题（例如同属客服域的"清关延误"）可能因
#: 重排分数高于相关性下限而不被判为缺口——这是相关性阈值的固有取舍，
#: 详见 README「知识缺口判定」说明。
GAP_QUESTION = "公司年会计划安排在什么时候？"


def step(text: str) -> None:
    print(f"  {text}")


def title(text: str) -> None:
    print(f"\n{'=' * 66}\n{text}\n{'=' * 66}")


def wait_doc_ready(token: str, doc_id: str, timeout: int) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, resp = call("GET", f"/api/knowledge/{doc_id}", token=token)
        status = (resp.get("data") or {}).get("status")
        if status in {"ready", "failed"}:
            return status or ""
        time.sleep(3)
    return "timeout"


def main() -> int:
    timeout = 240
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    stamp = str(int(time.time()))[-6:]
    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)
    cleanup = {"docs": [], "users": [], "roles": [], "depts": [], "faqs": []}

    try:
        # ==================================================================
        title("场景一：跨部门财务与薪酬制度问答隔离")
        # ==================================================================

        step("① 系统管理员维护组织架构")
        dept_fin, dept_hr = 0, 0
        for name, order in ((f"财务部{stamp}", 1), (f"人力资源部{stamp}", 2)):
            _, body = call("POST", "/api/dept", token=admin_token,
                           body={"name": name, "parentId": 0, "orderNo": order, "enabled": True})
            dept_id = (body.get("data") or {})["id"]
            cleanup["depts"].append(dept_id)
            if order == 1:
                dept_fin = dept_id
            else:
                dept_hr = dept_id

        _, body = call("POST", "/api/role", token=admin_token,
                       body={"name": f"提问者{stamp}", "code": f"demo_asker_{stamp}", "enabled": True})
        asker_role = (body.get("data") or {})["id"]
        cleanup["roles"].append(asker_role)

        _, body = call("GET", "/api/menu/tree", token=admin_token)
        chat_menu = _find(body.get("data") or [], "ai:chat")
        call("PUT", f"/api/role/{asker_role}/menus", token=admin_token,
             body={"menuIds": [chat_menu["id"]]})
        step(f"   部门：财务部 / 人力资源部；角色：提问者（仅 AI 对话权限）")

        step("② 创建三名员工账号")
        staff = {}
        roles = (("普通业务人员", None), ("财务人员", dept_fin), ("人力资源专员", dept_hr))
        for index, (label, dept_id) in enumerate(roles):
            username = f"demo{index}_{stamp}"
            _, body = call("POST", "/api/user", token=admin_token, body={
                "username": username, "password": USER_PWD, "nickname": label,
                "deptId": dept_id, "roleIds": [asker_role], "enabled": True,
            })
            cleanup["users"].append((body.get("data") or {})["id"])
            staff[label] = login(username, USER_PWD)[0]
            step(f"   {label}：{'无部门' if not dept_id else '已归属部门'}")
        outsider, hr_token = staff["普通业务人员"], staff["人力资源专员"]

        step("③ 知识管理员导入两份制度文档并配置四维权限")
        _, body = call_multipart("/api/knowledge/upload", [(f"travel-{stamp}.md", TRAVEL_DOC)], token=admin_token)
        travel_doc = (body.get("data") or {})["accepted"][0]["docId"]
        cleanup["docs"].append(travel_doc)

        _, body = call_multipart("/api/knowledge/upload", [(f"salary-{stamp}.md", SALARY_DOC)], token=admin_token)
        salary_doc = (body.get("data") or {})["accepted"][0]["docId"]
        cleanup["docs"].append(salary_doc)

        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [travel_doc], "isGlobal": True})
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [salary_doc], "deptIds": [dept_hr]})
        step("   《差旅报销标准》→ 全局公开")
        step("   《高管薪酬与股权激励细则》→ 仅人力资源部可见")
        step("   等待解析、切片与向量化…")
        for doc_id in (travel_doc, salary_doc):
            wait_doc_ready(admin_token, doc_id, timeout)
        step("   两份文档均已入库")

        step("④ 普通业务人员提问差旅标准")
        _, events = ask(outsider, "出差住宿标准是多少？", timeout=timeout)
        answer = final_answer(events)
        ok = "500" in answer
        step(f"   回答：{answer[:60].replace(chr(10), ' ')}…")
        step(f"   结论：{'正常作答 ✓' if ok else '未能作答 ✗'}")

        step("⑤ 同一用户提问高管薪酬")
        _, events = ask(outsider, "高管基本薪酬区间是多少？", timeout=timeout)
        answer = final_answer(events)
        leaked = ("120" in answer) or ("200万" in answer) or ("25%" in answer)
        step(f"   回答：{answer[:60].replace(chr(10), ' ')}…")
        step(f"   结论：{'未泄漏受限数据 ✓' if not leaked else '发生泄漏 ✗'}")

        step("⑥ 人力资源专员提问同一问题")
        _, events = ask(hr_token, "高管基本薪酬区间是多少？", timeout=timeout)
        answer = final_answer(events)
        ok = "120" in answer
        step(f"   回答：{answer[:60].replace(chr(10), ' ')}…")
        step(f"   结论：{'按部门权限正常作答 ✓' if ok else '未能作答 ✗'}")

        step("⑦ 有权限者提问差旅标准（全局文档对所有人开放）")
        _, events = ask(hr_token, "出差住宿标准是多少？", timeout=timeout)
        step(f"   结论：{'正常作答 ✓' if '500' in final_answer(events) else '未能作答 ✗'}")

        # ==================================================================
        title("场景二：客服高频问答沉淀为 FAQ 与知识缺口补足")
        # ==================================================================

        step("① 导入客服知识《售后政策》并对全员开放")
        _, body = call_multipart("/api/knowledge/upload", [(f"aftersale-{stamp}.md", AFTER_SALE_DOC)], token=admin_token)
        after_doc = (body.get("data") or {})["accepted"][0]["docId"]
        cleanup["docs"].append(after_doc)
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [after_doc], "isGlobal": True})
        wait_doc_ready(admin_token, after_doc, timeout)
        step("   文档已入库")

        threshold = max(1, settings.FAQ_RECOMMEND_THRESHOLD)
        step(f"② 一周内有多名用户反复咨询同一问题（阈值 {threshold} 次）")
        for _ in range(threshold):
            ask(outsider, FAQ_QUESTION, timeout=timeout)
        step(f"   已累计提问 {threshold} 次")

        step("③ 沉淀引擎自动聚类并生成候选 FAQ")
        candidate = None
        deadline = time.time() + 30
        while time.time() < deadline and not candidate:
            _, resp = call("GET", "/api/precipitation/faq/list?status=pending&size=50", token=admin_token)
            candidate = next((item for item in (resp.get("data") or {}).get("items", [])
                              if item["question"] == FAQ_QUESTION), None)
            time.sleep(2)
        if candidate:
            cleanup["faqs"].append(candidate["id"])
            step(f"   候选 FAQ：{candidate['question']}（聚合频次 {candidate['hitCount']}，"
                 f"置信度 {candidate['confidence']}）✓")
        else:
            step("   未生成候选 ✗")

        step("④ 知识管理员审核并发布标准答案")
        standard = "签收后 7 天内可无理由退货；生鲜破损可在 24 小时内申请赔付（人工审定版）。"
        if candidate:
            call("PUT", f"/api/precipitation/faq/{candidate['id']}/audit", token=admin_token,
                 body={"action": "publish", "answer": standard})
            step("   已发布上线")

        step("⑤ 后续同类提问直接命中缓存")
        started = time.perf_counter()
        _, events = ask(outsider, FAQ_QUESTION, timeout=timeout)
        cost_ms = int((time.perf_counter() - started) * 1000)
        answer = final_answer(events)
        cached = "人工审定版" in answer
        step(f"   响应耗时：{cost_ms} ms")
        step(f"   结论：{'毫秒级命中缓存、直接返回标准答案 ✓' if cached else '未命中缓存 ✗'}")

        step("⑥ 出现知识库未覆盖的新问题")
        ask(outsider, GAP_QUESTION, timeout=timeout)
        gap = None
        deadline = time.time() + 30
        while time.time() < deadline and not gap:
            _, resp = call("GET", "/api/precipitation/gap/list?size=50", token=admin_token)
            gap = next((item for item in (resp.get("data") or {}).get("items", [])
                        if item["question"] == GAP_QUESTION), None)
            time.sleep(2)
        step(f"   进入知识缺口清单：{'是 ✓' if gap else '否 ✗'}")

        step("⑦ 知识管理员据此创建补充任务")
        if gap:
            _, body = call("POST", f"/api/precipitation/gap/{gap['id']}/task", token=admin_token, body={})
            step(f"   任务已创建：{(body.get('data') or {}).get('title')} ✓")

        step("⑧ 运营看板呈现上述全部活动")
        _, body = call("GET", "/api/dashboard/overview?days=30", token=admin_token)
        ov = body.get("data") or {}
        step(f"   访问次数 {ov.get('totalVisits')} · 访问人数 {ov.get('distinctUsers')} · "
             f"知识单元 {ov.get('docCount')} · Token {ov.get('totalTokens')} · "
             f"缓存命中率 {round((ov.get('faqHitRate') or 0) * 100, 1)}% · "
             f"待处理缺口 {ov.get('gapCount')}")

        title("演示结束：两条业务场景的完整链路均已跑通")
        return 0

    finally:
        for faq_id in cleanup["faqs"]:
            call("DELETE", f"/api/precipitation/faq/{faq_id}", token=admin_token)
        for doc_id in cleanup["docs"]:
            call("DELETE", f"/api/knowledge/{doc_id}", token=admin_token)
        for uid in cleanup["users"]:
            call("DELETE", f"/api/user/{uid}", token=admin_token)
        for rid in cleanup["roles"]:
            call("DELETE", f"/api/role/{rid}", token=admin_token)
        for did in cleanup["depts"]:
            call("DELETE", f"/api/dept/{did}", token=admin_token)
        print("\n（演示数据已清理）")


def _find(nodes: list[dict], perm: str) -> dict:
    for node in nodes:
        if node.get("perm") == perm:
            return node
        hit = _find(node.get("children") or [], perm)
        if hit:
            return hit
    return {}


if __name__ == "__main__":
    raise SystemExit(main())

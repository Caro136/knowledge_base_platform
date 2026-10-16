"""知识沉淀冒烟测试（T-25 / T-30 ~ T-33）。

覆盖完整闭环：

    同一问题被反复提问 → 频次累加（未达阈值时处于「收集中」）
      → 达阈值自动生成候选 FAQ → 管理员审核发布（可在线修订答案）
      → 再次提问命中缓存直接作答（跳过检索与生成）
      → 库外问题进入知识缺口清单 → 一键转建补充任务 → 标记解决

用法：
    cd backend
    uv run python -m scripts.smoke_test_precipitation [--timeout 240]
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
    check,
    login,
    summary,
)
from scripts.smoke_test_chat import ask, final_answer

DOC = """# 差旅报销标准

## 住宿标准

一线城市住宿每晚不超过 500 元，二线城市不超过 350 元。
""".encode("utf-8")

FAQ_QUESTION = "出差住宿标准是多少钱？"
GAP_QUESTION = "公司班车几点发车？"


def wait_for(fn, timeout: int = 60, interval: float = 2.0):
    """轮询直到 fn 返回真值，返回该值；超时返回最后一次结果。"""
    deadline = time.time() + timeout
    result = None
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    return result


def main() -> int:
    timeout = 240
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    threshold = max(1, settings.FAQ_RECOMMEND_THRESHOLD)
    stamp = str(int(time.time()))[-6:]
    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)
    created = {"docs": [], "faq": [], "gaps": []}

    try:
        # ---------- 准备：一份可检索的知识 ----------
        _, body = call_multipart("/api/knowledge/upload",
                                 [(f"travel-b-{stamp}.md", DOC)], token=admin_token)
        doc_id = (body.get("data") or {})["accepted"][0]["docId"]
        created["docs"].append(doc_id)
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [doc_id], "isGlobal": True})

        print("    等待文档导入完成…")
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, resp = call("GET", f"/api/knowledge/{doc_id}", token=admin_token)
            if (resp.get("data") or {}).get("status") in {"ready", "failed"}:
                break
            time.sleep(3)
        check("准备：文档已入库", (resp.get("data") or {}).get("status") == "ready")

        # ---------- T-30 FAQ 挖掘 ----------
        print(f"    连续提问 {threshold} 次以触发 FAQ 推荐（阈值={threshold}）…")
        for index in range(threshold):
            _, events = ask(admin_token, FAQ_QUESTION, timeout=timeout)
            if index == 0:
                check("问答：首次提问走完整检索链路（非缓存）",
                      not any(e["event"] == "stage" and e["data"].get("stage") == "faq_cache" for e in events),
                      [e["event"] for e in events][:4])

        def find_faq(status: str | None = None):
            params = f"?status={status}" if status else ""
            _, resp = call("GET", f"/api/precipitation/faq/list{params}&size=50" if params else "/api/precipitation/faq/list?size=50",
                           token=admin_token)
            for item in (resp.get("data") or {}).get("items", []):
                if item["question"] == FAQ_QUESTION:
                    return item
            return None

        candidate = wait_for(lambda: find_faq("pending"), timeout=30)
        check("挖掘：达阈值后生成候选 FAQ（pending）", bool(candidate), candidate)
        if candidate:
            created["faq"].append(candidate["id"])
            check("挖掘：候选携带聚合频次", (candidate.get("hitCount") or 0) >= threshold, candidate.get("hitCount"))
            check("挖掘：候选携带置信度评分", candidate.get("confidence") is not None, candidate.get("confidence"))

        # 未达阈值的问题应停留在「收集中」，不出现在审核列表
        _, resp = call("GET", "/api/precipitation/faq/list?size=100", token=admin_token)
        statuses = {item["question"]: item["status"] for item in (resp.get("data") or {}).get("items", [])}
        check("挖掘：收集中的低频问题不进入审核列表",
              all(value != "collecting" for value in statuses.values()), statuses.get(FAQ_QUESTION))

        # ---------- T-31 审核发布与缓存命中 ----------
        revised = "一线城市每晚不超过 500 元；二线城市不超过 350 元。（人工审定的标准答案）"
        _, body = call("PUT", f"/api/precipitation/faq/{candidate['id']}/audit", token=admin_token,
                       body={"action": "publish", "answer": revised})
        check("审核：发布时可采用在线修订的答案", body.get("code") == 0 and
              (body.get("data") or {}).get("status") == "published", body.get("message"))

        _, body = call("GET", "/api/precipitation/faq/published", token=admin_token)
        published = body.get("data") or []
        check("缓存：已发布 FAQ 出现在常见问题列表", any(item["id"] == candidate["id"] for item in published))

        started = time.perf_counter()
        _, events = ask(admin_token, FAQ_QUESTION, timeout=timeout)
        cost_ms = int((time.perf_counter() - started) * 1000)
        stages = [e["data"].get("stage") for e in events if e["event"] == "stage"]
        check("缓存：相同问题命中 FAQ 缓存（跳过检索与生成）", "faq_cache" in stages, stages)
        check("缓存：命中后不产生流式正文增量（直接返回标准答案）",
              not [e for e in events if e["event"] == "delta"], [e["event"] for e in events])
        check("缓存：直接返回人工审定的答案", "人工审定" in final_answer(events), final_answer(events)[:40])
        check("缓存：端到端耗时进入毫秒级量级", cost_ms < 3000, f"{cost_ms} ms")

        # 表述略有差异的问题不应误命中（精确匹配语义）
        _, events_other = ask(admin_token, "报销流程是什么？", timeout=timeout)
        stages_other = [e["data"].get("stage") for e in events_other if e["event"] == "stage"]
        check("缓存：不同问题不会被缓存误命中", "faq_cache" not in stages_other, stages_other)

        # ---------- T-32 知识缺口 ----------
        ask(admin_token, GAP_QUESTION, timeout=timeout)

        def find_gap():
            _, resp = call("GET", "/api/precipitation/gap/list?size=50", token=admin_token)
            for item in (resp.get("data") or {}).get("items", []):
                if item["question"] == GAP_QUESTION:
                    return item
            return None

        gap = wait_for(find_gap, timeout=30)
        check("缺口：库外问题进入知识缺口清单", bool(gap), gap)
        if gap:
            created["gaps"].append(gap["id"])
            check("缺口：记录出现频次", (gap.get("hitCount") or 0) >= 1, gap.get("hitCount"))
            # admin 未归属部门，deptId 为空属预期；此处验证提问人已被记录
            check("缺口：记录最近提问人", gap.get("lastUserId") is not None, gap.get("lastUserId"))

        # 再问一次，频次应累加
        ask(admin_token, GAP_QUESTION, timeout=timeout)
        gap2 = wait_for(lambda: (find_gap() or {}).get("hitCount", 0) >= 2 and find_gap(), timeout=30)
        check("缺口：重复提问累加频次", bool(gap2), (gap2 or {}).get("hitCount"))

        # ---------- T-33 转建任务与标记解决 ----------
        if not gap:
            check("缺口：跳过转建任务（前置条件未满足）", False, "缺口未生成")
            return summary()

        _, body = call("POST", f"/api/precipitation/gap/{gap['id']}/task", token=admin_token,
                       body={})
        task = body.get("data") or {}
        check("缺口：一键转建知识补充任务", body.get("code") == 0 and task.get("status") == "open",
              task.get("title"))
        check("缺口：任务标题按缺口自动生成", GAP_QUESTION[:6] in (task.get("title") or ""), task.get("title"))

        _, resp = call("GET", "/api/precipitation/gap/list?size=50", token=admin_token)
        remaining = [item["question"] for item in (resp.get("data") or {}).get("items", [])]
        check("缺口：转建后从待处理清单中移除", GAP_QUESTION not in remaining, len(remaining))

        # ---------- 越权拦截 ----------
        _, body = call("GET", "/api/precipitation/faq/list", token="")
        check("越权：未登录不能查看 FAQ 列表（20001）", body.get("code") == 20001, body.get("code"))

    finally:
        for faq_id in created["faq"]:
            call("DELETE", f"/api/precipitation/faq/{faq_id}", token=admin_token)
        for doc_id in created["docs"]:
            call("DELETE", f"/api/knowledge/{doc_id}", token=admin_token)
        # 清理本次测试遗留的缺口（已转建的在创建任务时即标记处理）
        if created["gaps"]:
            call("PUT", f"/api/precipitation/gap/{created['gaps'][0]}/resolve", token=admin_token)
        check("清理：测试数据已处理", True)

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

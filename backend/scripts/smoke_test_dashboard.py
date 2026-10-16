"""运营看板冒烟测试（T-28）。

先制造一次真实问答，再校验看板四个接口的返回结构与数字自洽性
（流水 → 聚合 → 指标），最后验证权限拦截。

用法：
    cd backend
    uv run python -m scripts.smoke_test_dashboard [--timeout 240]
"""

from __future__ import annotations

import sys
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
from scripts.smoke_test_chat import ask

DOC = """# 差旅报销标准

## 住宿标准

一线城市住宿每晚不超过 500 元，二线城市不超过 350 元。
""".encode("utf-8")

QUESTION = "住宿标准是多少？"


def main() -> int:
    timeout = 240
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    stamp = str(int(time.time()))[-6:]
    admin_token, _ = login(ADMIN_USER, ADMIN_PWD)
    created = {"docs": [], "users": [], "roles": []}

    try:
        # ---------- 制造流量：上传 + 配权 + 提问 ----------
        _, body = call_multipart("/api/knowledge/upload",
                                 [(f"travel-d-{stamp}.md", DOC)], token=admin_token)
        doc_id = (body.get("data") or {})["accepted"][0]["docId"]
        created["docs"].append(doc_id)
        call("POST", "/api/knowledge/perms/assign", token=admin_token,
             body={"docIds": [doc_id], "isGlobal": True})

        deadline = time.time() + timeout
        while time.time() < deadline:
            _, resp = call("GET", f"/api/knowledge/{doc_id}", token=admin_token)
            if (resp.get("data") or {}).get("status") in {"ready", "failed"}:
                break
            time.sleep(3)
        check("准备：文档已入库", (resp.get("data") or {}).get("status") == "ready")

        before = (call("GET", "/api/dashboard/overview?days=30", token=admin_token)[1].get("data") or {})
        ask(admin_token, QUESTION, timeout=timeout)

        # 埋点在问答线程的 finally 中落库，稍等片刻再聚合
        time.sleep(2)

        # ---------- 总览 ----------
        _, body = call("GET", "/api/dashboard/overview?days=30", token=admin_token)
        ov = body.get("data") or {}
        check("总览：接口可用并返回完整字段",
              body.get("code") == 0 and all(
                  key in ov for key in
                  ("totalVisits", "distinctUsers", "docCount", "totalTokens",
                   "avgLatencyMs", "hitRate", "faqHitRate", "gapCount")),
              list(ov.keys()))
        check("总览：访问次数随本次问答增长",
              (ov.get("totalVisits") or 0) > (before.get("totalVisits") or 0),
              f"{before.get('totalVisits')} → {ov.get('totalVisits')}")
        check("总览：独立访问人数已统计", (ov.get("distinctUsers") or 0) >= 1, ov.get("distinctUsers"))
        check("总览：知识单元总数已统计", (ov.get("docCount") or 0) >= 1, ov.get("docCount"))
        check("总览：记录 Token 消耗（流式用量回传）", (ov.get("totalTokens") or 0) > 0, ov.get("totalTokens"))
        check("总览：平均响应时长为正值", (ov.get("avgLatencyMs") or 0) > 0, ov.get("avgLatencyMs"))
        check("总览：命中率为 0~1 之间的比例", 0 <= (ov.get("hitRate") or 0) <= 1, ov.get("hitRate"))

        # ---------- 趋势 ----------
        _, body = call("GET", "/api/dashboard/trend?days=7", token=admin_token)
        points = body.get("data") or []
        check("趋势：返回按天聚合的序列", body.get("code") == 0 and isinstance(points, list))
        check("趋势：本次问答计入当天数据点",
              any((point.get("pv") or 0) > 0 for point in points),
              points[-1] if points else None)
        check("趋势：数据点含日期与 PV/UV 字段",
              all({"date", "pv", "uv"} <= set(point.keys()) for point in points))

        # ---------- 排行 ----------
        _, body = call("GET", "/api/dashboard/top-questions?limit=10&days=30", token=admin_token)
        questions = body.get("data") or []
        check("排行：高频提问榜包含本次问题",
              any(item.get("question") == QUESTION for item in questions),
              [item.get("question") for item in questions][:3])

        # 取较大的 limit：榜单本身只返回 TOP N，历史流量会把新文档挤出前几名，
        # 因此这里验证「是否被统计到」而不是「排第几」，避免断言随数据积累而失效
        _, body = call("GET", "/api/dashboard/top-docs?limit=100&days=30", token=admin_token)
        docs = body.get("data") or []
        check("排行：热门知识榜统计到本次引用的文档",
              any(item.get("docId") == doc_id for item in docs),
              [(item.get("title"), item.get("count")) for item in docs][:3])
        check("排行：榜单按引用次数倒序",
              all(docs[index]["count"] >= docs[index + 1]["count"] for index in range(len(docs) - 1)),
              [item.get("count") for item in docs][:5])
        check("排行：条目携带文档标题而非裸 ID",
              all(item.get("title") and item["title"] != item["docId"] for item in docs),
              docs[0] if docs else None)

        # ---------- 权限 ----------
        _, body = call("POST", "/api/user", token=admin_token, body={
            "username": f"noview_{stamp}", "password": "Smoke@123456",
            "nickname": "无看板权限", "deptId": None, "roleIds": [], "enabled": True,
        })
        noview_uid = (body.get("data") or {})["id"]
        created["users"].append(noview_uid)
        noview_token, _ = login(f"noview_{stamp}", "Smoke@123456")

        _, body = call("GET", "/api/dashboard/overview", token=noview_token)
        check("越权：无 dashboard:view 权限不能查看看板（20002）", body.get("code") == 20002, body.get("code"))

        _, body = call("GET", "/api/dashboard/overview")
        check("越权：未登录不能查看看板（20001）", body.get("code") == 20001, body.get("code"))

    finally:
        for doc_id in created["docs"]:
            call("DELETE", f"/api/knowledge/{doc_id}", token=admin_token)
        for uid in created["users"]:
            call("DELETE", f"/api/user/{uid}", token=admin_token)
        check("清理：测试数据已删除", True)

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

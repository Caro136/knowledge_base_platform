"""知识台账与导入任务冒烟测试（T-10 / T-11）。

覆盖：格式清单、批量上传（含格式拒绝）、台账检索、详情、编辑、任务状态、
对象存储落地校验、删除级联清理、越权拦截。

用法：
    cd backend
    uv run python -m scripts.smoke_test_knowledge

脚本会在测试过程中创建知识单元，并在结束前删除；对象存储中的对象随之清理。
"""

from __future__ import annotations

from scripts.smoke_common import (
    ADMIN_PWD,
    ADMIN_USER,
    call,
    call_multipart,
    check,
    login,
    summary,
)

MARKDOWN_CONTENT = (
    "# 差旅报销标准\n\n"
    "## 住宿标准\n\n"
    "一线城市每晚不超过 500 元，二线城市不超过 350 元。\n"
).encode("utf-8")

TXT_CONTENT = "设备使用说明：开机前请检查电源指示灯。\n".encode("utf-8")

EXE_CONTENT = b"MZ\x90\x00fake-binary-content"


def main() -> int:
    admin_token, admin_info = login(ADMIN_USER, ADMIN_PWD)
    check("登录：超管登录成功", bool(admin_token), admin_info.get("username"))

    created_doc_ids: list[str] = []

    try:
        # ---------- T-10 格式清单 ----------
        status, body = call("GET", "/api/knowledge/supported-formats", token=admin_token)
        formats = body.get("data") or []
        source_types = {item["sourceType"] for item in formats}
        check("格式：返回 7 类来源格式（决策 D1）", len(formats) == 7, sorted(source_types))
        check(
            "格式：覆盖 TXT 与图片（参考基线缺失项）",
            {"txt", "image"} <= source_types,
            sorted(source_types),
        )
        all_exts = {ext for item in formats for ext in item["extensions"]}
        check("格式：扩展名清单完整", {".pdf", ".docx", ".md", ".txt", ".pptx", ".xlsx", ".png"} <= all_exts)

        # ---------- T-11 批量上传（部分成功） ----------
        status, body = call_multipart(
            "/api/knowledge/upload",
            [("travel-policy.md", MARKDOWN_CONTENT), ("device-note.txt", TXT_CONTENT), ("virus.exe", EXE_CONTENT)],
            token=admin_token,
        )
        data = body.get("data") or {}
        accepted = data.get("accepted") or []
        rejected = data.get("rejected") or []
        check("上传：合法文件被接受，非法文件被拒绝", body.get("code") == 0 and len(accepted) == 2 and len(rejected) == 1, f"accepted={len(accepted)} rejected={len(rejected)}")
        check("上传：拒绝原因说明格式不支持", rejected and "格式" in rejected[0].get("reason", ""), rejected[0].get("reason") if rejected else "")
        check("上传：返回 doc_id 与 task_id", all(item.get("docId") and item.get("taskId") for item in accepted))
        check("上传：按扩展名识别来源格式", {item["sourceType"] for item in accepted} == {"md", "txt"}, [item["sourceType"] for item in accepted])

        created_doc_ids = [item["docId"] for item in accepted]
        md_doc = next(item for item in accepted if item["sourceType"] == "md")
        doc_id = md_doc["docId"]
        task_id = md_doc["taskId"]

        # 空文件应被拒绝
        status, body = call_multipart("/api/knowledge/upload", [("empty.txt", b"")], token=admin_token)
        empty_rejected = (body.get("data") or {}).get("rejected") or []
        check("上传：空文件被拒绝", bool(empty_rejected), empty_rejected[0].get("reason") if empty_rejected else "")

        # ---------- 对象存储落地 ----------
        from app.services.storage_service import get_storage

        storage = get_storage()
        object_key = f"documents/{doc_id}.md"
        check("存储：文件已写入对象存储", storage.exists(object_key), storage.describe())

        # ---------- 台账与详情 ----------
        status, body = call("GET", "/api/knowledge/list?keyword=travel-policy", token=admin_token)
        page = body.get("data") or {}
        items = page.get("items") or []
        check("台账：可按关键词检索到新上传的文档", body.get("code") == 0 and len(items) == 1, len(items))
        if items:
            check("台账：标题取自文件名（去扩展名）", items[0]["title"] == "travel-policy", items[0]["title"])
            check("台账：初始状态为 pending（等待导入引擎）", items[0]["status"] == "pending", items[0]["status"])
            check("台账：返回权限摘要（未配置=无权限）", items[0]["permSummary"]["isGlobal"] is False, items[0]["permSummary"])

        status, body = call("GET", f"/api/knowledge/{doc_id}", token=admin_token)
        detail = body.get("data") or {}
        check("详情：可按 doc_id 查询", body.get("code") == 0 and detail.get("docId") == doc_id)

        # ---------- 导入任务状态 ----------
        status, body = call("GET", f"/api/knowledge/status/{task_id}", token=admin_token)
        task = body.get("data") or {}
        check("任务：可查询导入任务", body.get("code") == 0 and task.get("taskId") == task_id)
        check("任务：当前停留在 pending（执行引擎见 T-12）", task.get("status") == "pending" and task.get("stage") == "pending", f"{task.get('status')}/{task.get('stage')}")

        # ---------- T-10 编辑（PATCH 语义） ----------
        status, body = call("PUT", f"/api/knowledge/{doc_id}", token=admin_token, body={"title": "差旅报销标准（2026版）", "category": "财务制度"})
        updated = body.get("data") or {}
        check("编辑：标题与分类已更新", body.get("code") == 0 and updated.get("title") == "差旅报销标准（2026版）" and updated.get("category") == "财务制度", updated.get("title"))
        check("编辑：未提交的字段保持原值", updated.get("remark") is None and updated.get("enabled") is True)

        status, body = call("PUT", f"/api/knowledge/{doc_id}", token=admin_token, body={"enabled": False})
        check("编辑：可单独停用知识单元", (body.get("data") or {}).get("enabled") is False)

        status, body = call("PUT", f"/api/knowledge/{doc_id}", token=admin_token, body={"enabled": True})
        check("编辑：可重新启用", (body.get("data") or {}).get("enabled") is True)

        status, body = call("PUT", "/api/knowledge/not-exist-doc", token=admin_token, body={"title": "x"})
        check("编辑：不存在的知识单元返回 30001", body.get("code") == 30001, body.get("code"))

        # ---------- 越权拦截 ----------
        status, body = call("GET", "/api/knowledge/list")
        check("越权：未登录访问台账被拒（20001）", body.get("code") == 20001, body.get("code"))

    finally:
        # ---------- T-10 删除与级联清理 ----------
        for doc_id in created_doc_ids:
            status, body = call("DELETE", f"/api/knowledge/{doc_id}", token=admin_token)
            check(f"删除：{doc_id[:8]} 删除成功", body.get("code") == 0, body.get("message"))

        if created_doc_ids:
            from app.services.storage_service import get_storage

            storage = get_storage()
            removed_doc = created_doc_ids[0]
            check("删除：对象存储中的文件已被级联清理", not storage.exists(f"documents/{removed_doc}.md"))

            status, body = call("GET", f"/api/knowledge/{removed_doc}", token=admin_token)
            check("删除：台账中已不可见（30001）", body.get("code") == 30001, body.get("code"))

            # 权限条目由外键 CASCADE 清理，这里做一次数据库侧确认
            from sqlalchemy import func, select

            from app.db.session import SessionLocal
            from app.models import KbDocPerm

            with SessionLocal() as db:
                left = db.scalar(
                    select(func.count()).select_from(KbDocPerm).where(KbDocPerm.doc_id == removed_doc)
                )
            check("删除：数据权限条目已被级联清理", left == 0, f"剩余 {left} 条")

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

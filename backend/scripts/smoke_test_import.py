"""导入流程冒烟测试（T-12 / T-13）。

覆盖：直读格式（Markdown）的完整导入链路 → 切片 → 向量化 → Milvus 入库 →
知识单元状态回填 → 删除时向量级联清理。

说明：本脚本刻意只使用 **本地直读格式**（.md / .txt），因此不依赖文档解析服务
与视觉模型，可在模型选型尚未完全就绪时独立验证导入管线。
解析服务与图片语义化需另行验证（见 README「模型服务验证」）。

用法：
    cd backend
    uv run python -m scripts.smoke_test_import [--timeout 300]

注意：首次运行需加载 BGE-M3 模型，CPU 模式下可能耗时数十秒。
"""

from __future__ import annotations

import sys
import time

from scripts.smoke_common import ADMIN_PWD, ADMIN_USER, call, call_multipart, check, login, summary

# 测试文档刻意包含：多级标题、表格、列表 —— 用于验证切片与表格线性化
DOCUMENT = """# 差旅报销标准（导入测试）

## 住宿标准

一线城市每晚不超过 500 元，二线城市不超过 350 元。

## 交通标准

| 职级 | 高铁 | 飞机 |
|------|------|------|
| 普通员工 | 二等座 | 经济舱 |
| 总监及以上 | 一等座 | 商务舱 |

## 报销流程

1. 出差结束后 15 个工作日内提交报销单；
2. 附上发票与行程单；
3. 由部门负责人审批后交财务。
""".encode("utf-8")


def _build_sample_docx() -> bytes:
    """用标准库构造一个最小 .docx（zip + OOXML），用于验证解析服务链路。

    不引入 python-docx 等额外依赖：.docx 本质是 zip 包，含三份 XML 即为合法文档。
    """
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )

    paragraphs = [
        "差旅报销标准",
        "住宿标准",
        "一线城市每晚不超过 500 元，二线城市不超过 350 元。",
        "交通标准",
        "普通员工出差乘坐高铁二等座，总监及以上可乘坐一等座。",
        "报销流程",
        "出差结束后 15 个工作日内提交报销单，附发票与行程单。",
    ]
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>' for text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _wait_done(task_id: str, token: str, timeout: int) -> tuple[dict, list[str]]:
    """轮询任务直到终态，返回 (最终任务状态, 阶段轨迹)。"""
    deadline = time.time() + timeout
    stages: list[str] = []
    last: dict = {}
    while time.time() < deadline:
        _, body = call("GET", f"/api/knowledge/status/{task_id}", token=token)
        last = body.get("data") or {}
        stage = f"{last.get('stage')}/{last.get('status')}"
        if not stages or stages[-1] != stage:
            stages.append(stage)
        if last.get("status") in {"done", "failed"}:
            return last, stages
        time.sleep(2)
    return last, stages


def main() -> int:
    timeout = 300
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    # 默认使用内置 Markdown 文档（走本地直读路径，不依赖解析服务）；
    # --file <路径>   上传任意受支持格式，验证解析服务链路；
    # --sample-docx   现场生成一个最小 .docx 验证解析链路，无需外部素材。
    external = "--file" in sys.argv or "--sample-docx" in sys.argv
    if "--file" in sys.argv:
        from pathlib import Path

        path = Path(sys.argv[sys.argv.index("--file") + 1])
        if not path.is_file():
            print(f"文件不存在：{path}")
            return 1
        upload_item = (path.name, path.read_bytes())
        print(f"    使用外部文件：{path.name}（{path.stat().st_size / 1024:.0f} KB）")
    elif "--sample-docx" in sys.argv:
        upload_item = ("travel-standard.docx", _build_sample_docx())
        print("    使用现场生成的 .docx 样本（验证解析服务链路）")
    else:
        upload_item = ("travel-standard.md", DOCUMENT)

    token, _ = login(ADMIN_USER, ADMIN_PWD)
    check("登录：超管登录成功", bool(token))

    doc_id = ""
    try:
        # ---------- 上传 ----------
        _, body = call_multipart("/api/knowledge/upload", [upload_item], token=token)
        accepted = (body.get("data") or {}).get("accepted") or []
        check("上传：文件被接受", body.get("code") == 0 and len(accepted) == 1, body.get("message"))
        if not accepted:
            return summary()

        doc_id = accepted[0]["docId"]
        task_id = accepted[0]["taskId"]

        # ---------- 等待导入完成 ----------
        print(f"    等待导入完成（最长 {timeout}s，首次需加载嵌入模型）…")
        task, stages = _wait_done(task_id, token, timeout)
        check("导入：任务进入终态", task.get("status") in {"done", "failed"}, f"status={task.get('status')}")
        check("导入：任务执行成功", task.get("status") == "done", task.get("errorMsg") or "")
        print(f"    阶段轨迹：{' → '.join(stages)}")

        if task.get("status") != "done":
            return summary()

        # ---------- 知识单元状态回填 ----------
        _, body = call("GET", f"/api/knowledge/{doc_id}", token=token)
        detail = body.get("data") or {}
        check("入库：知识单元状态为 ready", detail.get("status") == "ready", detail.get("status"))
        chunk_count = detail.get("chunkCount") or 0
        check("入库：切片数量已回填", chunk_count > 0, f"{chunk_count} 个切片")

        # ---------- 向量库校验 ----------
        from app.services import vector_service

        stored = vector_service.count_by_doc_id(doc_id)
        check("向量：Milvus 中可查到该知识单元的切片", stored == chunk_count, f"milvus={stored} db={chunk_count}")

        client = vector_service.get_client()
        collection = vector_service.ensure_collection()
        rows = client.query(
            collection_name=collection,
            filter=f'doc_id == "{doc_id}"',
            output_fields=[
                "doc_id", "content", "title", "parent_title", "file_title",
                "dense_vector", "sparse_vector",
            ],
            limit=10,
        )
        check("向量：切片携带权限锚点 doc_id", all(row.get("doc_id") == doc_id for row in rows), len(rows))

        contents = "\n".join(str(row.get("content") or "") for row in rows)
        check("切片：正文内容已入库并可检索", "差旅报销标准" in contents, contents[:50].replace("\n", " / "))
        if not external:
            # 表格线性化只在内置 Markdown 样本中验证（外部样本不含表格）
            check(
                "切片：表格已线性化为「列名: 值」",
                "高铁: 二等座" in contents or "职级: 普通员工" in contents,
                contents[:120].replace("\n", " / "),
            )
        check("切片：稀疏向量非空（关键词检索可用）", any(row.get("sparse_vector") for row in rows))
        first_dense = rows[0].get("dense_vector") if rows else None
        check("切片：稠密向量维度正确（1024）", bool(first_dense) and len(first_dense) == 1024, len(first_dense or []))

        # ---------- 删除与级联清理 ----------
        _, body = call("DELETE", f"/api/knowledge/{doc_id}", token=token)
        check("删除：知识单元删除成功", body.get("code") == 0, body.get("message"))

        # collection 使用 Strong 一致性，删除应立即可见；仍保留短重试以吸收网络抖动
        remain = vector_service.count_by_doc_id(doc_id)
        for _ in range(5):
            if remain == 0:
                break
            time.sleep(1)
            remain = vector_service.count_by_doc_id(doc_id)
        check("删除：向量切片被级联清理", remain == 0, f"剩余 {remain} 条")
        doc_id = ""

    finally:
        if doc_id:
            call("DELETE", f"/api/knowledge/{doc_id}", token=token)

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())

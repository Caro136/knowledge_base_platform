"""知识单元与导入任务领域服务（T-10 / T-11）。

职责边界（SPEC §3.1 模块 M2）：
- 负责知识单元的台账、编辑、删除与级联清理；
- 负责文件格式校验、对象存储落地、doc_id 生成与导入任务登记；
- **不做**检索、不做权限判定，只负责写入权限锚点 ``doc_id``。
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError
from app.core.response import PageData
from app.models import (
    DOC_STATUS_PENDING,
    IMPORT_STATUS_PENDING,
    PERM_DEPARTMENT,
    PERM_GLOBAL,
    PERM_ROLE,
    PERM_USER,
    SOURCE_EXCEL,
    SOURCE_IMAGE,
    SOURCE_MD,
    SOURCE_PDF,
    SOURCE_PPT,
    SOURCE_TXT,
    SOURCE_WORD,
    KbDocPerm,
    KbDocument,
    KbImportTask,
    User,
)
from app.schemas.knowledge import (
    DocOut,
    DocPermSummary,
    DocQuery,
    DocUpdateIn,
    FormatItem,
    ImportTaskOut,
    RejectedItem,
    UploadedItem,
    UploadResult,
)
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 支持的来源格式（PRD 决策 D1：7 类）
# ---------------------------------------------------------------------------

EXT_SOURCE_MAP: dict[str, str] = {
    ".pdf": SOURCE_PDF,
    ".doc": SOURCE_WORD,
    ".docx": SOURCE_WORD,
    ".md": SOURCE_MD,
    ".markdown": SOURCE_MD,
    ".txt": SOURCE_TXT,
    ".ppt": SOURCE_PPT,
    ".pptx": SOURCE_PPT,
    ".xls": SOURCE_EXCEL,
    ".xlsx": SOURCE_EXCEL,
    ".png": SOURCE_IMAGE,
    ".jpg": SOURCE_IMAGE,
    ".jpeg": SOURCE_IMAGE,
}

FORMAT_LABELS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (SOURCE_PDF, "PDF 文档", (".pdf",)),
    (SOURCE_WORD, "Word 文档", (".doc", ".docx")),
    (SOURCE_MD, "Markdown", (".md", ".markdown")),
    (SOURCE_TXT, "纯文本", (".txt",)),
    (SOURCE_PPT, "PPT 演示文稿", (".ppt", ".pptx")),
    (SOURCE_EXCEL, "Excel 表格", (".xls", ".xlsx")),
    (SOURCE_IMAGE, "图片", (".png", ".jpg", ".jpeg")),
)


def _get_doc(db: Session, doc_id: str) -> KbDocument:
    doc = db.scalar(select(KbDocument).where(KbDocument.doc_id == doc_id))
    if doc is None:
        raise BizError(Code.DOCUMENT_NOT_FOUND)
    return doc


def _perm_summaries(db: Session, doc_ids: list[str]) -> dict[str, DocPermSummary]:
    """一次性汇总多个知识单元的数据权限，避免列表渲染时的 N+1 查询。"""
    if not doc_ids:
        return {}

    buckets: dict[str, dict[str, object]] = defaultdict(
        lambda: {"global": False, "dept": [], "role": [], "user": []}
    )
    rows = db.scalars(select(KbDocPerm).where(KbDocPerm.doc_id.in_(doc_ids))).all()
    for row in rows:
        bucket = buckets[row.doc_id]
        if row.perm_type == PERM_GLOBAL:
            bucket["global"] = True
        elif row.perm_type == PERM_DEPARTMENT:
            bucket["dept"].append(row.entity_id)  # type: ignore[union-attr]
        elif row.perm_type == PERM_ROLE:
            bucket["role"].append(row.entity_id)  # type: ignore[union-attr]
        elif row.perm_type == PERM_USER:
            bucket["user"].append(row.entity_id)  # type: ignore[union-attr]

    return {
        doc_id: DocPermSummary(
            is_global=bool(values["global"]),
            dept_ids=sorted(values["dept"]),  # type: ignore[arg-type]
            role_ids=sorted(values["role"]),  # type: ignore[arg-type]
            user_ids=sorted(values["user"]),  # type: ignore[arg-type]
        )
        for doc_id, values in buckets.items()
    }


def _to_doc_out(doc: KbDocument, summary: DocPermSummary | None = None) -> DocOut:
    return DocOut(
        id=doc.id,
        doc_id=doc.doc_id,
        title=doc.title,
        file_title=doc.file_title,
        source_type=doc.source_type,
        item_name=doc.item_name,
        category=doc.category,
        chunk_count=doc.chunk_count,
        status=doc.status,
        enabled=doc.enabled,
        remark=doc.remark,
        uploader_id=doc.uploader_id,
        task_id=doc.task_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        perm_summary=summary or DocPermSummary(),
    )


class KnowledgeService:
    """知识单元台账与导入任务。"""

    # ---------------- 格式清单 ----------------

    @staticmethod
    def supported_formats() -> list[FormatItem]:
        return [
            FormatItem(source_type=source, label=label, extensions=list(exts))
            for source, label, exts in FORMAT_LABELS
        ]

    # ---------------- 台账 ----------------

    @staticmethod
    def list_page(db: Session, query: DocQuery) -> PageData[DocOut]:
        conditions = []
        if query.keyword:
            like = f"%{query.keyword}%"
            conditions.append(
                or_(
                    KbDocument.title.like(like),
                    KbDocument.file_title.like(like),
                    KbDocument.item_name.like(like),
                )
            )
        if query.source_type:
            conditions.append(KbDocument.source_type == query.source_type)
        if query.category:
            conditions.append(KbDocument.category == query.category)
        if query.status:
            conditions.append(KbDocument.status == query.status)
        if query.enabled is not None:
            conditions.append(KbDocument.enabled.is_(query.enabled))

        total = db.scalar(select(func.count()).select_from(KbDocument).where(*conditions)) or 0
        rows = db.scalars(
            select(KbDocument)
            .where(*conditions)
            .order_by(KbDocument.id.desc())
            .offset((query.page - 1) * query.size)
            .limit(query.size)
        ).all()

        summaries = _perm_summaries(db, [row.doc_id for row in rows])
        return PageData[DocOut](
            items=[_to_doc_out(row, summaries.get(row.doc_id)) for row in rows],
            total=total,
            page=query.page,
            size=query.size,
        )

    @staticmethod
    def detail(db: Session, doc_id: str) -> DocOut:
        doc = _get_doc(db, doc_id)
        return _to_doc_out(doc, _perm_summaries(db, [doc_id]).get(doc_id))

    # ---------------- 编辑 / 删除 ----------------

    @staticmethod
    def update(db: Session, doc_id: str, payload: DocUpdateIn) -> DocOut:
        """部分更新：仅覆盖本次提交的字段（PATCH 语义）。"""
        doc = _get_doc(db, doc_id)
        submitted = payload.model_fields_set

        if "title" in submitted and payload.title:
            doc.title = payload.title
        if "category" in submitted:
            doc.category = payload.category
        if "item_name" in submitted:
            doc.item_name = payload.item_name
        if "remark" in submitted:
            doc.remark = payload.remark
        if "enabled" in submitted and payload.enabled is not None:
            doc.enabled = payload.enabled

        db.commit()
        db.refresh(doc)
        return _to_doc_out(doc, _perm_summaries(db, [doc_id]).get(doc_id))

    @staticmethod
    def delete(db: Session, doc_id: str) -> None:
        """删除知识单元并级联清理关联数据（FR-09）。

        清理顺序：先提交数据库事务（权限条目由外键 CASCADE 删除），
        再清理对象存储与向量库——避免"存储已删但事务回滚"造成的数据不一致。
        """
        doc = _get_doc(db, doc_id)
        storage_key = doc.minio_object

        db.delete(doc)
        db.commit()

        if storage_key:
            try:
                get_storage().delete(storage_key)
            except Exception as exc:  # noqa: BLE001 - 存储清理失败不应阻断删除
                logger.warning("对象存储清理失败 doc_id=%s key=%s: %s", doc_id, storage_key, exc)

        _purge_vectors(doc_id)
        logger.info("知识单元已删除 doc_id=%s", doc_id)

    # ---------------- 上传（T-11） ----------------

    @staticmethod
    async def upload(db: Session, files: list[UploadFile], uploader: User) -> UploadResult:
        """批量上传：逐文件校验格式与大小，落地对象存储，登记知识单元与导入任务。

        部分成功是常态（一个批次里允许混有格式不支持的文件），
        因此返回结构区分 accepted / rejected，由前端分别展示。
        """
        if not files:
            raise BizError(Code.PARAM_INVALID, "未接收到任何文件")

        storage = get_storage()
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        result = UploadResult()

        for upload_file in files:
            filename = (upload_file.filename or "").strip()
            if not filename:
                result.rejected.append(RejectedItem(filename="(未命名)", reason="文件名为空"))
                continue

            ext = Path(filename).suffix.lower()
            source_type = EXT_SOURCE_MAP.get(ext)
            if source_type is None:
                result.rejected.append(
                    RejectedItem(filename=filename, reason=f"不支持的文件格式：{ext or '未知扩展名'}")
                )
                continue

            try:
                data = await upload_file.read()
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取上传文件失败 %s: %s", filename, exc)
                result.rejected.append(RejectedItem(filename=filename, reason="文件读取失败"))
                continue

            if not data:
                result.rejected.append(RejectedItem(filename=filename, reason="文件内容为空"))
                continue

            if len(data) > max_bytes:
                result.rejected.append(
                    RejectedItem(filename=filename, reason=f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制")
                )
                continue

            doc_id = uuid.uuid4().hex
            task_id = uuid.uuid4().hex
            object_key = f"documents/{doc_id}{ext}"

            try:
                # 存储写入是同步阻塞 IO，放到线程池避免阻塞事件循环
                await run_in_threadpool(storage.put, object_key, data, None)
            except BizError as exc:
                result.rejected.append(RejectedItem(filename=filename, reason=exc.message))
                continue

            file_title = Path(filename).stem or filename
            doc = KbDocument(
                doc_id=doc_id,
                title=file_title,
                file_title=file_title,
                source_type=source_type,
                minio_object=object_key,
                chunk_count=0,
                status=DOC_STATUS_PENDING,   # 等待导入引擎处理
                enabled=True,
                task_id=task_id,
                uploader_id=uploader.id,
            )
            task = KbImportTask(
                task_id=task_id,
                doc_id=doc_id,
                filename=filename,
                source_type=source_type,
                stage="pending",
                status=IMPORT_STATUS_PENDING,
            )
            db.add(doc)
            db.add(task)
            db.commit()

            result.accepted.append(
                UploadedItem(
                    task_id=task_id,
                    doc_id=doc_id,
                    filename=filename,
                    source_type=source_type,
                    size=len(data),
                )
            )

        if result.accepted:
            _dispatch_import([item.task_id for item in result.accepted])

        return result

    # ---------------- 任务状态 ----------------

    @staticmethod
    def task_status(db: Session, task_id: str) -> ImportTaskOut:
        task = db.scalar(select(KbImportTask).where(KbImportTask.task_id == task_id))
        if task is None:
            raise BizError(Code.NOT_FOUND, "导入任务不存在")
        return ImportTaskOut(
            task_id=task.task_id,
            doc_id=task.doc_id,
            filename=task.filename,
            source_type=task.source_type,
            stage=task.stage,
            status=task.status,
            error_msg=task.error_msg,
            created_at=task.created_at,
            finished_at=task.finished_at,
        )


def _dispatch_import(task_ids: list[str]) -> None:
    """把导入任务交给执行引擎（T-12 起真实执行）。

    在线程池中异步执行导入 DAG，本函数立即返回，不阻塞上传接口。
    若执行引擎不可用（依赖缺失等），显式把任务标记为失败，
    而不是让任务永远停留在 pending 状态。
    """
    try:
        from app.processor.runner import submit_import
    except Exception as exc:  # noqa: BLE001
        _mark_dispatch_failed(task_ids, f"导入执行引擎不可用：{exc}")
        return

    for task_id in task_ids:
        submit_import(task_id)
    logger.info("已提交 %d 个导入任务到执行引擎", len(task_ids))


def _mark_dispatch_failed(task_ids: list[str], reason: str) -> None:
    """调度失败时把任务与知识单元标记为失败，原因写入任务详情。"""
    from datetime import datetime

    from app.db.session import SessionLocal
    from app.models import DOC_STATUS_FAILED, IMPORT_STATUS_FAILED, KbImportTask

    logger.error("提交导入任务失败：%s", reason)
    with SessionLocal() as db:
        for task_id in task_ids:
            task = db.scalar(select(KbImportTask).where(KbImportTask.task_id == task_id))
            if task is None:
                continue
            task.status = IMPORT_STATUS_FAILED
            task.stage = "failed"
            task.error_msg = reason[:500]
            task.finished_at = datetime.now()

            doc = db.scalar(select(KbDocument).where(KbDocument.doc_id == task.doc_id))
            if doc is not None:
                doc.status = DOC_STATUS_FAILED
        db.commit()


def _purge_vectors(doc_id: str) -> None:
    """清理向量库中该知识单元的全部切片。

    T-13 实现向量服务后自动生效；当前阶段向量库尚无数据，静默跳过。
    """
    try:
        from app.services.vector_service import delete_by_doc_id  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        delete_by_doc_id(doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("向量切片清理失败 doc_id=%s: %s", doc_id, exc)

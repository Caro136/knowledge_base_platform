"""导入任务调度器（T-12）。

用固定大小线程池执行导入 DAG：导入是「网络 IO（解析服务）+ CPU 密集（向量化）」
混合型任务，并发过高会压垮单机算力（尤其 CPU 模式下的 BGE 推理），
因此 worker 数量保守设定，多任务时排队执行。

阶段进度通过 ``stream_mode="updates"`` 在**每个节点完成后**落库，
前端轮询即可看到「解析 → 图片理解 → 切片 → 向量化」的推进过程。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.db.session import SessionLocal
from app.models import (
    DOC_STATUS_FAILED,
    DOC_STATUS_READY,
    IMPORT_STATUS_DONE,
    IMPORT_STATUS_FAILED,
    IMPORT_STATUS_RUNNING,
    KbDocument,
    KbImportTask,
)
from app.processor.graph import get_import_graph
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)

#: 导入并发度：单机 + CPU 推理场景下不宜过高
MAX_CONCURRENT_IMPORTS = 2

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_IMPORTS, thread_name_prefix="kb-import")

#: LangGraph 节点 → 对外展示的阶段名
_STAGE_BY_NODE: dict[str, str] = {
    "entry": "reading",
    "doc_parse": "parsing",
    "image_summary": "images",
    "split": "splitting",
    "embed_store": "embedding",
}


def submit_import(task_id: str) -> None:
    """提交导入任务（非阻塞，立即返回）。"""
    _executor.submit(run_import_task, task_id)
    logger.info("导入任务已入队：%s", task_id)


def run_import_task(task_id: str) -> None:
    """执行单个导入任务（在线程池中运行）。"""
    with SessionLocal() as db:
        task = db.scalar(select(KbImportTask).where(KbImportTask.task_id == task_id))
        if task is None:
            logger.warning("导入任务不存在，跳过：%s", task_id)
            return

        doc = db.scalar(select(KbDocument).where(KbDocument.doc_id == task.doc_id))
        if doc is None:
            logger.warning("知识单元不存在，跳过导入：%s", task.doc_id)
            _fail(db, task, "知识单元不存在")
            return

        try:
            _touch(db, task, stage="reading", status=IMPORT_STATUS_RUNNING)

            file_bytes = get_storage().get(doc.minio_object or "")
            if not file_bytes:
                raise BizError(Code.PARSE_FAILED, "原始文件内容为空")

            state = {
                "doc_id": doc.doc_id,
                "task_id": task.task_id,
                "filename": task.filename,
                "source_type": doc.source_type,
                "file_bytes": file_bytes,
            }

            final_state = dict(state)
            for update in get_import_graph().stream(state, stream_mode="updates"):
                for node_name, node_output in update.items():
                    if isinstance(node_output, dict):
                        final_state.update(node_output)
                    stage = _STAGE_BY_NODE.get(node_name)
                    if stage:
                        _touch(db, task, stage=stage)

            _succeed(db, task, doc, final_state)

        except Exception as exc:  # noqa: BLE001 - 任何失败都要落到任务状态上
            db.rollback()
            message = exc.message if isinstance(exc, BizError) else str(exc)
            logger.exception("导入失败 task_id=%s doc_id=%s", task_id, task.doc_id)
            _fail(db, task, message)


def _touch(db: Session, task: KbImportTask, *, stage: str | None = None, status: str | None = None) -> None:
    """更新任务阶段并落库（供前端轮询读取）。"""
    if stage:
        task.stage = stage
    if status:
        task.status = status
    db.commit()


def _succeed(db: Session, task: KbImportTask, doc: KbDocument, final_state: dict) -> None:
    """任务成功收尾：回填切片数、状态与警告信息。"""
    task = db.get(KbImportTask, task.id)
    doc = db.get(KbDocument, doc.id)

    if doc is None:
        # 导入过程中知识单元被删除：此时刚写入的向量切片需要回收，任务以失败收尾
        logger.warning("导入完成时知识单元已被删除，回收其向量切片 doc_id=%s", task.doc_id)
        try:
            from app.services.vector_service import delete_by_doc_id

            delete_by_doc_id(task.doc_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("回收向量切片失败 doc_id=%s: %s", task.doc_id, exc)

        task.status = IMPORT_STATUS_FAILED
        task.stage = "failed"
        task.error_msg = "知识单元已被删除，导入结果未采用"
        task.finished_at = datetime.now()
        db.commit()
        return

    doc.chunk_count = int(final_state.get("chunk_count") or 0)
    doc.status = DOC_STATUS_READY

    task.status = IMPORT_STATUS_DONE
    task.stage = "done"
    task.finished_at = datetime.now()

    warnings = [str(item) for item in (final_state.get("warnings") or [])]
    if warnings:
        # 成功但存在非致命问题（如个别图片语义化失败），保留在任务详情中便于排查
        task.error_msg = ("部分内容处理存在警告：" + "；".join(warnings))[:500]

    db.commit()
    logger.info("导入完成 doc_id=%s，切片 %d 个", doc.doc_id, doc.chunk_count)


def _fail(db: Session, task: KbImportTask, message: str) -> None:
    """任务失败收尾。"""
    if task.id:
        task = db.get(KbImportTask, task.id) or task
        doc = db.scalar(select(KbDocument).where(KbDocument.doc_id == task.doc_id))

        task.status = IMPORT_STATUS_FAILED
        task.stage = "failed"
        task.error_msg = (message or "未知错误")[:500]
        task.finished_at = datetime.now()

        if doc is not None:
            doc.status = DOC_STATUS_FAILED

        db.commit()

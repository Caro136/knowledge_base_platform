"""知识管理接口（T-10 / T-11）。

路由注册顺序说明：``/supported-formats``、``/upload``、``/status/{task_id}``、``/list``
必须排在 ``/{doc_id}`` 之前，否则会被后者当作 doc_id 捕获。
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_any_permission, require_permission
from app.models import User
from app.schemas.knowledge import DocQuery, DocUpdateIn
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["知识管理"])

#: 只读权限点：台账菜单权限与查询按钮权限均可读
_READ_PERMS = ("knowledge:list", "knowledge:query")


@router.get("/supported-formats", summary="支持的文档格式")
def supported_formats(
    _: User = Depends(require_any_permission(*_READ_PERMS, "knowledge:import")),
) -> dict:
    return ok(KnowledgeService.supported_formats())


@router.post("/upload", summary="批量上传文档")
async def upload(
    files: list[UploadFile] = File(..., description="支持一次上传多个文件"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:import")),
) -> dict:
    return ok(await KnowledgeService.upload(db, files, user))


@router.get("/status/{task_id}", summary="查询导入任务进度")
def task_status(
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    return ok(KnowledgeService.task_status(db, task_id))


@router.get("/list", summary="知识单元台账（分页）")
def list_docs(
    keyword: str | None = Query(default=None, description="标题/来源文件名/产品名模糊匹配"),
    sourceType: str | None = Query(default=None, description="来源格式"),  # noqa: N803
    category: str | None = Query(default=None),
    status: str | None = Query(default=None, description="pending/ready/failed"),
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    query = DocQuery(
        keyword=keyword,
        source_type=sourceType,
        category=category,
        status=status,
        enabled=enabled,
        page=page,
        size=size,
    )
    return ok(KnowledgeService.list_page(db, query))


@router.get("/{doc_id}", summary="知识单元详情")
def detail(
    doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    return ok(KnowledgeService.detail(db, doc_id))


@router.get("/{doc_id}/assets/{name}", summary="知识单元图片资源（答案配图）")
def asset(
    doc_id: str,
    name: str,
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> Response:
    """按文件名返回图片内容。

    仅允许访问该知识单元目录下的图片：文件名经 ``Path(...).name`` 归一化，
    存储层还会再校验一次路径越界。
    """
    from urllib.parse import quote

    from app.services.storage_service import get_storage

    safe_name = Path(name).name
    key = f"documents/{doc_id}/images/{safe_name}"
    data = get_storage().get(key)
    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(safe_name)}"},
    )


@router.put("/{doc_id}", summary="编辑知识单元")
def update_doc(
    doc_id: str,
    payload: DocUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("knowledge:update")),
) -> dict:
    return ok(KnowledgeService.update(db, doc_id, payload))


@router.delete("/{doc_id}", summary="删除知识单元（级联清理切片与权限）")
def delete_doc(
    doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("knowledge:delete")),
) -> dict:
    KnowledgeService.delete(db, doc_id)
    return ok(message="删除成功")

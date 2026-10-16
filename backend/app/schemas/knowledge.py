"""知识管理 Schema（T-10 / T-11）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel, InModel

# ---------------------------------------------------------------------------
# 知识单元
# ---------------------------------------------------------------------------


class DocPermSummary(CamelModel):
    """知识单元的权限摘要（台账列表的「权限标签」列）。"""

    is_global: bool = False
    dept_ids: list[int] = Field(default_factory=list)
    role_ids: list[int] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)


class DocOut(CamelModel):
    """知识单元台账项。"""

    id: int
    doc_id: str
    title: str
    file_title: str | None = None
    source_type: str
    item_name: str | None = None
    category: str | None = None
    chunk_count: int = 0
    status: str
    enabled: bool = True
    remark: str | None = None
    uploader_id: int | None = None
    task_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    perm_summary: DocPermSummary = Field(default_factory=DocPermSummary)


class DocQuery(InModel):
    """台账查询条件。"""

    keyword: str | None = Field(default=None, description="按标题/来源文件名模糊匹配")
    source_type: str | None = None
    category: str | None = None
    status: str | None = None
    enabled: bool | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)


class DocUpdateIn(InModel):
    """知识单元编辑入参。

    仅提交需要修改的字段；未提交的字段保持原值（PATCH 语义）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=64)
    item_name: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# 上传与导入任务
# ---------------------------------------------------------------------------


class UploadedItem(CamelModel):
    """单个文件的上传结果。"""

    task_id: str
    doc_id: str
    filename: str
    source_type: str
    size: int


class RejectedItem(CamelModel):
    """被拒绝的文件及原因（格式不支持、超限等）。"""

    filename: str
    reason: str


class UploadResult(CamelModel):
    """批量上传结果：部分成功是常态，故拆分为 accepted / rejected。"""

    accepted: list[UploadedItem] = Field(default_factory=list)
    rejected: list[RejectedItem] = Field(default_factory=list)


class ImportTaskOut(CamelModel):
    """导入任务状态（前端轮询进度）。"""

    task_id: str
    doc_id: str
    filename: str
    source_type: str
    stage: str
    status: str
    error_msg: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class FormatItem(CamelModel):
    """支持的来源格式（供前端展示可上传的扩展名）。"""

    source_type: str
    label: str
    extensions: list[str]

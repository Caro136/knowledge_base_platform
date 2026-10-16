"""知识域模型（SPEC §5.2 知识域）。

核心约定：``kb_document.doc_id`` 是**数据权限锚点**，会被冗余写入
向量库的每个切片；鉴权时按切片携带的 doc_id 反查权限。
切片不带 doc_id 时一律拒绝（fail-closed）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---------- 四维数据权限类型（PRD §2.3 / 决策 D1） ----------
PERM_GLOBAL = "global"
PERM_DEPARTMENT = "department"
PERM_ROLE = "role"
PERM_USER = "user"
PERM_TYPES: tuple[str, ...] = (PERM_GLOBAL, PERM_DEPARTMENT, PERM_ROLE, PERM_USER)

# ---------- 知识单元状态 ----------
DOC_STATUS_PENDING = "pending"
DOC_STATUS_READY = "ready"
DOC_STATUS_FAILED = "failed"

# ---------- 来源格式（PRD 决策 D1：7 类） ----------
SOURCE_PDF = "pdf"
SOURCE_WORD = "word"
SOURCE_MD = "md"
SOURCE_TXT = "txt"
SOURCE_PPT = "ppt"
SOURCE_EXCEL = "excel"
SOURCE_IMAGE = "image"

#: 与前端展示顺序一致
SUPPORTED_SOURCE_TYPES: tuple[str, ...] = (
    SOURCE_PDF, SOURCE_WORD, SOURCE_MD, SOURCE_TXT, SOURCE_PPT, SOURCE_EXCEL, SOURCE_IMAGE,
)

# ---------- 导入任务 ----------
IMPORT_STATUS_PENDING = "pending"
IMPORT_STATUS_RUNNING = "running"
IMPORT_STATUS_DONE = "done"
IMPORT_STATUS_FAILED = "failed"


class KbDocument(Base, TimestampMixin):
    """知识单元（文档级元数据）。"""

    __tablename__ = "kb_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="权限锚点，uuid hex"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="知识单元标题")
    file_title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="来源文件名（去扩展名）")
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="来源格式")
    item_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="商品/产品名")
    category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="所属分类（PRD Q3 待确认）"
    )
    minio_object: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="对象存储路径")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="切片数量")
    status: Mapped[str] = mapped_column(
        String(16), default=DOC_STATUS_PENDING, nullable=False, index=True, comment="处理状态"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")
    task_id: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="最近一次导入任务ID")
    uploader_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="上传人")
    remark: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="备注")

    perms: Mapped[list["KbDocPerm"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class KbDocPerm(Base, TimestampMixin):
    """知识单元的四维数据权限条目（命中任一即放行）。

    默认无任何记录 = 无任何用户可访问（拒绝优先）。
    """

    __tablename__ = "kb_doc_perm"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="权限锚点")
    document_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_document.id", ondelete="CASCADE"), nullable=False, comment="知识单元主键"
    )
    perm_type: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True, comment="权限类型：global/department/role/user"
    )
    entity_id: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, index=True, comment="部门/角色/用户ID，global 时为 0"
    )

    document: Mapped[KbDocument] = relationship(back_populates="perms")


class KbImportTask(Base, TimestampMixin):
    """导入任务（异步进度持久化，PRD FR-07）。

    独立成表的原因：上传后立即返回 task_id，解析/向量化为长耗时后台任务，
    进程重启后仍需能查询到任务状态。
    """

    __tablename__ = "kb_import_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True, comment="任务ID")
    doc_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="关联知识单元锚点")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="来源格式")
    stage: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, comment="当前阶段")
    status: Mapped[str] = mapped_column(
        String(16), default=IMPORT_STATUS_PENDING, nullable=False, index=True, comment="任务状态"
    )
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败原因")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")

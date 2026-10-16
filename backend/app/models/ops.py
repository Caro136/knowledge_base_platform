"""运营与沉淀域模型（SPEC §5.2 运营与沉淀域）。

- ``kb_access_log``：问答流水，看板全部指标的单一数据源
- ``kb_faq`` / ``kb_faq_perm``：FAQ 沉淀与缓存
- ``kb_knowledge_gap`` / ``kb_gap_task``：知识缺口与转建任务
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---------- FAQ 状态 ----------
FAQ_STATUS_PENDING = "pending"
FAQ_STATUS_PUBLISHED = "published"
FAQ_STATUS_REJECTED = "rejected"

# ---------- FAQ 来源 ----------
FAQ_SOURCE_AUTO = "auto"
FAQ_SOURCE_MANUAL = "manual"

# ---------- 知识补充任务状态 ----------
GAP_TASK_OPEN = "open"
GAP_TASK_PROCESSING = "processing"
GAP_TASK_DONE = "done"


class KbAccessLog(Base):
    """问答审计流水（PRD FR-40）。

    按决策 D3：**不记录鉴权拦截明细**（denied 集合仅在应用日志中保留，
    用于短期排障，不作为长期审计数据）。
    本表写入量大，只保留 created_at，不设 updated_at。
    """

    __tablename__ = "kb_access_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="会话ID")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="用户ID")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="用户名快照")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="部门快照")
    question: Mapped[str] = mapped_column(String(512), nullable=False, index=True, comment="提问文本")
    hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否有有权上下文")
    faq_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否命中FAQ缓存")
    is_gap: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="是否判定为知识缺口（决策D2三条件）"
    )
    recalled_doc_ids: Mapped[str | None] = mapped_column(String(1024), nullable=True, comment="召回单元ID，逗号分隔")
    authorized_doc_ids: Mapped[str | None] = mapped_column(String(1024), nullable=True, comment="鉴权通过单元ID，逗号分隔")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="输入Token")
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="输出Token")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="总Token")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="响应耗时(ms)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True, comment="创建时间"
    )


class KbFaq(Base, TimestampMixin):
    """FAQ 问答对（候选推荐 / 已发布缓存）。"""

    __tablename__ = "kb_faq"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(512), nullable=False, index=True, comment="标准问题")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="标准答案")
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="聚合命中次数")
    status: Mapped[str] = mapped_column(
        String(16), default=FAQ_STATUS_PENDING, nullable=False, index=True, comment="状态"
    )
    source: Mapped[str] = mapped_column(
        String(16), default=FAQ_SOURCE_AUTO, nullable=False, comment="来源：auto/manual"
    )
    cluster_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="聚类键（问题标准化后的指纹）"
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="推荐置信度得分")
    auditor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="审核人")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发布时间")

    perms: Mapped[list["KbFaqPerm"]] = relationship(
        back_populates="faq", cascade="all, delete-orphan", passive_deletes=True
    )


class KbFaqPerm(Base, TimestampMixin):
    """FAQ 数据权限条目。

    注意语义差异：PRD Q8 待确认。当前按参考基线实现为
    **无任何记录 = 公开可见**；若评审改为拒绝优先，只需调整鉴权服务的默认分支。
    """

    __tablename__ = "kb_faq_perm"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    faq_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_faq.id", ondelete="CASCADE"), nullable=False, index=True, comment="FAQ主键"
    )
    perm_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="权限类型")
    entity_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="实体ID")

    faq: Mapped[KbFaq] = relationship(back_populates="perms")


class KbKnowledgeGap(Base, TimestampMixin):
    """知识缺口（PRD FR-50，决策 D2 判定口径）。

    判定条件（三者同时满足）：
    1. 确实执行过检索；
    2. 没有任何有权上下文；
    3. 不是因权限拒绝导致。
    """

    __tablename__ = "kb_knowledge_gap"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(512), nullable=False, index=True, comment="未命中提问文本")
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True, comment="出现次数")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="最近提问部门")
    last_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="最近提问人")
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="是否已解决"
    )


class KbGapTask(Base, TimestampMixin):
    """知识补充任务（PRD FR-52，形态待 Q9 确认，此处取最小实现）。"""

    __tablename__ = "kb_gap_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gap_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_knowledge_gap.id", ondelete="CASCADE"), nullable=False,
        index=True, comment="来源缺口"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务标题")
    status: Mapped[str] = mapped_column(
        String(16), default=GAP_TASK_OPEN, nullable=False, index=True, comment="任务状态"
    )
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="负责人")

"""知识沉淀相关 Schema（T-30 ~ T-33）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel, InModel

# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------


class FaqOut(CamelModel):
    """FAQ 条目（候选/已发布共用）。"""

    id: int
    question: str
    answer: str | None = None
    hit_count: int = 0
    status: str
    source: str = "auto"
    confidence: float | None = None
    auditor_id: int | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FaqQuery(InModel):
    """FAQ 列表查询。"""

    keyword: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)


class FaqAuditIn(InModel):
    """FAQ 审核：发布或驳回。"""

    action: str = Field(description="publish 或 reject")
    answer: str | None = Field(default=None, description="发布时可在线修订标准答案")


class PublishedFaqOut(CamelModel):
    """已发布 FAQ（供对话工作台的常见问题展示）。"""

    id: int
    question: str
    hit_count: int = 0


# ---------------------------------------------------------------------------
# 知识缺口
# ---------------------------------------------------------------------------


class GapOut(CamelModel):
    """知识缺口条目。"""

    id: int
    question: str
    hit_count: int = 1
    dept_id: int | None = None
    dept_name: str | None = None
    last_user_id: int | None = None
    resolved: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GapQuery(InModel):
    """缺口清单查询。"""

    include_resolved: bool = False
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)


class GapTaskIn(InModel):
    """缺口转建补充任务。"""

    title: str | None = Field(default=None, max_length=255, description="留空则按缺口问题自动生成")
    owner_id: int | None = Field(default=None, description="负责人，可为空")


class GapTaskOut(CamelModel):
    """知识补充任务。"""

    id: int
    gap_id: int
    title: str
    status: str
    owner_id: int | None = None
    created_at: datetime | None = None

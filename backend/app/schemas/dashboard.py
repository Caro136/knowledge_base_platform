"""运营看板 Schema（T-28）。"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class OverviewOut(CamelModel):
    """看板总览指标（FR-33 ~ FR-38、FR-42）。"""

    days: int = Field(default=30, description="统计窗口（天）")
    total_visits: int = Field(default=0, description="访问次数 PV")
    distinct_users: int = Field(default=0, description="独立访问人数 UV")
    doc_count: int = Field(default=0, description="知识单元总数")
    total_tokens: int = Field(default=0, description="Token 消耗总量")
    avg_latency_ms: float = Field(default=0.0, description="平均响应时长（毫秒）")
    hit_rate: float = Field(default=0.0, description="检索命中率（存在有权上下文的比例）")
    faq_hit_rate: float = Field(default=0.0, description="FAQ 缓存直接命中率")
    gap_count: int = Field(default=0, description="待处理知识缺口数")


class TrendPoint(CamelModel):
    """访问趋势的一个数据点。"""

    date: str
    pv: int = 0
    uv: int = 0


class TopQuestion(CamelModel):
    """高频提问条目。"""

    question: str
    count: int = 0


class TopDoc(CamelModel):
    """热门知识单元条目。"""

    doc_id: str
    title: str
    count: int = 0

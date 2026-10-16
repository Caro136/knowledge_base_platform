"""运营看板聚合（T-28）。

数据源单一化：所有指标都从 ``kb_access_log`` 派生（外加知识单元与缺口计数），
避免同一口径在多处各写一遍导致数字打架（SPEC §8 可观测性）。

聚合策略：单机规模下按需聚合即可（``created_at`` 上有索引）。若日志涨到百万级，
可引入按日汇总表——届时只需替换本模块实现，接口契约保持不变。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KbAccessLog, KbDocument, KbKnowledgeGap
from app.schemas.dashboard import OverviewOut, TopDoc, TopQuestion, TrendPoint

logger = logging.getLogger(__name__)


def _since(days: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=max(1, days))


def overview(db: Session, days: int = 30) -> OverviewOut:
    """总览指标卡（FR-33 ~ FR-38、FR-42）。"""
    since = _since(days)
    window = KbAccessLog.created_at >= since

    total_visits = db.scalar(
        select(func.count()).select_from(KbAccessLog).where(window)
    ) or 0
    distinct_users = db.scalar(
        select(func.count(func.distinct(KbAccessLog.user_id))).where(window)
    ) or 0
    total_tokens = db.scalar(select(func.sum(KbAccessLog.total_tokens)).where(window)) or 0
    avg_latency = db.scalar(select(func.avg(KbAccessLog.latency_ms)).where(window)) or 0
    hit_count = db.scalar(
        select(func.count()).select_from(KbAccessLog).where(window, KbAccessLog.hit.is_(True))
    ) or 0
    faq_hits = db.scalar(
        select(func.count()).select_from(KbAccessLog).where(window, KbAccessLog.faq_hit.is_(True))
    ) or 0

    doc_count = db.scalar(select(func.count()).select_from(KbDocument)) or 0
    gap_count = db.scalar(
        select(func.count()).select_from(KbKnowledgeGap).where(KbKnowledgeGap.resolved.is_(False))
    ) or 0

    return OverviewOut(
        days=days,
        total_visits=total_visits,
        distinct_users=distinct_users,
        doc_count=doc_count,
        total_tokens=int(total_tokens),
        avg_latency_ms=round(float(avg_latency), 1),
        # 分母为 0 时比例记为 0，避免出现 NaN 传到前端
        hit_rate=round(hit_count / total_visits, 4) if total_visits else 0.0,
        faq_hit_rate=round(faq_hits / total_visits, 4) if total_visits else 0.0,
        gap_count=gap_count,
    )


def trend(db: Session, days: int = 14) -> list[TrendPoint]:
    """按天聚合的访问趋势（PV / UV）。"""
    since = _since(days)
    rows = db.execute(
        select(
            func.date(KbAccessLog.created_at).label("day"),
            func.count().label("pv"),
            func.count(func.distinct(KbAccessLog.user_id)).label("uv"),
        )
        .where(KbAccessLog.created_at >= since)
        .group_by("day")
        .order_by("day")
    ).all()

    return [
        TrendPoint(date=str(row.day), pv=int(row.pv or 0), uv=int(row.uv or 0))
        for row in rows
    ]


def top_questions(db: Session, limit: int = 10, days: int = 30) -> list[TopQuestion]:
    """高频提问排行（不区分是否命中——"问到什么"本身就是运营信号）。"""
    since = _since(days)
    rows = db.execute(
        select(KbAccessLog.question, func.count().label("cnt"))
        .where(KbAccessLog.created_at >= since)
        .group_by(KbAccessLog.question)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [TopQuestion(question=row.question, count=int(row.cnt or 0)) for row in rows]


def top_docs(db: Session, limit: int = 10, days: int = 30) -> list[TopDoc]:
    """热门知识单元排行。

    实现说明：命中来源以逗号分隔的字符串存在流水里，SQL 侧拆分不划算，
    因此在应用层统计。窗口限定在近 N 天，数据量可控。
    """
    since = _since(days)
    rows = db.scalars(
        select(KbAccessLog.authorized_doc_ids).where(KbAccessLog.created_at >= since)
    ).all()

    counter: Counter[str] = Counter()
    for value in rows:
        for doc_id in (value or "").split(","):
            doc_id = doc_id.strip()
            if doc_id:
                counter[doc_id] += 1

    if not counter:
        return []

    top = counter.most_common(limit)
    titles = {
        doc.doc_id: doc.title
        for doc in db.scalars(
            select(KbDocument).where(KbDocument.doc_id.in_([item[0] for item in top]))
        )
    }
    return [
        TopDoc(doc_id=doc_id, title=titles.get(doc_id, "（已删除）"), count=count)
        for doc_id, count in top
    ]

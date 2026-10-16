"""运营埋点与知识缺口（T-27 埋点 / T-32 缺口 / T-33 转建任务）。

设计与安全约束：
- 按决策 D3，审计流水**不记录鉴权拦截明细**（拒绝的 doc_id 不落库）；
- 埋点与沉淀累计全部包裹异常处理——统计出问题绝不能让用户拿不到答案；
- 知识缺口判定遵循决策 D2 的**三条件**（确实检索过 + 无任何有权上下文 + 非权限拒绝），
  判定发生在调用方（chat_service），本模块只负责落库与累加。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.core.response import PageData
from app.models import (
    GAP_TASK_OPEN,
    Dept,
    KbAccessLog,
    KbGapTask,
    KbKnowledgeGap,
    User,
)
from app.schemas.ops import GapOut, GapQuery, GapTaskIn, GapTaskOut
from app.services.faq_service import bump_faq

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 问答埋点（T-27）
# ---------------------------------------------------------------------------


def record_access(
    db: Session,
    *,
    user: User | None,
    session_id: str | None,
    question: str,
    hit: bool,
    faq_hit: bool,
    is_gap: bool,
    recalled_doc_ids: list[str] | None = None,
    authorized_doc_ids: list[str] | None = None,
    usage: dict | None = None,
    latency_ms: int = 0,
) -> None:
    """落库一次问答流水，并触发 FAQ 频次与知识缺口的累计。

    :param hit: 是否存在有权上下文（决定看板的「命中」统计）
    :param faq_hit: 是否由 FAQ 缓存直接作答
    :param is_gap: 是否判定为知识缺口（决策 D2）
    """
    try:
        usage = usage or {}
        db.add(
            KbAccessLog(
                session_id=session_id,
                user_id=user.id if user else None,
                username=user.username if user else None,
                dept_id=user.dept_id if user else None,
                question=question[:512],
                hit=hit,
                faq_hit=faq_hit,
                is_gap=is_gap,
                recalled_doc_ids=",".join(dict.fromkeys(recalled_doc_ids or []))[:1024],
                authorized_doc_ids=",".join(dict.fromkeys(authorized_doc_ids or []))[:1024],
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                latency_ms=latency_ms,
            )
        )
        db.commit()

        # 只有「正常作答」的提问参与 FAQ 挖掘：
        # 缺口类提问没有答案，缓存命中的提问本就在 FAQ 中（match_published 已计数）
        if not faq_hit and not is_gap:
            bump_faq(db, question)

        if is_gap:
            _bump_gap(db, question, user)

    except Exception as exc:  # noqa: BLE001 - 统计失败不影响问答主流程
        db.rollback()
        logger.warning("问答埋点失败（不影响本次回答）：%s", exc)


# ---------------------------------------------------------------------------
# 知识缺口（T-32 / T-33）
# ---------------------------------------------------------------------------


def _bump_gap(db: Session, question: str, user: User | None) -> None:
    """缺口频次累加（已解决的缺口再次被问到则重新打开）。"""
    text = question[:512]
    gap = db.scalar(select(KbKnowledgeGap).where(KbKnowledgeGap.question == text))

    if gap is None:
        db.add(
            KbKnowledgeGap(
                question=text,
                hit_count=1,
                dept_id=user.dept_id if user else None,
                last_user_id=user.id if user else None,
                resolved=False,
            )
        )
        logger.info("新增知识缺口：%s", text[:30])
    else:
        gap.hit_count += 1
        gap.last_user_id = user.id if user else None
        if gap.resolved:
            # 补充后仍被问到，说明补充内容没有覆盖该问题，重新纳入清单
            gap.resolved = False
            logger.info("知识缺口重新打开：%s", text[:30])
    db.commit()


def list_gaps(db: Session, query: GapQuery) -> PageData[GapOut]:
    """知识缺口清单：默认只列未解决项，按出现频次倒序。"""
    conditions = []
    if not query.include_resolved:
        conditions.append(KbKnowledgeGap.resolved.is_(False))

    total = db.scalar(select(func.count()).select_from(KbKnowledgeGap).where(*conditions)) or 0
    rows = db.scalars(
        select(KbKnowledgeGap)
        .where(*conditions)
        .order_by(KbKnowledgeGap.hit_count.desc(), KbKnowledgeGap.id.desc())
        .offset((query.page - 1) * query.size)
        .limit(query.size)
    ).all()

    # 一次性补齐部门名，避免逐行查询
    dept_ids = {row.dept_id for row in rows if row.dept_id}
    dept_names: dict[int, str] = {}
    if dept_ids:
        dept_names = {
            dept.id: dept.name
            for dept in db.scalars(select(Dept).where(Dept.id.in_(dept_ids)))
        }

    return PageData[GapOut](
        items=[
            GapOut(
                id=row.id,
                question=row.question,
                hit_count=row.hit_count,
                dept_id=row.dept_id,
                dept_name=dept_names.get(row.dept_id) if row.dept_id else None,
                last_user_id=row.last_user_id,
                resolved=row.resolved,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=total,
        page=query.page,
        size=query.size,
    )


def resolve_gap(db: Session, gap_id: int) -> None:
    """标记缺口已解决（例如已补充文档或确认为无效提问）。"""
    gap = db.get(KbKnowledgeGap, gap_id)
    if gap is None:
        raise BizError(Code.NOT_FOUND, "知识缺口不存在")
    gap.resolved = True
    db.commit()


def create_gap_task(db: Session, gap_id: int, payload: GapTaskIn, operator: User) -> GapTaskOut:
    """把缺口转建为知识补充任务（FR-52）。

    形态说明：PRD Q9 尚未确认任务的流转规则，此处取**最小实现**──
    一条任务记录 + 状态字段（open/processing/done）与负责人。
    转建后缺口标记为已处理，避免清单里长期挂着同一条。
    """
    gap = db.get(KbKnowledgeGap, gap_id)
    if gap is None:
        raise BizError(Code.NOT_FOUND, "知识缺口不存在")

    if payload.owner_id and db.get(User, payload.owner_id) is None:
        raise BizError(Code.PARAM_INVALID, "负责人不存在")

    title = (payload.title or f"补充知识：{gap.question}")[:255]
    task = KbGapTask(
        gap_id=gap.id,
        title=title,
        status=GAP_TASK_OPEN,
        owner_id=payload.owner_id or operator.id,
    )
    db.add(task)
    gap.resolved = True
    db.commit()
    db.refresh(task)

    logger.info("知识缺口已转建任务：gap=%s task=%s", gap.id, task.id)
    return _to_task_out(task)


def list_gap_tasks(db: Session, gap_id: int | None = None) -> list[GapTaskOut]:
    stmt = select(KbGapTask).order_by(KbGapTask.id.desc()).limit(200)
    if gap_id is not None:
        stmt = stmt.where(KbGapTask.gap_id == gap_id)
    return [_to_task_out(task) for task in db.scalars(stmt)]


def _to_task_out(task: KbGapTask) -> GapTaskOut:
    return GapTaskOut(
        id=task.id,
        gap_id=task.gap_id,
        title=task.title,
        status=task.status,
        owner_id=task.owner_id,
        created_at=task.created_at,
    )

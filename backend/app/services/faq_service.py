"""FAQ 沉淀与快速应答缓存（T-25 / T-30 / T-31）。

两条主线：

1. **挖掘**：以「问题标准化后的指纹」聚合提问频次，达到阈值自动生成候选 FAQ，
   供知识管理员审核。低于阈值的问题处于「收集中」状态，不会涌入审核列表。
2. **缓存命中**：审核发布的 FAQ 在问答链路入口做精确匹配，命中即直接返回
   人工审定的标准答案，**跳过整条检索与生成流程**（FR-47）。

关于「内存缓存」：SPEC/PRD 描述了「发布后写入内存缓存」。本实现改为
**带唯一索引的精确查询**（``cluster_key`` 上有索引）——FAQ 命中后仍必须
做一次数据权限判定，那是无法省去的库查询，因此额外的进程内缓存只能省下
一次按 key 的索引查询，却要付出多实例不一致与失效维护的成本。
实测命中耗时在毫秒级，效果与目标一致；如需退化为纯内存命中，
可在本模块加一层 ``dict`` 缓存并在 :func:`audit` 中维护。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError
from app.core.response import PageData
from app.models import (
    FAQ_SOURCE_AUTO,
    FAQ_STATUS_COLLECTING,
    FAQ_STATUS_PENDING,
    FAQ_STATUS_PUBLISHED,
    FAQ_STATUS_REJECTED,
    KbFaq,
    KbFaqPerm,
    User,
)
from app.schemas.knowledge import AssignPermsIn, AssignPermsOut, DocPermDetail, DocPermSummary
from app.schemas.ops import FaqAuditIn, FaqOut, FaqQuery, PublishedFaqOut
from app.services.authz_service import AuthzService

logger = logging.getLogger(__name__)

#: 空白与标点（Unicode 模式下保留中文，仅剥离符号与空格）
_NORMALIZE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_question(text: str) -> str:
    """问题标准化指纹：去空白与标点、转小写。

    让「住宿标准是多少？」与「住宿标准是多少」归入同一簇，
    是实现「语义去重」的轻量近似（真正语义聚类成本高，收益有限）。
    """
    if not text:
        return ""
    return _NORMALIZE_RE.sub("", text.lower())[:200]


def _get_faq(db: Session, faq_id: int) -> KbFaq:
    faq = db.get(KbFaq, faq_id)
    if faq is None:
        raise BizError(Code.NOT_FOUND, "FAQ 不存在")
    return faq


def _to_out(faq: KbFaq) -> FaqOut:
    return FaqOut(
        id=faq.id,
        question=faq.question,
        answer=faq.answer,
        hit_count=faq.hit_count,
        status=faq.status,
        source=faq.source,
        confidence=faq.confidence,
        auditor_id=faq.auditor_id,
        published_at=faq.published_at,
        created_at=faq.created_at,
        updated_at=faq.updated_at,
    )


# ---------------------------------------------------------------------------
# 挖掘：频次聚合与候选生成（T-30）
# ---------------------------------------------------------------------------


def bump_faq(db: Session, question: str) -> KbFaq | None:
    """按标准化指纹累加频次；达到阈值时把候选转入待审核（FR-43/FR-44）。"""
    key = normalize_question(question)
    if not key:
        return None

    threshold = max(1, settings.FAQ_RECOMMEND_THRESHOLD)
    faq = db.scalar(select(KbFaq).where(KbFaq.cluster_key == key))

    try:
        if faq is None:
            faq = KbFaq(
                question=question[:512],
                cluster_key=key,
                hit_count=1,
                status=FAQ_STATUS_COLLECTING,
                source=FAQ_SOURCE_AUTO,
                confidence=round(1.0 / threshold, 3),
            )
            db.add(faq)
            db.commit()
            return faq

        faq.hit_count += 1
        # 仅「收集中」的候选会因达到阈值而升级，避免低频问题涌入审核列表
        if faq.status == FAQ_STATUS_COLLECTING and faq.hit_count >= threshold:
            faq.status = FAQ_STATUS_PENDING
            # 置信度取启发式值：频次相对阈值的饱满程度
            faq.confidence = round(min(0.99, faq.hit_count / (threshold * 2)), 3)
            logger.info("候选 FAQ 已生成：%s（累计 %d 次）", faq.question[:30], faq.hit_count)
        db.commit()
        return faq
    except Exception as exc:  # noqa: BLE001 - 沉淀失败不应影响问答
        db.rollback()
        logger.warning("FAQ 频次累加失败：%s", exc)
        return None


# ---------------------------------------------------------------------------
# 缓存：发布 FAQ 的精确匹配（T-25 / T-31）
# ---------------------------------------------------------------------------


def match_published(db: Session, user: User | None, question: str) -> KbFaq | None:
    """FAQ 快速应答匹配。

    命中条件（三者必须同时满足）：
    1. 问题指纹与已发布 FAQ 一致；
    2. 该 FAQ 有非空标准答案；
    3. 当前用户对该 FAQ 有数据权限。

    未命中（含无权访问）时返回 None，调用方继续走正常检索链路——
    无权 FAQ 不命中缓存，但相关文档若有权仍可正常回答。
    """
    key = normalize_question(question)
    if not key:
        return None

    faq = db.scalar(
        select(KbFaq).where(
            KbFaq.cluster_key == key,
            KbFaq.status == FAQ_STATUS_PUBLISHED,
        )
    )
    if faq is None or not (faq.answer or "").strip():
        return None

    allowed, _ = AuthzService.filter_faq_ids(db, user, [faq.id])
    if not allowed:
        logger.info("FAQ 命中但当前用户无权访问 id=%s", faq.id)
        return None

    try:
        faq.hit_count += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("FAQ 命中计数失败：%s", exc)
    return faq


# ---------------------------------------------------------------------------
# 审核与列表（T-31）
# ---------------------------------------------------------------------------


def list_faqs(db: Session, query: FaqQuery) -> PageData[FaqOut]:
    conditions = []
    if query.status:
        conditions.append(KbFaq.status == query.status)
    else:
        # 默认不展示「收集中」的低频候选
        conditions.append(KbFaq.status != FAQ_STATUS_COLLECTING)
    if query.keyword:
        like = f"%{query.keyword}%"
        conditions.append(or_(KbFaq.question.like(like), KbFaq.answer.like(like)))

    total = db.scalar(select(func.count()).select_from(KbFaq).where(*conditions)) or 0
    rows = db.scalars(
        select(KbFaq)
        .where(*conditions)
        .order_by(KbFaq.status.desc(), KbFaq.hit_count.desc(), KbFaq.id.desc())
        .offset((query.page - 1) * query.size)
        .limit(query.size)
    ).all()
    return PageData[FaqOut](
        items=[_to_out(faq) for faq in rows],
        total=total,
        page=query.page,
        size=query.size,
    )


def audit(db: Session, faq_id: int, payload: FaqAuditIn, auditor: User) -> FaqOut:
    """审核候选 FAQ：发布（可在线修订答案）或驳回（FR-46）。"""
    faq = _get_faq(db, faq_id)

    if payload.action == "publish":
        answer = (payload.answer or faq.answer or "").strip()
        if not answer:
            raise BizError(Code.PARAM_INVALID, "发布前必须填写标准答案")
        faq.answer = answer
        faq.status = FAQ_STATUS_PUBLISHED
        faq.published_at = datetime.now(UTC)
        logger.info("FAQ 已发布：%s", faq.question[:30])
    elif payload.action == "reject":
        faq.status = FAQ_STATUS_REJECTED
    else:
        raise BizError(Code.PARAM_INVALID, "action 仅支持 publish 或 reject")

    faq.auditor_id = auditor.id
    db.commit()
    db.refresh(faq)
    return _to_out(faq)


def delete_faq(db: Session, faq_id: int) -> None:
    """删除 FAQ（已发布的删除后即不再命中缓存）。"""
    faq = _get_faq(db, faq_id)
    db.delete(faq)
    db.commit()


def list_published(db: Session, user: User | None, limit: int = 20) -> list[PublishedFaqOut]:
    """已发布 FAQ（供对话工作台的「常见问题」展示），按权限过滤（FR-48）。"""
    rows = db.scalars(
        select(KbFaq)
        .where(KbFaq.status == FAQ_STATUS_PUBLISHED, KbFaq.answer.is_not(None))
        .order_by(KbFaq.hit_count.desc())
        .limit(50)
    ).all()
    if not rows:
        return []

    allowed, _ = AuthzService.filter_faq_ids(db, user, [row.id for row in rows])
    allowed_set = set(allowed)
    return [
        PublishedFaqOut(id=row.id, question=row.question, hit_count=row.hit_count)
        for row in rows
        if row.id in allowed_set
    ][:limit]


# ---------------------------------------------------------------------------
# FAQ 数据权限（FR-49）
# ---------------------------------------------------------------------------


def get_faq_perms(db: Session, faq_id: int) -> DocPermDetail:
    _get_faq(db, faq_id)
    detail = DocPermDetail(doc_id=str(faq_id))
    rows = db.scalars(select(KbFaqPerm).where(KbFaqPerm.faq_id == faq_id)).all()
    for row in rows:
        if row.perm_type == "global":
            detail.is_global = True
        elif row.perm_type == "department":
            detail.dept_ids.append(row.entity_id)
        elif row.perm_type == "role":
            detail.role_ids.append(row.entity_id)
        elif row.perm_type == "user":
            detail.user_ids.append(row.entity_id)
    detail.dept_ids.sort()
    detail.role_ids.sort()
    detail.user_ids.sort()
    return detail


def assign_faq_perms(db: Session, payload: AssignPermsIn) -> AssignPermsOut:
    """覆盖式分配 FAQ 数据权限。

    与知识单元不同：**清空全部维度 = 公开可见**（默认语义相反，见 Q8）。
    """
    faq_ids = [int(item) for item in payload.doc_ids]
    faqs = list(db.scalars(select(KbFaq).where(KbFaq.id.in_(faq_ids))))
    if len(faqs) != len(set(faq_ids)):
        raise BizError(Code.NOT_FOUND, "存在无效的 FAQ ID")

    from sqlalchemy import delete

    db.execute(delete(KbFaqPerm).where(KbFaqPerm.faq_id.in_([faq.id for faq in faqs])))

    records: list[KbFaqPerm] = []
    for faq in faqs:
        if payload.is_global:
            records.append(KbFaqPerm(faq_id=faq.id, perm_type="global", entity_id=0))
            continue
        records.extend(
            KbFaqPerm(faq_id=faq.id, perm_type=kind, entity_id=entity_id)
            for kind, ids in (
                ("department", payload.dept_ids),
                ("role", payload.role_ids),
                ("user", payload.user_ids),
            )
            for entity_id in sorted(set(ids))
        )

    db.add_all(records)
    db.commit()
    return AssignPermsOut(
        affected=len(faqs),
        perm=DocPermSummary(
            is_global=payload.is_global,
            dept_ids=[] if payload.is_global else sorted(set(payload.dept_ids)),
            role_ids=[] if payload.is_global else sorted(set(payload.role_ids)),
            user_ids=[] if payload.is_global else sorted(set(payload.user_ids)),
        ),
    )

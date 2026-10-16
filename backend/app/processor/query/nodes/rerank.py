"""精排与截断节点（T-21）。

对**已通过鉴权**的切片做精排（未授权内容此前进不来），再用「断崖截断」压缩条数：

之所以要截断：上下文里塞入大量低相关切片会稀释关键信息并推高 Token 成本。
断崖检测的思路是——如果第 i 条与第 i+1 条的分数出现明显落差，
说明后面的内容相关性骤降，此处截断比固定取 Top-K 更贴合实际分布。

精排失败时降级为「按融合顺序取前若干条」，保证问答不因精排不可用而中断。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.exceptions import BizError
from app.processor.query.state import QueryState
from app.utils import rerank_client

logger = logging.getLogger(__name__)


def _cliff_cutoff(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在 [min_top_k, max_top_k] 区间内寻找分数断崖并截断。"""
    min_k = max(1, settings.RERANK_MIN_TOP_K)
    max_k = max(min_k, settings.RERANK_MAX_TOP_K)
    limit = min(len(docs), max_k)

    if limit <= min_k:
        return docs[:limit]

    for index in range(min_k - 1, limit - 1):
        current = docs[index].get("rerank_score") or 0.0
        following = docs[index + 1].get("rerank_score") or 0.0
        drop = current - following
        if drop >= settings.RERANK_GAP_ABS:
            return docs[: index + 1]
        if current and (drop / abs(current)) >= settings.RERANK_GAP_RATIO:
            return docs[: index + 1]

    return docs[:limit]


def rerank_node(state: QueryState) -> QueryState:
    chunks = state.get("authorized_chunks") or []
    if not chunks:
        return {"ranked_docs": []}

    question = state.get("question") or ""
    try:
        scores = rerank_client.rerank(question, [chunk.get("content") or "" for chunk in chunks])
        scored = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
        ranked = [{**chunk, "rerank_score": score} for chunk, score in scored]
    except BizError as exc:
        # 精排不可用不应阻断问答：退化为融合顺序（融合本身已融合两路排名）
        logger.warning("精排失败，降级为融合顺序：%s", exc.message)
        ranked = list(chunks)

    # 相关性下限过滤：低于门槛的切片不算「有效上下文」。
    # 这既是知识缺口识别的前提（否则向量检索总有 Top-K 返回，缺口永不触发），
    # 也让进入 Prompt 的内容更干净。重排失败降级时分数为 None，此时保守放行。
    relevant = [
        item
        for item in ranked
        if item.get("rerank_score") is None or item["rerank_score"] >= settings.RAG_MIN_RELEVANCE
    ]
    if len(relevant) != len(ranked):
        logger.info(
            "相关性过滤：%d 条候选 → %d 条达标（阈值 %.2f）",
            len(ranked), len(relevant), settings.RAG_MIN_RELEVANCE,
        )

    cut = _cliff_cutoff(relevant)
    logger.info("精排完成：%d 条候选 → 截断保留 %d 条", len(ranked), len(cut))
    return {"ranked_docs": cut}

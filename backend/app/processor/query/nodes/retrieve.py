"""混合检索节点（T-19，FR-23）。

流程：问题向量化 → 稠密（语义）与稀疏（关键词）两路召回 → RRF 融合。

用 RRF（Reciprocal Rank Fusion）而非加权求和的理由：稠密相似度与稀疏内积
量纲不同，直接加权需要调参；RRF 只看排名，对两路分数量纲不敏感，
是混合检索的稳健默认选择。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.processor.query.state import QueryState
from app.services import vector_service
from app.utils.embedding_client import embed_query

logger = logging.getLogger(__name__)


def _rrf_fuse(
    result_lists: list[list[dict[str, Any]]], k: int, top_n: int
) -> list[dict[str, Any]]:
    """倒数排名融合：score = Σ 1 / (k + rank)。"""
    scores: dict[Any, float] = {}
    store: dict[Any, dict[str, Any]] = {}

    for results in result_lists:
        for rank, hit in enumerate(results):
            chunk_id = hit.get("chunk_id")
            if chunk_id is None:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            store.setdefault(chunk_id, hit)

    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:top_n]
    return [{**store[chunk_id], "rrf_score": score} for chunk_id, score in ordered]


def retrieve_node(state: QueryState) -> QueryState:
    question = (state.get("question") or "").strip()
    if not question:
        return {"dense_hits": [], "sparse_hits": [], "fused_chunks": []}

    dense_vector, sparse_vector = embed_query(question)
    dense_hits, sparse_hits = vector_service.search_chunks(
        dense_vector,
        sparse_vector,
        limit=settings.RETRIEVE_TOP_K,
    )

    fused = _rrf_fuse([dense_hits, sparse_hits], k=settings.RRF_K, top_n=settings.RRF_MAX_RESULTS)
    logger.info(
        "检索完成：稠密 %d 条 / 稀疏 %d 条 → 融合 %d 条",
        len(dense_hits), len(sparse_hits), len(fused),
    )
    return {"dense_hits": dense_hits, "sparse_hits": sparse_hits, "fused_chunks": fused}

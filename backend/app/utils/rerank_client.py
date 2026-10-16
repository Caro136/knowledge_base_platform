"""BGE-reranker 精排客户端（T-21）。

精排模型与嵌入模型一样是本地权重，按需惰性加载；推理用全局锁串行化，
避免单机并发推理把内存/显存打满（SPEC ADR-007 的已知代价）。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

_model: Any = None
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


def _get_model():
    """惰性加载并缓存重排模型。"""
    global _model
    if _model is not None:
        return _model

    with _load_lock:
        if _model is not None:
            return _model

        if not settings.RERANK_MODEL_PATH:
            raise BizError(Code.INTERNAL_ERROR, "未配置重排模型路径（RERANK_MODEL_PATH）")

        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:  # pragma: no cover
            raise BizError(Code.INTERNAL_ERROR, "缺少 FlagEmbedding 依赖") from exc

        logger.info(
            "加载重排模型：%s（device=%s, fp16=%s）",
            settings.RERANK_MODEL_PATH,
            settings.BGE_RERANKER_DEVICE,
            settings.BGE_RERANKER_FP16,
        )
        try:
            _model = FlagReranker(
                settings.RERANK_MODEL_PATH,
                use_fp16=settings.BGE_RERANKER_FP16,
                devices=settings.BGE_RERANKER_DEVICE,
            )
        except Exception as exc:  # noqa: BLE001
            raise BizError(Code.INTERNAL_ERROR, f"重排模型加载失败：{exc}") from exc
        logger.info("重排模型加载完成")
        return _model


def rerank(query: str, documents: list[str]) -> list[float]:
    """对候选文档打分，返回与入参等长的分数列表（越大越相关）。

    调用方负责排序与截断；本函数失败时抛 :class:`BizError`，
    由流程节点决定降级策略。
    """
    if not documents:
        return []

    model = _get_model()
    pairs = [[query, doc] for doc in documents]

    try:
        with _infer_lock:  # 单机推理串行，避免并发争抢资源
            scores = model.compute_score(pairs, normalize=True)
    except Exception as exc:  # noqa: BLE001
        raise BizError(Code.INTERNAL_ERROR, f"重排计算失败：{exc}") from exc

    # compute_score 在单条时返回 float，多条时返回 list
    if isinstance(scores, (int, float)):
        return [float(scores)]
    return [float(score) for score in scores]

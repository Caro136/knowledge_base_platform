"""BGE-M3 嵌入客户端（导入 T-13 与检索 T-19 共用）。

为什么要独立成模块：导入流程与问答流程都要用嵌入模型。若各自加载一份，
内存占用翻倍且行为可能不一致；共用单例后，模型只加载一次，
推理用全局锁串行化，避免并发争抢 CPU/显存（SPEC ADR-007）。
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


def get_model():
    """惰性加载并缓存 BGE-M3（首次调用开销较大）。"""
    global _model
    if _model is not None:
        return _model

    with _load_lock:
        if _model is not None:
            return _model

        if not settings.EMBEDDING_MODEL_PATH:
            raise BizError(Code.INTERNAL_ERROR, "未配置嵌入模型路径（EMBEDDING_MODEL_PATH）")

        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover
            raise BizError(Code.INTERNAL_ERROR, "缺少 FlagEmbedding 依赖") from exc

        logger.info(
            "加载嵌入模型：%s（device=%s, fp16=%s）",
            settings.EMBEDDING_MODEL_PATH,
            settings.BGE_DEVICE,
            settings.BGE_FP16,
        )
        try:
            _model = BGEM3FlagModel(
                settings.EMBEDDING_MODEL_PATH,
                use_fp16=settings.BGE_FP16,
                devices=settings.BGE_DEVICE,
            )
        except Exception as exc:  # noqa: BLE001
            raise BizError(Code.INTERNAL_ERROR, f"嵌入模型加载失败：{exc}") from exc
        logger.info("嵌入模型加载完成")
        return _model


def embed_texts(
    texts: list[str], batch_size: int | None = None
) -> tuple[list[list[float]], list[dict[int, float]]]:
    """批量生成稠密与稀疏向量。"""
    if not texts:
        return [], []

    model = get_model()
    try:
        with _infer_lock:
            output = model.encode(
                texts,
                batch_size=batch_size or settings.EMBEDDING_BATCH_SIZE,
                max_length=8192,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
    except Exception as exc:  # noqa: BLE001
        raise BizError(Code.INTERNAL_ERROR, f"向量计算失败：{exc}") from exc

    dense = [[float(value) for value in vector] for vector in output["dense_vecs"]]
    sparse = [
        {int(token): float(weight) for token, weight in weights.items()}
        for weights in output["lexical_weights"]
    ]
    return dense, sparse


def embed_query(question: str) -> tuple[list[float], dict[int, float]]:
    """单条查询的向量化（问答链路的入口）。"""
    dense, sparse = embed_texts([question])
    if not dense:
        raise BizError(Code.INTERNAL_ERROR, "查询向量化为空")
    return dense[0], sparse[0]

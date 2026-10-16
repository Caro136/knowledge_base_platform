"""向量化与入库节点（T-13）。

- 用 BGE-M3 生成**稠密 + 稀疏**双向量（中文语义与关键词兼顾）；
- 写入 Milvus，每个切片冗余 ``doc_id`` 作为权限锚点；
- 模型按需惰性加载并缓存，设备（cpu/cuda）与精度由配置决定。

单机部署下嵌入推理较慢（尤其 CPU 模式），因此本节点是整个导入流程的耗时大头。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError
from app.processor.state import ImportState
from app.services import vector_service

logger = logging.getLogger(__name__)

_model: Any = None
_model_lock = threading.Lock()


def _get_embedding_model():
    """惰性加载并缓存 BGE-M3（首次调用开销较大）。"""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
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


def _embed_texts(texts: list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
    """批量生成稠密与稀疏向量。"""
    model = _get_embedding_model()
    try:
        output = model.encode(
            texts,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
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


def embed_store_node(state: ImportState) -> ImportState:
    chunks = state.get("chunks") or []
    doc_id = state.get("doc_id") or ""
    if not chunks:
        raise BizError(Code.PARSE_FAILED, "没有可入库的切片")
    if not doc_id:
        raise BizError(Code.INTERNAL_ERROR, "缺少知识单元锚点 doc_id")

    texts = [chunk["content"] for chunk in chunks]
    dense_vectors, sparse_vectors = _embed_texts(texts)

    if len(dense_vectors) != len(chunks):
        raise BizError(Code.INTERNAL_ERROR, "向量数量与切片数量不一致")

    rows = [
        {
            "dense_vector": dense_vectors[index],
            "sparse_vector": sparse_vectors[index],
            "content": chunk["content"],
            "title": chunk.get("title") or "",
            "parent_title": chunk.get("parent_title") or "",
        }
        for index, chunk in enumerate(chunks)
    ]

    count = vector_service.upsert_doc_chunks(
        doc_id=doc_id,
        file_title=state.get("filename") or "",
        item_name="",
        rows=rows,
    )
    logger.info("向量入库完成 doc_id=%s，切片 %d 条", doc_id, count)
    return {"chunk_count": count}

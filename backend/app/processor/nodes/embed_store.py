"""向量化与入库节点（T-13）。

嵌入模型由 :mod:`app.utils.embedding_client` 统一提供——与问答检索共用同一实例，
既避免重复加载，也让单机资源占用可预期。
"""

from __future__ import annotations

import logging

from app.core.codes import Code
from app.core.exceptions import BizError
from app.processor.state import ImportState
from app.services import vector_service
from app.utils.embedding_client import embed_texts

logger = logging.getLogger(__name__)


def embed_store_node(state: ImportState) -> ImportState:
    chunks = state.get("chunks") or []
    doc_id = state.get("doc_id") or ""
    if not chunks:
        raise BizError(Code.PARSE_FAILED, "没有可入库的切片")
    if not doc_id:
        raise BizError(Code.INTERNAL_ERROR, "缺少知识单元锚点 doc_id")

    texts = [chunk["content"] for chunk in chunks]
    dense_vectors, sparse_vectors = embed_texts(texts)

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

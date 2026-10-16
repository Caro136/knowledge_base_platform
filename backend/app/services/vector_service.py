"""向量库服务（T-13）。

职责：Milvus collection 的建/写/删。**不负责**向量计算（那是 processor 层的职责），
也**不负责**权限判定（那是鉴权引擎的职责）。

关键设计（SPEC §5.3）：
- 每个切片冗余存储 ``doc_id`` 作为**权限锚点**，检索后按它做数据权限过滤；
- 写入采用「先插入、再按 doc_id 删除旧切片（排除本次新 id）」的幂等策略，
  避免"先删后插"在中断时造成的数据空窗。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

#: 稠密向量维度（BGE-M3）
DENSE_DIM = 1024

#: 客户端与已建 collection 的进程内缓存
_client: Any = None
_ready_collections: set[str] = set()


def _milvus_uri() -> str:
    return f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"


def get_client():
    """获取 Milvus 客户端（延迟导入 + 单例）。"""
    global _client
    if _client is not None:
        return _client

    try:
        from pymilvus import MilvusClient
    except ImportError as exc:  # pragma: no cover
        raise BizError(Code.VECTOR_DB_UNAVAILABLE, "缺少 pymilvus 客户端依赖") from exc

    try:
        _client = MilvusClient(uri=_milvus_uri())
    except Exception as exc:  # noqa: BLE001
        logger.error("连接 Milvus 失败：%s", exc)
        raise BizError(Code.VECTOR_DB_UNAVAILABLE, f"向量库不可用：{_milvus_uri()}") from exc
    return _client


def reset_client() -> None:
    """重置客户端缓存（配置变更或测试使用）。"""
    global _client
    _client = None
    _ready_collections.clear()


def ensure_collection(name: str | None = None) -> str:
    """确保切片 collection 存在（含稠密/稀疏向量索引）。"""
    collection = name or settings.MILVUS_CHUNK_COLLECTION
    if collection in _ready_collections:
        return collection

    from pymilvus import DataType, MilvusClient

    client = get_client()
    if client.has_collection(collection):
        _align_consistency(client, collection)
        _ready_collections.add(collection)
        return collection

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("content", DataType.VARCHAR, max_length=65535)
    schema.add_field("title", DataType.VARCHAR, max_length=512)
    schema.add_field("parent_title", DataType.VARCHAR, max_length=512)
    schema.add_field("file_title", DataType.VARCHAR, max_length=512)
    schema.add_field("item_name", DataType.VARCHAR, max_length=256)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=64)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="dense_vector", index_type="AUTOINDEX", metric_type="COSINE")
    index_params.add_index(
        field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP"
    )

    try:
        client.create_collection(
            collection_name=collection,
            schema=schema,
            index_params=index_params,
            # 强一致性：删除/覆盖导入后立即生效，避免检索到已删除的切片
            consistency_level="Strong",
        )
        logger.info("已创建向量 collection：%s（Strong 一致性）", collection)
    except Exception as exc:  # noqa: BLE001
        # 并发创建时可能已被其他请求创建，此时忽略
        if not client.has_collection(collection):
            raise BizError(Code.VECTOR_DB_UNAVAILABLE, f"创建 collection 失败：{exc}") from exc

    _ready_collections.add(collection)
    return collection


def _align_consistency(client: Any, collection: str) -> None:
    """把已存在 collection 的一致性级别对齐为 Strong。

    默认的 Bounded 一致性允许「删除后仍短暂读到旧数据」；对本平台而言，
    删除知识单元后不应再检索到其切片（否则会给出已下线的答案）。
    """
    try:
        info = client.describe_collection(collection)
        if info.get("consistency_level") == 0:  # 0 = Strong
            return
        client.alter_collection_properties(
            collection_name=collection,
            properties={"consistency_level": "Strong"},
        )
        logger.info("collection %s 一致性级别已调整为 Strong", collection)
    except Exception as exc:  # noqa: BLE001
        logger.warning("调整 collection 一致性级别失败（不影响读写）：%s", exc)


def upsert_doc_chunks(
    doc_id: str,
    file_title: str,
    item_name: str,
    rows: list[dict[str, Any]],
) -> int:
    """写入某个知识单元的全部切片，并清理其历史切片。

    :param rows: 每条含 dense_vector / sparse_vector / content / title / parent_title
    :return: 本次写入的切片数量
    """
    if not rows:
        return 0

    collection = ensure_collection()
    client = get_client()

    payload = [
        {
            "dense_vector": row["dense_vector"],
            "sparse_vector": row["sparse_vector"],
            "content": row["content"][:65535],
            "title": (row.get("title") or "")[:512],
            "parent_title": (row.get("parent_title") or "")[:512],
            "file_title": (file_title or "")[:512],
            "item_name": (item_name or "")[:256],
            "doc_id": doc_id,
        }
        for row in rows
    ]

    try:
        result = client.insert(collection_name=collection, data=payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("向量写入失败 doc_id=%s: %s", doc_id, exc)
        raise BizError(Code.VECTOR_DB_UNAVAILABLE, f"向量写入失败：{exc}") from exc

    new_ids = list(result.get("ids") or [])
    _remove_stale_chunks(client, collection, doc_id, new_ids)
    return len(payload)


def _remove_stale_chunks(client: Any, collection: str, doc_id: str, keep_ids: list[int]) -> None:
    """删除该知识单元的历史切片，保留本次新写入的。"""
    try:
        if keep_ids and len(keep_ids) <= 1000:
            expr = f'doc_id == "{doc_id}" and chunk_id not in {keep_ids}'
            client.delete(collection_name=collection, filter=expr)
        else:
            # 新切片过多（或没有新切片）时按 doc_id 全删
            client.delete(collection_name=collection, filter=f'doc_id == "{doc_id}"')
    except Exception as exc:  # noqa: BLE001
        # 清理失败不影响本次写入结果，但需留痕以便人工核对
        logger.warning("历史切片清理失败 doc_id=%s: %s", doc_id, exc)


def delete_by_doc_id(doc_id: str) -> None:
    """删除某个知识单元的全部切片（知识单元删除时调用）。"""
    if not doc_id:
        return
    try:
        client = get_client()
        collection = ensure_collection()
        client.delete(collection_name=collection, filter=f'doc_id == "{doc_id}"')
        logger.info("已清理向量切片 doc_id=%s", doc_id)
    except BizError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BizError(Code.VECTOR_DB_UNAVAILABLE, f"向量清理失败：{exc}") from exc


def search_chunks(
    dense_vector: list[float],
    sparse_vector: dict[int, float] | None,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """混合检索：稠密与稀疏两路各自召回，返回 (稠密结果, 稀疏结果)。

    两路结果不在此融合——融合（RRF）属于查询流程的业务逻辑，
    放在节点里更容易替换与测试。
    """
    collection = ensure_collection()
    client = get_client()
    output_fields = ["chunk_id", "content", "title", "parent_title", "file_title", "doc_id"]

    try:
        dense_hits = client.search(
            collection_name=collection,
            data=[dense_vector],
            anns_field="dense_vector",
            limit=limit,
            output_fields=output_fields,
            search_params={"metric_type": "COSINE"},
        )[0]
        sparse_hits = []
        if sparse_vector:
            sparse_hits = client.search(
                collection_name=collection,
                data=[sparse_vector],
                anns_field="sparse_vector",
                limit=limit,
                output_fields=output_fields,
                search_params={"metric_type": "IP"},
            )[0]
    except Exception as exc:  # noqa: BLE001
        logger.error("向量检索失败：%s", exc)
        raise BizError(Code.VECTOR_DB_UNAVAILABLE, f"向量检索失败：{exc}") from exc

    return [_normalize_hit(hit) for hit in dense_hits], [_normalize_hit(hit) for hit in sparse_hits]


def _normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """把 Milvus 的检索结果整理成流程内部使用的扁平结构。"""
    entity = hit.get("entity") or {}
    return {
        # MilvusClient 以「主键字段名」作为返回键（本项目主键为 chunk_id），
        # 部分版本返回通用的 "id"，两种都兼容
        "chunk_id": hit.get("chunk_id", hit.get("id")),
        "score": hit.get("distance"),
        "content": entity.get("content") or "",
        "title": entity.get("title") or "",
        "parent_title": entity.get("parent_title") or "",
        "file_title": entity.get("file_title") or "",
        "doc_id": entity.get("doc_id") or "",
    }


def count_by_doc_id(doc_id: str) -> int:
    """统计某知识单元的切片数量（供任务收尾校验）。"""
    try:
        client = get_client()
        collection = ensure_collection()
        rows = client.query(
            collection_name=collection,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["count(*)"],
        )
        if rows and isinstance(rows[0], dict):
            return int(rows[0].get("count(*)", 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("切片数量统计失败 doc_id=%s: %s", doc_id, exc)
    return 0

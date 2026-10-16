"""导入流程编排（T-12 / T-13）。

流程图：

    START → entry ─┬─(md/txt 直读)──────────────────→ image_summary
                   └─(pdf/word/ppt/excel/图片)→ doc_parse ┘
                                                        ↓
                                                     split → embed_store → END

用 LangGraph 而非手写串联的原因（SPEC ADR-002）：分支路由、节点级进度回传、
以及后续插入新节点（如商品名识别）都只需改边定义，不必动主流程。
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.processor.nodes.doc_parse import doc_parse_node
from app.processor.nodes.embed_store import embed_store_node
from app.processor.nodes.entry import ROUTE_DIRECT, ROUTE_PARSE, entry_node, route_after_entry
from app.processor.nodes.image_summary import image_summary_node
from app.processor.nodes.split import split_node
from app.processor.state import ImportState

logger = logging.getLogger(__name__)

_graph = None


def build_import_graph():
    """构建导入流程图（每次调用返回新实例）。"""
    graph = StateGraph(ImportState)

    graph.add_node("entry", entry_node)
    graph.add_node("doc_parse", doc_parse_node)
    graph.add_node("image_summary", image_summary_node)
    graph.add_node("split", split_node)
    graph.add_node("embed_store", embed_store_node)

    graph.add_edge(START, "entry")
    graph.add_conditional_edges(
        "entry",
        route_after_entry,
        {ROUTE_DIRECT: "image_summary", ROUTE_PARSE: "doc_parse"},
    )
    graph.add_edge("doc_parse", "image_summary")
    graph.add_edge("image_summary", "split")
    graph.add_edge("split", "embed_store")
    graph.add_edge("embed_store", END)

    return graph.compile()


def get_import_graph():
    """获取编译后的图（进程内缓存，编译有开销）。"""
    global _graph
    if _graph is None:
        _graph = build_import_graph()
        logger.info("导入流程图已编译")
    return _graph

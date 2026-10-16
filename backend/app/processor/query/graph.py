"""问答流程编排（T-19 ~ T-23）。

    START → retrieve → authz_filter ─┬─(有有权切片)→ rerank → build_context → END
                                     └─(无)→ build_context → END

鉴权节点被刻意放在**召回之后、重排之前**（SPEC ADR-003）：
- 放在召回前需要把权限条件下推成向量库的过滤表达式，实现复杂且易漏；
- 放在重排后则会让未授权内容参与打分，浪费算力且增加泄漏面。

流式生成不放在图内：LangGraph 节点适合"数据进、数据出"的纯计算，
而流式输出需要把 token 增量实时推给 HTTP 连接。因此图负责产出
``messages`` 与 ``references``，由 :mod:`app.services.chat_service` 驱动流式生成。
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.processor.query.nodes.authz_filter import authz_filter_node, has_authorized_chunks
from app.processor.query.nodes.build_context import build_context_node
from app.processor.query.nodes.rerank import rerank_node
from app.processor.query.nodes.retrieve import retrieve_node
from app.processor.query.state import QueryState

logger = logging.getLogger(__name__)

_graph = None


def build_query_graph():
    graph = StateGraph(QueryState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("authz_filter", authz_filter_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("build_context", build_context_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "authz_filter")
    graph.add_conditional_edges(
        "authz_filter",
        has_authorized_chunks,
        {"rerank": "rerank", "build_context": "build_context"},
    )
    graph.add_edge("rerank", "build_context")
    graph.add_edge("build_context", END)

    return graph.compile()


def get_query_graph():
    """获取编译后的问答流程图（进程内缓存）。"""
    global _graph
    if _graph is None:
        _graph = build_query_graph()
        logger.info("问答流程图已编译")
    return _graph

"""上下文组装节点（T-21 / T-23）。

职责：把重排后的切片拼成 Prompt 上下文、生成引用溯源元数据、组装完整消息列表。

安全约束：本节点只接受 ``ranked_docs``（已鉴权集合），**不存在任何旁路**——
这是「未授权内容绝不进入大模型上下文」这条红线的最后一道保证。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.processor.query.state import QueryState

logger = logging.getLogger(__name__)

#: 检索增强场景的系统提示：约束模型只依据资料作答，并显式标注来源序号
SYSTEM_PROMPT = (
    "你是企业知识库助手，负责依据内部资料回答员工提问。\n"
    "必须遵守以下规则：\n"
    "1. 只使用下方「参考资料」中的信息作答，不得引入资料之外的臆测与常识补充；\n"
    "2. 引用资料时在句末标注来源序号，如 [1]、[2]；\n"
    "3. 若资料不足以回答问题，直接说明「知识库中未收录相关内容」，不要编造；\n"
    "4. 用简体中文、条理清晰地回答，必要时使用列表或表格。"
)

#: 多轮对话注入的历史轮数上限
HISTORY_TURNS = 6


def _user_prompt(question: str, context: str) -> str:
    if not context:
        return f"问题：{question}\n\n（知识库中未检索到相关资料，请如实说明未收录。）"
    return f"参考资料：\n{context}\n\n问题：{question}"


def build_context_node(state: QueryState) -> QueryState:
    docs = state.get("ranked_docs") or []

    parts: list[str] = []
    references: list[dict[str, Any]] = []
    used_chars = 0

    for index, doc in enumerate(docs, start=1):
        label = doc.get("parent_title") or doc.get("title") or doc.get("file_title") or "未命名资料"
        piece = f"[{index}] {label}\n{doc.get('content') or ''}"
        # 上下文预算：超出上限即停止拼接（宁可少给一条，不超预算）
        if used_chars + len(piece) > settings.MAX_CONTEXT_CHARS:
            break

        parts.append(piece)
        used_chars += len(piece)
        references.append(
            {
                "index": index,
                "doc_id": doc.get("doc_id"),
                "chunk_id": doc.get("chunk_id"),
                "title": doc.get("title") or doc.get("file_title") or "未命名",
                "parent_title": doc.get("parent_title") or "",
                "file_title": doc.get("file_title") or "",
                "snippet": (doc.get("content") or "")[:200],
                "score": doc.get("rerank_score"),
            }
        )

    context = "\n\n".join(parts)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for message in (state.get("history") or [])[-HISTORY_TURNS:]:
        role = message.get("role")
        content = message.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": _user_prompt(state.get("question") or "", context)})

    logger.info("上下文组装完成：%d 条引用，%d 字符", len(references), used_chars)
    return {
        "context": context,
        "references": references,
        "messages": messages,
        "has_context": bool(parts),
    }

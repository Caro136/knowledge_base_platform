"""AI 鉴权问答编排（T-19 ~ T-24）。

职责边界：
- 调用查询图（检索 → 鉴权 → 精排 → 组装上下文）；
- 驱动**流式生成**并把 token 增量经 SSE 推给前端（图不负责流式，见 graph.py 说明）；
- 维护会话历史（MongoDB）；
- 权限受限时**不调用大模型**，直接返回固定提示。

安全红线（PRD M3：越权泄漏 0 次）：
本模块只使用查询图产出的 ``messages`` 与 ``references``——它们全部来自
「已通过鉴权」的切片。此处不存在任何"补上下文"的旁路。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.models import User
from app.processor.query.graph import get_query_graph
from app.schemas.chat import ChatQueryIn, ChatQueryOut, ReferenceOut
from app.services import session_service
from app.utils import llm_client

logger = logging.getLogger(__name__)

#: 权限受限提示文案（PRD Q5 待确认；此处取「说明原因 + 给出后续动作」的版本）
PERMISSION_DENIED_NOTICE = (
    "检测到与您的问题相关的知识内容，但您当前的部门/角色无权查阅。"
    "如需访问，请联系管理员为您开通对应知识的权限。"
)

#: 无任何相关资料时的兜底提示（不调用大模型，避免凭空作答）
NO_CONTEXT_NOTICE = "知识库中暂未收录与该问题相关的内容，建议补充相关文档后再试。"

#: 完成任务在内存中的保留时长（秒），用于前端断线重连
TASK_TTL_SECONDS = 600

#: 会话标题长度
TITLE_LENGTH = 30


@dataclass
class StreamTask:
    """一次问答的流式状态。"""

    task_id: str
    session_id: str
    user_id: int
    question: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    loop: asyncio.AbstractEventLoop | None = None
    answer: str = ""
    references: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    created_at: float = field(default_factory=time.time)


_tasks: dict[str, StreamTask] = {}
_tasks_lock = threading.Lock()


def _prune_tasks() -> None:
    """清理过期的已完成任务，避免内存持续增长。"""
    now = time.time()
    with _tasks_lock:
        expired = [
            task_id
            for task_id, task in _tasks.items()
            if task.finished and now - task.created_at > TASK_TTL_SECONDS
        ]
        for task_id in expired:
            _tasks.pop(task_id, None)


def _emit(task: StreamTask, event: str, data: dict[str, Any]) -> None:
    """从工作线程向事件循环投递一条 SSE 事件。"""
    if task.loop is None:
        return
    task.loop.call_soon_threadsafe(task.queue.put_nowait, {"event": event, "data": data})


# ---------------------------------------------------------------------------
# 受理与执行
# ---------------------------------------------------------------------------


async def prepare_query(db: Session, user: User, payload: ChatQueryIn) -> ChatQueryOut:
    """受理一次问答：准备会话、登记任务、投递后台执行。"""
    _prune_tasks()

    session_id = payload.session_id
    if session_id:
        if session_service.get_session(session_id, user.id) is None:
            raise BizError(Code.NOT_FOUND, "会话不存在或不属于当前用户")
    else:
        session_id = session_service.create_session(user.id, payload.question[:TITLE_LENGTH])

    # 用户消息先落库（即使生成失败，提问记录也保留）
    session_service.append_message(
        session_id, user.id, {"role": "user", "content": payload.question}
    )

    task = StreamTask(
        task_id=uuid.uuid4().hex,
        session_id=session_id,
        user_id=user.id,
        question=payload.question,
        loop=asyncio.get_running_loop(),
    )
    with _tasks_lock:
        _tasks[task.task_id] = task

    thread = threading.Thread(
        target=_run_query, args=(task,), name=f"kb-chat-{task.task_id[:8]}", daemon=True
    )
    thread.start()

    return ChatQueryOut(task_id=task.task_id, session_id=session_id)


def _run_query(task: StreamTask) -> None:
    """在工作线程中执行查询图与流式生成。"""
    try:
        _emit(task, "stage", {"stage": "retrieving", "label": "检索知识库并校验权限"})

        history = session_service.get_history(task.session_id, task.user_id, limit=10)
        state = {
            "question": task.question,
            "user_id": task.user_id,
            "session_id": task.session_id,
            "history": [{"role": m.get("role"), "content": m.get("content")} for m in history],
        }
        result = get_query_graph().invoke(state)

        references = result.get("references") or []
        task.references = references
        has_context = bool(result.get("has_context"))

        if references:
            # 对外统一 camelCase，与 done 事件及 REST 接口保持一致
            items = [ReferenceOut(**item).model_dump(by_alias=True) for item in references]
            _emit(task, "references", {"items": items})

        # 权限受限：存在相关知识但均无权访问 —— 不调用大模型，直接给出安全提示
        if not has_context and result.get("permission_denied"):
            _emit(task, "notice", {"type": "permission_denied", "message": PERMISSION_DENIED_NOTICE})
            _finalize(task, PERMISSION_DENIED_NOTICE)
            return

        if not has_context:
            # 真正的知识缺口：不调用大模型，避免模型凭常识作答
            _emit(task, "notice", {"type": "no_context", "message": NO_CONTEXT_NOTICE})
            _finalize(task, NO_CONTEXT_NOTICE)
            return

        # 流式生成
        _emit(task, "stage", {"stage": "generating", "label": "生成回答"})
        pieces: list[str] = []
        for token in llm_client.chat_stream(result.get("messages") or []):
            pieces.append(token)
            _emit(task, "delta", {"text": token})

        answer = "".join(pieces).strip()
        if not answer:
            raise BizError(Code.LLM_UNAVAILABLE, "模型未返回内容")
        _finalize(task, answer)

    except BizError as exc:
        logger.warning("问答失败 task=%s：%s", task.task_id, exc.message)
        _emit(task, "error", {"code": exc.code, "message": exc.message})
        task.finished = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("问答异常 task=%s", task.task_id)
        _emit(task, "error", {"code": Code.INTERNAL_ERROR, "message": f"服务异常：{exc}"})
        task.finished = True


def _finalize(task: StreamTask, answer: str) -> None:
    """落库助手消息并发送完成事件。"""
    task.answer = answer
    references = [ReferenceOut(**item).model_dump(by_alias=True) for item in task.references]

    try:
        session_service.append_message(
            task.session_id,
            task.user_id,
            {"role": "assistant", "content": answer, "references": references},
        )
    except Exception as exc:  # noqa: BLE001 - 落库失败不应影响已生成的回答
        logger.warning("助手消息落库失败 session=%s：%s", task.session_id, exc)

    _emit(
        task,
        "done",
        {
            "session_id": task.session_id,
            "answer": answer,
            "references": task.references,
        },
    )
    task.finished = True


# ---------------------------------------------------------------------------
# SSE 输出
# ---------------------------------------------------------------------------


async def event_stream(task_id: str):
    """把任务事件队列转成 SSE 文本流。"""
    task = _tasks.get(task_id)
    if task is None:
        yield _sse("error", {"code": Code.NOT_FOUND, "message": "任务不存在或已过期"})
        return

    while True:
        try:
            payload = await asyncio.wait_for(task.queue.get(), timeout=15)
        except asyncio.TimeoutError:
            # 心跳，避免代理层因空闲断开连接
            yield ": keep-alive\n\n"
            if task.finished and task.queue.empty():
                break
            continue

        yield _sse(payload["event"], payload["data"])
        if payload["event"] in ("done", "error"):
            break


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 会话查询
# ---------------------------------------------------------------------------


def list_user_sessions(user: User, limit: int = 50) -> list[dict[str, Any]]:
    # 经 Schema 转换，保证对外字段为 camelCase（与前端契约一致）
    from app.schemas.chat import SessionOut

    return [SessionOut(**item) for item in session_service.list_sessions(user.id, limit)]


def get_session_messages(user: User, session_id: str) -> list[dict[str, Any]]:
    session = session_service.get_session(session_id, user.id)
    if session is None:
        raise BizError(Code.NOT_FOUND, "会话不存在或不属于当前用户")
    return session.get("messages") or []


def delete_user_session(user: User, session_id: str) -> None:
    if not session_service.delete_session(session_id, user.id):
        raise BizError(Code.NOT_FOUND, "会话不存在或不属于当前用户")

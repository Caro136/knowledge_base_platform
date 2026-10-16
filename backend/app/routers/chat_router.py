"""AI 鉴权问答接口（T-19 ~ T-24）。

问答采用「先受理、后推送」两段式：
- ``POST /chat/query`` 立即返回 task_id（生成是长耗时操作，不能占住请求）；
- ``GET /chat/stream/{task_id}`` 以 SSE 推送阶段、正文增量、引用与完成事件。

前端请使用 fetch + ReadableStream 读取（原生 EventSource 无法携带
Authorization 头，而本接口要求登录态）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_permission
from app.models import User
from app.schemas.chat import ChatQueryIn
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["AI 问答"])

#: SSE 所需的响应头：禁用缓存与中间层缓冲，保证增量及时到达
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/query", summary="发起问答（返回 task_id，生成过程经 SSE 推送）")
async def query(
    payload: ChatQueryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    return ok(await chat_service.prepare_query(db, user, payload))


@router.get("/stream/{task_id}", summary="问答流式输出（SSE）")
async def stream(
    task_id: str,
    _: User = Depends(require_permission("ai:chat")),
) -> StreamingResponse:
    return StreamingResponse(
        chat_service.event_stream(task_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/sessions", summary="当前用户的会话列表")
def list_sessions(
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    return ok(chat_service.list_user_sessions(user))


@router.get("/history/{session_id}", summary="会话消息历史")
def history(
    session_id: str,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    return ok(chat_service.get_session_messages(user, session_id))


@router.delete("/history/{session_id}", summary="删除会话")
def delete_history(
    session_id: str,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    chat_service.delete_user_session(user, session_id)
    return ok(message="会话已删除")

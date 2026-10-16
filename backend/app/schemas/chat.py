"""问答相关 Schema（T-19 ~ T-24）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel, InModel


class ChatQueryIn(InModel):
    """发起问答。"""

    question: str = Field(min_length=1, max_length=1000, description="用户提问")
    session_id: str | None = Field(default=None, description="会话 ID；为空则新建会话")


class ChatQueryOut(CamelModel):
    """问答受理结果：生成过程经 SSE 推送，此处只返回任务与会话标识。"""

    task_id: str
    session_id: str


class SessionOut(CamelModel):
    """会话列表项。"""

    session_id: str
    title: str
    updated_at: datetime | None = None


class ReferenceOut(CamelModel):
    """引用溯源卡片。"""

    index: int
    doc_id: str | None = None
    chunk_id: int | None = None
    title: str = ""
    parent_title: str = ""
    file_title: str = ""
    snippet: str = ""
    score: float | None = None


class MessageOut(CamelModel):
    """历史消息。"""

    role: str
    content: str
    references: list[ReferenceOut] = Field(default_factory=list)
    created_at: datetime | None = None

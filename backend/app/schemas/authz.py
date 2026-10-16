"""鉴权引擎的入参/出参（T-16）。"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel, InModel


class AuthzFilterIn(InModel):
    """批量鉴权入参。"""

    user_id: int | None = Field(
        default=None, description="目标用户；不传表示当前登录用户，查询他人需超管权限"
    )
    doc_ids: list[str] = Field(default_factory=list, description="候选知识单元锚点列表")


class AuthzFilterOut(CamelModel):
    """批量鉴权结果：允许 / 拒绝两组，均保持入参顺序。"""

    allowed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)


class AuthzExplainOut(CamelModel):
    """单个知识单元的鉴权解释，用于排障与权限演示。"""

    doc_id: str
    allowed: bool
    reason: str
    matched: list[str] = Field(default_factory=list, description="命中的权限实体，如 ['department:3']")

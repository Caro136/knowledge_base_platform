"""Schema 公共基类。

前后端字段命名约定：Python 内部用 snake_case，对外 JSON 输出 camelCase
（由 alias_generator 自动转换，FastAPI 序列化默认 by_alias=True）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """对外输出 camelCase 的模型基类。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,   # 允许按字段名构造，便于内部代码书写
        from_attributes=True,    # 支持直接从 ORM 对象转换
    )


class InModel(BaseModel):
    """入参模型：接受 camelCase 或 snake_case，宽松解析。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )

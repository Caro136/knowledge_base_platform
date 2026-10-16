"""建表工具。

仅负责结构创建（幂等），种子数据见 :mod:`app.seed`。
"""

from __future__ import annotations

import logging

from app.db.session import engine

logger = logging.getLogger(__name__)


def init_db() -> None:
    """按 ORM 元数据创建所有缺失的表（已存在的表不会被修改）。"""
    # 导入包以完成 metadata 注册，不可省略
    import app.models  # noqa: F401
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
    table_names = sorted(Base.metadata.tables.keys())
    logger.info("数据表已就绪，共 %d 张：%s", len(table_names), ", ".join(table_names))


def drop_all() -> None:
    """删除所有表（仅供测试使用，禁止在生产环境调用）。"""
    import app.models  # noqa: F401
    from app.db.base import Base

    Base.metadata.drop_all(bind=engine)
    logger.warning("所有数据表已删除")

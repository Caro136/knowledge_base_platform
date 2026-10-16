"""MySQL 引擎与会话管理。

注意：``create_engine`` 是惰性的，导入本模块不会建立连接，
因此测试或离线环境下导入应用不会因数据库不可达而失败。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_mysql_url = URL.create(
    drivername="mysql+pymysql",
    username=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    database=settings.MYSQL_DB,
    query={"charset": "utf8mb4"},
)

engine = create_engine(
    _mysql_url,
    echo=settings.MYSQL_ECHO,
    pool_pre_ping=True,   # 断线自动重连，避免内网长连接被中间设备回收后报错
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # 提交后仍可读取对象属性，便于接口层组装响应
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供一个请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

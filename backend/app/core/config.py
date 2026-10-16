"""配置中心。

所有可调参数集中在此，遵循 SPEC §8「参数可配置，禁止硬编码」的要求。
配置来源优先级：环境变量 > .env 文件 > 类内默认值。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 目录（本文件位于 backend/app/core/config.py）
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置。属性名即环境变量名（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    APP_NAME: str = "知识库管理平台"
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    API_PREFIX: str = "/api"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    STATIC_DIR: str = "../frontend/dist"

    # ---------- MySQL ----------
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "kb"
    MYSQL_PASSWORD: str = "kb_pass_2026"
    MYSQL_DB: str = "kb_platform"
    MYSQL_ECHO: bool = False

    # ---------- MongoDB ----------
    MONGO_URL: str = "mongodb://127.0.0.1:27017"
    MONGO_DB_NAME: str = "kb_platform"

    # ---------- Milvus ----------
    MILVUS_HOST: str = "127.0.0.1"
    MILVUS_PORT: int = 19530
    MILVUS_CHUNK_COLLECTION: str = "kb_chunks"
    MILVUS_ITEM_COLLECTION: str = "kb_item_name"

    # ---------- MinIO ----------
    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "kbminio"
    MINIO_SECRET_KEY: str = "kbminio_pass_2026"
    MINIO_BUCKET_FILES: str = "kb-files"
    MINIO_SECURE: bool = False

    # ---------- 认证 ----------
    JWT_SECRET: str = "change-me-in-production-please"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720

    # ---------- 初始管理员 ----------
    INIT_ADMIN_USERNAME: str = "admin"
    INIT_ADMIN_PASSWORD: str = "Admin@123456"
    INIT_ADMIN_NICKNAME: str = "超级管理员"

    # ---------- 大模型 ----------
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: int = 120

    # ---------- 视觉模型 ----------
    VLM_BASE_URL: str = ""
    VLM_API_KEY: str = ""
    VLM_MODEL: str = ""
    IMG_SUMMARY_QPM: int = 30

    # ---------- 文档解析服务 ----------
    DOC_PARSE_BASE_URL: str = ""
    DOC_PARSE_API_TOKEN: str = ""

    # ---------- 本地模型权重 ----------
    EMBEDDING_MODEL_PATH: str = ""
    RERANK_MODEL_PATH: str = ""

    # ---------- 检索参数 ----------
    RETRIEVE_TOP_K: int = 5
    RRF_K: int = 60
    RRF_MAX_RESULTS: int = 10
    RERANK_MIN_TOP_K: int = 6
    RERANK_MAX_TOP_K: int = 20
    RERANK_GAP_ABS: float = 0.5
    RERANK_GAP_RATIO: float = 0.25
    MAX_CONTEXT_CHARS: int = 12000

    # ---------- 切片参数 ----------
    CHUNK_MAX_LENGTH: int = 500
    CHUNK_MIN_LENGTH: int = 200

    # ---------- 知识沉淀 ----------
    FAQ_RECOMMEND_THRESHOLD: int = 5

    # ---------- 派生属性 ----------
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS 白名单列表（逗号分隔解析，空白项忽略）。"""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def static_dir_abs(self) -> Path:
        """前端产物目录的绝对路径。"""
        path = Path(self.STATIC_DIR)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV.lower() in {"dev", "local", "development"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。"""
    return Settings()


settings = get_settings()

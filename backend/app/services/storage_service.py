"""对象存储抽象层（T-11）。

设计目的：把「原文件与文档图片存哪里」与业务解耦。
默认实现为 MinIO（SPEC §12 I-01），本地文件系统保留为备选后端
（`STORAGE_BACKEND=local`），二者实现同一接口，业务代码无感切换。

约定：对象 key 由服务端生成（`documents/{doc_id}{ext}`），不使用用户上传的原始
文件名，避免路径穿越与特殊字符问题；原始文件名保存在数据库 ``file_title`` 中。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """对象存储统一接口。"""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """写入对象，返回可持久化的存储路径/键。"""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """读取对象内容。"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除对象；对象不存在时应静默成功（幂等）。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """对象是否存在。"""

    @abstractmethod
    def describe(self) -> dict[str, str]:
        """返回后端描述信息（供健康检查/排障）。"""


class LocalStorage(StorageBackend):
    """本地文件系统后端。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """把 key 解析为根目录下的绝对路径，并阻止目录穿越。"""
        candidate = (self.root / key).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise BizError(Code.PARAM_INVALID, "非法的存储路径")
        return candidate

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise BizError(Code.NOT_FOUND, "存储对象不存在")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def describe(self) -> dict[str, str]:
        return {"backend": "local", "root": str(self.root)}


class MinioStorage(StorageBackend):
    """MinIO（S3 兼容）后端。"""

    def __init__(self) -> None:
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - 依赖缺失属于部署问题
            raise BizError(Code.OBJECT_STORAGE_UNAVAILABLE, "缺少 minio 客户端依赖") from exc

        self.bucket = settings.MINIO_BUCKET_FILES
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """确保 bucket 存在（不存在则创建），避免首次上传失败。"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("已创建对象存储 bucket：%s", self.bucket)
        except Exception as exc:  # noqa: BLE001
            logger.error("对象存储不可用（%s）：%s", settings.MINIO_ENDPOINT, exc)
            raise BizError(
                Code.OBJECT_STORAGE_UNAVAILABLE,
                f"对象存储不可用：{settings.MINIO_ENDPOINT}",
            ) from exc

    @staticmethod
    def _to_stream(data: bytes):
        import io

        return io.BytesIO(data)

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        try:
            self.client.put_object(
                self.bucket,
                key,
                self._to_stream(data),
                length=len(data),
                content_type=content_type or "application/octet-stream",
            )
            return key
        except BizError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("对象写入失败 key=%s: %s", key, exc)
            raise BizError(Code.OBJECT_STORAGE_UNAVAILABLE, "对象写入失败") from exc

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:  # noqa: BLE001
            logger.error("对象读取失败 key=%s: %s", key, exc)
            raise BizError(Code.NOT_FOUND, "存储对象不存在或不可读") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except Exception as exc:  # noqa: BLE001
            # 删除失败不阻断业务（例如对象本就不存在），但要留痕
            logger.warning("对象删除失败 key=%s: %s", key, exc)

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def describe(self) -> dict[str, str]:
        return {"backend": "minio", "endpoint": settings.MINIO_ENDPOINT, "bucket": self.bucket}


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """获取存储后端单例（首次调用时按配置初始化）。"""
    global _storage
    if _storage is None:
        backend = (settings.STORAGE_BACKEND or "local").strip().lower()
        if backend == "minio":
            _storage = MinioStorage()
            logger.info("对象存储后端：MinIO %s", settings.MINIO_ENDPOINT)
        else:
            root = Path(settings.LOCAL_STORAGE_DIR)
            if not root.is_absolute():
                from app.core.config import BACKEND_DIR

                root = BACKEND_DIR / root
            _storage = LocalStorage(root)
            logger.info("对象存储后端：本地文件系统 %s", root)
    return _storage


def reset_storage() -> None:
    """重置单例（配置变更或测试时使用）。"""
    global _storage
    _storage = None

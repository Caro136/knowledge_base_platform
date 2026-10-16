"""MinerU 云解析客户端（T-12）。

对接 MinerU v4 HTTP API，把 PDF / Word / PPT / Excel / 图片统一转成 Markdown：

1. ``POST /file-urls/batch``  申请上传链接，拿到 batch_id 与签名 URL
2. ``PUT  <签名 URL>``        上传原始文件
3. ``GET  /extract-results/batch/{batch_id}``  轮询解析状态，done 时取结果 zip
4. 下载 zip 并在内存中解压，取出 Markdown 正文与图片

全部请求显式禁用系统代理，避免内网代理配置干扰。
"""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tiff"}


class MinerUClient:
    """MinerU v4 解析客户端。"""

    def __init__(self) -> None:
        self.base_url = (settings.DOC_PARSE_BASE_URL or "").rstrip("/")
        self.token = (settings.DOC_PARSE_API_TOKEN or "").strip()
        self.poll_interval = max(1, settings.DOC_PARSE_POLL_INTERVAL_SECONDS)
        self.timeout = max(30, settings.DOC_PARSE_TIMEOUT_SECONDS)

        if not self.base_url or not self.token:
            raise BizError(
                Code.DOC_PARSE_UNAVAILABLE,
                "未配置文档解析服务（DOC_PARSE_BASE_URL / DOC_PARSE_API_TOKEN）",
            )

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def parse(self, filename: str, data: bytes) -> tuple[str, dict[str, bytes]]:
        """解析文件，返回 (Markdown 文本, {zip 内图片路径: 图片字节})。"""
        batch_id, upload_url = self._request_upload_url(filename)
        self._upload(upload_url, filename, data)
        zip_url = self._poll_result(batch_id, filename)
        return self._fetch_result(zip_url)

    # ------------------------------------------------------------------
    # 分步实现
    # ------------------------------------------------------------------

    def _request_upload_url(self, filename: str) -> tuple[str, str]:
        payload = self._json_request(
            "POST",
            f"{self.base_url}/file-urls/batch",
            {"files": [{"name": filename}]},
        )
        file_urls = payload.get("file_urls") or []
        batch_id = payload.get("batch_id")
        if not file_urls or not batch_id:
            raise BizError(Code.PARSE_FAILED, f"解析服务未返回上传链接：{payload}")
        return str(batch_id), str(file_urls[0])

    def _upload(self, signed_url: str, filename: str, data: bytes) -> None:
        """把文件 PUT 到签名地址。

        实现细节：OSS 预签名 URL 的签名可能绑定 Content-Type，多带或少带都会 403。
        而 ``urllib`` 在有 body 时会自动注入 ``Content-Type: application/x-www-form-urlencoded``，
        ``requests`` 则会受系统代理影响——两者都不可控，因此这里用 ``http.client``
        手工发起请求：先按不带 Content-Type 上传，失败再带上按扩展名推断的类型重试。
        """
        import http.client
        from urllib.parse import urlsplit

        parts = urlsplit(signed_url)
        if not parts.hostname:
            raise BizError(Code.PARSE_FAILED, f"签名上传地址无效：{signed_url[:80]}")

        path = parts.path + (f"?{parts.query}" if parts.query else "")
        guessed_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        attempts: list[dict[str, str]] = [{}, {"Content-Type": guessed_type}]
        last_error = "未知错误"

        for headers in attempts:
            connection_cls = (
                http.client.HTTPSConnection
                if parts.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = connection_cls(parts.hostname, parts.port, timeout=180)
            try:
                connection.request("PUT", path, body=data, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                if response.status in (200, 201, 204):
                    return
                last_error = f"HTTP {response.status}：{payload[:120].decode('utf-8', 'replace')}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            finally:
                connection.close()

        raise BizError(Code.PARSE_FAILED, f"文件上传失败：{last_error}")

    def _poll_result(self, batch_id: str, filename: str) -> str:
        deadline = time.time() + self.timeout
        url = f"{self.base_url}/extract-results/batch/{batch_id}"

        while time.time() < deadline:
            try:
                payload = self._json_request("GET", url, None)
            except BizError as exc:
                # 解析服务偶发 5xx / 网络抖动时继续重试，直到超时
                logger.warning("轮询解析结果失败，稍后重试：%s", exc.message)
                time.sleep(self.poll_interval)
                continue

            results = payload.get("extract_result") or []
            if results:
                item = results[0]
                state = str(item.get("state") or "").lower()
                if state == "done":
                    zip_url = item.get("full_zip_url")
                    if not zip_url:
                        raise BizError(Code.PARSE_FAILED, "解析完成但未返回结果下载地址")
                    logger.info("解析完成：%s", filename)
                    return str(zip_url)
                if state in {"failed", "error"}:
                    reason = item.get("err_msg") or "解析服务返回失败状态"
                    raise BizError(Code.PARSE_FAILED, f"解析失败：{reason}")

            time.sleep(self.poll_interval)

        raise BizError(Code.PARSE_FAILED, f"解析超时（>{self.timeout}s）：{filename}")

    def _fetch_result(self, zip_url: str) -> tuple[str, dict[str, bytes]]:
        raw = self._bytes_request(zip_url)
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise BizError(Code.PARSE_FAILED, "解析结果不是有效的压缩包") from exc

        with archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]

            # 优先取嵌套目录下的 md（MinerU 产出形如 hybrid_auto/xxx.md）
            md_name = next((n for n in names if n.endswith(".md") and "/" in n), None)
            if md_name is None:
                md_name = next((n for n in names if n.endswith(".md")), None)
            if md_name is None:
                raise BizError(Code.PARSE_FAILED, "解析结果中未找到 Markdown 文件")

            content = archive.read(md_name).decode("utf-8", errors="replace")
            base_dir = str(Path(md_name).parent)

            images: dict[str, bytes] = {}
            for name in names:
                if Path(name).suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                images[name] = archive.read(name)
                # 同时以「相对 md 的路径」为键，简化调用方的匹配
                if base_dir and base_dir != "." and name.startswith(f"{base_dir}/"):
                    images[name[len(base_dir) + 1 :]] = images[name]

        logger.info("解析结果读取完成：md=%s，图片 %d 张", md_name, len(images))
        return content, images

    # ------------------------------------------------------------------
    # HTTP 基础
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _json_request(self, method: str, url: str, payload: dict | None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in self._headers().items():
            request.add_header(key, value)

        try:
            with _OPENER.open(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise BizError(Code.PARSE_FAILED, f"解析服务返回 {exc.code}：{detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise BizError(Code.DOC_PARSE_UNAVAILABLE, f"解析服务调用失败：{exc}") from exc

        # MinerU 统一返回 {code, msg, data}
        if isinstance(body, dict) and "code" in body and body.get("code") not in (0, "0", None):
            raise BizError(Code.PARSE_FAILED, f"解析服务返回错误：{body.get('msg') or body.get('message') or body}")
        data_field = body.get("data") if isinstance(body, dict) else None
        return data_field if isinstance(data_field, dict) else (body if isinstance(body, dict) else {})

    @staticmethod
    def _bytes_request(url: str) -> bytes:
        try:
            with _OPENER.open(url, timeout=180) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001
            raise BizError(Code.PARSE_FAILED, f"结果下载失败：{exc}") from exc

"""冒烟测试公共工具（供各 smoke_test_*.py 复用）。

依赖：后端已启动（python -m app.main），且已执行 python -m app.seed。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

# 输出被重定向（管道/文件）时统一为 UTF-8，避免 Windows 控制台中文乱码
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty() and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402

BASE = f"http://127.0.0.1:{settings.APP_PORT}"
ADMIN_USER = settings.INIT_ADMIN_USERNAME
ADMIN_PWD = settings.INIT_ADMIN_PASSWORD

_results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: object = "") -> None:
    """记录并打印一条断言结果。"""
    _results.append((name, passed, str(detail)))
    flag = "PASS" if passed else "FAIL"
    print(f"[{flag}] {name}" + (f" | {detail}" if detail else ""))


def call(
    method: str,
    path: str,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
    """发起 JSON 请求，返回 (http_status, 响应体)。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return _send(request)


def call_multipart(
    path: str,
    files: list[tuple[str, bytes]],
    token: str | None = None,
    field_name: str = "files",
) -> tuple[int, dict]:
    """发起 multipart/form-data 请求（模拟前端文件上传）。

    注意：文件名请使用 ASCII，避免 Content-Disposition 的编码差异干扰测试。
    """
    boundary = f"----kbsmoke{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for filename, content in files:
        chunks.append(f"--{boundary}".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode()
        )
        chunks.append(b"Content-Type: application/octet-stream")
        chunks.append(b"")
        chunks.append(content)
    chunks.append(f"--{boundary}--".encode())
    chunks.append(b"")
    body = b"\r\n".join(chunks)

    request = urllib.request.Request(BASE + path, data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return _send(request)


def _send(request: urllib.request.Request) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def login(username: str, password: str) -> tuple[str, dict]:
    """登录并返回 (token, userInfo)。"""
    _, body = call("POST", "/api/auth/login", body={"username": username, "password": password})
    data = body.get("data") or {}
    return data.get("token", ""), (data.get("userInfo") or {})


def summary() -> int:
    """打印汇总，返回进程退出码（0 表示全部通过）。"""
    total = len(_results)
    failed = [name for name, passed, _ in _results if not passed]
    print("-" * 62)
    print(f"总计 {total} 项，通过 {total - len(failed)}，失败 {len(failed)}")
    for name in failed:
        print(f"  失败：{name}")
    return 1 if failed else 0

"""大模型与视觉模型客户端（OpenAI 兼容协议）。

用标准库实现，避免为一次 HTTP 调用引入额外依赖；显式禁用系统代理，
避免内网环境下的代理配置干扰调用。

T-18 之后问答链路（T-19）也会复用本模块。
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

#: 不走系统代理的 opener（内网部署时更可预期）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise BizError(Code.LLM_UNAVAILABLE, f"模型服务返回 {exc.code}：{detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise BizError(Code.LLM_UNAVAILABLE, f"模型服务调用失败：{exc}") from exc


def _extract_content(body: dict) -> str:
    """从 OpenAI 兼容响应中取出正文。

    注意：推理类模型可能把 token 全部用于思考过程而返回空 content，
    这里显式报错而不是静默返回空串，便于定位配置问题。
    """
    choices = body.get("choices") or []
    if not choices:
        raise BizError(Code.LLM_UNAVAILABLE, "模型服务返回结果为空")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        reasoning = (message.get("reasoning_content") or "").strip()
        hint = "（模型仅返回了推理内容，可能 max_tokens 过小）" if reasoning else ""
        raise BizError(Code.LLM_UNAVAILABLE, f"模型未返回正文内容{hint}")
    return content


def chat(
    messages: list[dict],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    """调用配置的 LLM（非流式）。"""
    if not settings.LLM_API_KEY or not settings.LLM_BASE_URL:
        raise BizError(Code.LLM_UNAVAILABLE, "未配置 LLM 服务（LLM_BASE_URL / LLM_API_KEY）")

    body = _post_json(
        f"{settings.LLM_BASE_URL.rstrip('/')}/v1/chat/completions",
        {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        settings.LLM_API_KEY,
        settings.LLM_TIMEOUT_SECONDS,
    )
    return _extract_content(body)


def chat_stream(
    messages: list[dict],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.3,
):
    """流式调用 LLM，逐块产出正文增量（SSE 用）。

    与 :func:`chat` 共用配置；上层负责把增量推送给前端并组装完整答案。
    """
    if not settings.LLM_API_KEY or not settings.LLM_BASE_URL:
        raise BizError(Code.LLM_UNAVAILABLE, "未配置 LLM 服务（LLM_BASE_URL / LLM_API_KEY）")

    request = urllib.request.Request(
        f"{settings.LLM_BASE_URL.rstrip('/')}/v1/chat/completions",
        data=json.dumps(
            {
                "model": settings.LLM_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
        ).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {settings.LLM_API_KEY}")

    try:
        with _OPENER.open(request, timeout=settings.LLM_TIMEOUT_SECONDS) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise BizError(Code.LLM_UNAVAILABLE, f"模型服务返回 {exc.code}：{detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise BizError(Code.LLM_UNAVAILABLE, f"模型流式调用失败：{exc}") from exc


def describe_image(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    """调用视觉模型描述图片内容（决策 D1：图片知识必须语义化后才能被检索）。"""
    if not settings.VLM_API_KEY or not settings.VLM_BASE_URL:
        raise BizError(Code.LLM_UNAVAILABLE, "未配置视觉模型服务（VLM_BASE_URL / VLM_API_KEY）")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    body = _post_json(
        f"{settings.VLM_BASE_URL.rstrip('/')}/chat/completions",
        {
            "model": settings.VLM_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "max_tokens": 512,
            "temperature": 0.2,
        },
        settings.VLM_API_KEY,
        settings.LLM_TIMEOUT_SECONDS,
    )
    return _extract_content(body)

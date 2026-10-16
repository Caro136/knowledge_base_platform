"""图片语义化节点：用视觉模型为图片生成中文描述（T-12，决策 D1）。

为什么必须做这一步：图片类文档若只保留图片引用，文本检索永远命中不到它。
把图片内容转成文本切片后，图片知识才真正「可被检索」。

同时把原图上传到对象存储，供问答答案配图使用。

失败处理策略：
- 普通文档中的图片语义化失败 → 记入 warnings，继续处理其余内容；
- **图片类文档**（整篇就是一张图）语义化失败 → 视为该文档无可用内容，任务判失败。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from app.core.codes import Code
from app.core.exceptions import BizError
from app.models import SOURCE_IMAGE
from app.processor.state import ImportState
from app.services.storage_service import get_storage
from app.utils.llm_client import describe_image
from app.utils.text_utils import append_image_description, extract_images, replace_image_url

logger = logging.getLogger(__name__)

IMAGE_PROMPT = (
    "请用简体中文客观描述这张图片的内容，用于企业知识库检索。"
    "若是设备、产品或界面截图，请说明对象、关键部件与图中文字；"
    "若是图表，请说明图表类型、坐标轴与关键结论；"
    "若包含文字或数值，请如实摘录。"
    "直接输出描述内容，不要以「这张图片」开头。"
)


def _resolve_blob(url: str, blobs: dict[str, bytes]) -> tuple[bytes | None, str]:
    """把 Markdown 中的图片地址映射到解析结果里的图片字节。"""
    if not blobs:
        return None, ""

    for candidate in (url, url.lstrip("./"), url.split("?")[0]):
        if candidate in blobs:
            return blobs[candidate], _guess_mime(candidate)

    # 退化为按文件名匹配（解析服务可能改写相对路径）
    target = Path(url).name
    for key, value in blobs.items():
        if Path(key).name == target:
            return value, _guess_mime(key)

    return None, ""


def _guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "image/png"


def image_summary_node(state: ImportState) -> ImportState:
    content = state.get("md_content") or ""
    blobs = state.get("image_blobs") or {}
    doc_id = state.get("doc_id") or ""
    source_type = state.get("source_type") or ""
    title = Path(state.get("filename") or "").stem or "图片"

    warnings: list[str] = []
    image_urls: dict[str, str] = {}

    images = extract_images(content)

    # 图片类文档：整篇就是图片本身，直接对原图做语义化
    if not images and source_type == SOURCE_IMAGE:
        raw = state.get("file_bytes") or b""
        if not raw:
            raise BizError(Code.PARSE_FAILED, "图片文件内容为空")
        try:
            description = describe_image(raw, _guess_mime(state.get("filename") or ""), IMAGE_PROMPT)
        except BizError as exc:
            raise BizError(Code.PARSE_FAILED, f"图片语义化失败：{exc.message}") from exc

        key = f"documents/{doc_id}/images/{Path(state.get('filename') or 'image').name}"
        try:
            get_storage().put(key, raw, _guess_mime(state.get("filename") or ""))
            image_urls[key] = key
        except BizError as exc:
            warnings.append(f"原图上传失败：{exc.message}")

        body = f"# {title}\n\n> 【图片内容】{description.strip()}\n"
        if content.strip():
            body = f"{body}\n{content.strip()}\n"
        return {"md_content": body, "image_urls": image_urls, "warnings": warnings}

    if not images:
        return {}

    storage = get_storage()

    for _alt, url in images:
        data, mime = _resolve_blob(url, blobs)
        if data is None:
            # 外部链接图片：当前阶段不下载，避免引入不可控出网行为
            warnings.append(f"图片未随解析结果返回，已跳过语义化：{url}")
            continue

        name = Path(url).name
        key = f"documents/{doc_id}/images/{name}"

        try:
            storage.put(key, data, mime)
        except BizError as exc:
            warnings.append(f"图片上传失败（{name}）：{exc.message}")
            continue

        image_urls[url] = key

        try:
            description = describe_image(data, mime, IMAGE_PROMPT)
        except BizError as exc:
            warnings.append(f"图片语义化失败（{name}）：{exc.message}")
            continue

        content = append_image_description(content, url, description)

    # 图片引用指向对象存储 key，前端通过资产接口访问
    for old_url, key in image_urls.items():
        content = replace_image_url(content, old_url, key)

    if warnings:
        logger.warning("图片处理存在 %d 个问题：%s", len(warnings), "；".join(warnings))

    return {"md_content": content, "image_urls": image_urls, "warnings": warnings}

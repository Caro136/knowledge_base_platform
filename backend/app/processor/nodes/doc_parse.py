"""文档解析节点：调用解析服务把非直读格式转为 Markdown（T-12）。"""

from __future__ import annotations

import logging

from app.processor.state import ImportState
from app.utils.mineru_client import MinerUClient

logger = logging.getLogger(__name__)


def doc_parse_node(state: ImportState) -> ImportState:
    """PDF / Word / PPT / Excel / 图片 → Markdown + 图片集合。"""
    filename = state.get("filename") or ""
    data = state.get("file_bytes") or b""
    if not data:
        raise ValueError("缺少待解析的文件内容")

    content, images = MinerUClient().parse(filename, data)
    logger.info("解析节点完成：%s，正文 %d 字符，图片 %d 张", filename, len(content), len(images))
    return {"md_content": content, "image_blobs": images}

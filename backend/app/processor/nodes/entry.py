"""入口节点：按文件类型路由（T-12 决策 D1）。

- ``.md`` / ``.markdown``：直接作为 Markdown 文本
- ``.txt``：按纯文本读取（参考基线不支持 TXT，本项目补齐）
- 其余（pdf/word/ppt/excel/图片）：交给文档解析节点转 Markdown
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.processor.state import ImportState

logger = logging.getLogger(__name__)

#: 本地直读、无需走解析服务的扩展名
DIRECT_EXTS = {".md", ".markdown", ".txt"}

#: 路由分支名
ROUTE_DIRECT = "direct"
ROUTE_PARSE = "parse"


def _decode_text(data: bytes) -> str:
    """尽力解码文本：UTF-8 → GB18030 兜底（国内文档常见编码）。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def entry_node(state: ImportState) -> ImportState:
    """本地可直读的格式在此完成转换，其余交给解析节点。"""
    filename = state.get("filename") or ""
    extension = Path(filename).suffix.lower()
    data = state.get("file_bytes") or b""

    if extension not in DIRECT_EXTS:
        logger.info("文件 %s 需走解析服务", filename)
        return {}

    content = _decode_text(data).replace("\r\n", "\n").replace("\r", "\n")
    logger.info("文件 %s 本地直读完成，%d 字符", filename, len(content))
    return {"md_content": content}


def route_after_entry(state: ImportState) -> str:
    """已获得 Markdown 内容则跳过解析节点。"""
    return ROUTE_DIRECT if (state.get("md_content") or "").strip() else ROUTE_PARSE

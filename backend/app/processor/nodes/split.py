"""切片节点：清洗与分块（T-12，FR-05）。

切片策略（SPEC §5.3 / 参考基线参数）：
1. 表格先线性化，避免切片把表头与数据拆散；
2. 按 Markdown 标题（1-6 级）切分，标题作为天然语义边界；
3. 超长段按段落 → 行 → 标点递归切分，上限 ``CHUNK_MAX_LENGTH``；
4. 相邻且同标题的过短切片贪心合并，下限 ``CHUNK_MIN_LENGTH``。
"""

from __future__ import annotations

import logging

from app.core.codes import Code
from app.core.config import settings
from app.core.exceptions import BizError
from app.processor.state import ImportState
from app.utils.text_utils import build_chunks

logger = logging.getLogger(__name__)


def split_node(state: ImportState) -> ImportState:
    content = (state.get("md_content") or "").strip()
    if not content:
        # 解析成功但没有文本（例如纯扫描件且 OCR 无结果），视为不可用内容
        raise BizError(Code.PARSE_FAILED, "文档未解析出可用文本内容")

    chunks = build_chunks(
        content,
        max_length=settings.CHUNK_MAX_LENGTH,
        min_length=settings.CHUNK_MIN_LENGTH,
    )
    if not chunks:
        raise BizError(Code.PARSE_FAILED, "切片结果为空")

    logger.info("切片完成：%d 个切片，正文 %d 字符", len(chunks), len(content))
    return {"chunks": chunks, "chunk_count": len(chunks)}

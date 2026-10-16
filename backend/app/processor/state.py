"""导入流程的状态定义。

LangGraph 的节点之间通过该状态字典传递数据；``total=False`` 表示
各字段按需出现，节点只返回自己修改的键。
"""

from __future__ import annotations

from typing import Any, TypedDict


class ImportState(TypedDict, total=False):
    """导入流程状态。"""

    # ---------- 输入（由调度器注入） ----------
    doc_id: str
    """知识单元权限锚点，会冗余写入每个切片。"""
    task_id: str
    filename: str
    source_type: str
    file_bytes: bytes
    """原始文件字节（从对象存储读入）。"""

    # ---------- 中间产物 ----------
    md_content: str
    """解析/直读得到的 Markdown 文本。"""
    image_blobs: dict[str, bytes]
    """解析结果中的图片：相对路径 → 图片字节。"""
    image_urls: dict[str, str]
    """原图地址 → 对象存储 key（供答案配图使用）。"""

    chunks: list[dict[str, Any]]
    """切片列表：[{content, title, parent_title}]。"""

    # ---------- 输出 ----------
    chunk_count: int
    warnings: list[str]
    """非致命问题（例如某张图片语义化失败），失败原因会展示在任务详情中。"""

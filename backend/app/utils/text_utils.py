"""Markdown 文本处理工具（T-12）。

提供三类能力：
1. 表格线性化：把 Markdown 表格转成「列名: 值」的连续文本，避免切片把一个表格
   拆散后语义丢失；
2. 按标题切片：以 Markdown 标题为天然语义边界切分，超长段再按标点/换行递归切分，
   相邻过短段合并；
3. 图片引用提取与替换：供图片语义化节点使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Markdown 标题：# 到 ######
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
# 图片引用：![alt](url) 或 ![alt](url "title")
_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
# 代码围栏开始/结束
_FENCE_RE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
# 表格分隔行：| --- | :---: |
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


@dataclass
class Section:
    """按标题切分出的一个语义段。"""

    title: str = ""
    parent_titles: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def title_path(self) -> str:
        """完整标题路径，如「差旅报销标准 > 住宿标准」。"""
        parts = [*self.parent_titles, self.title] if self.title else list(self.parent_titles)
        return " > ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# 表格线性化
# ---------------------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def linearize_tables(content: str) -> str:
    """把 Markdown 表格转成逐行的「列名: 值」文本。

    表格被切片拆散后极易失去含义（表头与数据分离），因此统一线性化后再切片。
    """
    lines = content.splitlines()
    output: list[str] = []
    index = 0
    in_fence = False

    while index < len(lines):
        line = lines[index]

        # 代码块内的竖线不是表格，原样保留
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            output.append(line)
            index += 1
            continue

        is_table_start = (
            not in_fence
            and "|" in line
            and index + 1 < len(lines)
            and "|" in lines[index + 1]
            and _TABLE_SEP_RE.match(lines[index + 1].replace("-", "-"))
            and set(lines[index + 1].strip()) <= set("|-: ")
        )

        if not is_table_start:
            output.append(line)
            index += 1
            continue

        headers = _split_row(line)
        index += 2  # 跳过表头与分隔行

        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            cells = _split_row(lines[index])
            pairs = [
                f"{headers[col] if col < len(headers) else f'列{col + 1}'}: {value}"
                for col, value in enumerate(cells)
                if value
            ]
            if pairs:
                output.append("；".join(pairs))
            index += 1

    return "\n".join(output)


# ---------------------------------------------------------------------------
# 图片引用
# ---------------------------------------------------------------------------


def extract_images(content: str) -> list[tuple[str, str]]:
    """提取 (alt 文本, 图片地址) 列表，按出现顺序去重。"""
    seen: set[str] = set()
    images: list[tuple[str, str]] = []
    for match in _IMAGE_RE.finditer(content):
        url = match.group("url")
        if url in seen:
            continue
        seen.add(url)
        images.append((match.group("alt") or "", url))
    return images


def append_image_description(content: str, url: str, description: str) -> str:
    """在图片引用后追加一行图片语义描述，使图片内容可被文本检索命中。"""
    if not description:
        return content

    def _replacer(match: re.Match[str]) -> str:
        if match.group("url") != url:
            return match.group(0)
        return f"{match.group(0)}\n\n> 【图片内容】{description.strip()}"

    return _IMAGE_RE.sub(_replacer, content, count=0)


def replace_image_url(content: str, old_url: str, new_url: str) -> str:
    """替换图片地址（例如把解析结果的本地相对路径换成对象存储地址）。"""

    def _replacer(match: re.Match[str]) -> str:
        if match.group("url") != old_url:
            return match.group(0)
        return match.group(0).replace(old_url, new_url)

    return _IMAGE_RE.sub(_replacer, content, count=0)


def strip_images(content: str) -> str:
    """移除图片引用（用于图片无法语义化时避免留下无效引用）。"""
    return _IMAGE_RE.sub("", content)


# ---------------------------------------------------------------------------
# 切片
# ---------------------------------------------------------------------------


def split_by_headings(content: str) -> list[Section]:
    """按 1-6 级标题切分为语义段（忽略代码块内的 # 行）。"""
    lines = content.splitlines()
    sections: list[Section] = []
    current = Section()
    heading_stack: list[str] = []
    in_fence = False
    buffer: list[str] = []

    def flush() -> None:
        if current.title or any(line.strip() for line in buffer):
            sections.append(
                Section(title=current.title, parent_titles=list(current.parent_titles), body="\n".join(buffer).strip())
            )

    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            current = Section(title=title, parent_titles=list(heading_stack[: level - 1]))
            heading_stack.append(title)
            buffer = []
            continue

        buffer.append(line)

    flush()
    return sections


def _recursive_split(text: str, max_length: int) -> list[str]:
    """超长文本递归切分：段落 → 行 → 句号 → 硬切。"""
    if len(text) <= max_length:
        return [text] if text.strip() else []

    for separator in ("\n\n", "\n", "。", "；", "，", " "):
        if separator not in text:
            continue
        pieces = text.split(separator)
        merged: list[str] = []
        buffer = ""
        for piece in pieces:
            candidate = f"{buffer}{separator}{piece}" if buffer else piece
            if len(candidate) <= max_length:
                buffer = candidate
                continue
            if buffer:
                merged.append(buffer)
            # 单个片段仍超长 → 继续用更细的分隔符切
            if len(piece) > max_length:
                merged.extend(_recursive_split(piece, max_length))
                buffer = ""
            else:
                buffer = piece
        if buffer:
            merged.append(buffer)
        return [item for item in merged if item.strip()]

    # 无可用分隔符：硬切
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


def build_chunks(
    content: str,
    max_length: int = 500,
    min_length: int = 200,
) -> list[dict]:
    """按标题切片并做长度治理，返回 [{content, title, parent_title}]。"""
    sections = split_by_headings(linearize_tables(content))
    chunks: list[dict] = []

    for section in sections:
        title_path = section.title_path
        body = section.body.strip()

        if not body and not title_path:
            continue

        pieces = _recursive_split(body, max_length) if body else [""]
        for piece in pieces:
            text = f"{title_path}\n\n{piece}".strip() if title_path else piece.strip()
            if text:
                chunks.append(
                    {
                        "content": text,
                        "title": section.title,
                        "parent_title": " > ".join(section.parent_titles),
                    }
                )

    return _merge_short_chunks(chunks, min_length=min_length)


def _merge_short_chunks(chunks: list[dict], min_length: int) -> list[dict]:
    """贪心合并相邻的过短切片，避免产生大量无上下文的碎片。"""
    merged: list[dict] = []
    for chunk in chunks:
        if (
            merged
            and len(chunk["content"]) < min_length
            and len(merged[-1]["content"]) + len(chunk["content"]) <= min_length * 3
            and merged[-1]["title"] == chunk["title"]
        ):
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{chunk['content']}"
            continue
        merged.append(dict(chunk))
    return merged

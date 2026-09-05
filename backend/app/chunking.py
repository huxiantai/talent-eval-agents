from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChunkStrategy(StrEnum):
    RECURSIVE = "recursive"
    MARKDOWN = "markdown"


@dataclass(slots=True)
class ChunkElement:
    id: str
    text: str
    page: int | None = None
    kind: str = "text"
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    speaker: str | None = None
    markdown_start: int | None = None
    markdown_end: int | None = None
    source_locator: dict = field(default_factory=dict)


@dataclass(slots=True)
class ChunkPiece:
    content: str
    element_ids: list[str]
    heading_path: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    markdown_start: int | None = None
    markdown_end: int | None = None
    source_locators: list[dict] = field(default_factory=list)


def _piece(elements: list[ChunkElement], heading_path: list[str] | None = None) -> ChunkPiece:
    pages = [item.page for item in elements if item.page is not None]
    starts = [item.timestamp_start for item in elements if item.timestamp_start is not None]
    ends = [item.timestamp_end for item in elements if item.timestamp_end is not None]
    markdown_starts = [item.markdown_start for item in elements if item.markdown_start is not None]
    markdown_ends = [item.markdown_end for item in elements if item.markdown_end is not None]
    return ChunkPiece(
        content="\n\n".join(item.text for item in elements).strip(),
        element_ids=[item.id for item in elements],
        heading_path=list(heading_path or []),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        timestamp_start=min(starts) if starts else None,
        timestamp_end=max(ends) if ends else None,
        markdown_start=min(markdown_starts) if markdown_starts else None,
        markdown_end=max(markdown_ends) if markdown_ends else None,
        source_locators=[item.source_locator for item in elements if item.source_locator],
    )


def _split_long_element(
    element: ChunkElement,
    splitter: RecursiveCharacterTextSplitter,
    heading_path: list[str] | None = None,
) -> list[ChunkPiece]:
    texts = splitter.split_text(element.text)
    if not texts:
        return []
    result: list[ChunkPiece] = []
    previous_end = 0
    overlap = int(getattr(splitter, "_chunk_overlap", 0))
    for text in texts:
        search_start = max(0, previous_end - overlap)
        local_start = element.text.find(text, search_start)
        if local_start < 0:
            local_start = search_start
        previous_end = local_start + len(text)
        result.append(
            ChunkPiece(
                content=text,
                element_ids=[element.id],
                heading_path=list(heading_path or []),
                page_start=element.page,
                page_end=element.page,
                timestamp_start=element.timestamp_start,
                timestamp_end=element.timestamp_end,
                markdown_start=(element.markdown_start + local_start) if element.markdown_start is not None else None,
                markdown_end=(element.markdown_start + previous_end) if element.markdown_start is not None else None,
                source_locators=[element.source_locator] if element.source_locator else [],
            )
        )
    return result


def _pack_elements(
    elements: Iterable[ChunkElement],
    splitter: RecursiveCharacterTextSplitter,
    chunk_size: int,
    heading_path: list[str] | None = None,
) -> list[ChunkPiece]:
    result: list[ChunkPiece] = []
    pending: list[ChunkElement] = []
    pending_length = 0
    for element in elements:
        text_length = len(element.text)
        separator_length = 2 if pending else 0
        if pending and pending_length + separator_length + text_length > chunk_size:
            result.append(_piece(pending, heading_path))
            pending = []
            pending_length = 0
        if text_length > chunk_size:
            result.extend(_split_long_element(element, splitter, heading_path))
            continue
        pending.append(element)
        pending_length += separator_length + text_length
    if pending:
        result.append(_piece(pending, heading_path))
    return result


def _markdown_chunks(
    elements: list[ChunkElement],
    splitter: RecursiveCharacterTextSplitter,
    chunk_size: int,
) -> list[ChunkPiece]:
    result: list[ChunkPiece] = []
    heading_path: list[str] = []
    section: list[ChunkElement] = []

    def flush() -> None:
        nonlocal section
        result.extend(_pack_elements(section, splitter, chunk_size, heading_path))
        section = []

    for element in elements:
        match = re.match(r"^(#{1,6})\s+(.+)$", element.text.strip())
        if element.kind == "heading" or match:
            flush()
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
            else:
                level = 1
                title = element.text.lstrip("# ").strip()
            heading_path = heading_path[: level - 1] + [title]
            continue
        section.append(element)
    flush()
    return result


def chunk_elements(
    elements: list[ChunkElement],
    *,
    strategy: ChunkStrategy,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[ChunkPiece]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")
    separators = ["\n\n", "\n", "。", "！", "？", ";", "；", "，", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        keep_separator=True,
    )
    if strategy == ChunkStrategy.MARKDOWN:
        return _markdown_chunks(elements, splitter, chunk_size)
    return _pack_elements(elements, splitter, chunk_size)

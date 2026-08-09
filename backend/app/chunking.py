from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable

from langchain_core.embeddings import Embeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChunkStrategy(StrEnum):
    FIXED = "fixed"
    RECURSIVE = "recursive"
    MARKDOWN = "markdown"
    SEMANTIC = "semantic"
    INTERVIEW_QA = "interview_qa"


@dataclass(slots=True)
class ChunkElement:
    id: str
    text: str
    page: int | None = None
    kind: str = "text"
    timestamp_start: float | None = None
    timestamp_end: float | None = None
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
    source_locators: list[dict] = field(default_factory=list)


def _piece(elements: list[ChunkElement], heading_path: list[str] | None = None) -> ChunkPiece:
    pages = [item.page for item in elements if item.page is not None]
    starts = [item.timestamp_start for item in elements if item.timestamp_start is not None]
    ends = [item.timestamp_end for item in elements if item.timestamp_end is not None]
    return ChunkPiece(
        content="\n\n".join(item.text for item in elements).strip(),
        element_ids=[item.id for item in elements],
        heading_path=list(heading_path or []),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        timestamp_start=min(starts) if starts else None,
        timestamp_end=max(ends) if ends else None,
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
        locator = dict(element.source_locator)
        if locator.get("kind") == "char_range":
            search_start = max(0, previous_end - overlap)
            local_start = element.text.find(text, search_start)
            if local_start < 0:
                local_start = search_start
            previous_end = local_start + len(text)
            base_start = int(element.source_locator["char_start"])
            locator["char_start"] = base_start + local_start
            locator["char_end"] = base_start + previous_end
        result.append(
            ChunkPiece(
                content=text,
                element_ids=[element.id],
                heading_path=list(heading_path or []),
                page_start=element.page,
                page_end=element.page,
                timestamp_start=element.timestamp_start,
                timestamp_end=element.timestamp_end,
                source_locators=[locator] if locator else [],
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


def _interview_chunks(
    elements: list[ChunkElement],
    splitter: RecursiveCharacterTextSplitter,
    chunk_size: int,
) -> list[ChunkPiece]:
    groups: list[list[ChunkElement]] = []
    current: list[ChunkElement] = []
    for element in elements:
        is_question = element.text.lstrip().startswith(("面试官", "访谈人", "评委")) # 当前实现，实际需要根据语音识别出的发言人名称
        if is_question and current:
            groups.append(current)
            current = []
        current.append(element)
    if current:
        groups.append(current)
    result: list[ChunkPiece] = []
    for index, group in enumerate(groups, start=1):
        result.extend(_pack_elements(group, splitter, chunk_size, ["面试问答", f"问答 {index}"]))
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
    if strategy == ChunkStrategy.FIXED:
        separators = [""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        keep_separator=True,
    )
    if strategy == ChunkStrategy.INTERVIEW_QA:
        return _interview_chunks(elements, splitter, chunk_size)
    if strategy == ChunkStrategy.MARKDOWN:
        return _markdown_chunks(elements, splitter, chunk_size)
    if strategy == ChunkStrategy.SEMANTIC:
        raise ValueError("语义分片需要通过 semantic_chunk_text 调用 Embedding 模型")
    return _pack_elements(elements, splitter, chunk_size)


def semantic_chunk_text(
    text: str,
    *,
    embeddings: Embeddings,
    breakpoint_threshold_type: str = "percentile",
    breakpoint_threshold_amount: float | None = 90,
    buffer_size: int = 1,
    sentence_split_regex: str = r"(?<=[。！？.!?])\s*",
) -> list[ChunkPiece]:
    splitter = SemanticChunker(
        embeddings,
        buffer_size=buffer_size,
        breakpoint_threshold_type=breakpoint_threshold_type,
        breakpoint_threshold_amount=breakpoint_threshold_amount,
        sentence_split_regex=sentence_split_regex,
    )
    documents = splitter.create_documents([text])
    return [ChunkPiece(content=document.page_content, element_ids=[]) for document in documents]

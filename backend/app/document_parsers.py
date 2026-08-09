import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_community.document_loaders import BSHTMLLoader, CSVLoader, JSONLoader
from pptx import Presentation

from app.parsers import parse_xlsx

_whisper_model = None


@dataclass(slots=True)
class ParseResult:
    parser_name: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    structured: dict[str, Any] | None = None


def join_documents(documents) -> str:
    return "\n\n".join(document.page_content for document in documents if document.page_content.strip())


def markdown_content_list(markdown: str) -> list[dict[str, Any]]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]
    cursor = 0
    result = []
    for block in blocks:
        start = markdown.find(block, cursor)
        end = start + len(block)
        cursor = end
        result.append(
            {
                "type": "title" if re.match(r"^#{1,6}\s+", block) else "text",
                "text": re.sub(r"^#{1,6}\s+", "", block),
                "locator": {"kind": "char_range", "char_start": start, "char_end": end},
            }
        )
    return result


def parse_docx_markdown(path: Path) -> ParseResult:
    document = WordDocument(path)
    markdown_blocks: list[str] = []
    content_list: list[dict[str, Any]] = []
    paragraph_number = 0
    table_number = 0
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            table_number += 1
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in block.rows]
            table_text = "\n".join(row for row in rows if row.strip(" |"))
            if table_text:
                markdown_blocks.append(table_text)
                content_list.append(
                    {
                        "type": "table",
                        "text": table_text,
                        "locator": {"kind": "word_table", "table": table_number},
                    }
                )
            continue
        if not isinstance(block, Paragraph):
            continue
        paragraph_number += 1
        paragraph = block
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style else "Normal"
        if style_name == "Title":
            markdown_text = f"# {text}"
            item_type = "title"
        else:
            match = re.match(r"Heading\s+(\d+)", style_name, flags=re.IGNORECASE)
            if match:
                markdown_text = f"{'#' * min(int(match.group(1)) + 1, 6)} {text}"
                item_type = "title"
            else:
                markdown_text = text
                item_type = "text"
        markdown_blocks.append(markdown_text)
        content_list.append(
            {
                "type": item_type,
                "text": text,
                "locator": {"kind": "word_paragraph", "paragraph": paragraph_number},
            }
        )
    return ParseResult(
        "python_docx_markdown",
        "\n\n".join(markdown_blocks),
        {"paragraph_count": len(document.paragraphs)},
        {"content_list": content_list},
    )


def transcript_segments_to_markdown(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    blocks = ["# 语音转录", "## 说话人 1"]
    content_list: list[dict[str, Any]] = [
        {"type": "title", "text": "语音转录", "locator": {"kind": "document"}},
        {"type": "title", "text": "说话人 1", "locator": {"kind": "speaker", "speaker": "说话人 1"}},
    ]
    for index, row in enumerate(rows, start=1):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        blocks.append(text)
        content_list.append(
            {
                "type": "text",
                "text": text,
                "locator": {
                    "kind": "time_range",
                    "segment": index,
                    "timestamp_start": float(row["start"]),
                    "timestamp_end": float(row["end"]),
                },
            }
        )
    return "\n\n".join(blocks), {"segments": rows, "content_list": content_list}


def parse_document(path: Path) -> ParseResult:
    global _whisper_model
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx_markdown(path)
    if suffix == ".csv":
        return ParseResult("langchain_csv", join_documents(CSVLoader(str(path), encoding="utf-8-sig").load()))
    if suffix == ".json":
        loader = JSONLoader(str(path), jq_schema=".", text_content=False)
        loaded = loader.load()
        normalized = []
        for document in loaded:
            value = json.loads(document.page_content)
            normalized.append(json.dumps(value, ensure_ascii=False, indent=2))
        return ParseResult("langchain_json", "\n\n".join(normalized))
    if suffix in {".html", ".htm"}:
        return ParseResult("langchain_bshtml", join_documents(BSHTMLLoader(str(path), open_encoding="utf-8").load()))
    if suffix in {".md", ".markdown"}:
        markdown = path.read_text(encoding="utf-8")
        return ParseResult("markdown_text", markdown, structured={"content_list": markdown_content_list(markdown)})
    if suffix == ".pptx":
        presentation = Presentation(str(path))
        blocks: list[str] = []
        content_list: list[dict[str, Any]] = []
        for number, slide in enumerate(presentation.slides, start=1):
            blocks.append(f"## Slide {number}")
            content_list.append({"type": "title", "text": f"Slide {number}", "locator": {"kind": "slide", "slide": number}})
            for shape_index, shape in enumerate(slide.shapes, start=1):
                text = shape.text.strip() if hasattr(shape, "text") else ""
                if not text:
                    continue
                is_title = shape == slide.shapes.title
                blocks.append(f"### {text}" if is_title else text)
                content_list.append(
                    {
                        "type": "title" if is_title else "text",
                        "text": text,
                        "locator": {
                            "kind": "slide_region",
                            "slide": number,
                            "shape": shape_index,
                            "bbox": [int(shape.left), int(shape.top), int(shape.left + shape.width), int(shape.top + shape.height)],
                            "coordinate_space": "pptx_emu",
                        },
                    }
                )
        return ParseResult("pptx_ooxml", "\n\n".join(blocks), {"slide_count": len(presentation.slides)}, {"content_list": content_list})
    if suffix == ".xlsx":
        structured = parse_xlsx(path.read_bytes())
        text_parts = []
        for sheet in structured["sheets"]:
            text_parts.append(f"## {sheet['name']}")
            text_parts.extend(" | ".join("" if value is None else str(value) for value in row) for row in sheet["rows"])
        return ParseResult("openpyxl", "\n".join(text_parts), {"sheet_count": len(structured["sheets"])}, structured)
    if suffix == ".pdf":
        raise ValueError("PDF 统一交给 MinerU 保留标题层级、页码与 bbox")
    if suffix in {".png", ".jpg", ".jpeg"}:
        raise ValueError("图片统一交给 MinerU 保留版面坐标与中文 OCR 结果")
    if suffix in {".wav", ".mp3", ".m4a"}:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = _whisper_model.transcribe(str(path), language="zh", vad_filter=True)
        rows = [{"start": round(item.start, 2), "end": round(item.end, 2), "text": item.text.strip()} for item in segments]
        text, structured = transcript_segments_to_markdown(rows)
        return ParseResult("faster_whisper_tiny", text, {"language": info.language, "duration": info.duration}, structured)
    raise ValueError(f"尚未注册解析器: {suffix}")

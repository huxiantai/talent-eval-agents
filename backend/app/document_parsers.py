import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import BSHTMLLoader, CSVLoader, Docx2txtLoader, JSONLoader
from pptx import Presentation
from pypdf import PdfReader

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


def parse_document(path: Path) -> ParseResult:
    global _whisper_model
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return ParseResult("langchain_docx2txt", join_documents(Docx2txtLoader(str(path)).load()))
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
        return ParseResult("markdown_text", path.read_text(encoding="utf-8"))
    if suffix == ".pptx":
        presentation = Presentation(str(path))
        slides = []
        for number, slide in enumerate(presentation.slides, start=1):
            texts = [shape.text.strip() for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
            slides.append(f"## Slide {number}\n" + "\n".join(texts))
        return ParseResult("pptx_ooxml", "\n\n".join(slides), {"slide_count": len(presentation.slides)})
    if suffix == ".xlsx":
        structured = parse_xlsx(path.read_bytes())
        text_parts = []
        for sheet in structured["sheets"]:
            text_parts.append(f"## {sheet['name']}")
            text_parts.extend(" | ".join("" if value is None else str(value) for value in row) for row in sheet["rows"])
        return ParseResult("openpyxl", "\n".join(text_parts), {"sheet_count": len(structured["sheets"])}, structured)
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise ValueError("PDF 没有可提取文本，需要 MinerU OCR")
        return ParseResult("pypdf", text, {"page_count": len(reader.pages)})
    if suffix in {".png", ".jpg", ".jpeg"}:
        raise ValueError("图片统一交给 MinerU 保留版面坐标与中文 OCR 结果")
    if suffix in {".wav", ".mp3", ".m4a"}:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = _whisper_model.transcribe(str(path), language="zh", vad_filter=True)
        rows = [{"start": round(item.start, 2), "end": round(item.end, 2), "text": item.text.strip()} for item in segments]
        text = "\n".join(f"[{item['start']:06.2f}-{item['end']:06.2f}] {item['text']}" for item in rows)
        return ParseResult("faster_whisper_tiny", text, {"language": info.language, "duration": info.duration}, {"segments": rows})
    raise ValueError(f"尚未注册解析器: {suffix}")

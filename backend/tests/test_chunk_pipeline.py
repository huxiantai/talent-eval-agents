import re
from pathlib import Path

import pytest

from app.chunk_service import elements_from_artifacts, parent_paths_for_heading
from app.chunking import ChunkStrategy, chunk_elements
from app.document_parsers import parse_document, transcript_segments_to_markdown
from app.mineru_client import parse_with_mineru


SAMPLES = Path(__file__).resolve().parents[2] / "sample-data" / "generated"
MARKDOWN_SAMPLES = sorted((SAMPLES / "markdown").glob("*.md"))[:2]
PDF_SAMPLES = sorted((SAMPLES / "pdf").glob("*.pdf"))[:2]


def content_list_for(markdown: str) -> list[dict]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]
    return [
        {
            "type": "title" if re.match(r"^#{1,6}\s+", block) else "text",
            "text": re.sub(r"^#{1,6}\s+", "", block),
            "page_idx": index // 4,
        }
        for index, block in enumerate(blocks)
    ]


@pytest.mark.parametrize("path", MARKDOWN_SAMPLES)
def test_native_markdown_parse_to_hierarchical_chunks(path: Path):
    parsed = parse_document(path)
    elements = elements_from_artifacts(parsed.text, parsed.structured or {})
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=400, chunk_overlap=40)

    assert parsed.parser_name == "markdown_text"
    assert len(parsed.text) > 700
    assert len(chunks) >= 4
    assert all(chunk.heading_path for chunk in chunks)
    assert all(parent_paths_for_heading(chunk.heading_path) for chunk in chunks)
    assert all(not element.id.startswith("pNone") for element in elements)


@pytest.mark.parametrize("pdf_path,markdown_path", list(zip(PDF_SAMPLES, MARKDOWN_SAMPLES)))
def test_simulated_mineru_pdf_parse_to_hierarchical_chunks(monkeypatch, pdf_path: Path, markdown_path: Path):
    markdown = markdown_path.read_text(encoding="utf-8")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "completed",
                "task_id": "test-mineru-task",
                "backend": "pipeline",
                "version": "3.4.4",
                "results": {
                    pdf_path.stem: {
                        "md_content": markdown,
                        "content_list": content_list_for(markdown),
                    }
                },
            }

    monkeypatch.setattr("app.mineru_client.httpx.post", lambda *args, **kwargs: Response())

    parsed = parse_with_mineru(pdf_path)
    elements = elements_from_artifacts(parsed.text, parsed.structured or {})
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=400, chunk_overlap=40)

    assert parsed.parser_name == "mineru_pipeline_3.4.4"
    assert len(chunks) >= 4
    assert all(chunk.page_start is not None for chunk in chunks)
    assert all(chunk.heading_path for chunk in chunks)


@pytest.mark.parametrize("pattern", ["docx/*.docx", "pptx/*.pptx"])
def test_office_parse_to_markdown_and_located_chunks(pattern: str):
    parsed = parse_document(sorted(SAMPLES.glob(pattern))[0])
    elements = elements_from_artifacts(parsed.text, parsed.structured or {})
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=400, chunk_overlap=40)

    assert parsed.text.startswith("#")
    assert any(chunk.heading_path for chunk in chunks)
    assert any(chunk.source_locators for chunk in chunks)


def test_simulated_long_transcript_to_speaker_parent_and_time_located_chunks():
    rows = [
        {"start": 0.0, "end": 42.0, "text": "候选人连续讲述项目背景和个人职责。" * 20},
        {"start": 42.0, "end": 90.0, "text": "候选人继续说明项目结果和复盘。" * 20},
    ]
    markdown, structured = transcript_segments_to_markdown(rows)
    elements = elements_from_artifacts(markdown, structured)
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=200, chunk_overlap=20)

    assert markdown.startswith("# 语音转录\n\n## 说话人 1")
    assert len(chunks) > 2
    assert all(chunk.heading_path == ["语音转录", "说话人 1"] for chunk in chunks)
    assert any(locator["kind"] == "time_range" for chunk in chunks for locator in chunk.source_locators)

import re
from pathlib import Path

import pytest

from app.chunk_service import elements_from_artifacts, parent_paths_for_heading
from app.chunking import ChunkStrategy, chunk_elements
from app.document_parsers import parse_document
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

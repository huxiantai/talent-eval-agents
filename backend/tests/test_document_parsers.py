from pathlib import Path

from app.document_parsers import parse_document


SAMPLES = Path(__file__).resolve().parents[2] / "sample-data" / "generated"


def first(pattern: str) -> Path:
    return sorted(SAMPLES.glob(pattern))[0]


def test_langchain_docx_loader_extracts_candidate_record():
    result = parse_document(first("docx/*.docx"))
    assert result.parser_name == "langchain_docx2txt"
    assert "候选人编号" in result.text
    assert "C001" in result.text


def test_langchain_csv_loader_extracts_hris_fields():
    result = parse_document(first("csv/*.csv"))
    assert result.parser_name == "langchain_csv"
    assert "candidate_id" in result.text
    assert "C001" in result.text


def test_langchain_json_loader_extracts_nested_profile():
    result = parse_document(first("json/*.json"))
    assert result.parser_name == "langchain_json"
    assert "AI 应用架构师" in result.text


def test_langchain_html_loader_removes_markup():
    result = parse_document(first("html/*.html"))
    assert result.parser_name == "langchain_bshtml"
    assert "内部岗位申请记录" in result.text
    assert "<main>" not in result.text


def test_markdown_parser_preserves_headings_and_content():
    result = parse_document(first("markdown/*.md"))
    assert result.parser_name == "markdown_text"
    assert "项目复盘" in result.text


def test_pptx_parser_extracts_slide_text():
    result = parse_document(first("pptx/*.pptx"))
    assert result.parser_name == "pptx_ooxml"
    assert "人才述职与岗位申请" in result.text
    assert result.metadata["slide_count"] == 4


def test_xlsx_parser_returns_structured_sheets():
    result = parse_document(first("xlsx/*.xlsx"))
    assert result.parser_name == "openpyxl"
    assert result.structured["kind"] == "workbook"
    assert len(result.structured["sheets"]) == 2

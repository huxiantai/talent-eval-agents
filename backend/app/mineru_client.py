import json
from pathlib import Path

import httpx

from app.config import get_settings
from app.document_parsers import ParseResult


def parse_with_mineru(path: Path) -> ParseResult:
    with path.open("rb") as handle:
        response = httpx.post(
            f"{get_settings().mineru_url}/file_parse",
            files={"files": (path.name, handle, "application/octet-stream")},
            data={"backend": "pipeline", "return_md": "true", "return_content_list": "true", "response_format_zip": "false"},
            timeout=900,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "completed" or not payload.get("results"):
        raise RuntimeError(payload.get("error") or "MinerU 未返回解析结果")
    name, result = next(iter(payload["results"].items()))
    content_list = result.get("content_list", "[]")
    structured = json.loads(content_list) if isinstance(content_list, str) else content_list
    return ParseResult(
        "mineru_pipeline_3.4.4",
        result.get("md_content", ""),
        {"task_id": payload.get("task_id"), "source_name": name, "backend": payload.get("backend"), "version": payload.get("version")},
        {"content_list": structured},
    )

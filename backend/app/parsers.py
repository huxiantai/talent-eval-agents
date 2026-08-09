import csv
import json
from io import BytesIO, StringIO
from typing import Any

from openpyxl import load_workbook


def parse_csv(content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return {
        "kind": "table",
        "columns": reader.fieldnames or [],
        "rows": list(reader),
    }


def parse_json(content: bytes) -> dict[str, Any]:
    return {"kind": "json", "data": json.loads(content.decode("utf-8-sig"))}


def parse_xlsx(content: bytes) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(content), data_only=False, read_only=True)
    sheets = [
        {"name": sheet.title, "rows": [list(row) for row in sheet.iter_rows(values_only=True)]}
        for sheet in workbook.worksheets
    ]
    return {"kind": "workbook", "sheets": sheets}

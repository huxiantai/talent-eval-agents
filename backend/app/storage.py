import re
from pathlib import PurePath


def build_object_key(tenant_id: str, document_id: str, version_no: int, filename: str) -> str:
    safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", PurePath(filename).name)
    return f"tenants/{tenant_id}/documents/{document_id}/versions/{version_no}/{safe_name}"

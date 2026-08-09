import hashlib
import json
import mimetypes
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.document_parsers import parse_document
from app.models import Document, DocumentVersion, EmployeeProfile, FileObject, ParseArtifact, ParseJob, ParseStatus
from app.mineru_client import parse_with_mineru
from app.object_store import ObjectStore
from app.router import choose_parser
from app.storage import build_object_key


def upload_document(db: Session, store: ObjectStore, *, filename: str, content: bytes, candidate_id: str, title: str, document_type: str, employee_id: UUID | None = None, knowledge_base_id: UUID | None = None, permission_scope: str = "hr_private", tenant_id: str = "course-demo") -> Document:
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    digest = hashlib.sha256(content).hexdigest()
    employee = db.get(EmployeeProfile, employee_id) if employee_id else None
    employee_no = employee.employee_no if employee else candidate_id
    document = Document(candidate_id=employee_no, employee_id=employee_id, knowledge_base_id=knowledge_base_id, tenant_id=tenant_id, title=title, document_type=document_type, permission_scope=permission_scope)
    db.add(document)
    db.flush()
    document.material_no = f"MAT-{str(document.id).split('-')[0].upper()}"
    key = build_object_key(tenant_id, str(document.id), 1, filename)
    store.put_bytes(key, content, mime)
    file_object = FileObject(bucket_name=store.settings.s3_bucket, object_key=key, original_name=filename, mime_type=mime, size_bytes=len(content), sha256=digest)
    db.add(file_object)
    db.flush()
    version = DocumentVersion(document_id=document.id, file_object_id=file_object.id, version_no=1, is_current=True)
    db.add(version)
    db.commit()
    db.refresh(document)
    return document


def parse_version(db: Session, store: ObjectStore, version_id: UUID, job_id: UUID | None = None) -> ParseJob:
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise ValueError("文档版本不存在")
    file_object = db.get(FileObject, version.file_object_id)
    parser_kind = choose_parser(file_object.original_name)
    job = db.get(ParseJob, job_id) if job_id else None
    if job is None:
        job = ParseJob(document_version_id=version.id, parser_name=parser_kind.value)
        db.add(job)
    job.parser_name = parser_kind.value
    job.status = ParseStatus.RUNNING
    job.progress = 10
    job.started_at = datetime.now(UTC)
    db.commit()
    try:
        content = store.get_bytes(file_object.object_key)
        suffix = Path(file_object.original_name).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp:
            temp.write(content)
            temp.flush()
            try:
                result = parse_document(Path(temp.name))
            except Exception:
                if suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                    raise
                result = parse_with_mineru(Path(temp.name))
        markdown = result.text.encode("utf-8")
        structured = json.dumps(result.structured or result.metadata, ensure_ascii=False, indent=2).encode("utf-8")
        base = f"artifacts/{job.id}"
        for artifact_type, key, body, content_type in [
            ("markdown", f"{base}/content.md", markdown, "text/markdown; charset=utf-8"),
            ("structured_json", f"{base}/structured.json", structured, "application/json"),
        ]:
            store.put_bytes(key, body, content_type)
            db.add(ParseArtifact(parse_job_id=job.id, artifact_type=artifact_type, bucket_name=store.settings.s3_bucket, object_key=key, content_type=content_type, size_bytes=len(body)))
        job.parser_name = result.parser_name
        job.status = ParseStatus.SUCCEEDED
        job.progress = 100
    except Exception as exc:
        job.status = ParseStatus.FAILED
        job.error_code = "PARSE_FAILED"
        job.error_message = str(exc)[:2000]
        job.progress = 100
    job.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


def current_version(db: Session, document_id: UUID) -> DocumentVersion | None:
    return db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id, DocumentVersion.is_current.is_(True)))

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Document, DocumentVersion, EmployeeProfile, FileObject, KnowledgeBase, ParseArtifact, ParseJob
from app.object_store import ObjectStore
from app.services import current_version, parse_version, upload_document

router = APIRouter(prefix="/api")


class EmployeeInput(BaseModel):
    employee_no: str
    name: str
    gender: str | None = None
    birth_date: date | None = None
    region: str | None = None
    current_position: str | None = None
    job_level: str | None = Field(default=None, pattern=r"^L\d+$")
    years_of_experience: float | None = None
    department: str | None = None


class KnowledgeBaseInput(BaseModel):
    name: str
    description: str | None = None
    permission_scope: str = "hr_private"


def employee_json(item: EmployeeProfile, material_count: int = 0):
    today = date.today()
    age = None
    if item.birth_date:
        age = today.year - item.birth_date.year - ((today.month, today.day) < (item.birth_date.month, item.birth_date.day))
    return {"id": item.id, "employee_no": item.employee_no, "name": item.name, "gender": item.gender, "birth_date": item.birth_date, "age": age, "region": item.region, "current_position": item.current_position, "job_level": item.job_level, "years_of_experience": item.years_of_experience, "department": item.department, "employment_status": item.employment_status, "material_count": material_count}


@router.get("/employees")
def list_employees(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Document.employee_id, func.count(Document.id)).where(Document.employee_id.is_not(None)).group_by(Document.employee_id)).all())
    return [employee_json(item, counts.get(item.id, 0)) for item in db.scalars(select(EmployeeProfile).order_by(EmployeeProfile.employee_no)).all()]


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeInput, db: Session = Depends(get_db)):
    if db.scalar(select(EmployeeProfile).where(EmployeeProfile.employee_no == payload.employee_no)):
        raise HTTPException(409, "员工工号已存在")
    item = EmployeeProfile(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return employee_json(item)


@router.get("/knowledge-bases")
def list_knowledge_bases(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Document.knowledge_base_id, func.count(Document.id)).where(Document.knowledge_base_id.is_not(None)).group_by(Document.knowledge_base_id)).all())
    items = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)).all()
    return [{"id": item.id, "name": item.name, "description": item.description, "permission_scope": item.permission_scope, "file_count": counts.get(item.id, 0)} for item in items]


@router.post("/knowledge-bases", status_code=201)
def create_knowledge_base(payload: KnowledgeBaseInput, db: Session = Depends(get_db)):
    item = KnowledgeBase(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name, "description": item.description, "permission_scope": item.permission_scope, "file_count": 0}


@router.get("/documents")
def list_documents(knowledge_base_id: UUID | None = None, db: Session = Depends(get_db)):
    query = select(Document).order_by(Document.created_at.desc())
    if knowledge_base_id:
        query = query.where(Document.knowledge_base_id == knowledge_base_id)
    items = db.scalars(query).all()
    return [{"id": item.id, "material_no": item.material_no, "candidate_id": item.candidate_id, "employee_name": item.employee.name if item.employee else item.candidate_id, "knowledge_base_id": item.knowledge_base_id, "title": item.title, "document_type": item.document_type, "status": item.status, "created_at": item.created_at} for item in items]


@router.post("/documents", status_code=201)
async def create_document(file: UploadFile = File(...), employee_id: UUID | None = Form(None), knowledge_base_id: UUID | None = Form(None), candidate_id: str = Form(""), title: str = Form(...), document_type: str = Form(...), permission_scope: str = Form("hr_private"), db: Session = Depends(get_db)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件内容为空")
    if employee_id and not db.get(EmployeeProfile, employee_id):
        raise HTTPException(404, "员工不存在")
    if knowledge_base_id and not db.get(KnowledgeBase, knowledge_base_id):
        raise HTTPException(404, "知识库不存在")
    document = upload_document(db, ObjectStore(), filename=file.filename or "upload.bin", content=content, candidate_id=candidate_id, employee_id=employee_id, knowledge_base_id=knowledge_base_id, title=title, document_type=document_type, permission_scope=permission_scope)
    return {"id": document.id, "material_no": document.material_no, "candidate_id": document.candidate_id, "title": document.title}


@router.get("/documents/{document_id}")
def get_document(document_id: UUID, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "文档不存在")
    version = current_version(db, document_id)
    file_object = db.get(FileObject, version.file_object_id) if version else None
    jobs = db.scalars(select(ParseJob).where(ParseJob.document_version_id == version.id).order_by(ParseJob.created_at.desc())).all() if version else []
    latest = jobs[0] if jobs else None
    artifacts = db.scalars(select(ParseArtifact).where(ParseArtifact.parse_job_id == latest.id)).all() if latest else []
    store = ObjectStore()
    artifact_items = []
    for item in artifacts:
        content = None
        if item.artifact_type == "markdown":
            content = store.get_bytes(item.object_key).decode("utf-8", errors="replace")
        artifact_items.append({"id": item.id, "type": item.artifact_type, "content_type": item.content_type, "url": store.presigned_get(item.object_key), "content": content})
    return {"id": document.id, "material_no": document.material_no, "candidate_id": document.candidate_id, "employee": {"id": document.employee.id, "employee_no": document.employee.employee_no, "name": document.employee.name} if document.employee else None, "knowledge_base": {"id": document.knowledge_base.id, "name": document.knowledge_base.name} if document.knowledge_base else None, "title": document.title, "document_type": document.document_type, "permission_scope": document.permission_scope, "created_at": document.created_at, "updated_at": document.updated_at, "version": {"id": version.id, "version_no": version.version_no, "created_at": version.created_at} if version else None, "file": {"name": file_object.original_name, "mime_type": file_object.mime_type, "size_bytes": file_object.size_bytes, "bucket_name": file_object.bucket_name, "object_key": file_object.object_key, "preview_url": store.presigned_get(file_object.object_key)} if file_object else None, "jobs": [{"id": job.id, "parser_name": job.parser_name, "parser_version": job.parser_version, "status": job.status, "progress": job.progress, "error_message": job.error_message, "created_at": job.created_at} for job in jobs], "artifacts": artifact_items}


@router.post("/documents/{document_id}/parse")
def parse_document_endpoint(document_id: UUID, async_mode: bool = True, db: Session = Depends(get_db)):
    version = current_version(db, document_id)
    if not version:
        raise HTTPException(404, "文档版本不存在")
    if async_mode:
        job = ParseJob(document_version_id=version.id, parser_name="queued")
        db.add(job)
        db.commit()
        Redis.from_url(get_settings().redis_url, decode_responses=True).rpush("talent:parse:queue", f"{job.id}:{version.id}")
        return {"id": job.id, "status": job.status, "parser_name": job.parser_name, "error_message": None}
    job = parse_version(db, ObjectStore(), version.id)
    return {"id": job.id, "status": job.status, "parser_name": job.parser_name, "error_message": job.error_message}


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: UUID, db: Session = Depends(get_db)):
    old = db.get(ParseJob, job_id)
    if not old:
        raise HTTPException(404, "解析任务不存在")
    job = ParseJob(document_version_id=old.document_version_id, parser_name="queued", retry_count=old.retry_count + 1)
    db.add(job)
    db.commit()
    Redis.from_url(get_settings().redis_url, decode_responses=True).rpush("talent:parse:queue", f"{job.id}:{job.document_version_id}")
    return {"id": job.id, "status": job.status, "retry_count": job.retry_count}


@router.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: UUID, db: Session = Depends(get_db)):
    items = db.scalars(select(ParseArtifact).where(ParseArtifact.parse_job_id == job_id)).all()
    store = ObjectStore()
    return [{"id": item.id, "type": item.artifact_type, "content_type": item.content_type, "url": store.presigned_get(item.object_key)} for item in items]

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    ChunkingRun,
    Document,
    DocumentChunk,
    DocumentMetadata,
    DocumentVersion,
    EvidenceIndexJob,
    FileObject,
    ParseArtifact,
    ParseJob,
)


def delete_document_bundle(db: Session, object_store, milvus_store, document_id: UUID) -> dict[str, object]:
    document = db.get(Document, document_id)
    if not document:
        raise ValueError("文档不存在")

    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)).all()
    version_ids = [version.id for version in versions]
    file_objects = db.scalars(
        select(FileObject).where(FileObject.id.in_([version.file_object_id for version in versions]))
    ).all() if versions else []
    parse_jobs = db.scalars(
        select(ParseJob).where(ParseJob.document_version_id.in_(version_ids))
    ).all() if version_ids else []
    parse_job_ids = [job.id for job in parse_jobs]
    artifacts = db.scalars(
        select(ParseArtifact).where(ParseArtifact.parse_job_id.in_(parse_job_ids))
    ).all() if parse_job_ids else []
    chunk_runs = db.scalars(
        select(ChunkingRun).where(ChunkingRun.parse_job_id.in_(parse_job_ids))
    ).all() if parse_job_ids else []
    chunk_run_ids = [run.id for run in chunk_runs]

    for version in versions:
        milvus_store.delete_version(tenant_id=document.tenant_id, document_version_id=str(version.id))
    for file_object in file_objects:
        object_store.delete(file_object.object_key)
    for artifact in artifacts:
        object_store.delete(artifact.object_key)

    if parse_job_ids:
        db.execute(delete(ParseArtifact).where(ParseArtifact.parse_job_id.in_(parse_job_ids)))
    if chunk_run_ids:
        db.execute(delete(DocumentChunk).where(DocumentChunk.chunking_run_id.in_(chunk_run_ids)))
        db.execute(delete(ChunkingRun).where(ChunkingRun.id.in_(chunk_run_ids)))
    if version_ids:
        db.execute(delete(EvidenceIndexJob).where(EvidenceIndexJob.document_version_id.in_(version_ids)))
        db.execute(delete(ParseJob).where(ParseJob.document_version_id.in_(version_ids)))
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(version_ids)))
        db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    if file_objects:
        db.execute(delete(FileObject).where(FileObject.id.in_([item.id for item in file_objects])))

    db.execute(delete(DocumentMetadata).where(DocumentMetadata.document_id == document.id))
    db.delete(document)
    db.commit()

    return {
        "document_id": str(document.id),
        "deleted_versions": [str(version.id) for version in versions],
        "deleted_objects": [item.object_key for item in [*file_objects, *artifacts]],
    }

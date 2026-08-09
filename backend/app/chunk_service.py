from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.chunk_evaluation import AnnotatedQuestion, EvaluatedChunk, boundary_scores, content_coverage, evidence_scores
from app.chunking import ChunkElement, ChunkPiece, ChunkStrategy, chunk_elements, semantic_chunk_text
from app.config import get_settings
from app.model_provider import get_embedding_model
from app.models import (
    BoundaryAnnotation,
    ChunkingRun,
    ChunkingStatus,
    ChunkStrategyName,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceQuestion,
    ParseArtifact,
    ParseJob,
    ParseStatus,
)
from app.object_store import ObjectStore


def default_chunk_strategy() -> ChunkStrategy:
    """Return the normalized default strategy for every material type.

    Material-specific structure is expressed while parsing the source into
    hierarchical Markdown rather than by selecting a different text splitter.
    """
    return ChunkStrategy.MARKDOWN


def parent_paths_for_heading(heading_path: list[str]) -> list[tuple[str, ...]]:
    return [tuple(heading_path[:index]) for index in range(1, len(heading_path) + 1)]


def content_element_ids(elements: list[ChunkElement]) -> list[str]:
    return [element.id for element in elements if element.kind != "heading"]


def elements_from_artifacts(markdown: str, structured: dict) -> list[ChunkElement]:
    content_list = structured.get("content_list") if isinstance(structured, dict) else None
    source_items: list[tuple[int, dict, str]] = []
    if isinstance(content_list, list):
        for index, item in enumerate(content_list, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("content") or "").strip()
            if text:
                source_items.append((index, item, text))

    if markdown.strip():
        blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]
        used_sources: set[int] = set()
        result: list[ChunkElement] = []
        for block_index, block in enumerate(blocks, start=1):
            normalized_block = re.sub(r"^#{1,6}\s+", "", block).strip()
            source = next(
                (
                    (index, item)
                    for index, item, text in source_items
                    if index not in used_sources and re.sub(r"\s+", " ", text) == re.sub(r"\s+", " ", normalized_block)
                ),
                None,
            )
            if source:
                source_index, source_item = source
                used_sources.add(source_index)
                page = int(source_item.get("page_idx", 0)) + 1
                element_id = f"p{page}-e{source_index}"
            else:
                source_item = {}
                page = None
                element_id = f"md-e{block_index}"
            is_heading = bool(re.match(r"^#{1,6}\s+", block)) or source_item.get("type") in {"title", "heading"}
            result.append(ChunkElement(id=element_id, text=block, page=page, kind="heading" if is_heading else str(source_item.get("type") or "text")))
        return result

    result = []
    for index, item, text in source_items:
        page = int(item.get("page_idx", 0)) + 1
        kind = "heading" if item.get("type") in {"title", "heading"} else str(item.get("type") or "text")
        result.append(ChunkElement(id=f"p{page}-e{index}", text=text, page=page, kind=kind))
    return result


def _load_parse_input(db: Session, store: ObjectStore, version_id: UUID) -> tuple[ParseJob, str, dict]:
    job = db.scalar(
        select(ParseJob)
        .where(ParseJob.document_version_id == version_id, ParseJob.status == ParseStatus.SUCCEEDED)
        .order_by(ParseJob.created_at.desc())
    )
    if not job:
        raise ValueError("文档尚无成功的解析任务")
    artifacts = db.scalars(select(ParseArtifact).where(ParseArtifact.parse_job_id == job.id)).all()
    markdown = ""
    structured: dict = {}
    for artifact in artifacts:
        body = store.get_bytes(artifact.object_key)
        if artifact.artifact_type == "markdown":
            markdown = body.decode("utf-8", errors="replace")
        elif artifact.artifact_type == "structured_json":
            structured = json.loads(body.decode("utf-8"))
    if not markdown and not structured:
        raise ValueError("解析任务没有可用的 Markdown 或结构化产物")
    return job, markdown, structured


def source_elements_for_version(db: Session, store: ObjectStore, version_id: UUID) -> list[ChunkElement]:
    _, markdown, structured = _load_parse_input(db, store, version_id)
    return elements_from_artifacts(markdown, structured)


def _semantic_pieces(elements: list[ChunkElement], threshold: float) -> list[ChunkPiece]:
    embeddings = get_embedding_model()
    if embeddings is None:
        raise ValueError("DASHSCOPE_API_KEY 未配置，无法执行语义分片")
    text = "\n".join(element.text for element in elements)
    pieces = semantic_chunk_text(
        text,
        embeddings=embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=threshold,
    )
    for piece in pieces:
        piece.element_ids = [element.id for element in elements if element.text in piece.content]
        pages = [element.page for element in elements if element.id in piece.element_ids and element.page is not None]
        piece.page_start = min(pages) if pages else None
        piece.page_end = max(pages) if pages else None
    return pieces


def create_chunking_run(
    db: Session,
    store: ObjectStore,
    document: Document,
    version: DocumentVersion,
    *,
    strategy: ChunkStrategy,
    chunk_size: int,
    chunk_overlap: int,
    semantic_threshold: float = 90,
) -> ChunkingRun:
    parse_job, markdown, structured = _load_parse_input(db, store, version.id)
    settings = get_settings()
    run = ChunkingRun(
        parse_job_id=parse_job.id,
        strategy=ChunkStrategyName(strategy.value),
        status=ChunkingStatus.RUNNING,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_model=settings.embedding_model if strategy == ChunkStrategy.SEMANTIC else None,
        configuration={"semantic_threshold": semantic_threshold},
    )
    db.add(run)
    db.flush()
    try:
        elements = elements_from_artifacts(markdown, structured)
        pieces = (
            _semantic_pieces(elements, semantic_threshold)
            if strategy == ChunkStrategy.SEMANTIC
            else chunk_elements(elements, strategy=strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        )
        children: list[DocumentChunk] = []
        parent_by_path: dict[tuple[str, ...], DocumentChunk] = {}
        for position, piece in enumerate(pieces):
            parent = None
            parents_for_piece: list[DocumentChunk] = []
            for path_key in parent_paths_for_heading(piece.heading_path):
                current_parent = parent_by_path.get(path_key)
                if current_parent is None:
                    current_parent = DocumentChunk(
                        chunking_run_id=run.id,
                        document_version_id=version.id,
                        candidate_id=document.candidate_id,
                        document_type=document.document_type,
                        permission_scope=document.permission_scope,
                        stable_key=_stable_key(version.id, strategy, f"parent:{'/'.join(path_key)}"),
                        position=position,
                        chunk_level="parent",
                        content="",
                        element_ids=[],
                        heading_path=list(path_key),
                        parent_chunk_id=parent.id if parent else None,
                    )
                    db.add(current_parent)
                    db.flush()
                    parent_by_path[path_key] = current_parent
                parent = current_parent
                parents_for_piece.append(current_parent)
            child = DocumentChunk(
                chunking_run_id=run.id,
                document_version_id=version.id,
                candidate_id=document.candidate_id,
                document_type=document.document_type,
                permission_scope=document.permission_scope,
                stable_key=_stable_key(version.id, strategy, f"{position}:{piece.content}"),
                position=position,
                chunk_level="child",
                content=piece.content,
                element_ids=piece.element_ids,
                heading_path=piece.heading_path,
                parent_chunk_id=parent.id if parent else None,
                page_start=piece.page_start,
                page_end=piece.page_end,
                timestamp_start=piece.timestamp_start,
                timestamp_end=piece.timestamp_end,
            )
            db.add(child)
            db.flush()
            for current_parent in parents_for_piece:
                current_parent.content = f"{current_parent.content}\n\n{child.content}".strip()
                current_parent.element_ids = list(dict.fromkeys([*current_parent.element_ids, *child.element_ids]))
            if children:
                child.previous_chunk_id = children[-1].id
                children[-1].next_chunk_id = child.id
            children.append(child)
        run.status = ChunkingStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        run.status = ChunkingStatus.FAILED
        run.error_message = str(exc)[:2000]
        run.finished_at = datetime.now(UTC)
        db.commit()
        raise


def _stable_key(version_id: UUID, strategy: ChunkStrategy, value: str) -> str:
    return hashlib.sha256(f"{version_id}:{strategy.value}:{value}".encode()).hexdigest()[:32]


def latest_chunks(db: Session, version_id: UUID) -> tuple[ChunkingRun | None, list[DocumentChunk]]:
    run = db.scalar(
        select(ChunkingRun)
        .join(ParseJob, ParseJob.id == ChunkingRun.parse_job_id)
        .where(ParseJob.document_version_id == version_id, ChunkingRun.status == ChunkingStatus.SUCCEEDED)
        .order_by(ChunkingRun.created_at.desc())
    )
    if not run:
        return None, []
    chunks = db.scalars(
        select(DocumentChunk).where(DocumentChunk.chunking_run_id == run.id).order_by(DocumentChunk.chunk_level, DocumentChunk.position)
    ).all()
    return run, chunks


def save_annotations(
    db: Session,
    version_id: UUID,
    *,
    boundaries: list[dict],
    questions: list[dict],
    annotator: str,
) -> None:
    db.execute(delete(BoundaryAnnotation).where(BoundaryAnnotation.document_version_id == version_id))
    db.execute(delete(EvidenceQuestion).where(EvidenceQuestion.document_version_id == version_id))
    db.add_all(
        BoundaryAnnotation(
            document_version_id=version_id,
            after_element_id=item["after_element_id"],
            after_position=item["after_position"],
            reason=item.get("reason"),
            annotator=annotator,
        )
        for item in boundaries
    )
    db.add_all(
        EvidenceQuestion(
            document_version_id=version_id,
            question=item["question"],
            required_element_ids=item["required_element_ids"],
            annotator=annotator,
        )
        for item in questions
    )
    db.commit()


def evaluate_latest_chunks(db: Session, version_id: UUID, source_elements: list[ChunkElement]) -> dict:
    _, stored = latest_chunks(db, version_id)
    child_chunks = [chunk for chunk in stored if chunk.chunk_level == "child"]
    evaluated = [EvaluatedChunk(str(chunk.id), chunk.element_ids, str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None) for chunk in child_chunks]
    boundaries = db.scalars(select(BoundaryAnnotation).where(BoundaryAnnotation.document_version_id == version_id)).all()
    questions = db.scalars(select(EvidenceQuestion).where(EvidenceQuestion.document_version_id == version_id)).all()
    positions = {element.id: index for index, element in enumerate(source_elements, start=1)}
    predicted = sorted(
        {
            max(positions[element_id] for element_id in chunk.element_ids if element_id in positions)
            for chunk in child_chunks[:-1]
            if any(element_id in positions for element_id in chunk.element_ids)
        }
    )
    coverage = content_coverage(content_element_ids(source_elements), evaluated)
    boundary = boundary_scores([item.after_position for item in boundaries], predicted, tolerance=1)
    evidence = evidence_scores(
        [AnnotatedQuestion(str(item.id), item.required_element_ids) for item in questions],
        evaluated,
    )
    return {
        "coverage": coverage.coverage,
        "duplicate_rate": coverage.duplicate_rate,
        "missing_element_ids": coverage.missing_element_ids,
        "boundary_precision": boundary.precision,
        "boundary_recall": boundary.recall,
        "boundary_f1": boundary.f1,
        "evidence_completeness_rate": evidence.completeness_rate,
        "average_dispersion": evidence.average_dispersion,
        "complete_questions": evidence.complete_count,
        "fragmented_questions": evidence.fragmented_count,
        "missing_questions": evidence.missing_count,
    }

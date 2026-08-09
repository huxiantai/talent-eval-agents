from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvaluatedChunk:
    id: str
    element_ids: list[str]
    parent_id: str | None = None


@dataclass(slots=True)
class AnnotatedQuestion:
    id: str
    required_element_ids: list[str]


@dataclass(slots=True)
class CoverageResult:
    coverage: float
    duplicate_rate: float
    missing_element_ids: list[str]


@dataclass(slots=True)
class BoundaryResult:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


@dataclass(slots=True)
class EvidenceResult:
    complete_count: int
    fragmented_count: int
    missing_count: int
    completeness_rate: float
    average_dispersion: float


def content_coverage(source_element_ids: list[str], chunks: list[EvaluatedChunk]) -> CoverageResult:
    source = set(source_element_ids)
    counts = {element_id: 0 for element_id in source_element_ids}
    for chunk in chunks:
        for element_id in set(chunk.element_ids):
            if element_id in counts:
                counts[element_id] += 1
    missing = [element_id for element_id in source_element_ids if counts[element_id] == 0]
    covered = sum(count > 0 for count in counts.values())
    duplicates = sum(count > 1 for count in counts.values())
    denominator = len(source)
    return CoverageResult(
        coverage=covered / denominator if denominator else 1.0,
        duplicate_rate=duplicates / denominator if denominator else 0.0,
        missing_element_ids=missing,
    )


def boundary_scores(
    gold_after_positions: list[int],
    predicted_after_positions: list[int],
    *,
    tolerance: int = 0,
) -> BoundaryResult:
    unmatched_gold = set(gold_after_positions)
    true_positive = 0
    for predicted in predicted_after_positions:
        matches = [gold for gold in unmatched_gold if abs(gold - predicted) <= tolerance]
        if matches:
            matched = min(matches, key=lambda gold: abs(gold - predicted))
            unmatched_gold.remove(matched)
            true_positive += 1
    false_positive = len(predicted_after_positions) - true_positive
    false_negative = len(gold_after_positions) - true_positive
    precision = true_positive / len(predicted_after_positions) if predicted_after_positions else 0.0
    recall = true_positive / len(gold_after_positions) if gold_after_positions else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return BoundaryResult(true_positive, false_positive, false_negative, precision, recall, f1)


def evidence_scores(questions: list[AnnotatedQuestion], chunks: list[EvaluatedChunk]) -> EvidenceResult:
    element_to_chunks: dict[str, set[str]] = {}
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    for chunk in chunks:
        for element_id in chunk.element_ids:
            element_to_chunks.setdefault(element_id, set()).add(chunk.id)

    complete_count = 0
    fragmented_count = 0
    missing_count = 0
    complete_dispersions: list[int] = []
    for question in questions:
        required = set(question.required_element_ids)
        if any(element_id not in element_to_chunks for element_id in required):
            missing_count += 1
            continue
        candidate_chunks = set().union(*(element_to_chunks[element_id] for element_id in required))
        direct = [chunk for chunk in chunks if required.issubset(set(chunk.element_ids))]
        parent_groups: dict[str, set[str]] = {}
        for chunk_id in candidate_chunks:
            chunk = chunk_by_id[chunk_id]
            if chunk.parent_id:
                parent_groups.setdefault(chunk.parent_id, set()).update(chunk.element_ids)
        same_parent = any(required.issubset(element_ids) for element_ids in parent_groups.values())
        if direct or same_parent:
            complete_count += 1
            complete_dispersions.append(1 if direct else len(candidate_chunks))
        else:
            fragmented_count += 1

    total = len(questions)
    average_dispersion = sum(complete_dispersions) / len(complete_dispersions) if complete_dispersions else 0.0
    return EvidenceResult(
        complete_count=complete_count,
        fragmented_count=fragmented_count,
        missing_count=missing_count,
        completeness_rate=complete_count / total if total else 1.0,
        average_dispersion=average_dispersion,
    )

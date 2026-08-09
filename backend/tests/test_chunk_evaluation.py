from app.chunk_evaluation import (
    AnnotatedQuestion,
    EvaluatedChunk,
    boundary_scores,
    content_coverage,
    evidence_scores,
)


def test_content_coverage_counts_source_elements_without_manual_labels():
    chunks = [
        EvaluatedChunk(id="c1", element_ids=["e1", "e2"]),
        EvaluatedChunk(id="c2", element_ids=["e2", "e3"]),
    ]

    result = content_coverage(["e1", "e2", "e3", "e4"], chunks)

    assert result.coverage == 0.75
    assert result.duplicate_rate == 0.25
    assert result.missing_element_ids == ["e4"]


def test_boundary_scores_support_exact_and_tolerant_matching():
    result = boundary_scores(
        gold_after_positions=[4, 10],
        predicted_after_positions=[5, 10, 15],
        tolerance=1,
    )

    assert result.true_positive == 2
    assert result.precision == 2 / 3
    assert result.recall == 1.0
    assert result.f1 == 0.8


def test_evidence_scores_accept_one_chunk_or_one_parent_group():
    chunks = [
        EvaluatedChunk(id="c1", parent_id="p1", element_ids=["e1", "e2"]),
        EvaluatedChunk(id="c2", parent_id="p1", element_ids=["e3"]),
        EvaluatedChunk(id="c3", parent_id="p2", element_ids=["e4"]),
    ]
    questions = [
        AnnotatedQuestion(id="q1", required_element_ids=["e1", "e2"]),
        AnnotatedQuestion(id="q2", required_element_ids=["e1", "e3"]),
        AnnotatedQuestion(id="q3", required_element_ids=["e3", "e4"]),
        AnnotatedQuestion(id="q4", required_element_ids=["e5"]),
    ]

    result = evidence_scores(questions, chunks)

    assert result.complete_count == 2
    assert result.fragmented_count == 1
    assert result.missing_count == 1
    assert result.completeness_rate == 0.5
    assert result.average_dispersion == 1.5

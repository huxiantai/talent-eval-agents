from langchain_core.embeddings import Embeddings

from app.chunking import ChunkElement, ChunkStrategy, chunk_elements, semantic_chunk_text


class TopicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "推荐" in text or "延迟" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def test_recursive_chunking_preserves_every_source_element():
    elements = [
        ChunkElement(id="e1", text="项目背景：推荐链路响应时间较长", page=1),
        ChunkElement(id="e2", text="本人职责：负责召回服务重构", page=1),
        ChunkElement(id="e3", text="项目结果：P95 延迟从 220ms 降至 95ms", page=1),
    ]

    chunks = chunk_elements(
        elements,
        strategy=ChunkStrategy.RECURSIVE,
        chunk_size=34,
        chunk_overlap=0,
    )

    covered = {element_id for chunk in chunks for element_id in chunk.element_ids}
    assert covered == {"e1", "e2", "e3"}
    assert all(chunk.content for chunk in chunks)


def test_fixed_chunking_uses_character_boundaries():
    chunks = chunk_elements(
        [ChunkElement(id="e1", text="甲乙丙丁戊己庚辛")],
        strategy=ChunkStrategy.FIXED,
        chunk_size=4,
        chunk_overlap=0,
    )

    assert [chunk.content for chunk in chunks] == ["甲乙丙丁", "戊己庚辛"]


def test_markdown_chunking_keeps_heading_path_as_parent_context():
    elements = [
        ChunkElement(id="e1", text="# 工作经历", page=1, kind="heading"),
        ChunkElement(id="e2", text="## 星云科技", page=1, kind="heading"),
        ChunkElement(id="e3", text="负责推荐系统升级", page=1),
    ]

    chunks = chunk_elements(
        elements,
        strategy=ChunkStrategy.MARKDOWN,
        chunk_size=100,
        chunk_overlap=0,
    )

    assert chunks[-1].heading_path == ["工作经历", "星云科技"]
    assert chunks[-1].element_ids == ["e3"]


def test_long_markdown_section_keeps_heading_path_after_recursive_split():
    elements = [
        ChunkElement(id="e1", text="# 项目经历", kind="heading"),
        ChunkElement(id="e2", text="负责推荐系统升级。" * 30),
    ]

    chunks = chunk_elements(
        elements,
        strategy=ChunkStrategy.MARKDOWN,
        chunk_size=100,
        chunk_overlap=10,
    )

    assert len(chunks) > 1
    assert all(chunk.heading_path == ["项目经历"] for chunk in chunks)


def test_long_markdown_element_refines_character_locator_for_each_child():
    text = "负责推荐系统升级。" * 30
    elements = [
        ChunkElement(id="e1", text="# 项目经历", kind="heading"),
        ChunkElement(
            id="e2",
            text=text,
            source_locator={"kind": "char_range", "char_start": 100, "char_end": 100 + len(text)},
        ),
    ]

    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=80, chunk_overlap=10)

    assert len(chunks) > 1
    for chunk in chunks:
        locator = chunk.source_locators[0]
        assert locator["char_end"] - locator["char_start"] == len(chunk.content)


def test_interview_strategy_keeps_question_and_answer_together():
    elements = [
        ChunkElement(id="e1", text="面试官 00:01 请介绍推荐系统升级项目", timestamp_start=1),
        ChunkElement(id="e2", text="候选人 00:08 我负责召回服务重构", timestamp_start=8),
        ChunkElement(id="e3", text="面试官 00:35 最终效果如何", timestamp_start=35),
        ChunkElement(id="e4", text="候选人 00:40 P95 延迟下降到 95ms", timestamp_start=40),
    ]

    chunks = chunk_elements(
        elements,
        strategy=ChunkStrategy.INTERVIEW_QA,
        chunk_size=200,
        chunk_overlap=0,
    )

    assert [chunk.element_ids for chunk in chunks] == [["e1", "e2"], ["e3", "e4"]]
    assert chunks[0].heading_path == ["面试问答", "问答 1"]
    assert chunks[1].heading_path == ["面试问答", "问答 2"]


def test_long_interview_answer_is_split_under_the_same_question_parent():
    elements = [
        ChunkElement(id="e1", text="面试官 请介绍项目"),
        ChunkElement(id="e2", text="候选人 " + "负责系统重构。" * 30),
    ]

    chunks = chunk_elements(
        elements,
        strategy=ChunkStrategy.INTERVIEW_QA,
        chunk_size=80,
        chunk_overlap=10,
    )

    assert len(chunks) > 1
    assert all(chunk.heading_path == ["面试问答", "问答 1"] for chunk in chunks)


def test_semantic_chunking_uses_supplied_embedding_model():
    text = "负责推荐召回服务。系统延迟下降一半。随后负责团队招聘。建立新人培养机制。"

    chunks = semantic_chunk_text(
        text,
        embeddings=TopicEmbeddings(),
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=80,
        buffer_size=0,
    )

    assert len(chunks) >= 2
    assert "".join(chunk.content for chunk in chunks).replace(" ", "") == text

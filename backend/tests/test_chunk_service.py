from app import chunk_service
from app.chunk_service import content_element_ids, default_chunk_strategy, elements_from_artifacts
from app.chunking import ChunkStrategy, chunk_elements


def test_mineru_content_list_becomes_page_aware_elements():
    structured = {
        "content_list": [
            {"type": "text", "text": "项目背景", "page_idx": 0},
            {"type": "text", "text": "负责推荐系统升级", "page_idx": 1},
        ]
    }

    elements = elements_from_artifacts("", structured)

    assert [element.id for element in elements] == ["p1-e1", "p2-e2"]
    assert [element.page for element in elements] == [1, 2]
    assert elements[0].text == "项目背景"


def test_markdown_fallback_preserves_headings_as_elements():
    elements = elements_from_artifacts("# 工作经历\n\n## 星云科技\n\n负责推荐系统升级", {})

    assert [element.kind for element in elements] == ["heading", "heading", "text"]
    assert elements[-1].text == "负责推荐系统升级"


def test_auto_mode_defaults_to_markdown_strategy():
    assert default_chunk_strategy() == ChunkStrategy.MARKDOWN


def test_mineru_content_list_adds_source_metadata_without_replacing_markdown_hierarchy():
    markdown = "# 项目经历\n\n## 推荐系统升级\n\n负责召回服务重构"
    structured = {
        "content_list": [
            {"type": "title", "text": "项目经历", "page_idx": 0},
            {"type": "title", "text": "推荐系统升级", "page_idx": 1},
            {"type": "text", "text": "负责召回服务重构", "page_idx": 1, "bbox": [10, 20, 300, 80]},
        ]
    }

    elements = elements_from_artifacts(markdown, structured)

    assert [element.text for element in elements] == ["# 项目经历", "## 推荐系统升级", "负责召回服务重构"]
    assert [element.page for element in elements] == [1, 2, 2]
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=100, chunk_overlap=0)
    assert chunks[0].heading_path == ["项目经历", "推荐系统升级"]
    assert chunks[0].source_locators[-1] == {
        "kind": "page_region",
        "page": 2,
        "bbox": [10, 20, 300, 80],
    }


def test_simulated_transcript_creates_one_speaker_parent_with_time_locators():
    structured = {
        "segments": [
            {"start": 0.0, "end": 30.0, "text": "第一段"},
            {"start": 30.0, "end": 65.0, "text": "第二段"},
        ]
    }

    elements = elements_from_artifacts("# 语音转录\n\n## 说话人 1\n\n第一段\n\n第二段", structured)
    chunks = chunk_elements(elements, strategy=ChunkStrategy.MARKDOWN, chunk_size=100, chunk_overlap=10)

    assert chunks[-1].heading_path == ["语音转录", "说话人 1"]
    assert any(locator.get("timestamp_start") == 0.0 for chunk in chunks for locator in chunk.source_locators)


def test_heading_path_expands_to_parent_tree_paths():
    assert chunk_service.parent_paths_for_heading(["项目经历", "推荐系统升级", "项目结果"]) == [
        ("项目经历",),
        ("项目经历", "推荐系统升级"),
        ("项目经历", "推荐系统升级", "项目结果"),
    ]


def test_coverage_denominator_excludes_headings_stored_as_metadata():
    elements = elements_from_artifacts("# 项目经历\n\n负责推荐系统升级", {})

    assert content_element_ids(elements) == ["md-e2"]

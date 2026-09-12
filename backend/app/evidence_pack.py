"""Lesson 9: evidence organization. Model judgments remain reviewable hypotheses."""
from __future__ import annotations

import json
import logging
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class FactSource(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=2000)


class ExtractedFact(StrictModel):
    event: str = Field(min_length=1, max_length=200)
    period: str = Field(pattern=r'^(?:unknown|\d{4}|\d{4}-\d{2}/\d{4}-\d{2})$')
    claim: str = Field(min_length=1, max_length=200)
    answer: Literal['yes', 'no']
    sources: list[FactSource] = Field(min_length=1, max_length=24)


class EvidenceExtraction(StrictModel):
    facts: list[ExtractedFact] = Field(default_factory=list, max_length=30)
    fully_supported: bool = False
    missing_information: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=10)


EXTRACTION_PROMPT = """根据给定查询要求整理材料中的事实陈述。
只抽取与 requirement 相关的项目、时期、职责或成果，保留原文限定词，不补全未知事实。
event 填写材料明确出现的项目、岗位或事项名称。材料出现星河项目时填写星河项目，只有材料没有可识别事项时才填写 unknown。
period 对同一时间范围统一写成 YYYY-MM/YYYY-MM，例如 2025 年 1 月至 6 月写成 2025-01/2025-06。
claim 把查询要求改写成可回答是或否的命题，例如担任项目总负责人。
answer 仅使用 yes、no。明确满足命题为 yes，明确否定命题为 no，未回答命题的背景内容不生成事实。
同一事实的重复转述使用相同的 event、period、claim 和 answer。
每条事实必须有输入 chunk_id 和连续原文 quote，quote 不得改写。
fully_supported 仅表示当前材料直接覆盖当前要求全部要素，缺失、冲突时为 false。
没有缺失信息时 missing_information 必须返回空数组，不能返回空字符串。
原文引用正确不代表事实已经独立核实。不评分、不推荐候选人。"""


def model_extractor(model):
    def extract(requirement, sources):
        payload = {'requirement': requirement['query'], 'sources': [
            {'chunk_id': row['chunk_id'], 'content': row['content']} for row in sources]}
        return model.with_structured_output(EvidenceExtraction).invoke([
            ('system', EXTRACTION_PROMPT),
            ('user', json.dumps(payload, ensure_ascii=False)),
        ])
    return extract


def _validate_fact_sources(facts, sources):
    """Reject model facts that cannot point back to an input Chunk and exact quote."""
    by_id = {row['chunk_id']: row for row in sources}
    validated = []
    for fact in facts:
        refs = []
        for ref in fact.sources:
            row = by_id.get(ref.chunk_id)
            quote_start = row['content'].find(ref.quote) if row is not None else -1
            if row is None or not ref.quote.strip() or quote_start < 0:
                raise ValueError('unverifiable_source')
            mapped = {
                'citation_id': row['citation_id'],
                'chunk_id': ref.chunk_id,
                'quote': ref.quote,
                'quote_start': quote_start,
                'quote_end': quote_start + len(ref.quote),
            }
            if mapped not in refs:
                refs.append(mapped)
        validated.append({**fact.model_dump(exclude={'sources'}), 'sources': refs})
    return validated


def _merge_duplicate_facts(facts):
    """Merge repeated descriptions while preserving every verified source."""
    merged, index_by_key = [], {}
    for fact in facts:
        key = (fact['event'], fact['period'], fact['claim'], fact['answer'])
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            merged.append({**fact, 'sources': []})
        index = index_by_key[key]
        for ref in fact['sources']:
            if ref not in merged[index]['sources']:
                merged[index]['sources'].append(ref)
    return merged


def _find_conflicts(facts):
    """Find yes/no answers about the same event, period and claim."""
    conflicts = []
    for left_index, left in enumerate(facts):
        for right_index in range(left_index + 1, len(facts)):
            right = facts[right_index]
            same_scope = all(left[key] == right[key] and left[key] != 'unknown'
                for key in ('event', 'period', 'claim'))
            opposite_answers = {left['answer'], right['answer']} == {'yes', 'no'}
            if same_scope and opposite_answers:
                conflicts.append([left_index, right_index])
    return conflicts


def _evidence_status(*, facts, conflicts, fully_supported, missing_information):
    if conflicts:
        return 'conflicting'
    if (any(fact['answer'] == 'yes' for fact in facts) and fully_supported
            and not missing_information):
        return 'sufficient'
    if facts:
        return 'partial'
    return 'missing'


def build_evidence_packs(*, candidate_ids, requirements, sources, extract):
    packs = []
    for candidate_id in dict.fromkeys(candidate_ids):
        items = []
        for requirement in requirements:
            rows = list({row['chunk_id']: row for row in sources
                if row['candidate_id'] == candidate_id
                and requirement['requirement_id'] in row['requirement_ids']}.values())
            item = {**requirement, 'status': 'missing', 'reason': 'no_accessible_hits',
                    'extraction_status': 'not_run', 'facts': [], 'conflicts': [],
                    'missing_information': [], 'citations': rows}
            if rows:
                try:
                    raw = extract(requirement, rows)
                    data = raw if isinstance(raw, EvidenceExtraction) else EvidenceExtraction.model_validate(raw)
                    facts = _merge_duplicate_facts(_validate_fact_sources(data.facts, rows))
                    conflicts = _find_conflicts(facts)
                    status = _evidence_status(facts=facts, conflicts=conflicts,
                        fully_supported=data.fully_supported, missing_information=data.missing_information)
                    item.update(status=status, reason='evidence_review' if facts else 'no_relevant_evidence',
                        extraction_status='succeeded', facts=facts, conflicts=conflicts,
                        missing_information=data.missing_information)
                except Exception as exc:
                    # Never return provider errors, raw prompts or document contents in errors.
                    logger.warning('evidence_extraction_failed type=%s', type(exc).__name__)
                    item.update(status='partial', reason='extraction_failed', extraction_status='failed')
            items.append(item)
        packs.append({'schema_version': '2.0', 'candidate_id': candidate_id, 'requirements': items})
    return packs

import React, { useState } from 'react';

type Citation = {
  citation_id: string; content: string; document_title: string;
  version_no: number; version_state: string; heading_path: string[];
  page_start: number | null; timestamp_start: number | null; markdown_start: number | null;
};
type Requirement = {
  requirement_id: string; query: string; status: string; extraction_status: string;
  missing_information: string[]; citations: Citation[];
  conflicts: number[][];
  facts: { event: string; period: string; claim: string; answer: string;
    sources: { citation_id: string; quote: string }[] }[];
};
type Pack = { candidate_id: string; requirements: Requirement[] };
const statusLabels: Record<string, string> = { sufficient: '材料支持当前要求', partial: '证据待补充或核查',
  missing: '未找到可支持要求的证据', conflicting: '材料存在待核查冲突' };
const answerLabels: Record<string, string> = { yes: '支持', no: '反向' };

export function EvidencePackPanel({ api, tenant }: { api: string; tenant: string }) {
  const [query, setQuery] = useState('查找在深圳且有 AI 项目工作经历的候选人');
  const [packs, setPacks] = useState<Pack[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [citation, setCitation] = useState<Citation | null>(null);
  const [citationBusy, setCitationBusy] = useState(false);
  const headers = { 'Content-Type': 'application/json', 'X-Tenant-ID': tenant, 'X-Permission-Scopes': 'hr_private' };
  async function read(path: string, options: RequestInit = {}) {
    const response = await fetch(`${api}${path}`, { ...options, headers });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    return data;
  }
  async function search() {
    setBusy(true); setError(''); setMessage(''); setPacks([]); setCitation(null);
    try {
      const data = await read('/talent-search', { method: 'POST', body: JSON.stringify({ query, include_evidence_pack: true, limit: 8 }) });
      setPacks(data.evidence_packs);
      if (!data.candidate_ids.length) setMessage('当前结构化条件下没有候选人');
      else if (data.evidence_status === 'not_requested') setMessage('查询未包含需要材料取证的要求');
    } catch (e) { setError(e instanceof Error ? e.message : '检索失败'); }
    finally { setBusy(false); }
  }
  async function openCitation(id: string) {
    setCitation(null); setError(''); setCitationBusy(true);
    try { setCitation(await read(`/evidence/citations/${encodeURIComponent(id)}`)); }
    catch (e) { setError(e instanceof Error ? e.message : '引用不可用'); }
    finally { setCitationBusy(false); }
  }
  return <details className="evidencePackPanel">
    <summary>人才证据整理与原文核查</summary>
    <div className="recallHead">
      <input aria-label="人才查询" value={query} onChange={e => setQuery(e.target.value)} style={{ flex: 1 }} />
      <button className="ghost" disabled={busy || !query.trim()} onClick={search}>{busy ? '整理中…' : '检索并整理证据'}</button>
    </div>
    {error && <p role="alert" className="chunkError">{error}</p>}
    {message && <p>{message}</p>}
    {citationBusy && <p role="status">正在核查引用权限…</p>}
    {packs.map(pack => <section key={pack.candidate_id}>
      <h3>{pack.candidate_id}</h3>
      {pack.requirements.map(req => <article className="recallCard" key={req.requirement_id}>
        <h4>{req.requirement_id} · {req.query}</h4>
        <p>{statusLabels[req.status]}{req.extraction_status === 'failed' ? ' · 抽取失败，保留原始材料' : ''}</p>
        {req.facts.map((fact, i) => <div key={i}>
          <p>{i + 1}. {fact.event} · {fact.period} · {answerLabels[fact.answer]} {fact.claim}</p>
          {fact.sources.map((ref, j) => <button className="ghost" disabled={citationBusy} key={j} onClick={() => openCitation(ref.citation_id)}>原文：{ref.quote}</button>)}
        </div>)}
        {req.conflicts.map((pair, i) => <p key={i}>待核查冲突：事实 {pair.map(n => n + 1).join(' 与 ')}</p>)}
        {req.missing_information.length > 0 && <p>待补充：{req.missing_information.join('、')}</p>}
        <details><summary>本轮原始证据（{req.citations.length}）</summary>
          {req.citations.map(ref => <button className="ghost" disabled={citationBusy} key={ref.citation_id} onClick={() => openCitation(ref.citation_id)}>{ref.document_title} · v{ref.version_no}</button>)}
        </details>
      </article>)}
    </section>)}
    {citation && <div className="drawerWrap" onClick={() => setCitation(null)}>
      <article className="drawer" role="dialog" aria-modal="true" aria-label="引用原文" onClick={e => e.stopPropagation()}>
        <div className="drawerHead"><h3>{citation.document_title}</h3><button className="ghost" onClick={() => setCitation(null)}>关闭</button></div>
        <p>版本 {citation.version_no} · {citation.version_state === 'historical' ? '历史版本' : '当前版本'}</p>
        <p>{citation.heading_path?.join(' / ')}</p>
        {citation.page_start != null && <p>页码：{citation.page_start}</p>}
        {citation.timestamp_start != null && <p>时间：{citation.timestamp_start} 秒</p>}
        {citation.markdown_start != null && <p>文本起始位置：{citation.markdown_start}</p>}
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{citation.content}</pre>
      </article>
    </div>}
  </details>;
}

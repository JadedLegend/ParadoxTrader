import { useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getRehearsalRuns, getRehearsalRun, getRehearsalJobs, getRehearsalRequests, getRehearsalRecord } from '../api'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'
import type { RehearsalAgentId, RehearsalJob, RehearsalRecordRef, RehearsalRecordResponse, RehearsalRequestsResponse, RehearsalRun, RehearsalRunsResponse } from '../rehearsal/contracts'

type ReadState<T> = { key: string; data: T | null; loading: boolean; error: boolean }
const empty = <T,>(): ReadState<T> => ({ key: '', data: null, loading: false, error: false })
const LIMIT = 50
const RUN_LIMIT = 20
const MAX_OFFSET = 1_000_000
const text = (value: unknown, max = 1000) => typeof value === 'string' ? value.length > max ? `${value.slice(0, max)}… [truncated]` : value : ''
const label = (value: string) => text(value, 100).replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
function dollars(value: string | null | undefined) {
  if (value === null || value === undefined) return 'Unavailable'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'Unavailable'
  if (numeric === 0 && !/[1-9]/.test(value)) return '$0'
  if (Math.abs(numeric) < 1e-12) return '<$0.000000000001'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 12 }).format(numeric)
}
const elapsed = (value: number | null | undefined) => value === null || value === undefined ? 'Unavailable' : `${value} ms`
function PrivateRecord({ value }: { value: RehearsalRecordResponse }) {
  const record = value.record
  return <article className="card rehearsal-private-record">
    <h3>{label(value.agent_id)} · {label(value.kind)} #{value.id}</h3>
    {'inquiry' in record ? <>
      <h4>{text(record.inquiry.title, 500)}</h4><p>Inquiry state: {label(record.inquiry.state)}</p>
      {record.entries.length === 0 ? <p>No inquiry notes recorded.</p> : record.entries.slice(0, 100).map(entry => <div className="rehearsal-record-entry" key={entry.entry_id}><strong>{label(entry.kind)}</strong><p>{text(entry.content, 12000)}</p><p className="rehearsal-meta">{entry.created_at} · {label(entry.source)}</p></div>)}
      {record.truncated && <p>Inquiry history is truncated.</p>}
    </> : 'text' in record ? <><p className="rehearsal-meta">{text(record.locator, 500)}</p><p>{text(record.text, 4000)}</p>{record.truncated && <p>Source excerpt is truncated.</p>}</> : <>
      {record.title && <h4>{text(record.title, 500)}</h4>}<p>{text(record.content, 12000)}</p><p className="rehearsal-meta">{record.created_at}</p>{record.truncated && <p>Private record is truncated.</p>}
    </>}
  </article>
}

export default function Rehearsal() {
  const [runId, setRunId] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<RehearsalAgentId>('tempest')
  const [selected, setSelected] = useState<RehearsalRecordRef | null>(null)
  const [runOffset, setRunOffset] = useState(0)
  const [requestOffset, setRequestOffset] = useState(0)
  const [retry, setRetry] = useState(0)
  // Generations distinguish A → B → A even when an old A promise resolves last.
  const selectionGeneration = useRef(0)
  const [generation, setGeneration] = useState(0)
  const listKey = JSON.stringify([runOffset, retry])
  const runKey = JSON.stringify([runId, retry])
  const requestsKey = JSON.stringify([runId, agentId, requestOffset, retry, generation])
  const recordKey = JSON.stringify([runId, agentId, selected, retry, generation])
  const [listState, setListState] = useState<ReadState<RehearsalRunsResponse>>(empty)
  const [runState, setRunState] = useState<ReadState<{ run: RehearsalRun; jobs: RehearsalJob[] }>>(empty)
  const [requestsState, setRequestsState] = useState<ReadState<RehearsalRequestsResponse>>(empty)
  const [recordState, setRecordState] = useState<ReadState<RehearsalRecordResponse>>(empty)

  useEffect(() => {
    let cancelled = false
    setListState({ key: listKey, data: null, loading: true, error: false })
    getRehearsalRuns(RUN_LIMIT, runOffset).then(data => {
      if (!cancelled) { setListState({ key: listKey, data, loading: false, error: false }); setRunId(current => current && data.runs.some(run => run.run_id === current) ? current : data.runs[0]?.run_id ?? null) }
    }).catch(() => { if (!cancelled) setListState({ key: listKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [listKey, runOffset])
  useEffect(() => {
    if (!runId) return
    let cancelled = false
    setRunState({ key: runKey, data: null, loading: true, error: false })
    Promise.all([getRehearsalRun(runId), getRehearsalJobs(runId)]).then(([run, jobs]) => {
      if (run.run_id !== runId || jobs.run_id !== runId || jobs.jobs.some(job => !REHEARSAL_AGENTS.some(agent => agent.id === job.agent_id))) throw new Error('Run scope mismatch')
      if (!cancelled) setRunState({ key: runKey, data: { run, jobs: jobs.jobs }, loading: false, error: false })
    }).catch(() => { if (!cancelled) setRunState({ key: runKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, runKey])
  useEffect(() => {
    if (!runId) return
    let cancelled = false
    const version = selectionGeneration.current
    setRequestsState({ key: requestsKey, data: null, loading: true, error: false })
    getRehearsalRequests(runId, agentId, LIMIT, requestOffset).then(data => {
      if (data.run_id !== runId || data.events.some(event => event.agent_id !== agentId)) throw new Error('Request owner mismatch')
      if (!cancelled && version === selectionGeneration.current) setRequestsState({ key: requestsKey, data, loading: false, error: false })
    }).catch(() => { if (!cancelled && version === selectionGeneration.current) setRequestsState({ key: requestsKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, agentId, requestOffset, requestsKey])
  useEffect(() => {
    if (!runId || !selected) return
    let cancelled = false
    const version = selectionGeneration.current
    setRecordState({ key: recordKey, data: null, loading: true, error: false })
    getRehearsalRecord(runId, agentId, selected.kind, selected.id).then(data => {
      if (data.run_id !== runId || data.agent_id !== agentId || data.kind !== selected.kind || String(data.id) !== String(selected.id)) throw new Error('Record owner mismatch')
      if ('inquiry' in data.record && data.record.inquiry.agent_id !== agentId) throw new Error('Inquiry owner mismatch')
      if (!cancelled && version === selectionGeneration.current) setRecordState({ key: recordKey, data, loading: false, error: false })
    }).catch(() => { if (!cancelled && version === selectionGeneration.current) setRecordState({ key: recordKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, agentId, selected, recordKey])

  function clearSelection() {
    selectionGeneration.current += 1
    setGeneration(selectionGeneration.current)
    setSelected(null)
    setRequestOffset(0)
    setRecordState(empty())
  }
  const list = listState.key === listKey && !listState.error ? listState.data : null
  const detail = runState.key === runKey && !runState.error ? runState.data : null
  const requests = requestsState.key === requestsKey && !requestsState.error ? requestsState.data : null
  const record = selected && recordState.key === recordKey && !recordState.error ? recordState.data : null
  const run = detail?.run
  const ownerJobs = detail?.jobs.filter(job => job.agent_id === agentId) ?? []
  const refs = ownerJobs.flatMap(job => job.record_refs).filter((ref, index, values) => values.findIndex(candidate => candidate.kind === ref.kind && String(candidate.id) === String(ref.id)) === index)
  const refresh = () => { clearSelection(); setRetry(value => value + 1) }

  return <div className="rehearsal-page">
    <header className="page-header"><h1 className="page-title">Rehearsal</h1><p className="page-sub">Seven-agent finite nontrading session · after-run inspection, read only.</p></header>
    <div className="notice rehearsal-notice"><strong>{IS_PREVIEW ? 'Mock runs · local fixture' : 'Recorded runs · operator-protected reads'}</strong>
      <p>{IS_PREVIEW ? 'All examples are mocked. Model names do not verify current real-model availability. No network fallback or paid launch occurs.' : 'No browser operator token or model credentials are configured here. Connected reads require deliberately integrated operator authentication.'}</p>
      <p>CLI owns prepare, start, stop and resume. No launch controls are available here; inspect when useful, not continuously.</p>
    </div>
    <div className="rehearsal-toolbar"><label htmlFor="rehearsal-run">Run</label><select id="rehearsal-run" className="select" value={runId ?? ''} onChange={event => { clearSelection(); setRunId(event.target.value || null) }} disabled={!list?.runs.length}>
      {!list?.runs.length && <option value="">No run selected</option>}{list?.runs.map(value => <option key={value.run_id} value={value.run_id}>{value.run_id.slice(0, 8)} · {label(value.status)} · {value.mode}</option>)}
    </select><button type="button" className="btn btn-ghost" onClick={refresh}>Refresh reads</button></div>
    {(listState.key !== listKey || listState.loading) && <p role="status">Loading runs…</p>}
    {listState.key === listKey && listState.error && <p role="alert" className="error-msg">Run list unavailable. A failed read is not an empty run list.</p>}
    {list && <div className="rehearsal-toolbar" aria-label="Run pagination"><span>{list.total} recorded run{list.total === 1 ? '' : 's'} · page offset {list.offset}</span>
      <button type="button" className="btn btn-ghost" disabled={list.offset === 0} onClick={() => { clearSelection(); setRunId(null); setRunOffset(Math.max(0, runOffset - RUN_LIMIT)) }}>Previous runs</button>
      <button type="button" className="btn btn-ghost" disabled={list.offset + RUN_LIMIT >= list.total || list.offset > MAX_OFFSET - RUN_LIMIT} onClick={() => { clearSelection(); setRunId(null); setRunOffset(runOffset + RUN_LIMIT) }}>Next runs</button></div>}
    {list?.runs.length === 0 && <p className="card">No rehearsals recorded on this page.</p>}
    {runId && (runState.key !== runKey || runState.loading) && <p role="status">Loading run metadata…</p>}
    {runId && runState.key === runKey && runState.error && <p role="alert" className="error-msg">Run metadata unavailable. Completion and spend are not inferred.</p>}
    {run && <>
      <section className="card rehearsal-summary" aria-label="Run limits and accounting"><h2>{label(run.status)} · {run.mode === 'offline' ? 'Offline execution' : 'Real-mode manifest'}</h2>
        <p className="rehearsal-meta">{run.run_id} · Created {run.created_at}<br />Started: {run.started_at ?? 'Not started'} · Ended: {run.ended_at ?? 'Not ended'} · Stop requested: {run.stop_requested ? 'Yes' : 'No'}</p>
        <dl className="rehearsal-metrics"><div><dt>HTTP attempts</dt><dd>{run.request_count} / {run.limits.max_requests}</dd></div><div><dt>Admission reserved</dt><dd>{dollars(run.reserved_usd)} / {dollars(run.limits.budget_usd)}</dd></div><div><dt>Known reported / estimated cost</dt><dd>{dollars(run.known_cost_usd)}</dd></div><div><dt>Unknown-cost requests</dt><dd>{run.unknown_cost_requests}</dd></div></dl>
        <p className="rehearsal-meta">Reported subtotal: {dollars(run.reported_cost_usd)} · Estimated subtotal: {dollars(run.estimated_cost_usd)}. Missing costs are unknown, not free; reservations are not an invoice.</p>
        <p>{run.limits.wakes_per_agent} wakes/member · concurrency ≤ {run.limits.max_parallelism} · input ≤ {run.limits.max_input_bytes} UTF-8 bytes · output ≤ {run.limits.max_output_tokens} tokens/request · request timeout {run.limits.request_timeout_seconds}s · runtime ≤ {run.limits.max_runtime_seconds}s</p>
        <p className="rehearsal-meta">Frozen limits are configured ceilings, not proof of upstream enforcement or an absolute invoice guarantee. Capabilities: {run.capabilities.join(', ')}. No trading, forum, peer messages or market evidence.</p>
      </section>
      <section className="card rehearsal-progress" aria-label="Seven-agent progress"><h2 className="card-title">Seven-agent progress</h2><p>Different models, rest and no change are legitimate outcomes. No personality grading or compulsory journal.</p>
        <div className="rehearsal-table-wrap" role="region" aria-label="Member progress table" tabIndex={0}><table className="rehearsal-table"><thead><tr><th>Member / assigned model</th><th>Pending</th><th>Completed</th><th>Failed</th><th>Stopped</th><th>Uncertain</th><th>Recorded actions</th></tr></thead><tbody>{REHEARSAL_AGENTS.map(agent => {
          const progress = run.agents.find(item => item.agent_id === agent.id)
          const jobs = detail!.jobs.filter(job => job.agent_id === agent.id)
          return <tr key={agent.id}><th scope="row"><button type="button" className="btn btn-ghost" aria-pressed={agentId === agent.id} onClick={() => { clearSelection(); setAgentId(agent.id) }}>{agent.name}</button><div className="rehearsal-meta">{text(run.agent_models[agent.id], 200) || 'Unavailable'}</div></th>{(['pending', 'completed', 'failed', 'stopped', 'uncertain'] as const).map(status => <td key={status}>{progress?.[status] ?? 'Unavailable'}</td>)}<td>{jobs.length ? jobs.map(job => <div key={job.wake_id}>Round {job.round}: {job.action ? label(job.action) : 'Choice not recorded'} · <span className={`rehearsal-status rehearsal-status-${job.status}`}>{label(job.status)}</span></div>) : 'Jobs unavailable'}</td></tr>
        })}</tbody></table></div>
      </section>
      <section className="card rehearsal-owner" aria-label="Selected-owner inspection"><div className="rehearsal-toolbar"><h2 className="card-title">Selected-owner inspection</h2><label htmlFor="rehearsal-owner">Owner</label><select id="rehearsal-owner" className="select" value={agentId} onChange={event => { clearSelection(); setAgentId(event.target.value as RehearsalAgentId) }}>{REHEARSAL_AGENTS.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></div>
        <p>Private records are separate from operational metadata. Only {label(agentId)}’s linked records are available.</p>
        {ownerJobs.map(job => <p className="rehearsal-meta" key={job.wake_id}>Round {job.round} · {label(job.status)} · {job.action ? label(job.action) : 'Choice not recorded'} · Requested {text(job.requested_model, 200) || 'Unavailable'} · Returned {text(job.response_model, 200) || 'Unavailable'} · Provider {text(job.provider, 100) || 'Unavailable'} · Latency {elapsed(job.duration_ms)}{job.failure_code ? ` · ${text(job.failure_code, 100)}` : ''}</p>)}
        <h3>Request metadata</h3>
        {(requestsState.key !== requestsKey || requestsState.loading) && <p role="status">Loading owner requests…</p>}
        {requestsState.key === requestsKey && requestsState.error && <p role="alert" className="error-msg">Owner requests unavailable. Missing telemetry is not zero usage.</p>}
        {requests && <><p className="rehearsal-meta">Showing {requests.events.length} of {requests.total} selected-owner requests · limit {requests.limit} · offset {requests.offset}. Costs on this page are not the complete run total.</p>
          {requests.events.length === 0 ? <p>No requests recorded on this owner page.</p> : <div className="rehearsal-table-wrap" role="region" aria-label="Request telemetry table" tabIndex={0}><table className="rehearsal-table"><thead><tr><th>Activity / outcome</th><th>Requested → returned model</th><th>Provider / latency</th><th>Cost coverage</th></tr></thead><tbody>{requests.events.map(event => <tr key={event.request_id}><td>{label(event.activity)} · {label(event.outcome)}{event.failure_code && <div>{text(event.failure_code, 100)}</div>}</td><td>{text(event.requested_model ?? event.model, 200) || 'Unavailable'}<br />→ {text(event.response_model, 200) || 'Unavailable'}</td><td>{text(event.provider, 100) || 'Unavailable'}<br />{elapsed(event.duration_ms)}</td><td>Reserved {dollars(event.reserved_usd)}<br />{event.usage?.cost_status ? label(event.usage.cost_status) : 'Unknown'}: {dollars(event.usage?.reported_cost_usd ?? event.usage?.estimated_cost_usd ?? event.usage?.cost_usd)}<div className="rehearsal-meta">Input tokens {event.usage?.input_tokens ?? event.usage?.prompt_tokens ?? 'Unavailable'} · Output {event.usage?.output_tokens ?? event.usage?.completion_tokens ?? 'Unavailable'}</div></td></tr>)}</tbody></table></div>}
          <div className="rehearsal-toolbar" aria-label="Request pagination"><button type="button" className="btn btn-ghost" disabled={requests.offset === 0} onClick={() => setRequestOffset(Math.max(0, requestOffset - LIMIT))}>Previous requests</button><button type="button" className="btn btn-ghost" disabled={requests.offset + LIMIT >= requests.total || requests.offset > MAX_OFFSET - LIMIT} onClick={() => setRequestOffset(requestOffset + LIMIT)}>Next requests</button></div></>}
        <h3>Optional private records</h3>{refs.length === 0 ? <p>No linked private records. A journal or inquiry is not required.</p> : <div className="rehearsal-record-links">{refs.map(ref => <button type="button" className="btn btn-ghost" key={`${ref.kind}|${ref.id}`} onClick={() => { selectionGeneration.current += 1; setGeneration(selectionGeneration.current); setSelected(ref); setRecordState(empty()) }}>Read {ref.kind} #{ref.id}</button>)}</div>}
        {selected && (recordState.key !== recordKey || recordState.loading) && <p role="status">Loading private record…</p>}
        {selected && recordState.key === recordKey && recordState.error && <p role="alert" className="error-msg">Private record unavailable or outside selected owner. No empty record inferred.</p>}
        {record && <PrivateRecord value={record} />}
      </section>
    </>}
  </div>
}

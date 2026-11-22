import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IS_PREVIEW, IS_PRIVATE_HOST, getRehearsalRequests, getUsageSummary, getUsageEvents } from '../api'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'
import type { RehearsalRequest, RehearsalRequestsResponse } from '../rehearsal/contracts'
import { dollars as sessionDollars, label } from '../rehearsal/format'
import { useRecordedRun } from '../rehearsal/useRecordedRun'
import agentFixture from '../preview/fixtures.json' with { type: 'json' }
import type { UsageEvent, UsageEventsResponse, UsageSummary, UsageSummaryResponse } from '../usage/contracts'

const EVENT_LIMIT = 50
const MAX_OFFSET = 2 ** 31 - 1
const AGENTS = agentFixture.agents.map(({ agent_id, name }) => ({ agent_id, name }))
const agentName = (id: string | null) => id === null ? 'Unattributed' : AGENTS.find(agent => agent.agent_id === id)?.name || id
const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 12 })
function dollars(value: string | null): string {
  if (value === null) return 'Unknown'
  const numeric = Number(value) // Display only; no dollar totals are added here.
  if (!Number.isFinite(numeric)) return `$${value}`
  if (numeric > 0 && numeric < 0.000000000001) return '<$0.000000000001'
  return USD.format(numeric)
}
const tokens = (value: number | null) => value === null ? 'Unknown' : value.toLocaleString('en-US')
function createdAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : `${date.toLocaleString('en-US', {
    timeZone: 'UTC', year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })} UTC`
}

type ReadState<T> = { key: string; data: T | null; loading: boolean; error: boolean }
function Breakdown({ title, groups }: { title: string; groups: (UsageSummary & { label: string })[] }) {
  return <section className="card" aria-label={title}>
    <h2 className="card-title">{title}</h2>
    {groups.length === 0 ? <p>No request groups for this filter.</p> : groups.map(group => <div key={group.label}>
      <h3>{group.label}</h3>
      <p className="usage-meta">{group.requests} requests · {group.failed_requests} failed · {group.unknown_cost_requests} cost unknown</p>
      <p>Reported subtotal: {dollars(group.reported_cost_usd)}<br />Estimated token-only subtotal: {dollars(group.estimated_cost_usd)}</p>
    </div>)}
  </section>
}
function CostCell({ event }: { event: UsageEvent }) {
  const source = event.pricing_snapshot?.source || event.pricing_source
  const asOf = event.pricing_snapshot?.as_of || event.pricing_as_of
  if (event.cost_status === 'unknown' || event.cost_usd === null) return <>
    <strong>Unknown</strong><div className="usage-meta">{event.cost_reason || 'Usage or pricing not available'}</div>
  </>
  return <>
    <strong>{dollars(event.cost_usd)}</strong>
    <div className="usage-meta">{event.cost_status === 'reported' ? 'Reported · provider total' : 'Estimated · token-only'}</div>
    {event.cost_status === 'estimated' && <div className="usage-meta">
      {source || 'Source not recorded'}{asOf ? ` · as of ${asOf}` : ''}
    </div>}
  </>
}

function FullCosts() {
  const [selection, setSelection] = useState({ agentId: '', offset: 0 })
  const [summaryRetry, setSummaryRetry] = useState(0)
  const [eventsRetry, setEventsRetry] = useState(0)
  const [summaryState, setSummaryState] = useState<ReadState<UsageSummaryResponse>>({ key: '', data: null, loading: true, error: false })
  const [eventsState, setEventsState] = useState<ReadState<UsageEventsResponse>>({ key: ':0', data: null, loading: true, error: false })
  const { agentId, offset } = selection
  const eventsKey = `${agentId}:${offset}`

  useEffect(() => {
    let cancelled = false
    setSummaryState({ key: agentId, data: null, loading: true, error: false })
    getUsageSummary(agentId || undefined).then(data => {
      if (!cancelled) setSummaryState({ key: agentId, data, loading: false, error: false })
    }).catch(() => {
      if (!cancelled) setSummaryState({ key: agentId, data: null, loading: false, error: true })
    })
    return () => { cancelled = true }
  }, [agentId, summaryRetry])

  useEffect(() => {
    let cancelled = false
    setEventsState({ key: eventsKey, data: null, loading: true, error: false })
    getUsageEvents(agentId || undefined, EVENT_LIMIT, offset).then(data => {
      if (!cancelled) setEventsState({ key: eventsKey, data, loading: false, error: false })
    }).catch(() => {
      if (!cancelled) setEventsState({ key: eventsKey, data: null, loading: false, error: true })
    })
    return () => { cancelled = true }
  }, [agentId, offset, eventsKey, eventsRetry])

  // Matching keys hide old data/errors immediately on a filter change, even
  // before effect cleanup. Cancelled promises can never restore stale results.
  const summaryCurrent = summaryState.key === agentId
  const eventsCurrent = eventsState.key === eventsKey
  const summaryLoading = !summaryCurrent || summaryState.loading
  const eventsLoading = !eventsCurrent || eventsState.loading
  const summaryError = summaryCurrent && summaryState.error
  const eventsError = eventsCurrent && eventsState.error
  const result = summaryCurrent && !summaryLoading && !summaryError ? summaryState.data : null
  const events = eventsCurrent && !eventsLoading && !eventsError ? eventsState.data : null
  const summary = result?.summary
  const previousDisabled = eventsLoading || !events || events.offset === 0
  const nextDisabled = eventsLoading || !events || events.offset + EVENT_LIMIT >= events.total || events.offset > MAX_OFFSET - EVENT_LIMIT

  return <div>
    <div className="page-header">
      <h1 className="page-title">Operating costs</h1>
      <p className="page-sub">Read-only visibility into recorded provider-request attempts and partial USD cost coverage.</p>
    </div>
    {IS_PREVIEW && <div className="notice">Simulated request examples — no actual spend is shown.</div>}
    <div className="notice">These request subtotals do not cover all operating costs: subscriptions, data-feed charges, infrastructure, and final account invoices are not included. Estimates cover tokens only; unknown requests may still incur charges.</div>
    <div className="usage-toolbar">
      <div className="input-group">
        <label className="input-label" htmlFor="usage-agent">Agent</label>
        <select className="select" id="usage-agent" value={agentId}
          onChange={event => setSelection({ agentId: event.target.value, offset: 0 })}>
          <option value="">All agents</option>
          {AGENTS.map(agent => <option key={agent.agent_id} value={agent.agent_id}>{agent.name}</option>)}
        </select>
      </div>
      <p className="usage-meta">All recorded times · USD · Request metadata only</p>
    </div>

    <section aria-label="Usage summary" aria-busy={summaryLoading}>
      {summaryLoading && <p role="status">Loading usage summary…</p>}
      {summaryError && <div className="error-msg" role="alert">Could not load usage summary. Retry to load recorded request subtotals.
        {' '}<button type="button" className="btn btn-ghost" onClick={() => setSummaryRetry(value => value + 1)}>Retry summary</button>
      </div>}
      {summary && <>
        {summary.requests === 0 && <p className="notice">No request events recorded for this filter yet.</p>}
        <div className="usage-metrics">
          <section className="card" aria-label="Reported subtotal">
            <h2 className="card-title">Reported subtotal</h2><strong>{dollars(summary.reported_cost_usd)}</strong>
            <p className="usage-meta">Provider-reported USD · {summary.reported_cost_requests} requests</p>
          </section>
          <section className="card" aria-label="Estimated token-only subtotal">
            <h2 className="card-title">Estimated token-only subtotal</h2><strong>{dollars(summary.estimated_cost_usd)}</strong>
            <p className="usage-meta">Explicit rate estimates · {summary.estimated_cost_requests} requests · Not a full provider invoice</p>
          </section>
          <section className="card" aria-label="Unknown cost requests">
            <h2 className="card-title">Unknown cost requests</h2><strong>{summary.unknown_cost_requests}</strong>
            <p className="usage-meta">Missing usage or rates is unknown, never assumed $0.</p>
          </section>
          <section className="card" aria-label="Request outcomes">
            <h2 className="card-title">Request outcomes</h2><strong>{summary.requests} attempts</strong>
            <p className="usage-meta">{summary.successful_requests} successful · {summary.failed_requests} failed · Retries counted separately</p>
          </section>
        </div>
        <section className="card" aria-label="Cost and token coverage">
          <h2 className="card-title">Cost and token coverage</h2>
          <p>{summary.reported_cost_requests + summary.estimated_cost_requests} of {summary.requests} requests have provider-reported or estimated costs; {summary.unknown_cost_requests} unknown.</p>
          <p>Usage reported for {summary.usage_known_requests} of {summary.requests} requests; {summary.usage_unknown_requests} have unknown usage.</p>
          <p className="usage-meta">Known token subtotals only — partial coverage. Individual token categories can be missing even when other usage is reported.</p>
          <p>Input: {tokens(summary.input_tokens)} · Output: {tokens(summary.output_tokens)} · Cached input: {tokens(summary.cached_input_tokens)} · Reasoning: {tokens(summary.reasoning_tokens)}</p>
        </section>
        {result?.groups_truncated && <p className="notice">Breakdowns are limited to 100 groups per category. Some groups are omitted; the overall summary still covers all matching requests.</p>}
        <div className="usage-breakdown">
          <Breakdown title="By provider" groups={result!.by_provider.map(group => ({ ...group, label: group.provider }))} />
          <Breakdown title="By activity" groups={result!.by_activity.map(group => ({ ...group, label: group.activity }))} />
          <Breakdown title="By agent" groups={result!.by_agent.map(group => ({ ...group, label: agentName(group.agent_id) }))} />
        </div>
      </>}
    </section>

    <section className="card" aria-label="Request events" aria-busy={eventsLoading}>
      <h2 className="card-title">Request events</h2>
      <p className="usage-meta">Up to 50 recorded HTTP attempts per page. Failed attempts can have unknown costs. No prompts or response content are displayed.</p>
      {eventsLoading && <p role="status">Loading request events…</p>}
      {eventsError && <div className="error-msg" role="alert">Could not load request events. Retry to load recorded attempts.
        {' '}<button type="button" className="btn btn-ghost" onClick={() => setEventsRetry(value => value + 1)}>Retry events</button>
      </div>}
      {events && (events.events.length === 0 ? <p>No request events on this page.</p> :
        <div className="usage-table-wrap" tabIndex={0} role="region" aria-label="Scrollable request metadata">
          <table className="usage-table">
            <thead><tr>
              <th scope="col">Time (UTC)</th><th scope="col">Agent / Activity</th><th scope="col">Provider / Model</th>
              <th scope="col">Attempt / Outcome</th><th scope="col">Input tokens</th><th scope="col">Output tokens</th>
              <th scope="col">Cached input</th><th scope="col">Reasoning</th><th scope="col">Cost (USD)</th>
            </tr></thead>
            <tbody>{events.events.map(event => <tr key={event.event_id}>
              <td><time dateTime={event.created_at}>{createdAt(event.created_at)}</time><div className="usage-meta">{event.duration_ms} ms</div></td>
              <td>{agentName(event.agent_id)}<div className="usage-meta">{event.activity}</div></td>
              <td>{event.provider}<div className="usage-meta">{event.model}</div>
                {event.response_model && event.response_model !== event.model && <div className="usage-meta">Response model: {event.response_model}</div>}
              </td>
              <td>Attempt {event.attempt}<div>{event.outcome}</div><div className="usage-meta">{event.http_status === null ? 'HTTP status unknown' : `HTTP ${event.http_status}`}</div></td>
              <td>{tokens(event.input_tokens)}</td><td>{tokens(event.output_tokens)}</td>
              <td>{tokens(event.cached_input_tokens)}</td><td>{tokens(event.reasoning_tokens)}</td>
              <td><CostCell event={event} /></td>
            </tr>)}</tbody>
          </table>
        </div>)}
      <div className="usage-toolbar" aria-label="Request events pagination">
        <button type="button" className="btn btn-ghost" disabled={previousDisabled}
          onClick={() => { if (events) setSelection({ agentId, offset: Math.max(0, events.offset - EVENT_LIMIT) }) }}>Previous events</button>
        {events && <span className="usage-meta">{events.events.length ? events.offset + 1 : 0}–{events.events.length ? Math.min(events.offset + events.events.length, events.total) : 0} of {events.total}</span>}
        <button type="button" className="btn btn-ghost" disabled={nextDisabled}
          onClick={() => { if (events) setSelection({ agentId, offset: Math.min(MAX_OFFSET, events.offset + EVENT_LIMIT) }) }}>Next events</button>
      </div>
    </section>
  </div>
}

const MEMBER_LIMIT = 50
type MemberRead = { status: 'ok'; data: RehearsalRequestsResponse } | { status: 'error' }
type MembersState = { key: string; reads: Record<string, MemberRead> | null }

// Sums reservations for display only. One event without a readable reservation makes the sum Unavailable.
function reservedSum(events: RehearsalRequest[]): string {
  let total = 0
  for (const event of events) {
    if (typeof event.reserved_usd !== 'string') return 'Unavailable'
    const value = Number(event.reserved_usd)
    if (!Number.isFinite(value)) return 'Unavailable'
    total += value
  }
  return sessionDollars(total.toFixed(12))
}
const costStatus = (event: RehearsalRequest) => event.usage?.cost_status ?? event.cost_status ?? 'unknown'

// Private host: only the session API (GET /api/rehearsals*) is served, so costs come from session records.
function PrivateCosts() {
  const { runs, runsLoading, runsError, runId, selectRun, detail, detailLoading, detailError, refresh } = useRecordedRun()
  const [members, setMembers] = useState<MembersState>({ key: '', reads: null })
  const [memberRetry, setMemberRetry] = useState(0)
  const membersKey = JSON.stringify([runId, memberRetry])
  const refreshAll = () => { refresh(); setMemberRetry(value => value + 1) }

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    setMembers({ key: membersKey, reads: null })
    Promise.allSettled(REHEARSAL_AGENTS.map(agent => Promise.resolve().then(() => getRehearsalRequests(runId, agent.id, MEMBER_LIMIT, 0)))).then(results => {
      if (cancelled) return
      const reads: Record<string, MemberRead> = {}
      results.forEach((result, index) => {
        const agent = REHEARSAL_AGENTS[index]
        const valid = result.status === 'fulfilled' && result.value.run_id === runId && Array.isArray(result.value.events)
          && Number.isFinite(result.value.total) && result.value.events.every(event => event.agent_id === agent.id)
        reads[agent.id] = valid ? { status: 'ok', data: result.value } : { status: 'error' }
      })
      setMembers({ key: membersKey, reads })
    })
    return () => { cancelled = true }
  }, [runId, membersKey])

  const reads = runId && members.key === membersKey ? members.reads : null
  const membersLoading = !!runId && !reads
  const memberFailed = !!reads && Object.values(reads).some(read => read.status === 'error')
  const run = detail?.run

  return <div>
    <header className="page-header">
      <h1 className="page-title">Operating costs</h1>
      <p className="page-sub">Per-session request costs recorded on this server</p>
    </header>
    <div className="notice" role="note">This server keeps session records only. These are the request costs a session recorded; subscriptions, data feeds, infrastructure and invoices are not included.</div>
    <div className="usage-toolbar">
      <div className="input-group">
        <label className="input-label" htmlFor="costs-run">Run</label>
        <select className="select" id="costs-run" value={runId ?? ''} disabled={!runs?.runs.length}
          onChange={event => selectRun(event.target.value || null)}>
          {!runs?.runs.length && <option value="">No run selected</option>}
          {runs?.runs.map(value => <option key={value.run_id} value={value.run_id}>{value.run_id.slice(0, 8)} · {label(value.status)} · {value.mode}</option>)}
        </select>
      </div>
      <button type="button" className="btn btn-ghost" onClick={refreshAll}>Refresh reads</button>
    </div>
    {runsLoading && <p role="status">Loading runs…</p>}
    {runsError && <p role="alert" className="error-msg">Run list unavailable. A failed read is not an empty run list.</p>}
    {runs?.runs.length === 0 && <div className="card">
      <p>No session runs recorded on this server yet.</p>
      <p className="rehearsal-meta">Runs are started from the CLI (scripts/rehearsal.py) as the paradoxtrader user; see deploy/README.md step 7.</p>
    </div>}
    {detailLoading && <p role="status">Loading run costs…</p>}
    {detailError && <p role="alert" className="error-msg">Run summary unavailable. A failed read is not a zero cost.</p>}
    {run && <section className="card" aria-label="Run cost summary">
      <h2 className="card-title">Run {run.run_id.slice(0, 8)} · {label(run.status)}</h2>
      <dl className="rehearsal-metrics">
        <div><dt>Request admissions</dt><dd>{run.request_count} / {run.limits.max_requests}</dd></div>
        <div><dt>Counted against the budget</dt><dd>{sessionDollars(run.counted_usd ?? run.reserved_usd)} / {sessionDollars(run.limits.budget_usd)}</dd></div>
        <div><dt>Known cost</dt><dd>{sessionDollars(run.known_cost_usd)}</dd></div>
        <div><dt>Reported subtotal</dt><dd>{sessionDollars(run.reported_cost_usd)}</dd></div>
        <div><dt>Estimated subtotal</dt><dd>{sessionDollars(run.estimated_cost_usd)}</dd></div>
        <div><dt>Unknown-cost requests</dt><dd>{run.unknown_cost_requests}</dd></div>
      </dl>
      <p className="usage-meta">Missing costs are unknown, not free; reservations are not an invoice.</p>
    </section>}
    {runId && <section className="card" aria-label="Costs per member" aria-busy={membersLoading}>
      <h2 className="card-title">Costs per member</h2>
      <p className="usage-meta">Reads the first {MEMBER_LIMIT} recorded requests per member. Status counts and reserved sums cover the shown requests only; a request without a recorded cost status counts as unknown.</p>
      {membersLoading && <p role="status">Loading member requests…</p>}
      {memberFailed && <p role="alert" className="error-msg">Some member request reads failed. A failed read is not zero requests.</p>}
      {reads && <div className="rehearsal-table-wrap" role="region" aria-label="Member cost table" tabIndex={0}>
        <table className="rehearsal-table">
          <thead><tr>
            <th scope="col">Member</th><th scope="col">Requests</th><th scope="col">Reserved</th>
            <th scope="col">Reported</th><th scope="col">Estimated</th><th scope="col">Unknown</th>
          </tr></thead>
          <tbody>{REHEARSAL_AGENTS.map(agent => {
            const read = reads[agent.id]
            if (!read || read.status === 'error') return <tr key={agent.id}>
              <th scope="row">{agent.name}</th><td>Unavailable</td><td>Unavailable</td><td>Unavailable</td><td>Unavailable</td><td>Unavailable</td>
            </tr>
            const { events, total } = read.data
            const count = (status: string) => events.filter(event => costStatus(event) === status).length
            return <tr key={agent.id}>
              <th scope="row">{agent.name}</th>
              <td>{total}{total > events.length && <div className="usage-meta">first {events.length} shown</div>}</td>
              <td>{reservedSum(events)}</td>
              <td>{count('reported')}</td><td>{count('estimated')}</td><td>{count('unknown')}</td>
            </tr>
          })}</tbody>
        </table>
      </div>}
      <Link className="btn btn-ghost" to="/rehearsal">Request details per member</Link>
    </section>}
  </div>
}

export default function Costs() {
  return IS_PRIVATE_HOST ? <PrivateCosts /> : <FullCosts />
}

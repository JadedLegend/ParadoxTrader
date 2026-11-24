import { useEffect, useRef, useState } from 'react'
import { getHeartbeat, type HeartbeatCalls, type HeartbeatView, type HeartbeatWake } from '../api'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'

// The heartbeat page (docs/specs/HEARTBEAT_PAGE.md): read-only. It never wakes,
// pauses or changes anything, and shows no key and no agent's private notes.

const REFRESH_MS = 60_000
const NAMES: Record<string, string> = Object.fromEntries(REHEARSAL_AGENTS.map(agent => [agent.id, agent.name]))
const agentName = (id: string) => NAMES[id] ?? id

function clock(iso: string | null | undefined) {
  if (!iso) return ''
  const moment = new Date(iso)
  return Number.isNaN(moment.getTime()) ? '' : moment.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function money(value: string | undefined) {
  const amount = Number(value)
  if (value === undefined || !Number.isFinite(amount)) return 'Unavailable'
  return `$${amount < 0.01 && amount > 0 ? amount.toFixed(4) : amount.toFixed(2)}`
}

function nowLine(view: HeartbeatView) {
  const reason = view.reason ?? ''
  if (reason.startsWith('running')) {
    const next = Object.entries(view.next_wake_by_agent ?? {}).sort((a, b) => a[1].localeCompare(b[1]))[0]
    return { tone: 'ok', text: next ? `Awake. Next wake ${clock(next[1])}, ${agentName(next[0])}.` : 'Awake.' }
  }
  if (reason === 'paused') return { tone: 'warn', text: 'Paused. No one wakes until the heartbeat is resumed.' }
  if (reason.startsWith('clock-only')) return { tone: 'warn', text: 'Clock-only. Wake times are kept, but no one is woken.' }
  if (reason.includes('key is not set')) return { tone: 'fail', text: 'No one can wake: the OpenRouter key is not set.' }
  if (reason.includes('budget is spent')) return { tone: 'warn', text: "Today's budget is spent. Wakes resume tomorrow." }
  if (reason.startsWith('quiet')) return { tone: 'ok', text: 'Quiet. No more wakes today.' }
  if (reason.startsWith("today's day could not open")) {
    return { tone: 'fail', text: `No one can wake: today's day could not open (${reason.slice(28)}). It is retried every minute.` }
  }
  if (reason.startsWith("today's day is")) return { tone: 'warn', text: `Today's run is ${reason.slice(15)}. No more wakes today.` }
  return { tone: 'warn', text: reason }
}

const OUTCOME: Record<string, string> = {
  woke: 'Woke', missed: 'Missed', blocked: 'Blocked', over_budget: 'Budget spent',
  not_started: 'Did not start', day_stopped: 'Day stopped',
}

function outcome(wake: HeartbeatWake) {
  if (wake.outcome === 'woke' && wake.wake_status && wake.wake_status !== 'completed') {
    return { tone: 'fail', text: wake.wake_status === 'uncertain' ? 'Unsure' : 'Failed' }
  }
  return { tone: wake.outcome === 'woke' ? 'ok' : 'warn', text: OUTCOME[wake.outcome] ?? wake.outcome }
}

function callsText(calls: HeartbeatCalls | null | undefined) {
  if (!calls || calls.open + calls.settled === 0) return ''
  const results = ([['right', calls.right], ['wrong', calls.wrong], ['flat', calls.flat], ['unsettled', calls.unsettled]] as const)
    .filter(([, count]) => count > 0).map(([name, count]) => `${count} ${name}`)
  return `${calls.open} open · ${calls.settled} settled${results.length ? ` (${results.join(', ')})` : ''}`
}

const choicesText = (wake: HeartbeatWake | null) => wake && wake.choices.length > 0 ? wake.choices.join(', ') : ''

export default function Heartbeat() {
  const [view, setView] = useState<HeartbeatView | null>(null)
  const [error, setError] = useState('')
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    const load = () => getHeartbeat()
      .then(value => { if (alive.current) { setView(value); setError(''); setLoadedAt(new Date()) } })
      .catch(() => { if (alive.current) setError('The heartbeat could not be read just now. This page tries again every minute.') })
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => { alive.current = false; window.clearInterval(timer) }
  }, [])

  const header = <header className="page-header">
    <h1 className="page-title">Heartbeat</h1>
    <p className="page-sub">Who woke today, what they chose, what it cost, and anything that needs a look.
      {loadedAt && <> Updated {clock(loadedAt.toISOString())}.</>}</p>
  </header>

  if (!view) return <div>{header}{error ? <div className="error-msg" role="alert">{error}</div>
    : <p className="loading" role="status">Reading the heartbeat…</p>}</div>
  if (!view.available) return <div>{header}
    {error && <div className="error-msg mb-16" role="alert">{error} Showing the last reading.</div>}<div className="card"><p className="empty-state">{view.reason}</p></div></div>

  const now = nowLine(view)
  const today = view.today
  const counts = today?.slot_outcomes ?? {}
  const wakes = view.wakes ?? []
  const woke = wakes.filter(w => w.outcome === 'woke')
  const failed = woke.filter(w => w.wake_status && w.wake_status !== 'completed').length
  const problems = view.problems ?? []

  return (
    <div className="heartbeat-page">
      {header}
      {error && <div className="error-msg mb-16" role="alert">{error} Showing the last reading.</div>}

      <section className={`card mb-16 heartbeat-now heartbeat-${now.tone}`} aria-labelledby="hb-now">
        <h2 className="card-title" id="hb-now">Now</h2>
        <p className="heartbeat-now-text" role="status">{now.text}</p>
        {view.choices_per_wake !== undefined && view.choices_per_wake > 1 &&
          <p className="settings-note">Each wake allows up to {view.choices_per_wake} choices.</p>}
      </section>

      <div className="grid-3 mb-16">
        <div className="stat-tile">
          <div className="stat-label">Wakes today</div>
          <div className="stat-value">{woke.length}</div>
          <div className="stat-sub">{failed} failed · {counts.missed ?? 0} missed{counts.blocked ? ` · ${counts.blocked} blocked` : ''}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">Spent today</div>
          <div className="stat-value">{money(today?.spent_usd)}</div>
          <div className="stat-sub">of {money(today?.daily_budget_usd)} a day{today?.spent_complete === false ? ' · some costs not reported yet' : ''}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">Counted against the budget</div>
          <div className="stat-value">{money(today?.counted_usd)}</div>
          <div className="stat-sub">Actual charges, plus worst-case holds not yet charged</div>
        </div>
      </div>

      <section className="card mb-16" aria-labelledby="hb-problems">
        <h2 className="card-title" id="hb-problems">Needs a look</h2>
        {problems.length === 0 ? <p className="settings-note">Nothing failed today.</p> :
          <ul className="settings-check-list">{problems.map(problem => <li key={`${problem.agent_id}-${problem.scheduled_at}`} className="check-fail">
            <span className="check-mark" aria-hidden="true">✕</span>
            <span><strong>{problem.agent_id ? agentName(problem.agent_id) : 'The whole day'}</strong> at {clock(problem.scheduled_at)}: {problem.note ?? 'failed without a reason recorded'}</span>
          </li>)}</ul>}
      </section>

      <section className="card mb-16" aria-labelledby="hb-agents">
        <h2 className="card-title" id="hb-agents">Each agent</h2>
        <div className="usage-table-wrap" tabIndex={0} role="region" aria-label="Each agent's last and next wake">
          <table className="usage-table heartbeat-table">
            <thead><tr><th scope="col">Agent</th><th scope="col">Last wake</th><th scope="col">Chose</th><th scope="col">Next wake</th><th scope="col">Calls</th><th scope="col">Notebook</th></tr></thead>
            <tbody>{(view.agents ?? []).map(agent => {
              const result = agent.last_wake ? outcome(agent.last_wake) : null
              return <tr key={agent.agent_id}>
                <td>{agentName(agent.agent_id)}</td>
                <td>{agent.last_wake && result ? <>{clock(agent.last_wake.scheduled_at)} <span className={`heartbeat-badge heartbeat-${result.tone}`}>{result.text}</span></>
                  : <span className="usage-meta">Not yet today</span>}</td>
                <td>{choicesText(agent.last_wake) || <span className="usage-meta">None</span>}</td>
                <td>{agent.next_wake ? clock(agent.next_wake) : <span className="usage-meta">Tomorrow</span>}</td>
                <td>{callsText(agent.calls) || <span className="usage-meta">None yet</span>}</td>
                <td>{typeof agent.notebook_chars === 'number' && agent.notebook_chars > 0 && view.notebook_capacity
                  ? `${agent.notebook_chars.toLocaleString()} of ${view.notebook_capacity.toLocaleString()} characters`
                  : <span className="usage-meta">Empty</span>}</td>
              </tr>
            })}</tbody>
          </table>
        </div>
      </section>

      <section className="card mb-16" aria-labelledby="hb-wakes">
        <h2 className="card-title" id="hb-wakes">Today's wakes</h2>
        {wakes.length === 0 ? <p className="settings-note">No one has woken yet today.</p> :
          <div className="usage-table-wrap" tabIndex={0} role="region" aria-label="Today's wakes, newest first">
            <table className="usage-table heartbeat-table">
              <thead><tr><th scope="col">Time</th><th scope="col">Agent</th><th scope="col">Outcome</th><th scope="col">Chose</th><th scope="col">Model</th></tr></thead>
              <tbody>{[...wakes].reverse().map(wake => {
                const result = outcome(wake)
                return <tr key={`${wake.agent_id}-${wake.scheduled_at}`}>
                  <td>{clock(wake.scheduled_at)}</td>
                  <td>{agentName(wake.agent_id)}</td>
                  <td><span className={`heartbeat-badge heartbeat-${result.tone}`}>{result.text}</span>
                    {wake.note && <div className="usage-meta">{wake.note}</div>}</td>
                  <td>{choicesText(wake) || <span className="usage-meta">None</span>}</td>
                  <td className="mono">{wake.model ?? <span className="usage-meta">Unknown</span>}</td>
                </tr>
              })}</tbody>
            </table>
          </div>}
      </section>

      <section className="card mb-16" aria-labelledby="hb-window">
        <h2 className="card-title" id="hb-window">What the agents see</h2>
        <p className="settings-help">The window lines exactly as they are quoted to the agents on every choice.</p>
        {(view.window?.lines ?? []).length > 0 && <ul className="heartbeat-lines">
          {(view.window?.lines ?? []).map(line => <li key={line}>{line}</li>)}
        </ul>}
        <ul className="settings-check-list mt-16">{(view.window?.feeds ?? []).map(feed =>
          <li key={feed.feed} className={feed.status === 'ok' ? 'check-ok' : feed.status === 'unchecked' ? 'check-idle' : 'check-warn'}>
            <span className="check-mark" aria-hidden="true">{feed.status === 'ok' ? '✓' : feed.status === 'unchecked' ? '–' : '!'}</span>
            <span><strong>{feed.feed}</strong> {feed.status === 'unchecked' ? 'Not read yet.' : feed.status === 'ok' ? 'Working.' : 'Unavailable.'}
              {feed.detail && <> {feed.detail.charAt(0).toUpperCase() + feed.detail.slice(1)}.</>}
              {feed.checked_at && <span className="settings-note"> Last read {clock(feed.checked_at)}.</span>}</span>
          </li>)}</ul>
      </section>
    </div>
  )
}

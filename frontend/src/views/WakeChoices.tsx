import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { IS_PREVIEW, IS_PRIVATE_HOST } from '../api'
import ChoiceDialog from '../components/ChoiceDialog'
import { fixture } from '../preview/readFixture'
import { makeReceipt } from '../preview/choiceState'
import type { DemonstrationReceipt } from '../preview/choiceState'
import type { ActionChoice } from '../data/contracts'

const SCENARIOS = [
  { id: 'phase0', label: 'Individual · phase 0' },
  { id: 'phase1', label: 'Community · phase 1' },
  { id: 'phase3', label: 'Council · phase 3' },
  { id: 'interval', label: 'Quiet interval' },
]

export default function WakeChoices() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('agent')
  const agent = fixture.agents.find(item => item.agent_id === requested) ?? fixture.agents[0]
  const [scenario, setScenario] = useState('phase0')
  const [open, setOpen] = useState(false)
  const [receipts, setReceipts] = useState<DemonstrationReceipt[]>([])
  const window = fixture.windows[agent.agent_id][scenario]

  if (IS_PRIVATE_HOST) return (
    <section><div className="page-header"><h1 className="page-title">Wake Choices</h1></div>
      <p className="notice">The choice-window demonstration is available in fixture preview only. On this host, the actions each recorded wake offered and their reservation ceilings are shown under Sessions: open a run and use Read decision context.</p>
      <Link className="btn btn-ghost" to="/rehearsal">Open Sessions</Link>
    </section>
  )
  if (!IS_PREVIEW) return (
    <section><div className="page-header"><h1 className="page-title">Wake Choices</h1></div>
      <p className="notice">The choice-window demonstration is available in fixture preview only. Connected choice observation and timer controls have not been implemented.</p>
      <Link className="btn btn-ghost" to="/agents">View agents</Link>
    </section>
  )

  const choose = (choice: ActionChoice) => {
    const receipt = makeReceipt(agent.agent_id, window, choice, new Date().toISOString())
    setReceipts(previous => [receipt, ...previous].slice(0, 12))
    setOpen(false)
  }

  return (
    <section>
      <div className="page-header">
        <span className="eyebrow">Community · work and exploration</span>
        <h1 className="page-title">Room to choose</h1>
        <p className="page-sub">See what an agent can choose at a wake. Trading work, exploration, and quiet rest share the same window.</p>
      </div>
      <div className="notice">These are runtime-derived example menus and sample resource states—not agent activity or paper-trading results. No schedule is running.</div>
      <div className="choice-workspace">
        <aside className="card choice-roster" aria-label="Choose an agent">
          <h2 className="card-title">Seven individual perspectives</h2>
          {fixture.agents.map(item => (
            <button key={item.agent_id} type="button" className={`roster-item ${item.agent_id === agent.agent_id ? 'selected' : ''}`}
              aria-pressed={item.agent_id === agent.agent_id} onClick={() => { setParams({ agent: item.agent_id }); setOpen(false) }}>
              <strong>{item.name}</strong><small>{item.epistemic_role}</small>
            </button>
          ))}
        </aside>
        <div className="choice-main">
          <div className="card">
            <div className="flex-between choice-profile"><div><span className="eyebrow">Current example</span><h2>{agent.name}</h2></div><span className="fixture-pill">Fixture</span></div>
            <p className="page-sub">{agent.core_drive}</p>
            <label className="input-label scenario-label" htmlFor="wake-scenario">Inspect a scenario</label>
            <select id="wake-scenario" className="select" value={scenario} onChange={event => { setScenario(event.target.value); setOpen(false) }}>
              {SCENARIOS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <div className="window-summary"><span>{window.in_interval ? 'Quiet interval example' : `Phase ${window.phase} example`}</span><span>{window.hrv.toFixed(1)} / {window.max_hrv.toFixed(1)} simulated HRV</span></div>
            <p className="page-sub">{window.in_interval
              ? 'Quiet recovery without a picker, journal, or account lookup in the actual interval path.'
              : 'Up to five affordable options, including rest. The current runtime randomly samples a menu; this fixture shows one reproducible example.'}</p>
            <button type="button" className="btn btn-primary mt-16" onClick={() => setOpen(true)}>Open example choice window</button>
          </div>
          <div className="card">
            <h2 className="card-title">A flexible balance</h2>
            <p>Roughly half active attention toward the trading work; room beyond it for curiosity, community, and unfamiliar interests. Treat this as a flexible balance.</p>
            <p className="page-sub mt-8">HRV is a simulated activity balance—not money, provider credits, or a judgment of accomplishment. Financial support comes from the creator’s available funding.</p>
          </div>
          <div className="card">
            <h2 className="card-title">Wake rhythm · planned</h2>
            <p className="page-sub">The proposed active and quieter windows, optional overnight requests, and shared routines come in a later scheduling slice. None are activated here.</p>
          </div>
        </div>
      </div>
      <div className="card mt-16">
        <div className="flex-between receipt-heading"><h2 className="card-title">Your local demonstrations</h2><button type="button" className="btn btn-ghost" disabled={!receipts.length} onClick={() => setReceipts([])}>Clear</button></div>
        <p className="page-sub">Session-only operator selections. Reloading clears them. These are not agent decisions, journals, forecasts, or orders; fixture resource state stays unchanged.</p>
        <div aria-live="polite" role="status">
          {receipts.length === 0 ? <p className="empty-state">No demonstrations yet. Opening and closing a window does not record anything.</p> :
            receipts.map((receipt, index) => <div className="receipt-row" key={`${receipt.selected_at}-${index}`}>
              <div><strong>{fixture.agents.find(item => item.agent_id === receipt.agent_id)?.name}</strong><p>{receipt.label}</p><small>Operator demonstration · {new Date(receipt.selected_at).toLocaleTimeString()}</small></div>
              <div className="receipt-estimate"><span>{receipt.hrv_before.toFixed(1)} → {receipt.hrv_estimate_after.toFixed(1)}</span><small>Simulated HRV estimate only</small></div>
            </div>)}
        </div>
      </div>
      {open && <ChoiceDialog key={`${agent.agent_id}-${scenario}`} name={agent.name} window={window} onChoose={choose} onClose={() => setOpen(false)} />}
    </section>
  )
}

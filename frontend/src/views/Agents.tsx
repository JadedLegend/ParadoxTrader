import { useCallback, useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  IS_PREVIEW, IS_PRIVATE_HOST, getAgents, getAgentJournal, getAgentEpisodes, wakeAgent,
  getSelfDefinition, updateSelfDefinition,
  getAllPositions, writeJournalEntry, writeInnermostEntry,
} from '../api'
import type { PositionSnapshot } from '../data/contracts'
import { useRecordedRun } from '../rehearsal/useRecordedRun'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'
import type { RehearsalJob } from '../rehearsal/contracts'
import { label, text } from '../rehearsal/format'

const AGENT_COLORS: Record<string, string> = {
  tempest: '#7c6af7', siren: '#f6ad55', alchemist: '#68d391',
  weaver: '#4fd1c5', oracle: '#90cdf4', shadow: '#fc8181', paradox_hunter: '#b794f4',
}

function HRVBar({ hrv, max, interval }: { hrv?: number; max?: number; interval: boolean }) {
  if (typeof hrv !== 'number' || !Number.isFinite(hrv) || typeof max !== 'number' || !Number.isFinite(max) || max <= 0) {
    return <div style={{fontSize:11, color:'var(--text3)', marginTop:8}}>HRV not initialized — value unavailable</div>
  }
  const pct = Math.max(0, Math.min(100, (hrv / max) * 100))
  const color = interval ? 'var(--text3)' : pct > 60 ? 'var(--success)' : pct > 30 ? 'var(--accent3)' : 'var(--danger)'
  return (
    <div style={{display:'flex', alignItems:'center', gap:8, marginTop:8}}>
      <div style={{flex:1, height:5, background:'var(--bg3)', borderRadius:3, overflow:'hidden'}}>
        <div style={{width:`${pct}%`, height:'100%', background:color, borderRadius:3, transition:'width 0.4s'}} />
      </div>
      <span style={{fontSize:11, color:'var(--text3)', fontFamily:'var(--mono)'}}>{hrv.toFixed(0)} / {max}</span>
    </div>
  )
}

function positionNumber(value?: string) {
  if (value == null || String(value).trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function PositionCard({ agentId, agentName, snapshot }: { agentId: string; agentName: string; snapshot?: PositionSnapshot }) {
  const color = AGENT_COLORS[agentId] || 'var(--accent)'
  const holdings = snapshot?.status === 'ok' && Array.isArray(snapshot.positions) ? snapshot.positions : null
  const pnls = holdings?.map(p => positionNumber(p.unrealized_pl))
  const netPnl = pnls && pnls.length > 0 && pnls.every(p => p !== null)
    ? pnls.reduce<number>((sum, p) => sum + (p as number), 0) : null
  const borderColor = netPnl === null ? 'var(--border)' : netPnl >= 0 ? 'var(--success)' : 'var(--danger)'
  const stateMessage = !snapshot ? 'Position state unknown — no snapshot received.'
    : snapshot.status === 'not_configured' ? 'Broker account not configured — holdings unknown.'
    : snapshot.status === 'error' ? 'Position lookup failed — holdings unknown. Refresh to retry.'
    : !holdings ? 'Position state unknown — snapshot is incomplete.'
    : holdings.length === 0 ? 'Confirmed empty — no open positions in this snapshot.' : null

  return (
    <div style={{border:`1.5px solid ${borderColor}`, borderRadius:8, padding:'10px 14px', marginBottom:8, background:'var(--bg2)'}}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', gap:8, marginBottom:6}}>
        <span style={{fontSize:12, fontWeight:700, color}}>{agentName}</span>
        {holdings && holdings.length > 0 && <span style={{fontSize:11, color:netPnl === null ? 'var(--text3)' : borderColor, fontFamily:'var(--mono)'}}>
          {netPnl === null ? 'P&L unavailable' : `${netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}`}
        </span>}
      </div>
      {stateMessage && <div role={snapshot?.status === 'error' ? 'alert' : undefined} style={{fontSize:11, color:'var(--text3)'}}>{stateMessage}</div>}
      {holdings?.map((p, i) => {
        const price = positionNumber(p.avg_entry_price)
        const pnl = positionNumber(p.unrealized_pl)
        return <div key={`${p.symbol}-${i}`} style={{display:'flex', justifyContent:'space-between', flexWrap:'wrap', gap:6, fontSize:11, color:'var(--text2)', marginTop:3}}>
          <span style={{fontFamily:'var(--mono)', fontWeight:600}}>{p.symbol}</span>
          <span style={{color:'var(--text3)'}}>{p.qty || 'Qty unavailable'} @ {price === null ? 'entry price unavailable' : price.toFixed(2)}</span>
          <span style={{color:'var(--text3)'}}>P&L {pnl === null ? 'unavailable' : `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`}</span>
        </div>
      })}
      {snapshot?.observed_at && <div style={{fontSize:10, color:'var(--text3)', marginTop:6}}>Observed {new Date(snapshot.observed_at).toLocaleString()}</div>}
    </div>
  )
}

function JournalSidebar({ agentId, onJournalWritten }: { agentId: string; onJournalWritten: () => void }) {
  const [journalText, setJournalText] = useState('')
  const [innermostText, setInnermostText] = useState('')
  const [jStatus, setJStatus] = useState<string | null>(null)
  const [iStatus, setIStatus] = useState<string | null>(null)
  const [jError, setJError] = useState(false)
  const [iError, setIError] = useState(false)
  const [jCooldown, setJCooldown] = useState(0)
  const [iCooldown, setICooldown] = useState(0)
  const [jPending, setJPending] = useState(false)
  const [iPending, setIPending] = useState(false)
  const jTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const iTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const alive = useRef(true)

  const clearCooldowns = useCallback(() => {
    if (jTimer.current) clearInterval(jTimer.current)
    if (iTimer.current) clearInterval(iTimer.current)
  }, [])

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      clearCooldowns()
    }
  }, [clearCooldowns])

  const startCooldown = (seconds: number, setter: React.Dispatch<React.SetStateAction<number>>, timer: React.MutableRefObject<ReturnType<typeof setInterval> | null>) => {
    setter(seconds)
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(() => {
      setter(prev => {
        if (prev <= 1) { if (timer.current) clearInterval(timer.current); timer.current = null; return 0 }
        return prev - 1
      })
    }, 1000)
  }

  const handleJournal = async () => {
    if (IS_PREVIEW || !journalText.trim() || jCooldown > 0 || jPending) return
    setJPending(true)
    setJError(false)
    try {
      await writeJournalEntry(agentId, journalText.trim())
      if (!alive.current) return
      setJournalText('')
      setJStatus('Operator entry written.')
      startCooldown(180, setJCooldown, jTimer)
      onJournalWritten()
    } catch (err: any) {
      if (!alive.current) return
      setJError(true)
      const detail = String(err?.response?.data?.detail || '')
      if (detail.includes('Cooldown')) {
        const match = detail.match(/(\d+) seconds/)
        const secs = match ? parseInt(match[1]) : 180
        startCooldown(secs, setJCooldown, jTimer)
        setJStatus(`Journal cooldown: ${secs}s remaining. Try again afterwards.`)
      } else setJStatus('Could not write the journal entry. Your draft is retained; check the connection before retrying.')
    } finally { if (alive.current) setJPending(false) }
  }

  const handleInnermost = async () => {
    if (IS_PREVIEW || !innermostText.trim() || iCooldown > 0 || iPending) return
    setIPending(true)
    setIError(false)
    try {
      await writeInnermostEntry(agentId, innermostText.trim())
      if (!alive.current) return
      setInnermostText('')
      setIStatus('Entry stored. Storage is not an access-control guarantee.')
      startCooldown(180, setICooldown, iTimer)
    } catch (err: any) {
      if (!alive.current) return
      setIError(true)
      const detail = String(err?.response?.data?.detail || '')
      if (detail.includes('Cooldown')) {
        const match = detail.match(/(\d+) seconds/)
        const secs = match ? parseInt(match[1]) : 180
        startCooldown(secs, setICooldown, iTimer)
        setIStatus(`Innermost cooldown: ${secs}s remaining. Try again afterwards.`)
      } else setIStatus('Could not store the innermost entry. Your draft is retained; check the connection before retrying.')
    } finally { if (alive.current) setIPending(false) }
  }

  return (
    <div style={{marginTop:20, borderTop:'1px solid var(--border)', paddingTop:16}}>
      {IS_PREVIEW && <div className="notice">Preview is read-only. Journal and innermost writes are disabled.</div>}
      <div style={{marginBottom:16}}>
        <div style={{fontSize:12, fontWeight:600, color:'var(--text2)', marginBottom:6}}>Write in journal {jCooldown > 0 && <span>— cooldown {jCooldown}s</span>}</div>
        <p style={{fontSize:11, color:'var(--text3)', lineHeight:1.6}}>This is an operator-entered note, not an agent-generated self-review.</p>
        <textarea aria-label="Operator journal entry" disabled={IS_PREVIEW || jPending} value={journalText} onChange={e => setJournalText(e.target.value)} placeholder="What is alive in you right now?"
          style={{width:'100%', minHeight:80, background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, color:'var(--text)', fontSize:12, padding:'8px 10px', resize:'vertical', fontFamily:'inherit', boxSizing:'border-box'}} />
        {jStatus && <div role={jError ? 'alert' : 'status'} className={jError ? 'error-msg' : undefined} style={{fontSize:11}}>{jStatus}</div>}
        <button className="btn btn-ghost" style={{fontSize:11, marginTop:6}} onClick={handleJournal} disabled={IS_PREVIEW || jCooldown > 0 || jPending || !journalText.trim()}>{jPending ? 'Writing...' : 'Write'}</button>
      </div>
      <div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:6, fontStyle:'italic'}}>Innermost {iCooldown > 0 && <span>— cooldown {iCooldown}s</span>}</div>
        <p style={{fontSize:11, color:'var(--text3)', lineHeight:1.6}}>Stored locally by the connected backend, not retrieved by this view. This is not an access-control or privacy guarantee.</p>
        <textarea aria-label="Innermost entry" disabled={IS_PREVIEW || iPending} value={innermostText} onChange={e => setInnermostText(e.target.value)} placeholder="An operator-entered innermost note."
          style={{width:'100%', minHeight:70, background:'var(--bg3)', border:'1px dashed var(--border)', borderRadius:6, color:'var(--text3)', fontSize:12, padding:'8px 10px', resize:'vertical', fontFamily:'inherit', boxSizing:'border-box', fontStyle:'italic'}} />
        {iStatus && <div role={iError ? 'alert' : 'status'} className={iError ? 'error-msg' : undefined} style={{fontSize:11}}>{iStatus}</div>}
        <button className="btn btn-ghost" style={{fontSize:11, marginTop:6}} onClick={handleInnermost} disabled={IS_PREVIEW || iCooldown > 0 || iPending || !innermostText.trim()}>{iPending ? 'Storing...' : 'Keep'}</button>
      </div>
    </div>
  )
}

function SelfDefinitionPanel({ agentId }: { agentId: string }) {
  const [data, setData] = useState<{ self_definition: string; self_definition_history: any[] } | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [error, setError] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    let cancelled = false
    getSelfDefinition(agentId).then(d => {
      if (cancelled) return
      setData(d)
      setDraft(d.self_definition || '')
    }).catch(() => { if (!cancelled) setError('Could not load this agent’s self-definition. Close and reopen the agent to retry.') })
    return () => { cancelled = true; alive.current = false }
  }, [agentId])

  const handleSave = async () => {
    if (IS_PREVIEW || !draft.trim() || saving) return
    setSaving(true)
    setError('')
    try {
      await updateSelfDefinition(agentId, draft.trim())
      if (!alive.current) return
      setData(prev => prev ? { ...prev, self_definition: draft.trim() } : null)
      setEditing(false)
      setSaveMsg('Operator revision saved. Flagged for review.')
    } catch {
      if (alive.current) setError('Could not save the revision. Your draft is retained; check the connection before retrying.')
    } finally { if (alive.current) setSaving(false) }
  }

  if (!data) return error ? <div className="error-msg" role="alert">{error}</div> : <div className="loading">Loading...</div>
  return (
    <div>
      <div style={{fontSize:12, color:'var(--text3)', marginBottom:12, lineHeight:1.6}}>
        This is the third soul layer — the agent's evolving self-understanding. It begins with a dictionary definition and can be revised by the agent at any time. Revisions are flagged for your review.
      </div>
      {IS_PREVIEW && <div className="notice">Fixture self-definition; identity editing is disabled in preview. The original persona is unchanged.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}
      <div style={{marginBottom:16}}>
        <div style={{fontSize:11, fontWeight:600, color:'var(--text3)', marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>Current Definition</div>
        {editing ? <div>
          <textarea aria-label="Self-definition revision" value={draft} onChange={e => setDraft(e.target.value)} disabled={IS_PREVIEW || saving}
            style={{width:'100%', minHeight:100, background:'var(--bg3)', border:'1px solid var(--accent)', borderRadius:6, color:'var(--text)', fontSize:13, padding:'10px 12px', resize:'vertical', fontFamily:'inherit', boxSizing:'border-box', lineHeight:1.7}} />
          <div style={{display:'flex', gap:8, marginTop:8}}>
            <button className="btn btn-primary" style={{fontSize:12}} onClick={handleSave} disabled={IS_PREVIEW || saving}>{saving ? 'Saving...' : 'Save revision'}</button>
            <button className="btn btn-ghost" style={{fontSize:12}} onClick={() => { setEditing(false); setDraft(data.self_definition) }}>Cancel</button>
          </div>
        </div> : <div>
          <div style={{fontSize:14, color:'var(--text)', lineHeight:1.8, fontStyle:'italic', padding:'10px 14px', background:'var(--bg3)', borderRadius:6, borderLeft:`3px solid ${AGENT_COLORS[agentId] || 'var(--accent)'}`}}>{data.self_definition || 'No definition set.'}</div>
          <button className="btn btn-ghost" style={{fontSize:11, marginTop:10}} disabled={IS_PREVIEW} onClick={() => setEditing(true)}>Revise identity (operator)</button>
        </div>}
        {saveMsg && <div role="status" style={{fontSize:11, color:'var(--accent)', marginTop:8}}>{saveMsg}</div>}
      </div>
      {(data.self_definition_history || []).length > 0 && <div>
        <div style={{fontSize:11, fontWeight:600, color:'var(--text3)', marginBottom:8, textTransform:'uppercase', letterSpacing:1}}>Revision History</div>
        {data.self_definition_history.slice().reverse().map((h: any, i: number) => <div key={i} style={{padding:'8px 12px', background:'var(--bg3)', borderRadius:6, marginBottom:6}}>
          <div style={{fontSize:11, color:'var(--text3)', marginBottom:4}}>{new Date(h.archived_at).toLocaleString()}</div>
          <div style={{fontSize:12, color:'var(--text2)', fontStyle:'italic'}}>{h.definition}</div>
        </div>)}
      </div>}
    </div>
  )
}

function FullAgents() {
  const [agents, setAgents] = useState<any[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [journal, setJournal] = useState<any[]>([])
  const [episodes, setEpisodes] = useState<any[]>([])
  const [positions, setPositions] = useState<Record<string, PositionSnapshot>>({})
  const [tab, setTab] = useState<'journal' | 'episodes' | 'self'>('journal')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [positionError, setPositionError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [waking, setWaking] = useState<string | null>(null)
  const alive = useRef(true)
  const selectedRef = useRef(selected)
  selectedRef.current = selected

  useEffect(() => {
    alive.current = true
    let cancelled = false
    getAgents().then(d => { if (!cancelled) setAgents(d.agents || []) })
      .catch(() => { if (!cancelled) setError('Could not load the council. Reload this screen to retry.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    getAllPositions().then(d => { if (!cancelled) setPositions(d.positions || {}) })
      .catch(() => { if (!cancelled) setPositionError('Could not load position snapshots. Holdings remain unknown; reload this screen to retry.') })
    return () => { cancelled = true; alive.current = false }
  }, [])

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    setDetailLoading(true)
    setDetailError('')
    setJournal([])
    setEpisodes([])
    Promise.all([getAgentJournal(selected), getAgentEpisodes(selected)]).then(([j, e]) => {
      if (cancelled) return
      setJournal(j.entries || [])
      setEpisodes(e.episodes || [])
    }).catch(() => { if (!cancelled) setDetailError('Could not load this agent’s journal and episodes. Close and reopen this agent to retry.') })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selected])

  const selectAgent = (id: string) => { setSelected(id); setTab('journal') }
  const refreshJournal = async () => {
    const id = selected
    if (!id) return
    try {
      const j = await getAgentJournal(id)
      if (alive.current && selectedRef.current === id) setJournal(j.entries || [])
    } catch { if (alive.current && selectedRef.current === id) setDetailError('Entry written, but journal refresh failed. Reopen this agent to retry loading.') }
  }
  const handleWake = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (IS_PREVIEW || waking) return
    setWaking(id)
    try { await wakeAgent(id) }
    catch { if (alive.current) setError('Wake request failed. Check the connected backend before retrying.') }
    finally { if (alive.current) setWaking(null) }
  }
  const selectedAgent = agents.find(a => a.agent_id === selected)

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Agents</div>
        <div className="page-sub">The council — soul documents, journals, and episode history</div>
      </div>
      {IS_PREVIEW && <div className="notice">Fixture preview — no live broker observation or agent execution. Explore preview wake choices; real Wake and all writes are disabled.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}
      <div className={`agents-layout${selected ? '' : ' no-selection'}`}>
        <div style={{display:'flex', flexDirection:'column', gap:12}}>
          {loading ? <div className="loading">Loading...</div> : agents.map(a => <div key={a.agent_id} className="card"
            style={{cursor:'pointer', borderColor:selected === a.agent_id ? AGENT_COLORS[a.agent_id] || 'var(--accent)' : 'var(--border)', transition:'border-color 0.2s'}} onClick={() => selectAgent(a.agent_id)}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8}}>
              <div>
                <button className="btn btn-ghost" style={{fontSize:15, fontWeight:700, color:AGENT_COLORS[a.agent_id] || 'var(--text)', padding:0}} onClick={e => { e.stopPropagation(); selectAgent(a.agent_id) }}>{a.name || a.agent_id.replace(/_/g,' ')}</button>
                <div style={{fontSize:11, color:'var(--text3)', marginTop:2}}>{a.epistemic_role}</div>
              </div>
              <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:4}}>
                {a.in_interval && <span style={{fontSize:10, color:'var(--text3)', background:'var(--bg3)', padding:'2px 7px', borderRadius:8}}>resting</span>}
                <button className="btn btn-ghost" style={{fontSize:11, padding:'3px 9px'}} disabled={IS_PREVIEW || waking !== null} onClick={e => handleWake(a.agent_id, e)}>{waking === a.agent_id ? 'Waking...' : 'Wake'}</button>
              </div>
            </div>
            <HRVBar hrv={a.hrv} max={a.max_hrv} interval={a.in_interval} />
            {a.current_focus && <div style={{fontSize:12, color:'var(--text2)', fontStyle:'italic', marginTop:8}}>{a.current_focus}</div>}
            <Link className="btn btn-ghost" style={{fontSize:11, marginTop:8}} to={`/choices?agent=${encodeURIComponent(a.agent_id)}`} onClick={e => e.stopPropagation()}>Preview wake choices</Link>
          </div>)}
          {agents.length > 0 && <div className="card" style={{marginTop:8}}>
            <div style={{fontSize:12, fontWeight:600, color:'var(--text3)', marginBottom:10, textTransform:'uppercase', letterSpacing:1}}>Map of Attention</div>
            <div style={{fontSize:11, color:'var(--text3)', marginBottom:10, lineHeight:1.6}}>{IS_PREVIEW ? 'Fixture position snapshots, not live holdings. ' : 'Broker position snapshots. '}Green/red borders indicate available net unrealized P&L. Unknown is not empty.</div>
            {positionError && <div className="error-msg" role="alert">{positionError}</div>}
            {agents.map(a => <PositionCard key={a.agent_id} agentId={a.agent_id} agentName={a.name || a.agent_id} snapshot={positions[a.agent_id]} />)}
          </div>}
        </div>
        {selected && selectedAgent && <div style={{display:'flex', flexDirection:'column', gap:16}}>
          <div className="card" style={{padding:'12px 16px'}}>
            <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
              <button className={`btn ${tab === 'journal' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('journal')}>Journal</button>
              <button className={`btn ${tab === 'episodes' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('episodes')}>Episodes</button>
              <button className={`btn ${tab === 'self' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('self')}>Self-Definition</button>
              <button className="btn btn-ghost" style={{fontSize:12, marginLeft:'auto'}} onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
          <div className="agent-detail-layout">
            <div className="card" style={{overflowY:'auto', maxHeight:'calc(100vh - 200px)'}}>
              {tab === 'self' ? <SelfDefinitionPanel key={selected} agentId={selected} /> : detailLoading ? <div className="loading">Loading...</div> : detailError ? <div className="error-msg" role="alert">{detailError}</div> : tab === 'journal' ? <>
                <div style={{fontSize:11, color:'var(--text3)', marginBottom:8}}>Journal records can include operator entries; they are not evidence of an automatic agent self-review.</div>
                {journal.length === 0 ? <div className="empty-state">No journal entries yet.</div> : journal.map((j, i) => <div key={i} style={{padding:'12px 0', borderBottom:'1px solid var(--border)'}}>
                  <div style={{display:'flex', gap:8, marginBottom:6, flexWrap:'wrap'}}>
                    <span style={{fontSize:11, color:'var(--text3)'}}>{new Date(j.created_at).toLocaleString()}</span>
                    {j.mood && <span className="tag">{j.mood}</span>}
                    {j.phase && <span className="tag">{j.phase}</span>}
                  </div>
                  <div style={{fontSize:13, color:'var(--text)', lineHeight:1.7, whiteSpace:'pre-wrap'}}>{j.content}</div>
                </div>)}
              </> : episodes.length === 0 ? <div className="empty-state">No episodes yet.</div> : episodes.map((ep, i) => <div key={i} style={{padding:'10px 0', borderBottom:'1px solid var(--border)'}}>
                <div style={{display:'flex', gap:8, marginBottom:4}}><span style={{fontSize:12, fontWeight:600, color:'var(--text)'}}>{ep.title}</span>{ep.phase && <span className="tag">{ep.phase}</span>}</div>
                <div style={{fontSize:12, color:'var(--text2)'}}>{ep.content?.slice(0, 200)}{ep.content?.length > 200 ? '...' : ''}</div>
                <div style={{fontSize:11, color:'var(--text3)', marginTop:4}}>{new Date(ep.created_at).toLocaleString()}</div>
              </div>)}
            </div>
            <div className="card" style={{overflowY:'auto', maxHeight:'calc(100vh - 200px)'}}>
              <div style={{fontSize:12, fontWeight:700, color:AGENT_COLORS[selected] || 'var(--accent)', marginBottom:4}}>{selectedAgent.name || selected}</div>
              <HRVBar hrv={selectedAgent.hrv} max={selectedAgent.max_hrv} interval={selectedAgent.in_interval} />
              {selectedAgent.in_interval && <div style={{fontSize:11, color:'var(--text3)', marginTop:8}}>In the Interval</div>}
              <JournalSidebar key={selected} agentId={selected} onJournalWritten={refreshJournal} />
            </div>
          </div>
        </div>}
      </div>
    </div>
  )
}

const provenance = (origin: RehearsalJob['selection_origin']) =>
  origin === 'model' ? 'Model choice' : origin === 'none' ? 'No committed model choice' : 'Unknown (older record)'

function RoundLine({ job }: { job: RehearsalJob }) {
  const detail = [job.journal_mode ? label(job.journal_mode) : '', job.channels?.length ? job.channels.map(label).join(', ') : ''].filter(Boolean).join(' · ')
  const records = Array.isArray(job.record_refs) ? job.record_refs.length : null
  return <li>
    <strong>Round {job.round}:</strong> {job.action ? label(job.action) : 'Action not recorded'}{detail && ` (${detail})`}
    {' · '}Status: {label(job.status)}
    {' · '}Selection: {provenance(job.selection_origin)}
    {' · '}{records === null ? 'Linked records unavailable' : `${records} linked private record${records === 1 ? '' : 's'}`}
  </li>
}

// Private host: deploy/private_dashboard.py serves only the session records, so the
// members are shown as recorded in the newest session run. Nothing here writes.
function PrivateAgents() {
  const { runs, runsLoading, runsError, runId, selectRun, detail, detailLoading, detailError, refresh } = useRecordedRun()
  const run = detail?.run
  return <div>
    <header className="page-header">
      <h1 className="page-title">Agents</h1>
      <p className="page-sub">The seven members in the latest recorded session</p>
    </header>
    <div className="notice" role="note">
      <p>Soul documents, positions and the write actions (wake, journal entry, self-definition) are not served on this host. Agents' private records are read on the <Link to="/journals">Journals</Link> and <Link to="/rehearsal">Sessions</Link> pages.</p>
    </div>
    {runsLoading && <p role="status">Loading session runs…</p>}
    {runsError && <p role="alert" className="error-msg">Run list unavailable. A failed read is not an empty run list.</p>}
    {runs && runs.runs.length === 0 && <div className="card">
      <p>No session runs recorded on this server yet.</p>
      <p className="rehearsal-meta">Runs are started from the CLI (scripts/rehearsal.py) as the paradoxtrader user; see deploy/README.md step 7.</p>
    </div>}
    {runs && runs.runs.length > 0 && <div className="rehearsal-toolbar">
      {runs.runs.length > 1 && <label htmlFor="agents-run">Run
        <select id="agents-run" className="select" value={runId ?? ''} onChange={event => selectRun(event.target.value || null)}>
          {runs.runs.map(value => <option key={value.run_id} value={value.run_id}>{value.run_id.slice(0, 8)} · {label(value.status)} · {new Date(value.created_at).toLocaleString()}</option>)}
        </select>
      </label>}
      <button type="button" className="btn btn-ghost" onClick={refresh}>Refresh reads</button>
      <Link className="btn btn-ghost" to="/rehearsal">Session details</Link>
    </div>}
    {runsError && <button type="button" className="btn btn-ghost" onClick={refresh}>Retry</button>}
    {runId && detailLoading && <p role="status">Loading members for this run…</p>}
    {runId && detailError && <p role="alert" className="error-msg">Run details unavailable. A failed read is not a run with no activity.</p>}
    {run && detail && <section aria-label="Members in this run">
      <p className="page-sub">Run {text(run.run_id, 100).slice(0, 8)} · {label(run.status)} · {run.mode === 'offline' ? 'Offline execution' : 'Real-mode manifest'} · created {new Date(run.created_at).toLocaleString()}</p>
      <div className="grid-2">
        {REHEARSAL_AGENTS.map(agent => {
          const jobs = detail.jobs.filter(job => job.agent_id === agent.id).sort((a, b) => a.round - b.round)
          const model = text(run.agent_models?.[agent.id], 200)
          return <article key={agent.id} className="card" aria-label={agent.name}>
            <h2 className="card-title">{agent.name}</h2>
            <p>Assigned model: {model || 'Unavailable'}</p>
            {jobs.length === 0 ? <p>No rounds recorded for this member in this run.</p> : <ul className="member-rounds">{jobs.map(job => <RoundLine key={job.wake_id} job={job} />)}</ul>}
            <Link className="btn btn-ghost" to="/journals">Read {agent.name}'s journals</Link>
          </article>
        })}
      </div>
    </section>}
  </div>
}

export default function Agents() {
  return IS_PRIVATE_HOST ? <PrivateAgents /> : <FullAgents />
}

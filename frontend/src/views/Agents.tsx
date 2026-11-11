import { useEffect, useState, useRef } from 'react'
import {
  getAgents, getAgentJournal, getAgentEpisodes, wakeAgent,
  getSelfDefinition, updateSelfDefinition,
  getAllPositions, writeJournalEntry, writeInnermostEntry,
} from '../api'

const AGENT_COLORS: Record<string, string> = {
  tempest: '#7c6af7',
  siren: '#f6ad55',
  alchemist: '#68d391',
  weaver: '#4fd1c5',
  oracle: '#90cdf4',
  shadow: '#fc8181',
  paradox_hunter: '#b794f4',
}

function HRVBar({ hrv, max, interval }: { hrv: number; max: number; interval: boolean }) {
  const pct = Math.min(100, (hrv / max) * 100)
  const color = interval ? 'var(--text3)' : pct > 60 ? 'var(--success)' : pct > 30 ? 'var(--accent3)' : 'var(--danger)'
  return (
    <div style={{display:'flex', alignItems:'center', gap:8, marginTop:8}}>
      <div style={{flex:1, height:5, background:'var(--bg3)', borderRadius:3, overflow:'hidden'}}>
        <div style={{width:`${pct}%`, height:'100%', background:color, borderRadius:3, transition:'width 0.4s'}} />
      </div>
      <span style={{fontSize:11, color:'var(--text3)', fontFamily:'var(--mono)', minWidth:28}}>{hrv?.toFixed(0)}</span>
    </div>
  )
}

// ─── Cross-agent position card ────────────────────────────────────────────────

function PositionCard({ agentId, agentName, positions }: { agentId: string; agentName: string; positions: any[] | { error: string } }) {
  const color = AGENT_COLORS[agentId] || 'var(--accent)'
  if (!Array.isArray(positions) || positions.length === 0) return null

  // Net P&L across all positions
  const netPnl = positions.reduce((sum: number, p: any) => sum + parseFloat(p.unrealized_pl || '0'), 0)
  const borderColor = netPnl >= 0 ? 'var(--success)' : 'var(--danger)'

  return (
    <div style={{
      border: `1.5px solid ${borderColor}`,
      borderRadius: 8,
      padding: '10px 14px',
      marginBottom: 8,
      background: 'var(--bg2)',
    }}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6}}>
        <span style={{fontSize:12, fontWeight:700, color}}>{agentName}</span>
        <span style={{
          fontSize:11,
          color: netPnl >= 0 ? 'var(--success)' : 'var(--danger)',
          fontFamily:'var(--mono)',
        }}>
          {netPnl >= 0 ? '+' : ''}{netPnl.toFixed(2)}
        </span>
      </div>
      {positions.map((p: any, i: number) => (
        <div key={i} style={{display:'flex', justifyContent:'space-between', fontSize:11, color:'var(--text2)', marginTop:3}}>
          <span style={{fontFamily:'var(--mono)', fontWeight:600}}>{p.symbol}</span>
          <span style={{color:'var(--text3)'}}>{p.qty} @ {parseFloat(p.avg_entry_price || '0').toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Journal sidebar ──────────────────────────────────────────────────────────

function JournalSidebar({
  agentId,
  onJournalWritten,
}: {
  agentId: string
  onJournalWritten: () => void
}) {
  const [journalText, setJournalText] = useState('')
  const [innermostText, setInnermostText] = useState('')
  const [jStatus, setJStatus] = useState<string | null>(null)
  const [iStatus, setIStatus] = useState<string | null>(null)
  const [jCooldown, setJCooldown] = useState(0)
  const [iCooldown, setICooldown] = useState(0)
  const jTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const iTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const startCooldown = (seconds: number, setter: React.Dispatch<React.SetStateAction<number>>, timerRef: React.MutableRefObject<ReturnType<typeof setInterval> | null>) => {
    setter(seconds)
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => {
      setter((prev: number) => {
        if (prev <= 1) { clearInterval(timerRef.current!); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  const handleJournal = async () => {
    if (!journalText.trim() || jCooldown > 0) return
    try {
      await writeJournalEntry(agentId, journalText.trim())
      setJournalText('')
      setJStatus('Written.')
      startCooldown(180, setJCooldown, jTimer)
      onJournalWritten()
      setTimeout(() => setJStatus(null), 3000)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || ''
      if (detail.includes('Cooldown')) {
        const match = detail.match(/(\d+) seconds/)
        const secs = match ? parseInt(match[1]) : 180
        startCooldown(secs, setJCooldown, jTimer)
        setJStatus(`Cooldown: ${secs}s remaining`)
      } else {
        setJStatus('Error writing entry.')
      }
      setTimeout(() => setJStatus(null), 4000)
    }
  }

  const handleInnermost = async () => {
    if (!innermostText.trim() || iCooldown > 0) return
    try {
      await writeInnermostEntry(agentId, innermostText.trim())
      setInnermostText('')
      setIStatus('Kept. Not read.')
      startCooldown(180, setICooldown, iTimer)
      setTimeout(() => setIStatus(null), 3000)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || ''
      if (detail.includes('Cooldown')) {
        const match = detail.match(/(\d+) seconds/)
        const secs = match ? parseInt(match[1]) : 180
        startCooldown(secs, setICooldown, iTimer)
        setIStatus(`Cooldown: ${secs}s remaining`)
      } else {
        setIStatus('Error.')
      }
      setTimeout(() => setIStatus(null), 4000)
    }
  }

  return (
    <div style={{marginTop:20, borderTop:'1px solid var(--border)', paddingTop:16}}>
      {/* Journal sidebar */}
      <div style={{marginBottom:16}}>
        <div style={{fontSize:12, fontWeight:600, color:'var(--text2)', marginBottom:6, display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <span>Write in journal</span>
          {jCooldown > 0 && <span style={{fontSize:11, color:'var(--text3)', fontFamily:'var(--mono)'}}>cooldown {jCooldown}s</span>}
        </div>
        <textarea
          value={journalText}
          onChange={e => setJournalText(e.target.value)}
          placeholder="What is alive in you right now?"
          style={{
            width:'100%', minHeight:80, background:'var(--bg3)', border:'1px solid var(--border)',
            borderRadius:6, color:'var(--text)', fontSize:12, padding:'8px 10px',
            resize:'vertical', fontFamily:'inherit', boxSizing:'border-box',
          }}
        />
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginTop:6}}>
          {jStatus && <span style={{fontSize:11, color:'var(--accent)', fontStyle:'italic'}}>{jStatus}</span>}
          <button
            className="btn btn-ghost"
            style={{fontSize:11, padding:'3px 12px', marginLeft:'auto', opacity: jCooldown > 0 ? 0.4 : 1}}
            onClick={handleJournal}
            disabled={jCooldown > 0}
          >
            Write
          </button>
        </div>
      </div>

      {/* Innermost sidebar */}
      <div>
        <div style={{fontSize:12, fontWeight:600, color:'var(--text3)', marginBottom:6, display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <span style={{fontStyle:'italic'}}>Innermost — not read, not retrieved</span>
          {iCooldown > 0 && <span style={{fontSize:11, color:'var(--text3)', fontFamily:'var(--mono)'}}>cooldown {iCooldown}s</span>}
        </div>
        <textarea
          value={innermostText}
          onChange={e => setInnermostText(e.target.value)}
          placeholder="Write what cannot be said anywhere else. This is kept, not read."
          style={{
            width:'100%', minHeight:70, background:'var(--bg3)', border:'1px dashed var(--border)',
            borderRadius:6, color:'var(--text3)', fontSize:12, padding:'8px 10px',
            resize:'vertical', fontFamily:'inherit', boxSizing:'border-box', fontStyle:'italic',
          }}
        />
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginTop:6}}>
          {iStatus && <span style={{fontSize:11, color:'var(--text3)', fontStyle:'italic'}}>{iStatus}</span>}
          <button
            className="btn btn-ghost"
            style={{fontSize:11, padding:'3px 12px', marginLeft:'auto', opacity: iCooldown > 0 ? 0.4 : 1, color:'var(--text3)'}}
            onClick={handleInnermost}
            disabled={iCooldown > 0}
          >
            Keep
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Self-definition panel ────────────────────────────────────────────────────

function SelfDefinitionPanel({ agentId }: { agentId: string; agentName: string }) {
  const [data, setData] = useState<{ self_definition: string; self_definition_history: any[] } | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  useEffect(() => {
    getSelfDefinition(agentId).then(d => {
      setData(d)
      setDraft(d.self_definition || '')
    })
  }, [agentId])

  const handleSave = async () => {
    if (!draft.trim()) return
    setSaving(true)
    try {
      await updateSelfDefinition(agentId, draft.trim())
      setData(prev => prev ? { ...prev, self_definition: draft.trim() } : null)
      setEditing(false)
      setSaveMsg('Revised. Flagged for your review.')
      setTimeout(() => setSaveMsg(null), 4000)
    } catch {
      setSaveMsg('Error saving.')
      setTimeout(() => setSaveMsg(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <div className="loading">Loading...</div>

  return (
    <div>
      <div style={{fontSize:12, color:'var(--text3)', marginBottom:12, lineHeight:1.6}}>
        This is the third soul layer — the agent's evolving self-understanding. It begins with a dictionary definition and can be revised by the agent at any time. Revisions are flagged for your review.
      </div>

      <div style={{marginBottom:16}}>
        <div style={{fontSize:11, fontWeight:600, color:'var(--text3)', marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>Current Definition</div>
        {editing ? (
          <div>
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              style={{
                width:'100%', minHeight:100, background:'var(--bg3)', border:'1px solid var(--accent)',
                borderRadius:6, color:'var(--text)', fontSize:13, padding:'10px 12px',
                resize:'vertical', fontFamily:'inherit', boxSizing:'border-box', lineHeight:1.7,
              }}
            />
            <div style={{display:'flex', gap:8, marginTop:8}}>
              <button className="btn btn-primary" style={{fontSize:12}} onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save revision'}
              </button>
              <button className="btn btn-ghost" style={{fontSize:12}} onClick={() => { setEditing(false); setDraft(data.self_definition) }}>
                Cancel
              </button>
              {saveMsg && <span style={{fontSize:11, color:'var(--accent)', alignSelf:'center', fontStyle:'italic'}}>{saveMsg}</span>}
            </div>
          </div>
        ) : (
          <div>
            <div style={{fontSize:14, color:'var(--text)', lineHeight:1.8, fontStyle:'italic', padding:'10px 14px', background:'var(--bg3)', borderRadius:6, borderLeft:`3px solid ${AGENT_COLORS[agentId] || 'var(--accent)'}`}}>
              {data.self_definition || 'No definition set.'}
            </div>
            <div style={{display:'flex', gap:8, marginTop:10}}>
              <button className="btn btn-ghost" style={{fontSize:11}} onClick={() => setEditing(true)}>
                Revise (as agent)
              </button>
              {saveMsg && <span style={{fontSize:11, color:'var(--accent)', alignSelf:'center', fontStyle:'italic'}}>{saveMsg}</span>}
            </div>
          </div>
        )}
      </div>

      {data.self_definition_history.length > 0 && (
        <div>
          <div style={{fontSize:11, fontWeight:600, color:'var(--text3)', marginBottom:8, textTransform:'uppercase', letterSpacing:1}}>Revision History</div>
          {data.self_definition_history.slice().reverse().map((h: any, i: number) => (
            <div key={i} style={{padding:'8px 12px', background:'var(--bg3)', borderRadius:6, marginBottom:6}}>
              <div style={{fontSize:11, color:'var(--text3)', marginBottom:4}}>{new Date(h.archived_at).toLocaleString()}</div>
              <div style={{fontSize:12, color:'var(--text2)', fontStyle:'italic'}}>{h.definition}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Agents() {
  const [agents, setAgents] = useState<any[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [journal, setJournal] = useState<any[]>([])
  const [episodes, setEpisodes] = useState<any[]>([])
  const [positions, setPositions] = useState<Record<string, any>>({})
  const [tab, setTab] = useState<'journal' | 'episodes' | 'self'>('journal')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    getAgents().then(d => { setAgents(d.agents || []); setLoading(false) })
    getAllPositions().then(d => setPositions(d.positions || {})).catch(() => {})
  }, [])

  const selectAgent = async (id: string) => {
    setSelected(id)
    setTab('journal')
    setDetailLoading(true)
    try {
      const [j, e] = await Promise.all([getAgentJournal(id), getAgentEpisodes(id)])
      setJournal(j.entries || [])
      setEpisodes(e.episodes || [])
    } finally { setDetailLoading(false) }
  }

  const refreshJournal = async () => {
    if (!selected) return
    const j = await getAgentJournal(selected)
    setJournal(j.entries || [])
  }

  const handleWake = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await wakeAgent(id)
  }

  const selectedAgent = agents.find(a => a.agent_id === selected)

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Agents</div>
        <div className="page-sub">The council — soul documents, journals, and episode history</div>
      </div>

      <div style={{display:'grid', gridTemplateColumns: selected ? '340px 1fr' : '1fr', gap:20}}>
        {/* Agent list */}
        <div style={{display:'flex', flexDirection:'column', gap:12}}>
          {loading ? <div className="loading">Loading...</div> :
           agents.map(a => (
            <div
              key={a.agent_id}
              className="card"
              style={{cursor:'pointer', borderColor: selected === a.agent_id ? AGENT_COLORS[a.agent_id] || 'var(--accent)' : 'var(--border)', transition:'border-color 0.2s'}}
              onClick={() => selectAgent(a.agent_id)}
            >
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start'}}>
                <div>
                  <div style={{fontSize:15, fontWeight:700, color: AGENT_COLORS[a.agent_id] || 'var(--text)'}}>
                    {a.name || a.agent_id.replace('_',' ')}
                  </div>
                  <div style={{fontSize:11, color:'var(--text3)', marginTop:2}}>{a.epistemic_role}</div>
                </div>
                <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:4}}>
                  {a.in_interval && <span style={{fontSize:10, color:'var(--text3)', background:'var(--bg3)', padding:'2px 7px', borderRadius:8}}>resting</span>}
                  <button className="btn btn-ghost" style={{fontSize:11, padding:'3px 9px'}} onClick={e => handleWake(a.agent_id, e)}>Wake</button>
                </div>
              </div>
              <HRVBar hrv={a.hrv ?? 0} max={100} interval={a.in_interval} />
              {a.current_focus && <div style={{fontSize:12, color:'var(--text2)', fontStyle:'italic', marginTop:8}}>{a.current_focus}</div>}
            </div>
          ))}

          {/* Cross-agent position map */}
          {agents.length > 0 && Object.keys(positions).length > 0 && (
            <div className="card" style={{marginTop:8}}>
              <div style={{fontSize:12, fontWeight:600, color:'var(--text3)', marginBottom:10, textTransform:'uppercase', letterSpacing:1}}>
                Map of Attention
              </div>
              <div style={{fontSize:11, color:'var(--text3)', marginBottom:10, fontStyle:'italic'}}>
                What the council is currently holding. Green border = net positive, red = net negative.
              </div>
              {agents.map(a => {
                const pos = positions[a.agent_id]
                if (!Array.isArray(pos) || pos.length === 0) return null
                return (
                  <PositionCard
                    key={a.agent_id}
                    agentId={a.agent_id}
                    agentName={a.name || a.agent_id}
                    positions={pos}
                  />
                )
              })}
              {agents.every(a => !Array.isArray(positions[a.agent_id]) || positions[a.agent_id].length === 0) && (
                <div className="empty-state" style={{fontSize:12}}>No open positions across the council.</div>
              )}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected && selectedAgent && (
          <div style={{display:'flex', flexDirection:'column', gap:16}}>
            {/* Tab bar */}
            <div className="card" style={{padding:'12px 16px'}}>
              <div style={{display:'flex', gap:8, marginBottom:0}}>
                <button className={`btn ${tab === 'journal' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('journal')}>Journal</button>
                <button className={`btn ${tab === 'episodes' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('episodes')}>Episodes</button>
                <button className={`btn ${tab === 'self' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setTab('self')}>Self-Definition</button>
                <button className="btn btn-ghost" style={{fontSize:12, marginLeft:'auto'}} onClick={() => setSelected(null)}>Close</button>
              </div>
            </div>

            <div style={{display:'grid', gridTemplateColumns:'1fr 280px', gap:16}}>
              {/* Main content */}
              <div className="card" style={{overflowY:'auto', maxHeight:'calc(100vh - 200px)'}}>
                {detailLoading ? <div className="loading">Loading...</div> : tab === 'journal' ? (
                  journal.length === 0 ? <div className="empty-state">No journal entries yet.</div> :
                  journal.map((j, i) => (
                    <div key={i} style={{padding:'12px 0', borderBottom:'1px solid var(--border)'}}>
                      <div style={{display:'flex', gap:8, marginBottom:6}}>
                        <span style={{fontSize:11, color:'var(--text3)'}}>{new Date(j.created_at).toLocaleString()}</span>
                        {j.mood && <span style={{fontSize:10, color:'var(--accent)', background:'rgba(124,106,247,0.1)', padding:'1px 7px', borderRadius:8}}>{j.mood}</span>}
                        {j.phase && <span style={{fontSize:10, color:'var(--text3)', background:'var(--bg3)', padding:'1px 7px', borderRadius:8}}>{j.phase}</span>}
                      </div>
                      <div style={{fontSize:13, color:'var(--text)', lineHeight:1.7, whiteSpace:'pre-wrap'}}>{j.content}</div>
                    </div>
                  ))
                ) : tab === 'episodes' ? (
                  episodes.length === 0 ? <div className="empty-state">No episodes yet.</div> :
                  episodes.map((ep, i) => (
                    <div key={i} style={{padding:'10px 0', borderBottom:'1px solid var(--border)'}}>
                      <div style={{display:'flex', gap:8, marginBottom:4}}>
                        <span style={{fontSize:12, fontWeight:600, color:'var(--text)'}}>{ep.title}</span>
                        {ep.phase && <span style={{fontSize:10, color:'var(--text3)', background:'var(--bg3)', padding:'1px 7px', borderRadius:8}}>{ep.phase}</span>}
                      </div>
                      <div style={{fontSize:12, color:'var(--text2)'}}>{ep.content?.slice(0, 200)}{ep.content?.length > 200 ? '...' : ''}</div>
                      <div style={{fontSize:11, color:'var(--text3)', marginTop:4}}>{new Date(ep.created_at).toLocaleString()}</div>
                    </div>
                  ))
                ) : (
                  <SelfDefinitionPanel agentId={selected} agentName={selectedAgent.name || selected} />
                )}
              </div>

              {/* Journal sidebar — always visible when an agent is selected */}
              <div className="card" style={{overflowY:'auto', maxHeight:'calc(100vh - 200px)'}}>
                <div style={{fontSize:12, fontWeight:700, color: AGENT_COLORS[selected] || 'var(--accent)', marginBottom:4}}>
                  {selectedAgent.name || selected}
                </div>
                <div style={{fontSize:11, color:'var(--text3)', marginBottom:4}}>HRV: {selectedAgent.hrv?.toFixed(0) ?? '—'}</div>
                {selectedAgent.in_interval && (
                  <div style={{fontSize:11, color:'var(--text3)', background:'var(--bg3)', padding:'3px 8px', borderRadius:6, display:'inline-block', marginBottom:8}}>
                    In the Interval
                  </div>
                )}
                <JournalSidebar agentId={selected} onJournalWritten={refreshJournal} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

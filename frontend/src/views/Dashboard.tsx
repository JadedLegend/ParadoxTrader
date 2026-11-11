import { useEffect, useRef, useState } from 'react'
import { getStatus, getSnapshot, getAnnouncements, getConfig, setPhase, initSystem, wakeAgent } from '../api'

const PHASE_NAMES: Record<number, string> = {
  0: 'Solo Incubation',
  1: 'Forum Opens',
  2: 'Countdown',
  3: 'Council Mode',
}

function HRVBar({ hrv, max, interval }: { hrv: number; max: number; interval: boolean }) {
  const pct = Math.min(100, (hrv / max) * 100)
  const cls = interval ? 'interval' : pct > 60 ? 'high' : pct > 30 ? 'mid' : 'low'
  return (
    <div className="hrv-bar-wrap">
      <div className="hrv-bar-bg">
        <div className="hrv-bar-fill" style={{ width: `${pct}%` }} data-cls={cls} />
      </div>
      <span className="hrv-val">{hrv.toFixed(0)}</span>
    </div>
  )
}

function formatCountdown(seconds: number) {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m ${s}s`
  return `${m}m ${s}s`
}

export default function Dashboard() {
  const [agents, setAgents] = useState<any[]>([])
  const [snapshot, setSnapshot] = useState<any>({})
  // countdown stores the target ISO string so we can tick client-side
  const [countdownTarget, setCountdownTarget] = useState<string | null>(null)
  const [countdownContent, setCountdownContent] = useState<string>('')
  const [countdownSeconds, setCountdownSeconds] = useState<number>(0)
  const [phase, setPhaseState] = useState<number | null>(null)  // null = not yet loaded
  const [loading, setLoading] = useState(true)
  const [initMsg, setInitMsg] = useState('')
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ─── Client-side countdown ticker ─────────────────────────────────────────
  useEffect(() => {
    if (tickRef.current) clearInterval(tickRef.current)
    if (!countdownTarget) return
    const tick = () => {
      const target = new Date(countdownTarget).getTime()
      const remaining = Math.max(0, Math.floor((target - Date.now()) / 1000))
      setCountdownSeconds(remaining)
    }
    tick()
    tickRef.current = setInterval(tick, 1000)
    return () => { if (tickRef.current) clearInterval(tickRef.current) }
  }, [countdownTarget])

  // ─── Data loading ──────────────────────────────────────────────────────────
  const load = async () => {
    try {
      const [s, snap, ann, cfg] = await Promise.all([
        getStatus(),
        getSnapshot(),
        getAnnouncements(),
        getConfig(),
      ])
      setAgents(s.agents || [])
      setSnapshot(snap)

      // Load phase from persisted backend config
      const backendPhase = cfg?.config?.runtime?.current_phase
      if (backendPhase != null) setPhaseState(Number(backendPhase))

      // Store countdown target for client-side ticking
      if (ann.countdown?.target) {
        setCountdownTarget(ann.countdown.target)
        setCountdownContent(ann.countdown.content || '')
      } else {
        setCountdownTarget(null)
        setCountdownSeconds(0)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  const handleInit = async () => {
    setInitMsg('Initializing...')
    try {
      await initSystem()
      setInitMsg('System initialized.')
      load()
    } catch { setInitMsg('Error during init.') }
  }

  const handlePhase = async (p: number) => {
    await setPhase(p)
    setPhaseState(p)
    load()
  }

  const handleWake = async (id: string) => {
    await wakeAgent(id)
  }

  const intervalCount = agents.filter(a => a.in_interval).length
  const activeCount = agents.length - intervalCount

  return (
    <div>
      <div className="page-header flex-between">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-sub">System overview and controls</div>
        </div>
        <div className="flex gap-8">
          <button className="btn btn-ghost" onClick={handleInit}>Initialize System</button>
          <button className="btn btn-primary" onClick={load}>Refresh</button>
        </div>
      </div>

      {initMsg && <div className="mb-16" style={{color:'var(--accent2)', fontSize:13}}>{initMsg}</div>}

      {/* Market Snapshot */}
      <div className="grid-4 mb-16">
        <div className="stat-tile">
          <div className="stat-label">VIX</div>
          <div className="stat-value">{snapshot.vix?.toFixed(2) ?? '—'}</div>
          <div className="stat-sub">{snapshot.vix_change_pct != null ? `${snapshot.vix_change_pct > 0 ? '+' : ''}${snapshot.vix_change_pct?.toFixed(2)}%` : ''}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">SPY</div>
          <div className="stat-value">{snapshot.spy_price?.toFixed(2) ?? '—'}</div>
          <div className="stat-sub">{snapshot.spy_change_pct != null ? `${snapshot.spy_change_pct > 0 ? '+' : ''}${snapshot.spy_change_pct?.toFixed(2)}%` : ''}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">Fear / Greed</div>
          <div className="stat-value">{snapshot.fear_greed_score ?? '—'}</div>
          <div className="stat-sub">{snapshot.fear_greed_rating ?? ''}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">Market Mood</div>
          <div className="stat-value" style={{fontSize:16, paddingTop:6}}>{snapshot.market_mood?.replace(/_/g,' ') ?? '—'}</div>
          <div className="stat-sub">{activeCount} active · {intervalCount} resting</div>
        </div>
      </div>

      {/* Phase Control — shows current persisted phase from backend */}
      <div className="card mb-16">
        <div className="card-title">
          Developmental Phase
          {phase !== null && (
            <span style={{marginLeft:12, fontSize:12, color:'var(--accent)', fontWeight:400}}>
              currently: Phase {phase} — {PHASE_NAMES[phase]}
            </span>
          )}
        </div>
        <div className="flex gap-8" style={{flexWrap:'wrap'}}>
          {[0,1,2,3].map(p => (
            <button
              key={p}
              className={`btn ${phase === p ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => handlePhase(p)}
            >
              Phase {p}: {PHASE_NAMES[p]}
            </button>
          ))}
        </div>
        {phase === null && <div style={{fontSize:12, color:'var(--text3)', marginTop:8}}>Loading phase from server...</div>}
      </div>

      {/* Countdown — ticks every second client-side */}
      {countdownTarget && countdownSeconds > 0 && (
        <div className="card mb-16">
          <div className="countdown">
            <div className="countdown-label">Council Convergence Countdown</div>
            <div className="countdown-value">{formatCountdown(countdownSeconds)}</div>
            <div style={{fontSize:12, color:'var(--text3)', marginTop:8}}>{countdownContent}</div>
          </div>
        </div>
      )}

      {/* Agent HRV Grid */}
      <div className="card">
        <div className="card-title">Agent Status</div>
        {loading ? <div className="loading">Loading...</div> : (
          <div style={{display:'flex', flexDirection:'column', gap:12}}>
            {agents.map(a => (
              <div key={a.agent_id} style={{display:'flex', alignItems:'center', gap:16}}>
                <div style={{width:140, minWidth:140}}>
                  <div style={{fontSize:13, fontWeight:700, color: a.in_interval ? 'var(--text3)' : 'var(--text)'}}>
                    {a.agent_id.replace('_',' ')}
                  </div>
                  {a.in_interval && <div className="interval-badge">in interval</div>}
                </div>
                <div style={{flex:1}}>
                  <HRVBar hrv={a.hrv ?? 0} max={100} interval={a.in_interval} />
                </div>
                <button className="btn btn-ghost" style={{fontSize:11, padding:'4px 10px'}} onClick={() => handleWake(a.agent_id)}>
                  Wake
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

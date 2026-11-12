import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { IS_PREVIEW, getStatus, getSnapshot, getAnnouncements, getConfig, setPhase, initSystem, wakeAgent } from '../api'

const PHASE_NAMES: Record<number, string> = {
  0: 'Solo Incubation', 1: 'Forum Opens', 2: 'Countdown', 3: 'Council Mode',
}

function HRVBar({ hrv, max, interval }: { hrv?: number; max?: number; interval: boolean }) {
  if (typeof hrv !== 'number' || !Number.isFinite(hrv) || typeof max !== 'number' || !Number.isFinite(max) || max <= 0) {
    return <div style={{fontSize:11, color:'var(--text3)'}}>HRV not initialized — value unavailable</div>
  }
  const pct = Math.max(0, Math.min(100, (hrv / max) * 100))
  const cls = interval ? 'interval' : pct > 60 ? 'high' : pct > 30 ? 'mid' : 'low'
  return (
    <div className="hrv-bar-wrap">
      <div className="hrv-bar-bg"><div className="hrv-bar-fill" style={{width:`${pct}%`}} data-cls={cls} /></div>
      <span className="hrv-val">{hrv.toFixed(0)} / {max}</span>
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
  const [countdownTarget, setCountdownTarget] = useState<string | null>(null)
  const [countdownContent, setCountdownContent] = useState('')
  const [countdownSeconds, setCountdownSeconds] = useState(0)
  const [phase, setPhaseState] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [initMsg, setInitMsg] = useState('')
  const [error, setError] = useState('')
  const [acting, setActing] = useState(false)
  const alive = useRef(true)
  const request = useRef(0)

  useEffect(() => {
    if (!countdownTarget) return
    const tick = () => {
      const target = new Date(countdownTarget).getTime()
      setCountdownSeconds(Number.isFinite(target) ? Math.max(0, Math.floor((target - Date.now()) / 1000)) : 0)
    }
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [countdownTarget])

  const load = useCallback(async () => {
    const current = ++request.current
    try {
      const [s, snap, ann, cfg] = await Promise.all([getStatus(), getSnapshot(), getAnnouncements(), getConfig()])
      if (!alive.current || current !== request.current) return
      setError('')
      setAgents(s.agents || [])
      setSnapshot(snap)
      const backendPhase = cfg?.config?.runtime?.current_phase
      setPhaseState(backendPhase != null && Number.isFinite(Number(backendPhase)) ? Number(backendPhase) : null)
      if (ann.countdown?.target) {
        setCountdownTarget(ann.countdown.target)
        setCountdownContent(ann.countdown.content || '')
      } else {
        setCountdownTarget(null)
        setCountdownSeconds(0)
      }
    } catch {
      if (alive.current && current === request.current) setError('Could not refresh the dashboard. Displayed values may be stale or unavailable; use Refresh to retry.')
    } finally { if (alive.current && current === request.current) setLoading(false) }
  }, [])

  useEffect(() => {
    alive.current = true
    void load()
    const timer = IS_PREVIEW ? null : setInterval(load, 30000)
    return () => { alive.current = false; if (timer) clearInterval(timer) }
  }, [load])

  const handleInit = async () => {
    if (IS_PREVIEW || acting) return
    setActing(true)
    setInitMsg('Initializing...')
    try {
      await initSystem()
      if (!alive.current) return
      setInitMsg('System initialized.')
      await load()
    } catch {
      if (alive.current) { setInitMsg(''); setError('Initialization failed. Check the connected backend before retrying.') }
    } finally { if (alive.current) setActing(false) }
  }
  const handlePhase = async (p: number) => {
    if (IS_PREVIEW || acting) return
    setActing(true)
    try {
      await setPhase(p)
      if (!alive.current) return
      setPhaseState(p)
      await load()
    } catch { if (alive.current) setError('Phase change failed. The last observed phase is unchanged; check the connection before retrying.') }
    finally { if (alive.current) setActing(false) }
  }
  const handleWake = async (id: string) => {
    if (IS_PREVIEW || acting) return
    setActing(true)
    try { await wakeAgent(id) }
    catch { if (alive.current) setError('Wake request failed. Check the connected backend before retrying.') }
    finally { if (alive.current) setActing(false) }
  }

  const initialized = agents.filter(a => typeof a.hrv === 'number' && Number.isFinite(a.hrv) && typeof a.max_hrv === 'number' && a.max_hrv > 0)
  const intervalCount = initialized.filter(a => a.in_interval).length
  const activeCount = initialized.length - intervalCount
  const unknownCount = agents.length - initialized.length

  return (
    <div>
      <div className="page-header flex-between">
        <div><div className="page-title">Dashboard</div><div className="page-sub">System overview and controls</div></div>
        <div className="flex gap-8">
          <button className="btn btn-ghost" disabled={IS_PREVIEW || acting} onClick={handleInit}>Initialize System</button>
          <button className="btn btn-primary" onClick={load}>Refresh</button>
        </div>
      </div>
      {IS_PREVIEW && <div className="notice">Fixture preview — market values and agent status are examples, not live observations. Initialize, phase changes, and real Wake are disabled. Preview wake choices do not run an agent.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}
      {initMsg && <div className="mb-16" role="status" style={{color:'var(--accent2)', fontSize:13}}>{initMsg}</div>}
      {snapshot.error && <div className="error-msg mb-16" role="alert">Market data unavailable: {String(snapshot.error)}</div>}
      <div className="grid-4 mb-16">
        <div className="stat-tile"><div className="stat-label">VIX</div><div className="stat-value">{snapshot.vix?.toFixed(2) ?? '—'}</div><div className="stat-sub">{snapshot.vix_change_pct != null ? `${snapshot.vix_change_pct > 0 ? '+' : ''}${snapshot.vix_change_pct.toFixed(2)}%` : 'Change unavailable'}</div></div>
        <div className="stat-tile"><div className="stat-label">SPY</div><div className="stat-value">{snapshot.spy_price?.toFixed(2) ?? '—'}</div><div className="stat-sub">{snapshot.spy_change_pct != null ? `${snapshot.spy_change_pct > 0 ? '+' : ''}${snapshot.spy_change_pct.toFixed(2)}%` : 'Change unavailable'}</div></div>
        <div className="stat-tile"><div className="stat-label">Fear / Greed</div><div className="stat-value">{snapshot.fear_greed_score ?? '—'}</div><div className="stat-sub">{snapshot.fear_greed_rating ?? ''}</div></div>
        <div className="stat-tile"><div className="stat-label">Market Mood</div><div className="stat-value" style={{fontSize:16, paddingTop:6}}>{snapshot.market_mood?.replace(/_/g,' ') ?? '—'}</div><div className="stat-sub">{activeCount} active · {intervalCount} resting{unknownCount > 0 ? ` · ${unknownCount} not initialized` : ''}</div></div>
      </div>
      <div className="card mb-16">
        <div className="card-title">Developmental Phase {phase !== null && <span style={{marginLeft:12, fontSize:12, color:'var(--accent)', fontWeight:400}}>currently: Phase {phase} — {PHASE_NAMES[phase] || 'Unknown phase'}</span>}</div>
        <div className="flex gap-8" style={{flexWrap:'wrap'}}>{[0,1,2,3].map(p => <button key={p} className={`btn ${phase === p ? 'btn-primary' : 'btn-ghost'}`} disabled={IS_PREVIEW || acting} onClick={() => handlePhase(p)}>Phase {p}: {PHASE_NAMES[p]}</button>)}</div>
        {phase === null && <div style={{fontSize:12, color:'var(--text3)', marginTop:8}}>{loading ? 'Loading phase...' : 'Current phase unavailable.'}</div>}
      </div>
      {countdownTarget && countdownSeconds > 0 && <div className="card mb-16"><div className="countdown"><div className="countdown-label">Council Convergence Countdown{IS_PREVIEW ? ' — fixture' : ''}</div><div className="countdown-value">{formatCountdown(countdownSeconds)}</div><div style={{fontSize:12, color:'var(--text3)', marginTop:8}}>{countdownContent}</div></div></div>}
      <div className="card">
        <div className="card-title">Agent Status</div>
        {loading ? <div className="loading">Loading...</div> : <div style={{display:'flex', flexDirection:'column', gap:12}}>
          {agents.map(a => <div key={a.agent_id} style={{display:'flex', alignItems:'center', gap:16, flexWrap:'wrap'}}>
            <div style={{width:140, minWidth:140}}><div style={{fontSize:13, fontWeight:700, color:a.in_interval ? 'var(--text3)' : 'var(--text)'}}>{a.name || a.agent_id.replace(/_/g,' ')}</div>{a.in_interval && <div className="interval-badge">in interval</div>}</div>
            <div style={{flex:'1 1 160px'}}><HRVBar hrv={a.hrv} max={a.max_hrv} interval={a.in_interval} /></div>
            <div className="flex gap-8" style={{flexWrap:'wrap'}}>
              <Link className="btn btn-ghost" style={{fontSize:11, padding:'4px 10px'}} to={`/choices?agent=${encodeURIComponent(a.agent_id)}`}>Preview wake choices</Link>
              <button className="btn btn-ghost" style={{fontSize:11, padding:'4px 10px'}} disabled={IS_PREVIEW || acting} onClick={() => handleWake(a.agent_id)}>Wake</button>
            </div>
          </div>)}
        </div>}
      </div>
    </div>
  )
}

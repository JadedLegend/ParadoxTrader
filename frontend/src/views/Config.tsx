import { useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getConfig, updateConfig, setCountdown } from '../api'

const AGENTS = ['tempest','siren','alchemist','weaver','oracle','shadow','paradox_hunter']

export default function Config() {
  const [cfg, setCfg] = useState<any>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [countdownDate, setCountdownDate] = useState('')
  const [countdownSaving, setCountdownSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    let cancelled = false
    getConfig().then(d => { if (!cancelled) setCfg(d.config || {}) })
      .catch(() => { if (!cancelled) setError('Could not load configuration. Reload this screen to retry; do not save unverified settings.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; alive.current = false }
  }, [])

  const save = async (key: string, value: unknown) => {
    if (IS_PREVIEW || saving) return
    setSaving(key)
    setError('')
    try {
      await updateConfig(key, value)
      if (!alive.current) return
      setCfg((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev))
        const parts = key.split('.')
        let node = next
        for (let i = 0; i < parts.length - 1; i++) {
          if (!node[parts[i]]) node[parts[i]] = {}
          node = node[parts[i]]
        }
        node[parts[parts.length - 1]] = value
        return next
      })
      setSaved(key)
    } catch { if (alive.current) setError('Could not save configuration. Your input is retained; check the connected backend before retrying.') }
    finally { if (alive.current) setSaving(null) }
  }

  const handleCountdown = async () => {
    if (IS_PREVIEW || !countdownDate || countdownSaving) return
    const date = new Date(countdownDate)
    if (!Number.isFinite(date.getTime())) { setError('Choose a valid countdown date and time.'); return }
    setCountdownSaving(true)
    setError('')
    try {
      await setCountdown(date.toISOString())
      if (alive.current) setMessage('Countdown set and posted to the forum.')
    } catch { if (alive.current) setError('Could not set the countdown. Check the connection before retrying.') }
    finally { if (alive.current) setCountdownSaving(false) }
  }

  // Preview returns before any credential form or connected mutation controls are rendered.
  if (IS_PREVIEW) return (
    <div>
      <div className="page-header"><div className="page-title">Configuration</div><div className="page-sub">Read-only fixture settings</div></div>
      <div className="notice">Preview uses fixture data. Configuration changes, credential entry, trading-mode changes, and countdown writes are disabled. No secret inputs are shown.</div>
      {error && <div className="error-msg" role="alert">{error}</div>}
      {loading ? <div className="loading">Loading fixture settings...</div> : <>
        <div className="card mb-16">
          <div className="card-title">Agent Model Assignments</div>
          {AGENTS.map(a => <div key={a} className="flex-between" style={{padding:'8px 0', display:'flex', gap:12, flexWrap:'wrap', borderBottom:'1px solid var(--border)', fontSize:13}}><span>{a.replace(/_/g,' ')}</span><span style={{color:'var(--text3)', overflowWrap:'anywhere'}}>{cfg.agent_models?.[a] || 'Not configured in fixture'}</span></div>)}
        </div>
        <div className="grid-2 mb-16">
          <div className="card"><div className="card-title">Trading Guardrails</div>
            <p style={{fontSize:13}}>Mode: {cfg.guardrails?.autonomous_trading_mode === true ? 'Autonomous (fixture only)' : cfg.guardrails?.autonomous_trading_mode === false ? 'Review required (fixture only)' : 'Unavailable'}</p>
            <p style={{fontSize:13}}>Max position size: {cfg.guardrails?.max_position_size_pct == null ? 'Unavailable' : `${cfg.guardrails.max_position_size_pct}%`}</p>
            <p style={{fontSize:13}}>Max open positions: {cfg.guardrails?.max_open_positions ?? 'Unavailable'}</p>
            <p style={{fontSize:13}}>Daily loss limit: {cfg.guardrails?.daily_loss_limit_pct == null ? 'Unavailable' : `${cfg.guardrails.daily_loss_limit_pct}%`}</p>
          </div>
          <div className="card"><div className="card-title">Runtime</div>
            <p style={{fontSize:13}}>Wake interval: {cfg.runtime?.wake_interval_seconds == null ? 'Unavailable' : `${cfg.runtime.wake_interval_seconds}s`}</p>
            <p style={{fontSize:13}}>Wake duration: {cfg.runtime?.wake_duration_seconds == null ? 'Unavailable' : `${cfg.runtime.wake_duration_seconds}s`}</p>
            <p style={{fontSize:13}}>Current phase: {cfg.runtime?.current_phase ?? 'Unavailable'}</p>
            <div style={{fontSize:12, color:'var(--text3)'}}>These settings do not start a scheduler, execute trades, or wake an agent.</div>
          </div>
        </div>
        <div className="card"><div className="card-title">Connected configuration</div><p style={{fontSize:13, color:'var(--text3)', lineHeight:1.7}}>Provider credentials are not displayed or editable in preview. The historical connected configuration endpoint requires a separate storage and security review; this interface makes no guarantee about where credentials are stored.</p></div>
      </>}
    </div>
  )

  if (loading) return <div className="loading">Loading config...</div>
  if (error && Object.keys(cfg).length === 0) return <div className="error-msg" role="alert">{error}</div>

  return (
    <div>
      <div className="page-header"><div className="page-title">Configuration</div><div className="page-sub">Connected backend configuration and system settings</div></div>
      <div className="notice">These historical controls submit values to the connected backend configuration endpoint. This screen does not verify secure secret storage. Review the backend's storage and access controls before entering credentials; environment-variable setup is a separate deployment operation.</div>
      {error && <div className="error-msg" role="alert">{error}</div>}
      {message && <div className="notice" role="status">{message}</div>}
      <div className="card mb-16">
        <div className="card-title">Agent Model Assignments</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>Each agent uses a different model via OpenRouter. Use the exact model ID from <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>openrouter.ai/models</a>. Changes take effect on the next agent wake cycle.</div>
        {AGENTS.map(a => <ConfigField key={a} label={a.replace(/_/g,' ')} keyPath={`agent_models.${a}`} value={cfg.agent_models?.[a]} type="text" onSave={save} saving={saving} saved={saved} />)}
      </div>
      <div className="card mb-16">
        <div className="card-title">Trading Guardrails</div>
        <div className="input-group">
          <label className="input-label">Autonomous Trading Mode</label>
          <div className="flex gap-8" style={{flexWrap:'wrap'}}>
            <button className={`btn ${cfg.guardrails?.autonomous_trading_mode ? 'btn-primary' : 'btn-ghost'}`} disabled={saving !== null} onClick={() => save('guardrails.autonomous_trading_mode', true)}>ON — trades execute automatically</button>
            <button className={`btn ${!cfg.guardrails?.autonomous_trading_mode ? 'btn-danger' : 'btn-ghost'}`} disabled={saving !== null} onClick={() => save('guardrails.autonomous_trading_mode', false)}>OFF — trades queue for review</button>
          </div>
          <div style={{fontSize:11, color:'var(--text3)', marginTop:6}}>Current: <strong>{cfg.guardrails?.autonomous_trading_mode === true ? 'AUTONOMOUS' : cfg.guardrails?.autonomous_trading_mode === false ? 'REVIEW REQUIRED' : 'UNAVAILABLE'}</strong></div>
        </div>
        <ConfigField label="Max Position Size (%)" keyPath="guardrails.max_position_size_pct" value={cfg.guardrails?.max_position_size_pct} type="number" onSave={save} saving={saving} saved={saved} />
        <ConfigField label="Max Open Positions" keyPath="guardrails.max_open_positions" value={cfg.guardrails?.max_open_positions} type="number" onSave={save} saving={saving} saved={saved} />
        <ConfigField label="Daily Loss Limit (%)" keyPath="guardrails.daily_loss_limit_pct" value={cfg.guardrails?.daily_loss_limit_pct} type="number" onSave={save} saving={saving} saved={saved} />
      </div>
      <div className="card mb-16"><div className="card-title">OpenRouter</div><div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>For environment-based deployment, configure OPENROUTER_API_KEY outside this form. Saving below uses the backend configuration endpoint instead.</div><ConfigField label="API Key (backend configuration)" keyPath="openrouter.api_key" value={cfg.openrouter?.api_key} type="password" onSave={save} saving={saving} saved={saved} /></div>
      <div className="card mb-16">
        <div className="card-title">Alpaca Paper Trading Accounts</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>One paper account per agent. Deployment environment names include ALPACA_KEY_TEMPEST and ALPACA_SECRET_TEMPEST. The fields below use the historical backend configuration path, not the deployment environment.</div>
        {AGENTS.map(a => <div key={a} style={{marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)'}}><div style={{fontSize:12, fontWeight:600, color:'var(--text)', marginBottom:6, textTransform:'capitalize'}}>{a.replace(/_/g,' ')}</div><div className="grid-2" style={{gap:8}}>
          <ConfigField label="API Key" keyPath={`alpaca.${a}.api_key`} value={cfg.alpaca?.[a]?.api_key} type="password" onSave={save} saving={saving} saved={saved} />
          <ConfigField label="Secret" keyPath={`alpaca.${a}.secret_key`} value={cfg.alpaca?.[a]?.secret_key} type="password" onSave={save} saving={saving} saved={saved} />
        </div></div>)}
      </div>
      <div className="card mb-16"><div className="card-title">Financial Modeling Prep</div><ConfigField label="API Key" keyPath="fmp.api_key" value={cfg.fmp?.api_key} type="password" onSave={save} saving={saving} saved={saved} /></div>
      <div className="card mb-16"><div className="card-title">Runtime</div><ConfigField label="Wake Interval (seconds)" keyPath="runtime.wake_interval_seconds" value={cfg.runtime?.wake_interval_seconds} type="number" onSave={save} saving={saving} saved={saved} /><ConfigField label="Wake Duration (seconds)" keyPath="runtime.wake_duration_seconds" value={cfg.runtime?.wake_duration_seconds} type="number" onSave={save} saving={saving} saved={saved} /></div>
      <div className="card mb-16"><div className="card-title">Phase 2 Countdown</div><div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>Set the date when the council converges. A countdown will appear on the dashboard and an announcement will be posted to the forum.</div><div className="flex gap-8" style={{flexWrap:'wrap'}}><input aria-label="Countdown date and time" type="datetime-local" className="input" value={countdownDate} onChange={e => setCountdownDate(e.target.value)} /><button className="btn btn-primary" onClick={handleCountdown} disabled={!countdownDate || countdownSaving}>{countdownSaving ? 'Setting...' : 'Set Countdown'}</button></div></div>
    </div>
  )
}

function ConfigField({ label, keyPath, value, type, onSave, saving, saved }: {
  label: string; keyPath: string; value: any; type: string;
  onSave: (k: string, v: unknown) => void; saving: string | null; saved: string | null
}) {
  const [val, setVal] = useState(value ?? '')
  useEffect(() => { setVal(value ?? '') }, [value])
  const isSaving = saving === keyPath
  const isSaved = saved === keyPath
  return <div className="input-group"><label className="input-label" htmlFor={keyPath}>{label}</label><div className="flex gap-8">
    <input id={keyPath} className="input" type={type === 'password' ? 'password' : type === 'number' ? 'number' : 'text'} value={val} onChange={e => setVal(type === 'number' ? Number(e.target.value) : e.target.value)} placeholder={type === 'password' ? '(backend configuration)' : ''} />
    <button className="btn btn-ghost" style={{minWidth:60, fontSize:12}} onClick={() => onSave(keyPath, val)} disabled={saving !== null}>{isSaving ? 'Saving...' : isSaved ? 'Saved' : 'Save'}</button>
  </div></div>
}

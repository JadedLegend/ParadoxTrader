import { useEffect, useState } from 'react'
import { getConfig, updateConfig, setCountdown } from '../api'

const AGENTS = ['tempest','siren','alchemist','weaver','oracle','shadow','paradox_hunter']

export default function Config() {
  const [cfg, setCfg] = useState<any>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [countdownDate, setCountdownDate] = useState('')

  useEffect(() => {
    getConfig().then(d => { setCfg(d.config || {}); setLoading(false) })
  }, [])

  const save = async (key: string, value: unknown) => {
    setSaving(key)
    try {
      await updateConfig(key, value)
      // Update local state immediately so UI reflects the change
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
      setTimeout(() => setSaved(null), 2000)
    } finally { setSaving(null) }
  }

  const handleCountdown = async () => {
    if (!countdownDate) return
    await setCountdown(new Date(countdownDate).toISOString())
    alert('Countdown set and posted to forum.')
  }

  if (loading) return <div className="loading">Loading config...</div>

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Configuration</div>
        <div className="page-sub">API keys and system settings — keys are stored as environment variables on Render and never committed to GitHub</div>
      </div>

      {/* Model Assignments */}
      <div className="card mb-16">
        <div className="card-title">Agent Model Assignments</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>
          Each agent uses a different model via OpenRouter. Use the exact model ID from{' '}
          <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>openrouter.ai/models</a>.
          Changes take effect on the next agent wake cycle.
        </div>
        {AGENTS.map(a => (
          <ConfigField
            key={a}
            label={a.replace('_', ' ')}
            keyPath={`agent_models.${a}`}
            value={cfg.agent_models?.[a]}
            type="text"
            onSave={save}
            saving={saving}
            saved={saved}
          />
        ))}
      </div>

      {/* Guardrails */}
      <div className="card mb-16">
        <div className="card-title">Trading Guardrails</div>

        <div className="input-group">
          <label className="input-label">Autonomous Trading Mode</label>
          <div className="flex gap-8">
            <button
              className={`btn ${cfg.guardrails?.autonomous_trading_mode ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => save('guardrails.autonomous_trading_mode', true)}
            >
              ON — trades execute automatically
            </button>
            <button
              className={`btn ${!cfg.guardrails?.autonomous_trading_mode ? 'btn-danger' : 'btn-ghost'}`}
              onClick={() => save('guardrails.autonomous_trading_mode', false)}
            >
              OFF — trades queue for review
            </button>
          </div>
          <div style={{fontSize:11, color:'var(--text3)', marginTop:6}}>
            Current: <strong style={{color: cfg.guardrails?.autonomous_trading_mode ? 'var(--success)' : 'var(--danger)'}}>
              {cfg.guardrails?.autonomous_trading_mode ? 'AUTONOMOUS' : 'REVIEW REQUIRED'}
            </strong>
          </div>
        </div>

        <ConfigField label="Max Position Size (%)" keyPath="guardrails.max_position_size_pct" value={cfg.guardrails?.max_position_size_pct} type="number" onSave={save} saving={saving} saved={saved} />
        <ConfigField label="Max Open Positions" keyPath="guardrails.max_open_positions" value={cfg.guardrails?.max_open_positions} type="number" onSave={save} saving={saving} saved={saved} />
        <ConfigField label="Daily Loss Limit (%)" keyPath="guardrails.daily_loss_limit_pct" value={cfg.guardrails?.daily_loss_limit_pct} type="number" onSave={save} saving={saving} saved={saved} />
      </div>

      {/* OpenRouter */}
      <div className="card mb-16">
        <div className="card-title">OpenRouter</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>
          Set your OpenRouter API key as the environment variable <code style={{background:'var(--bg3)', padding:'1px 5px', borderRadius:3}}>OPENROUTER_API_KEY</code> in your Render dashboard. It will never be stored in the repo.
        </div>
        <ConfigField label="API Key (stored in env var, shown as ***)" keyPath="openrouter.api_key" value={cfg.openrouter?.api_key} type="password" onSave={save} saving={saving} saved={saved} />
      </div>

      {/* Alpaca Accounts */}
      <div className="card mb-16">
        <div className="card-title">Alpaca Paper Trading Accounts</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>
          One paper trading account per agent. Set keys as environment variables in Render: <code style={{background:'var(--bg3)', padding:'1px 5px', borderRadius:3}}>ALPACA_KEY_TEMPEST</code>, <code style={{background:'var(--bg3)', padding:'1px 5px', borderRadius:3}}>ALPACA_SECRET_TEMPEST</code>, etc.
        </div>
        {AGENTS.map(a => (
          <div key={a} style={{marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)'}}>
            <div style={{fontSize:12, fontWeight:600, color:'var(--text)', marginBottom:6, textTransform:'capitalize'}}>{a.replace('_',' ')}</div>
            <div className="grid-2" style={{gap:8}}>
              <ConfigField label="API Key" keyPath={`alpaca.${a}.api_key`} value={cfg.alpaca?.[a]?.api_key} type="password" onSave={save} saving={saving} saved={saved} />
              <ConfigField label="Secret" keyPath={`alpaca.${a}.secret_key`} value={cfg.alpaca?.[a]?.secret_key} type="password" onSave={save} saving={saving} saved={saved} />
            </div>
          </div>
        ))}
      </div>

      {/* FMP */}
      <div className="card mb-16">
        <div className="card-title">Financial Modeling Prep</div>
        <ConfigField label="API Key" keyPath="fmp.api_key" value={cfg.fmp?.api_key} type="password" onSave={save} saving={saving} saved={saved} />
      </div>

      {/* Runtime */}
      <div className="card mb-16">
        <div className="card-title">Runtime</div>
        <ConfigField label="Wake Interval (seconds)" keyPath="runtime.wake_interval_seconds" value={cfg.runtime?.wake_interval_seconds} type="number" onSave={save} saving={saving} saved={saved} />
        <ConfigField label="Wake Duration (seconds)" keyPath="runtime.wake_duration_seconds" value={cfg.runtime?.wake_duration_seconds} type="number" onSave={save} saving={saving} saved={saved} />
      </div>

      {/* Countdown */}
      <div className="card mb-16">
        <div className="card-title">Phase 2 Countdown</div>
        <div style={{fontSize:12, color:'var(--text3)', marginBottom:12}}>Set the date when the council converges. A countdown will appear on the dashboard and an announcement will be posted to the forum.</div>
        <div className="flex gap-8">
          <input type="datetime-local" className="input" value={countdownDate} onChange={e => setCountdownDate(e.target.value)} />
          <button className="btn btn-primary" onClick={handleCountdown} disabled={!countdownDate}>Set Countdown</button>
        </div>
      </div>
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
  return (
    <div className="input-group">
      <label className="input-label">{label}</label>
      <div className="flex gap-8">
        <input
          className="input"
          type={type === 'password' ? 'password' : type === 'number' ? 'number' : 'text'}
          value={val}
          onChange={e => setVal(type === 'number' ? Number(e.target.value) : e.target.value)}
          placeholder={type === 'password' ? '(set via env var on Render)' : ''}
        />
        <button className="btn btn-ghost" style={{minWidth:60, fontSize:12}} onClick={() => onSave(keyPath, val)} disabled={isSaving}>
          {isSaving ? '...' : isSaved ? '✓' : 'Save'}
        </button>
      </div>
    </div>
  )
}

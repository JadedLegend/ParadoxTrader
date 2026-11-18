import { useEffect, useMemo, useRef, useState } from 'react'
import { getSettings, saveSettings, type OwnerSettings, type SettingsChanges } from '../api'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'

const SLOTS = [...REHEARSAL_AGENTS.map(agent => ({ id: agent.id as string, name: agent.name })), { id: 'witness', name: 'Witness' }]
const CATALOG_URL = 'https://openrouter.ai/api/v1/models'
// Data and broker keys: stored for later steps; nothing uses them yet.
const SECRETS = [
  { id: 'alpaca_key_id', name: 'Alpaca key ID (paper)', placeholder: 'PK...', note: 'Paper-trading keys only. Live keys (AK...) are refused.' },
  { id: 'alpaca_secret', name: 'Alpaca secret (paper)', placeholder: '', note: '' },
  { id: 'public_com', name: 'Public.com', placeholder: '', note: 'For market data. Nothing here places orders.' },
  { id: 'alphavantage', name: 'Alpha Vantage', placeholder: '', note: '' },
  { id: 'fmp', name: 'Financial Modeling Prep', placeholder: '', note: '' },
  { id: 'bigdata', name: 'Bigdata.com', placeholder: '', note: '' },
] as const
const FIELD_LABEL: Record<string, string> = {
  daily_budget_usd: 'Daily budget', openrouter_key: 'OpenRouter key',
  ...Object.fromEntries(SECRETS.map(item => [`secret.${item.id}`, item.name])),
}

interface CatalogModel { id: string; prompt: number; completion: number }

// The public OpenRouter catalog is read straight from the browser: the server has
// no internet access and no key is sent. If it cannot load, model IDs can be typed.
async function loadCatalog(signal: AbortSignal): Promise<CatalogModel[]> {
  const response = await fetch(CATALOG_URL, { signal, credentials: 'omit' })
  if (!response.ok) throw new Error('catalog unavailable')
  const body = await response.json() as { data?: { id?: unknown; pricing?: { prompt?: unknown; completion?: unknown } }[] }
  return (body.data ?? [])
    .filter(row => typeof row.id === 'string')
    .map(row => ({ id: row.id as string, prompt: Number(row.pricing?.prompt ?? NaN), completion: Number(row.pricing?.completion ?? NaN) }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

function perMillion(rate: number) {
  return Number.isFinite(rate) ? `$${(rate * 1_000_000).toFixed(2)}` : 'unknown'
}

function fieldName(field: string) {
  if (field.startsWith('model.')) {
    const slot = SLOTS.find(item => item.id === field.slice(6))
    return `${slot?.name ?? field.slice(6)}'s model`
  }
  return FIELD_LABEL[field] ?? field
}

export default function Settings() {
  const [settings, setSettings] = useState<OwnerSettings | null>(null)
  const [loadError, setLoadError] = useState('')
  const [catalog, setCatalog] = useState<CatalogModel[] | null>(null)
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [models, setModels] = useState<Record<string, string>>({})
  const [budget, setBudget] = useState('')
  const [key, setKey] = useState('')
  const [secretDrafts, setSecretDrafts] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const alive = useRef(true)

  const apply = (value: OwnerSettings) => {
    setSettings(value)
    setModels(Object.fromEntries(SLOTS.map(slot => [slot.id, value.models[slot.id] ?? ''])))
    setBudget(value.daily_budget_usd ?? '')
  }

  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    getSettings().then(value => { if (alive.current) apply(value) })
      .catch(() => { if (alive.current) setLoadError('Settings could not be loaded. Reload this page to try again; nothing was changed.') })
    loadCatalog(controller.signal).then(rows => { if (alive.current) setCatalog(rows) })
      .catch(() => { if (alive.current) setCatalogFailed(true) })
    return () => { alive.current = false; controller.abort() }
  }, [])

  const prices = useMemo(() => new Map((catalog ?? []).map(row => [row.id, row])), [catalog])

  const save = async (what: string, changes: SettingsChanges, done: string) => {
    if (saving) return
    setSaving(what)
    setError('')
    setMessage('')
    try {
      const value = await saveSettings(changes)
      if (!alive.current) return
      apply(value)
      if (what === 'key') setKey('')
      if (what.startsWith('secret.')) setSecretDrafts(current => ({ ...current, [what.slice(7)]: '' }))
      setMessage(done)
    } catch {
      if (alive.current) setError('That was not saved. Check the value and try again; your input is still here.')
    } finally {
      if (alive.current) setSaving(null)
    }
  }

  const changedModels = Object.fromEntries(SLOTS.filter(slot => models[slot.id] && models[slot.id] !== (settings?.models[slot.id] ?? ''))
    .map(slot => [slot.id, models[slot.id].trim()]))

  if (loadError) return <div><header className="page-header"><h1 className="page-title">Settings</h1></header><div className="error-msg" role="alert">{loadError}</div></div>
  if (!settings) return <div className="loading" role="status">Loading settings...</div>

  return (
    <div className="settings">
      <header className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-sub">Each agent's model, the OpenRouter key and the daily budget. Changes apply from each agent's next wake.</p>
      </header>
      {message && <div className="notice" role="status">{message}</div>}
      {error && <div className="error-msg mb-16" role="alert">{error}</div>}

      <section className="card mb-16" aria-labelledby="settings-models">
        <h2 className="card-title" id="settings-models">Models</h2>
        <p className="settings-help">{catalogFailed
          ? 'The OpenRouter model list could not be loaded, so type the exact model ID (for example deepseek/deepseek-v3.2).'
          : 'Pick from the OpenRouter catalog or type a model ID. Prices are per million tokens, input / output.'}</p>
        <datalist id="openrouter-models">{(catalog ?? []).map(row => <option key={row.id} value={row.id} />)}</datalist>
        <div className="settings-models">
          {SLOTS.map(slot => {
            const price = prices.get(models[slot.id])
            return <div className="input-group settings-model" key={slot.id}>
              <label className="input-label" htmlFor={`model-${slot.id}`}>{slot.name}</label>
              <input id={`model-${slot.id}`} className="input" list="openrouter-models" value={models[slot.id] ?? ''}
                placeholder="Not chosen yet" spellCheck={false} autoComplete="off"
                onChange={event => setModels(current => ({ ...current, [slot.id]: event.target.value }))} />
              <span className="settings-note">{slot.id === 'witness'
                ? 'Saved for when the witness writes its daily account in prose. It uses no model yet.'
                : price ? `${perMillion(price.prompt)} / ${perMillion(price.completion)}` : models[slot.id] && catalog ? 'Not in the current catalog' : ''}</span>
            </div>
          })}
        </div>
        <button className="btn btn-primary" disabled={saving !== null || Object.keys(changedModels).length === 0}
          onClick={() => save('models', { models: changedModels }, 'Models saved. Each agent uses its new model from its next wake.')}>
          {saving === 'models' ? 'Saving...' : 'Save models'}
        </button>
      </section>

      <div className="grid-2 mb-16">
        <section className="card" aria-labelledby="settings-budget">
          <h2 className="card-title" id="settings-budget">Daily budget</h2>
          <div className="input-group">
            <label className="input-label" htmlFor="daily-budget">US dollars per day, for all seven together</label>
            <div className="flex gap-8">
              <input id="daily-budget" className="input" type="number" inputMode="decimal" min="0" max="100" step="0.01"
                value={budget} placeholder="Not set" onChange={event => setBudget(event.target.value)} />
              <button className="btn btn-primary" disabled={saving !== null || !budget || budget === settings.daily_budget_usd}
                onClick={() => save('budget', { daily_budget_usd: Number(budget).toFixed(2) }, 'Daily budget saved.')}>
                {saving === 'budget' ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
          <p className="settings-note">Lowering it applies at once. Raising it applies from the next wake. The agents stop for the day when it is spent.</p>
        </section>

        <section className="card" aria-labelledby="settings-key">
          <h2 className="card-title" id="settings-key">OpenRouter key</h2>
          <p className="settings-key-status">{settings.key.set ? <>Set, ends in <code>…{settings.key.ends_with}</code></> : 'Not set: the agents cannot wake with real models.'}</p>
          <div className="input-group">
            <label className="input-label" htmlFor="openrouter-key">{settings.key.set ? 'Replace the key' : 'Add a key'}</label>
            <div className="flex gap-8">
              <input id="openrouter-key" className="input" type="password" autoComplete="off" spellCheck={false}
                value={key} placeholder="sk-or-..." onChange={event => setKey(event.target.value)} />
              <button className="btn btn-primary" disabled={saving !== null || !key.trim()}
                onClick={() => save('key', { openrouter_key: key.trim() }, 'Key saved. It is stored on the server and never shown again.')}>
                {saving === 'key' ? 'Saving...' : 'Save key'}
              </button>
            </div>
          </div>
          {settings.key.set && <button className="btn btn-ghost" disabled={saving !== null}
            onClick={() => { if (window.confirm('Remove the OpenRouter key? Real wakes stop until a new key is saved.')) void save('remove', { openrouter_key: '' }, 'Key removed. Real wakes are off until a new key is saved.') }}>
            Remove key
          </button>}
          <p className="settings-note">Stored only on your server, readable by the agents' service. This page never receives it back.</p>
        </section>
      </div>

      <section className="card mb-16" aria-labelledby="settings-secrets">
        <h2 className="card-title" id="settings-secrets">Data and broker keys</h2>
        <p className="settings-help">Stored on your server for the market-data and paper-trading steps. Nothing uses them yet, and like the OpenRouter key they are never shown again.</p>
        <div className="settings-secrets">
          {SECRETS.map(item => {
            const state = settings.secrets?.[item.id]
            const draft = secretDrafts[item.id] ?? ''
            return <div className="input-group settings-secret" key={item.id}>
              <label className="input-label" htmlFor={`secret-${item.id}`}>{item.name}</label>
              <span className="settings-note">{state?.set ? <>Set, ends in <code>…{state.ends_with}</code></> : 'Not set'}</span>
              <div className="flex gap-8">
                <input id={`secret-${item.id}`} className="input" type="password" autoComplete="off" spellCheck={false}
                  value={draft} placeholder={item.placeholder} onChange={event => setSecretDrafts(current => ({ ...current, [item.id]: event.target.value }))} />
                <button className="btn btn-primary" disabled={saving !== null || !draft.trim()} aria-label={`Save ${item.name}`}
                  onClick={() => save(`secret.${item.id}`, { secrets: { [item.id]: draft.trim() } }, `${item.name} saved.`)}>
                  {saving === `secret.${item.id}` ? 'Saving...' : 'Save'}
                </button>
                {state?.set && <button className="btn btn-ghost" disabled={saving !== null} aria-label={`Remove ${item.name}`}
                  onClick={() => { if (window.confirm(`Remove the ${item.name} key?`)) void save(`secret.${item.id}`, { secrets: { [item.id]: '' } }, `${item.name} removed.`) }}>
                  Remove
                </button>}
              </div>
              {item.note && <span className="settings-note">{item.note}</span>}
            </div>
          })}
        </div>
      </section>

      <section className="card" aria-labelledby="settings-history">
        <h2 className="card-title" id="settings-history">Recent changes</h2>
        {settings.history.length === 0 ? <p className="settings-note">Nothing has been changed yet.</p> :
          <ul className="settings-history">{settings.history.map((row, index) => <li key={`${row.changed_at}-${row.field}-${index}`}>
            <time dateTime={row.changed_at}>{new Date(row.changed_at).toLocaleString()}</time>
            <span>{fieldName(row.field)}: {String(row.value)}</span>
          </li>)}</ul>}
      </section>
    </div>
  )
}

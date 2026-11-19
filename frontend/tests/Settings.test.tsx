import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../src/api'
import Settings from '../src/views/Settings'
import { createApiClient } from '../src/data/client'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  getSettings: vi.fn(), saveSettings: vi.fn(), checkConnection: vi.fn(), getConnectionCheck: vi.fn(),
}))

const EMPTY: api.OwnerSettings = { models: {}, daily_budget_usd: null, key: { set: false, ends_with: null }, history: [] }
const CATALOG = { data: [
  { id: 'deepseek/deepseek-v3.2', pricing: { prompt: '0.00000027', completion: '0.0000011' } },
  { id: 'google/gemini-2.5-pro', pricing: { prompt: '0.00000125', completion: '0.00001' } },
] }

beforeEach(() => {
  vi.mocked(api.getSettings).mockReset().mockResolvedValue(EMPTY)
  vi.mocked(api.saveSettings).mockReset()
  vi.mocked(api.getConnectionCheck).mockReset().mockResolvedValue({ state: 'none', requested_at: null, result: null })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => CATALOG }))
})
afterEach(() => vi.unstubAllGlobals())

describe('Settings page', () => {
  it('checks the connection and names the agents and model that failed', async () => {
    const result: api.ConnectionCheck = {
      checked_at: '2026-11-18T14:00:00Z', status: 'fail', free_limits_url: 'https://openrouter.ai/collections/free-models',
      key: { status: 'ok', message: 'The key works.' },
      models: [
        { model: 'xiaomi/mimo-v2.6-flash', used_by: ['Siren', 'Shadow'], kind: 'paid', status: 'ok', message: '3 providers serving it.' },
        { model: 'baidu/ernie-5.5-flash-preview:free', used_by: ['Alchemist'], kind: 'free', status: 'fail', message: 'rate limited' },
      ],
      unset: ['Witness'],
      services: [
        { service: 'FMP', group: 'data', status: 'fail', message: 'the key was rejected' },
        { service: 'SignalStack', group: 'broker', status: 'skipped', message: 'Stored only. Never called.' },
      ],
    }
    vi.mocked(api.checkConnection).mockReset().mockResolvedValue({ state: 'pending', requested_at: '2026-11-18T14:00:00Z', result: null })
    vi.mocked(api.getConnectionCheck).mockReset()
      .mockResolvedValueOnce({ state: 'none', requested_at: null, result: null })
      .mockResolvedValue({ state: 'done', requested_at: null, result })
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<Settings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Check connection' }))
    await vi.advanceTimersByTimeAsync(2500)
    expect(await screen.findByText('Something is not working.')).toBeTruthy()
    expect(screen.getByText('Siren, Shadow')).toBeTruthy()
    expect(screen.getByText('baidu/ernie-5.5-flash-preview:free')).toBeTruthy()
    expect(screen.getByText(/rate limited/)).toBeTruthy()
    expect(screen.getByText(/That is fine for now/)).toBeTruthy()
    expect(screen.getByText('FMP')).toBeTruthy()
    expect(screen.getByText(/the key was rejected/)).toBeTruthy()
    expect(screen.getByText(/Never called/)).toBeTruthy()
    expect(api.checkConnection).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('shows all seven agents plus the witness, and that no key is set', async () => {
    render(<Settings />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
    for (const name of ['Tempest', 'Siren', 'Alchemist', 'Weaver', 'Oracle', 'Shadow', 'ParadoxHunter', 'Witness']) {
      expect(screen.getByLabelText(name)).toBeTruthy()
    }
    expect(screen.getByText(/Not set: the agents cannot wake with real models/)).toBeTruthy()
    expect(screen.getByText(/It uses no model yet/)).toBeTruthy()
  })

  it('reads the public catalog without credentials and shows prices per million tokens', async () => {
    render(<Settings />)
    const tempest = await screen.findByLabelText('Tempest')
    fireEvent.change(tempest, { target: { value: 'deepseek/deepseek-v3.2' } })
    expect(await screen.findByText('$0.27 / $1.10')).toBeTruthy()
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('https://openrouter.ai/api/v1/models', expect.objectContaining({ credentials: 'omit' }))
  })

  it('saves only the models that changed', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, models: { oracle: 'google/gemini-2.5-pro' } })
    render(<Settings />)
    fireEvent.change(await screen.findByLabelText('Oracle'), { target: { value: 'google/gemini-2.5-pro' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save models' }))
    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ models: { oracle: 'google/gemini-2.5-pro' } }))
    expect(await screen.findByText(/from its next wake/)).toBeTruthy()
  })

  it('saves a cleaned market watchlist and refuses more than five tickers', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, watchlist: ['NVDA', 'SPY'] })
    render(<Settings />)
    const field = await screen.findByLabelText(/Up to 5 tickers/) as HTMLInputElement
    expect(field.value).toBe('SPY, QQQ, IWM, TLT, GLD')
    fireEvent.change(field, { target: { value: 'a, b, c, d, e, f' } })
    expect((screen.getByRole('button', { name: 'Save watchlist' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(field, { target: { value: 'nvda,  spy, nvda' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save watchlist' }))
    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ watchlist: ['NVDA', 'SPY'] }))
    expect(await screen.findByText('Market watchlist saved.')).toBeTruthy()
  })

  it('saves the budget with two decimals', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, daily_budget_usd: '1.50' })
    render(<Settings />)
    fireEvent.change(await screen.findByLabelText(/US dollars per day/), { target: { value: '1.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ daily_budget_usd: '1.50' }))
  })

  it('sends the key once, clears the field, and only ever shows its last four characters', async () => {
    const key = 'sk-or-v1-' + 'abcd1234'.repeat(8)
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, key: { set: true, ends_with: '1234' } })
    render(<Settings />)
    const field = await screen.findByLabelText('Add a key') as HTMLInputElement
    expect(field.type).toBe('password')
    fireEvent.change(field, { target: { value: key } })
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }))
    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ openrouter_key: key }))
    expect(await screen.findByText('…1234')).toBeTruthy()
    expect((screen.getByLabelText('Replace the key') as HTMLInputElement).value).toBe('')
    expect(document.body.textContent).not.toContain(key)
  })

  it('saves a data key once and shows only its last four characters', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, secrets: { fmp: { set: true, ends_with: 'wxyz' } } })
    render(<Settings />)
    const field = await screen.findByLabelText('Financial Modeling Prep') as HTMLInputElement
    expect(field.type).toBe('password')
    fireEvent.change(field, { target: { value: 'abcdefghijklmnopqrstuvwxyz' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Financial Modeling Prep' }))
    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ secrets: { fmp: 'abcdefghijklmnopqrstuvwxyz' } }))
    expect(await screen.findByText('…wxyz')).toBeTruthy()
    expect(api.saveSettings).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).not.toContain('abcdefghijklmnopqrstuvwxyz')
    expect(field.value).toBe('')
    expect(screen.getByText(/Live keys .AK.... are refused/)).toBeTruthy()
    expect(screen.getByLabelText('Shadow: key ID')).toBeTruthy()
    expect(screen.getByLabelText('SignalStack webhook')).toBeTruthy()
    expect(screen.getByLabelText('Unusual Whales API token')).toBeTruthy()
    expect(screen.getByLabelText('EODHD API token')).toBeTruthy()
    expect(screen.getByText('Brokers and signal routes')).toBeTruthy()
  })

  it.each(['save', 'remove'])('preserves a draft edited during a %s request', async action => {
    vi.mocked(api.getSettings).mockResolvedValue({ ...EMPTY, secrets: { fmp: { set: true, ends_with: 'aaaa' } } })
    let finish!: (value: api.OwnerSettings) => void
    vi.mocked(api.saveSettings).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<Settings />)
    const field = await screen.findByLabelText('Financial Modeling Prep') as HTMLInputElement
    fireEvent.change(field, { target: { value: 'a'.repeat(32) } })
    fireEvent.click(screen.getByRole('button', { name: `${action === 'save' ? 'Save' : 'Remove'} Financial Modeling Prep` }))
    fireEvent.change(field, { target: { value: 'b'.repeat(32) } })
    finish(EMPTY)
    expect(await screen.findByText(`Financial Modeling Prep ${action === 'save' ? 'saved' : 'removed'}.`)).toBeTruthy()
    expect(field.value).toBe('b'.repeat(32))
    expect(api.saveSettings).toHaveBeenCalledTimes(1)
    confirm.mockRestore()
  })

  it('keeps an unsent replacement draft after removing the stored credential', async () => {
    vi.mocked(api.getSettings).mockResolvedValue({ ...EMPTY, secrets: { fmp: { set: true, ends_with: 'aaaa' } } })
    vi.mocked(api.saveSettings).mockResolvedValue(EMPTY)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<Settings />)
    const field = await screen.findByLabelText('Financial Modeling Prep') as HTMLInputElement
    fireEvent.change(field, { target: { value: 'b'.repeat(32) } })
    fireEvent.click(screen.getByRole('button', { name: 'Remove Financial Modeling Prep' }))
    expect(await screen.findByText('Financial Modeling Prep removed.')).toBeTruthy()
    expect(api.saveSettings).toHaveBeenCalledExactlyOnceWith({ secrets: { fmp: '' } })
    expect(field.value).toBe('b'.repeat(32))
    confirm.mockRestore()
  })

  it('saves a credential with Enter', async () => {
    const user = userEvent.setup()
    vi.mocked(api.saveSettings).mockResolvedValue(EMPTY)
    render(<Settings />)
    const field = await screen.findByLabelText('Financial Modeling Prep')
    await user.type(field, 'a'.repeat(32) + '{Enter}')
    expect(await screen.findByText('Financial Modeling Prep saved.')).toBeTruthy()
    expect(api.saveSettings).toHaveBeenCalledExactlyOnceWith({ secrets: { fmp: 'a'.repeat(32) } })
  })

  it('retains unsent model and budget edits when saving a credential', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY, secrets: { fmp: { set: true, ends_with: 'aaaa' } } })
    render(<Settings />)
    const model = await screen.findByLabelText('Oracle') as HTMLInputElement
    const budget = screen.getByLabelText(/US dollars per day/) as HTMLInputElement
    fireEvent.change(model, { target: { value: 'example/unsaved' } })
    fireEvent.change(budget, { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Financial Modeling Prep'), { target: { value: 'a'.repeat(32) } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Financial Modeling Prep' }))
    expect(await screen.findByText('Financial Modeling Prep saved.')).toBeTruthy()
    expect(model.value).toBe('example/unsaved')
    expect(budget.value).toBe('3')
    expect(screen.getByText('…aaaa')).toBeTruthy()
  })

  it('shows unreadable credentials and reports a failed confirmed clear', async () => {
    vi.mocked(api.getSettings).mockResolvedValue({ ...EMPTY, secrets: {
      fmp: { set: false, ends_with: null, error: 'secret_unreadable' },
    } })
    vi.mocked(api.saveSettings).mockRejectedValue(new Error('clear failed'))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<Settings />)
    expect(await screen.findByText('Credential unreadable. Replace it or try removing it.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Financial Modeling Prep'), { target: { value: 'a'.repeat(32) } })
    expect((screen.getByRole('button', { name: 'Save Financial Modeling Prep' }) as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Remove Financial Modeling Prep' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(api.saveSettings).toHaveBeenCalledExactlyOnceWith({ secrets: { fmp: '' } })
    expect(screen.queryByText('Financial Modeling Prep removed.')).toBeNull()
    expect(screen.getByText('Credential unreadable. Replace it or try removing it.')).toBeTruthy()
    confirm.mockRestore()
  })

  it('adopts server changes for untouched inputs while preserving real drafts', async () => {
    vi.mocked(api.saveSettings).mockResolvedValue({ ...EMPTY,
      models: { oracle: 'example/server', siren: 'example/server' }, daily_budget_usd: '5.00',
    })
    render(<Settings />)
    const oracle = await screen.findByLabelText('Oracle') as HTMLInputElement
    fireEvent.change(screen.getByLabelText('Siren'), { target: { value: 'example/draft' } })
    fireEvent.change(screen.getByLabelText('Financial Modeling Prep'), { target: { value: 'a'.repeat(32) } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Financial Modeling Prep' }))
    await screen.findByText('Financial Modeling Prep saved.')
    expect(oracle.value).toBe('example/server')
    expect((screen.getByLabelText('Siren') as HTMLInputElement).value).toBe('example/draft')
    expect((screen.getByLabelText(/US dollars per day/) as HTMLInputElement).value).toBe('5.00')
  })

  it.each(['models', 'budget'])('preserves edits during a pending %s save', async kind => {
    let finish!: (value: api.OwnerSettings) => void
    vi.mocked(api.saveSettings).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<Settings />)
    const oracle = await screen.findByLabelText('Oracle') as HTMLInputElement
    const budget = screen.getByLabelText(/US dollars per day/) as HTMLInputElement
    const field = kind === 'models' ? oracle : budget
    fireEvent.change(field, { target: { value: kind === 'models' ? 'example/first' : '2' } })
    fireEvent.click(screen.getByRole('button', { name: kind === 'models' ? 'Save models' : 'Save' }))
    fireEvent.change(field, { target: { value: kind === 'models' ? 'example/second' : '3' } })
    finish({ ...EMPTY, models: { oracle: 'example/first' }, daily_budget_usd: '2.00' })
    await waitFor(() => expect((screen.getByRole('button', { name: kind === 'models' ? 'Save models' : 'Save' }) as HTMLButtonElement).disabled).toBe(false))
    expect(field.value).toBe(kind === 'models' ? 'example/second' : '3')
  })

  it('lets a model ID be typed when the catalog cannot load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<Settings />)
    expect(await screen.findByText(/could not be loaded, so type the exact model ID/)).toBeTruthy()
  })

  it('keeps the input and says so when a save fails', async () => {
    vi.mocked(api.saveSettings).mockRejectedValue(new Error('400'))
    render(<Settings />)
    const budget = await screen.findByLabelText(/US dollars per day/) as HTMLInputElement
    fireEvent.change(budget, { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(budget.value).toBe('2')
  })
})

describe('private host client', () => {
  it('sends GET and POST /api/settings, and still refuses every other write', async () => {
    const transport = vi.fn().mockResolvedValue({ ok: true })
    const request = createApiClient('connected', () => ({}), transport, 'private')
    await request('GET', '/api/settings')
    await request('POST', '/api/settings', { daily_budget_usd: '1.00' })
    expect(transport).toHaveBeenCalledTimes(2)
    await expect(request('POST', '/api/settings/other', {})).rejects.toThrow(/read-only/)
    await expect(request('POST', '/api/config', {})).rejects.toThrow(/read-only/)
    expect(transport).toHaveBeenCalledTimes(2)
  })
})

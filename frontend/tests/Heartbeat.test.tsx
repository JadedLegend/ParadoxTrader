import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../src/api'
import Heartbeat from '../src/views/Heartbeat'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  getHeartbeat: vi.fn(),
}))

const VIEW: api.HeartbeatView = {
  available: true, reason: 'running: next wake 2026-11-19T10:08:00-05:00', paused: false, dispatch: 'live',
  choices_per_wake: 2,
  today: { run_id: 'r1', status: 'open', reserved_usd: '0.3653', spent_usd: '0.0933', spent_complete: true,
    daily_budget_usd: '3.00', slot_outcomes: { woke: 2, missed: 1 } },
  next_wake_by_agent: { siren: '2026-11-19T10:08:00-05:00', tempest: '2026-11-19T10:30:00-05:00' },
  problems: [{ agent_id: 'oracle', scheduled_at: '2026-11-19T09:34:00-05:00', note: 'oracle on z-ai/glm-5.3: output_truncated' }],
  wakes: [
    { agent_id: 'siren', scheduled_at: '2026-11-19T09:08:00-05:00', outcome: 'woke', wake_status: 'completed',
      choices: ['library', 'rest'], model: 'xiaomi/mimo-v2.6-flash', note: null },
    { agent_id: 'oracle', scheduled_at: '2026-11-19T09:34:00-05:00', outcome: 'woke', wake_status: 'failed',
      choices: [], model: 'z-ai/glm-5.3', note: 'oracle on z-ai/glm-5.3: output_truncated' },
  ],
  agents: [
    { agent_id: 'siren', last_wake: null, next_wake: '2026-11-19T10:08:00-05:00' },
    { agent_id: 'tempest', last_wake: null, next_wake: null },
  ],
  window: {
    lines: ['Market window (market closed, last prices) as of Nov 18 16:44 ET, IEX feed, may be delayed: SPY 731.12 (-0.18%).',
      'On X: unavailable (it answered 403).'],
    feeds: [{ feed: 'Prices', status: 'ok', checked_at: '2026-11-19T14:00:00Z', detail: 'market closed, last prices' },
      { feed: 'X posts', status: 'unavailable', checked_at: '2026-11-19T14:00:00Z', detail: 'it answered 403' },
      { feed: 'Reddit', status: 'unchecked', checked_at: null, detail: null }],
  },
}

describe('Heartbeat page', () => {
  beforeEach(() => { vi.mocked(api.getHeartbeat).mockReset() })

  it('says plainly what is happening, what it cost and what needs a look', async () => {
    vi.mocked(api.getHeartbeat).mockResolvedValue(VIEW)
    render(<Heartbeat />)
    expect(await screen.findByText(/Awake\. Next wake .*Siren\./)).toBeTruthy()
    expect(screen.getByText('Each wake allows up to 2 choices.')).toBeTruthy()
    expect(screen.getByText('$0.09')).toBeTruthy()
    expect(screen.getByText(/of \$3\.00 a day/)).toBeTruthy()
    expect(screen.getAllByText(/output_truncated/).length).toBeGreaterThan(0)
    expect(screen.getByText('library, rest')).toBeTruthy()
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0)
    expect(screen.getByText('Tomorrow')).toBeTruthy()
    expect(screen.getByText(/SPY 731\.12/)).toBeTruthy()
    expect(screen.getByText(/Market closed, last prices\./)).toBeTruthy()
    expect(screen.getByText('Not read yet.')).toBeTruthy()
  })

  it('shows quiet empty states and the not-set-up message', async () => {
    vi.mocked(api.getHeartbeat).mockResolvedValueOnce({ ...VIEW, reason: 'paused', problems: [], wakes: [] })
    const { unmount } = render(<Heartbeat />)
    expect(await screen.findByText(/Paused\./)).toBeTruthy()
    expect(screen.getByText('Nothing failed today.')).toBeTruthy()
    expect(screen.getByText('No one has woken yet today.')).toBeTruthy()
    unmount()
    vi.mocked(api.getHeartbeat).mockResolvedValueOnce({ available: false, reason: 'The heartbeat is not set up on this server yet.' })
    render(<Heartbeat />)
    expect(await screen.findByText('The heartbeat is not set up on this server yet.')).toBeTruthy()
  })

  it('shows refresh errors after a not-set-up reading and clears them on recovery', async () => {
    const reason = 'The heartbeat is not set up on this server yet.'
    vi.mocked(api.getHeartbeat).mockResolvedValue({ available: false, reason })
    const timer = vi.spyOn(window, 'setInterval')
    const { unmount } = render(<Heartbeat />)
    try {
      await screen.findByText(reason)
      expect(screen.queryByRole('alert')).toBeNull()
      const refresh = timer.mock.calls.find(([, delay]) => delay === 60_000)![0] as () => void
      vi.mocked(api.getHeartbeat).mockRejectedValueOnce(new Error('down'))
      await act(async () => { refresh() })
      expect(screen.getByRole('alert').textContent).toContain('could not be read')
      expect(screen.getByText(reason)).toBeTruthy()
      await act(async () => { refresh() })
      expect(screen.queryByRole('alert')).toBeNull()
      expect(screen.getByText(reason)).toBeTruthy()
    } finally {
      unmount()
      timer.mockRestore()
    }
  })

  it('says plainly when the day could not open', async () => {
    vi.mocked(api.getHeartbeat).mockResolvedValue({ ...VIEW, reason: "today's day could not open: invalid_catalog_price",
      problems: [{ agent_id: null, scheduled_at: '2026-11-19T09:00:00-05:00', note: "today's day could not open: invalid_catalog_price" }] })
    render(<Heartbeat />)
    expect(await screen.findByText(/No one can wake: today's day could not open \(invalid_catalog_price\)/)).toBeTruthy()
    expect(screen.getByText('The whole day')).toBeTruthy()
  })

  it('reports a failed read without blanking the page', async () => {
    vi.mocked(api.getHeartbeat).mockRejectedValue(new Error('down'))
    render(<Heartbeat />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText(/tries again every minute/)).toBeTruthy()
  })
})

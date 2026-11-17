import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Costs from '../src/views/Costs'
import { getRehearsalJobs, getRehearsalRequests, getRehearsalRun, getRehearsalRuns, getUsageEvents, getUsageSummary } from '../src/api'
import type { RehearsalAgentId, RehearsalRequest, RehearsalRequestsResponse, RehearsalRun } from '../src/rehearsal/contracts'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()), IS_PREVIEW: false, IS_PRIVATE_HOST: true,
  getRehearsalRuns: vi.fn(), getRehearsalRun: vi.fn(), getRehearsalJobs: vi.fn(), getRehearsalRequests: vi.fn(),
  getUsageSummary: vi.fn(), getUsageEvents: vi.fn(),
}))

const ID = 'aaaaaaaa-0000-4000-8000-000000000001'
const OTHER = 'bbbbbbbb-0000-4000-8000-000000000002'
const run = (run_id = ID): RehearsalRun => ({
  run_id, mode: 'real', status: 'completed', created_at: '2026-11-01T00:00:00Z', started_at: '2026-11-01T00:00:01Z', ended_at: '2026-11-01T00:10:00Z',
  stop_requested: false,
  limits: { wakes_per_agent: 2, max_requests: 40, max_output_tokens: 800, max_input_bytes: 20000, max_runtime_seconds: 900, request_timeout_seconds: 60, max_parallelism: 2, budget_usd: '2.00' },
  agent_models: {} as RehearsalRun['agent_models'], capabilities: ['rest', 'journal'],
  request_count: 12, reserved_usd: '0.48', known_cost_usd: '0.0213', unknown_cost_requests: 1,
  reported_cost_usd: '0.02', estimated_cost_usd: '0.0013', agents: [],
})
const event = (agent: RehearsalAgentId, index: number, status: 'reported' | 'estimated' | 'unknown' | undefined, reserved = '0.01'): RehearsalRequest => ({
  request_id: `${agent}-${index}`, wake_id: `${agent}-wake`, agent_id: agent, activity: 'journal', response_model: null, provider: null,
  outcome: 'success', duration_ms: 10, input_bytes: 100, max_output_tokens: 800, reserved_usd: reserved,
  usage: status ? { cost_status: status } : null, failure_code: null,
})
function requests(run_id: string, agent: RehearsalAgentId): RehearsalRequestsResponse {
  if (agent === 'tempest') return { run_id, total: 3, limit: 50, offset: 0, events: [event(agent, 1, 'reported'), event(agent, 2, 'estimated', '0.02'), event(agent, 3, 'unknown')] }
  if (agent === 'siren') return { run_id, total: 120, limit: 50, offset: 0, events: Array.from({ length: 50 }, (_, index) => event(agent, index, 'reported')) }
  return { run_id, total: 0, limit: 50, offset: 0, events: [] }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(yes => { resolve = yes })
  return { promise, resolve }
}

beforeEach(() => {
  vi.mocked(getRehearsalRuns).mockReset().mockResolvedValue({ runs: [run()], total: 1, limit: 20, offset: 0 })
  vi.mocked(getRehearsalRun).mockReset().mockImplementation(async id => run(id))
  vi.mocked(getRehearsalJobs).mockReset().mockImplementation(async id => ({ run_id: id, jobs: [] }))
  vi.mocked(getRehearsalRequests).mockReset().mockImplementation(async (id, agent) => requests(id, agent as RehearsalAgentId))
  vi.mocked(getUsageSummary).mockReset()
  vi.mocked(getUsageEvents).mockReset()
})
const renderCosts = () => render(<MemoryRouter><Costs /></MemoryRouter>)
const row = (name: string) => within(screen.getByRole('table')).getByRole('rowheader', { name }).closest('tr')! as HTMLElement

describe('Operating costs on the private host', () => {
  it('shows the run summary and per-member costs from session records', async () => {
    renderCosts()
    expect(screen.getByRole('heading', { name: 'Operating costs', level: 1 })).toBeTruthy()
    expect(screen.getByText('Per-session request costs recorded on this server')).toBeTruthy()
    const summary = await screen.findByRole('region', { name: 'Run cost summary' })
    expect(within(summary).getByText('12 / 40')).toBeTruthy()
    expect(within(summary).getByText('$0.48 / $2.00')).toBeTruthy()
    expect(within(summary).getByText('$0.0213')).toBeTruthy()
    expect(within(summary).getByText('$0.02')).toBeTruthy()
    expect(within(summary).getByText('$0.0013')).toBeTruthy()
    expect(within(summary).getByText('Missing costs are unknown, not free; reservations are not an invoice.')).toBeTruthy()
    await screen.findByRole('table')
    const tempest = row('Tempest')
    expect(within(tempest).getByText('3')).toBeTruthy()
    expect(within(tempest).getByText('$0.04')).toBeTruthy()
    expect(within(tempest).getAllByText('1')).toHaveLength(3)
    expect(within(row('Siren')).getByText('first 50 shown')).toBeTruthy()
    expect(within(row('Siren')).getByText('$0.50')).toBeTruthy()
    expect(within(row('Oracle')).getByText('$0')).toBeTruthy()
    expect(getRehearsalRequests).toHaveBeenCalledTimes(7)
    expect(getRehearsalRequests).toHaveBeenCalledWith(ID, 'tempest', 50, 0)
    expect(screen.getByRole('link', { name: 'Request details per member' }).getAttribute('href')).toBe('/rehearsal')
    expect(getUsageSummary).not.toHaveBeenCalled()
    expect(getUsageEvents).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows an explicit empty state when no runs are recorded', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [], total: 0, limit: 20, offset: 0 })
    renderCosts()
    expect(await screen.findByText('No session runs recorded on this server yet.')).toBeTruthy()
    expect(screen.getByText(/scripts\/rehearsal\.py/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    expect(getRehearsalRequests).not.toHaveBeenCalled()
  })

  it('reports a failed run list as an alert, not as an empty list', async () => {
    vi.mocked(getRehearsalRuns).mockRejectedValue(new Error('secret 500 body'))
    renderCosts()
    expect((await screen.findByRole('alert')).textContent).toBe('Run list unavailable. A failed read is not an empty run list.')
    expect(screen.queryByText('No session runs recorded on this server yet.')).toBeNull()
    expect(screen.queryByText(/secret 500 body/)).toBeNull()
  })

  it('shows Unavailable for a failed member read, with one alert and no zeros', async () => {
    vi.mocked(getRehearsalRequests).mockImplementation(async (id, agent) => {
      if (agent === 'weaver') throw new Error('boom')
      return requests(id, agent as RehearsalAgentId)
    })
    renderCosts()
    await screen.findByRole('table')
    expect(within(row('Weaver')).getAllByText('Unavailable')).toHaveLength(5)
    expect(within(row('Weaver')).queryByText('0')).toBeNull()
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(screen.getByRole('alert').textContent).toMatch(/A failed read is not zero requests/)
  })

  it('shows Unavailable reserved when an event lacks a reservation', async () => {
    vi.mocked(getRehearsalRequests).mockImplementation(async (id, agent) => agent === 'shadow'
      ? { run_id: id, total: 2, limit: 50, offset: 0, events: [event('shadow', 1, 'reported'), { ...event('shadow', 2, undefined), reserved_usd: undefined as unknown as string }] }
      : requests(id, agent as RehearsalAgentId))
    renderCosts()
    await screen.findByRole('table')
    const shadow = row('Shadow')
    expect(within(shadow).getByText('Unavailable')).toBeTruthy()
    expect(within(shadow).getAllByText('1')).toHaveLength(2)
  })

  it('ignores stale member responses after the run changes', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [run(), run(OTHER)], total: 2, limit: 20, offset: 0 })
    const stale = deferred<RehearsalRequestsResponse>()
    vi.mocked(getRehearsalRequests).mockImplementation(async (id, agent) => {
      if (id === ID && agent === 'tempest') return stale.promise
      return requests(id, agent as RehearsalAgentId)
    })
    const user = userEvent.setup()
    renderCosts()
    await screen.findByRole('region', { name: 'Run cost summary' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Run' }), OTHER)
    await screen.findByRole('table')
    stale.resolve({ run_id: ID, total: 999, limit: 50, offset: 0, events: [] })
    await waitFor(() => expect(within(row('Tempest')).getByText('3')).toBeTruthy())
    expect(screen.queryByText('999')).toBeNull()
  })

  it('re-reads member requests when Refresh reads is pressed', async () => {
    let failWeaver = true
    vi.mocked(getRehearsalRequests).mockImplementation(async (id, agent) => {
      if (agent === 'weaver' && failWeaver) throw new Error('boom')
      return requests(id, agent as RehearsalAgentId)
    })
    const user = userEvent.setup()
    renderCosts()
    await screen.findByRole('table')
    expect(within(row('Weaver')).getAllByText('Unavailable')).toHaveLength(5)
    failWeaver = false
    await user.click(screen.getByRole('button', { name: 'Refresh reads' }))
    await waitFor(() => expect(within(row('Weaver')).queryByText('Unavailable')).toBeNull())
    expect(screen.queryByText(/Some member request reads failed/)).toBeNull()
    expect(vi.mocked(getRehearsalRequests).mock.calls.filter(call => call[1] === 'weaver')).toHaveLength(2)
  })

  it('renders no write or launch controls', async () => {
    renderCosts()
    await screen.findByRole('table')
    const names = screen.getAllByRole('button').map(button => button.textContent)
    expect(names).toEqual(['Refresh reads'])
    expect(screen.queryByRole('button', { name: /start|wake|stop|resume|launch|delete|save/i })).toBeNull()
  })
})

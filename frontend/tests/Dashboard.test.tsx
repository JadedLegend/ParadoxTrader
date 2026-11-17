import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from '../src/views/Dashboard'
import { getRehearsalJobs, getRehearsalRun, getRehearsalRuns, getStatus } from '../src/api'
import { REHEARSAL_AGENTS } from '../src/rehearsal/contracts'
import type { RehearsalJob, RehearsalRun } from '../src/rehearsal/contracts'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  IS_PREVIEW: false, IS_PRIVATE_HOST: true,
  getRehearsalRuns: vi.fn(), getRehearsalRun: vi.fn(), getRehearsalJobs: vi.fn(), getRehearsalRequests: vi.fn(),
  getStatus: vi.fn(), getSnapshot: vi.fn(), getAnnouncements: vi.fn(), getConfig: vi.fn(),
  setPhase: vi.fn(), initSystem: vi.fn(), wakeAgent: vi.fn(),
}))

const ID = '11111111-1111-4111-8111-111111111111'
const OTHER = '22222222-2222-4222-8222-222222222222'
const TIME = '2026-11-12T00:00:00Z'
function run(id = ID, mode: RehearsalRun['mode'] = 'offline'): RehearsalRun {
  return { run_id: id, mode, status: 'partial', created_at: TIME, started_at: TIME, ended_at: id === ID ? '2026-11-12T00:15:00Z' : null, stop_requested: false,
    limits: { wakes_per_agent: 2, max_requests: 28, max_output_tokens: 1024, max_input_bytes: 24000, max_runtime_seconds: 900, request_timeout_seconds: 60, max_parallelism: 3, budget_usd: '1' },
    agent_models: Object.fromEntries(REHEARSAL_AGENTS.map(owner => [owner.id, `mock/exact-${owner.id}`])) as RehearsalRun['agent_models'],
    request_count: 7, reserved_usd: '0.1', known_cost_usd: null, unknown_cost_requests: 3, capabilities: ['rest', 'journal'],
    agents: REHEARSAL_AGENTS.map((owner, index) => ({ agent_id: owner.id, pending: 0, completed: index === 0 ? 2 : 0, failed: index === 2 ? 1 : 0, stopped: 0, uncertain: 0 })),
  }
}
function jobs(): RehearsalJob[] {
  return REHEARSAL_AGENTS.flatMap((owner, index) => [1, 2].map(round => ({ wake_id: `${owner.id}-r${round}`, agent_id: owner.id, round,
    status: index === 2 ? 'failed' as const : 'completed' as const, action: index === 0 ? 'journal' as const : null, failure_code: null,
    requested_model: null, response_model: null, provider: null, request_count: 1, duration_ms: null, record_refs: [], updated_at: TIME })))
}
const renderPage = () => render(<MemoryRouter><Dashboard /></MemoryRouter>)

beforeEach(() => {
  vi.mocked(getRehearsalRuns).mockReset().mockResolvedValue({ runs: [run()], total: 1, limit: 20, offset: 0 })
  vi.mocked(getRehearsalRun).mockReset().mockImplementation(async id => run(id, id === OTHER ? 'real' : 'offline'))
  vi.mocked(getRehearsalJobs).mockReset().mockImplementation(async id => ({ run_id: id, jobs: jobs() }))
  vi.mocked(getStatus).mockReset()
})

describe('private-host dashboard', () => {
  it('summarises the newest recorded run and all seven agents', async () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeTruthy()
    expect(screen.getByText('Latest recorded session on this server')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toMatch(/Loading/)
    const summary = await screen.findByRole('region', { name: 'Latest run summary' })
    expect(within(summary).getByText('Partial · Offline execution')).toBeTruthy()
    expect(within(summary).getByText(/Ended: 2026-11-12T00:15:00Z/)).toBeTruthy()
    expect(within(summary).getByText('7 / 28')).toBeTruthy()
    expect(within(summary).getByText('$0.10 / $1.00')).toBeTruthy()
    expect(within(summary).getByText('Unavailable')).toBeTruthy()
    expect(within(summary).getByText('3')).toBeTruthy()
    const table = within(screen.getByRole('region', { name: 'Agent summary table' }))
    for (const agent of REHEARSAL_AGENTS) {
      const row = within(table.getByRole('rowheader', { name: new RegExp(agent.name) }).closest('tr')!)
      expect(row.getByText(`mock/exact-${agent.id}`)).toBeTruthy()
    }
    expect(table.getAllByText(/Round 1: Journal/).length).toBe(1)
    expect(table.getAllByText(/Choice not recorded/).length).toBe(12)
    expect(screen.getByRole('link', { name: 'Open session details' }).getAttribute('href')).toBe('/rehearsal')
    expect(screen.getByRole('link', { name: 'Read journals' }).getAttribute('href')).toBe('/journals')
    expect(screen.getByText(/Market data, phase controls and wakes are not part of this host/)).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'Run' })).toBeNull()
    expect(getStatus).not.toHaveBeenCalled()
  })

  it('renders no write controls', async () => {
    renderPage()
    await screen.findByRole('region', { name: 'Latest run summary' })
    expect(screen.queryByRole('button', { name: /initialize|wake|phase|start|stop|resume|launch/i })).toBeNull()
    expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual(['Refresh reads'])
  })

  it('switches between several runs', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [run(), run(OTHER, 'real')], total: 2, limit: 20, offset: 0 })
    renderPage()
    await screen.findByText('Partial · Offline execution')
    await userEvent.setup().selectOptions(screen.getByRole('combobox', { name: 'Run' }), OTHER)
    expect(await screen.findByText('Partial · Real-mode manifest')).toBeTruthy()
    expect(getRehearsalRun).toHaveBeenLastCalledWith(OTHER)
  })

  it('states an empty server plainly', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [], total: 0, limit: 20, offset: 0 })
    renderPage()
    expect(await screen.findByText('No session runs recorded on this server yet.')).toBeTruthy()
    expect(screen.getByText(/scripts\/rehearsal\.py.*paradoxtrader user.*deploy\/README\.md step 7/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(getRehearsalRun).not.toHaveBeenCalled()
  })

  it('reports a failed list read as unavailable, not empty', async () => {
    vi.mocked(getRehearsalRuns).mockRejectedValue(new Error('secret upstream detail'))
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Run list unavailable. A failed read is not an empty run list.')
    expect(screen.queryByText(/No session runs recorded/)).toBeNull()
    expect(screen.queryByText(/secret upstream detail/)).toBeNull()
  })

  it('reports a failed detail read without inferring spend', async () => {
    vi.mocked(getRehearsalJobs).mockRejectedValue(new Error('boom'))
    renderPage()
    expect((await screen.findByRole('alert')).textContent).toMatch(/Run summary unavailable/)
    expect(screen.queryByRole('region', { name: 'Latest run summary' })).toBeNull()
  })
})

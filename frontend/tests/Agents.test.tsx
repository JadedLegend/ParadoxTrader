import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Agents from '../src/views/Agents'
import { getAgents, getAllPositions, getRehearsalJobs, getRehearsalRun, getRehearsalRuns, wakeAgent } from '../src/api'
import { REHEARSAL_AGENTS } from '../src/rehearsal/contracts'
import type { RehearsalJob, RehearsalRun } from '../src/rehearsal/contracts'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  IS_PREVIEW: false, IS_PRIVATE_HOST: true,
  getRehearsalRuns: vi.fn(), getRehearsalRun: vi.fn(), getRehearsalJobs: vi.fn(), getRehearsalRequests: vi.fn(),
  getAgents: vi.fn(), getAllPositions: vi.fn(), wakeAgent: vi.fn(),
}))

const ID = '11111111-1111-4111-8111-111111111111'
const TIME = '2026-11-12T00:00:00Z'
function run(id = ID): RehearsalRun {
  return { run_id: id, mode: 'offline', status: 'completed', created_at: TIME, started_at: TIME, ended_at: TIME, stop_requested: false,
    limits: { wakes_per_agent: 2, max_requests: 28, max_output_tokens: 1024, max_input_bytes: 24000, max_runtime_seconds: 900, request_timeout_seconds: 60, max_parallelism: 3, budget_usd: '1' },
    agent_models: Object.fromEntries(REHEARSAL_AGENTS.map(owner => [owner.id, `mock/exact-${owner.id}`])) as RehearsalRun['agent_models'],
    request_count: 14, reserved_usd: '0.1', known_cost_usd: '0', unknown_cost_requests: 0, capabilities: ['rest', 'journal', 'inquire', 'library', 'roam'],
    agents: REHEARSAL_AGENTS.map(owner => ({ agent_id: owner.id, pending: 0, completed: 2, failed: 0, stopped: 0, uncertain: 0 })),
  }
}
function jobs(): RehearsalJob[] {
  return REHEARSAL_AGENTS.flatMap((owner, index) => [1, 2].map(round => ({ wake_id: `${owner.id}-r${round}`, agent_id: owner.id, round,
    status: 'completed' as const, action: index === 0 && round === 1 ? 'journal' as const : 'rest' as const, failure_code: null,
    requested_model: `mock/exact-${owner.id}`, response_model: null, provider: null, request_count: 1, duration_ms: null,
    record_refs: index === 0 && round === 1 ? [{ kind: 'journal' as const, id: 1 }, { kind: 'episode' as const, id: 2 }] : [], updated_at: TIME,
    selection_origin: index === 0 ? 'model' as const : index === 1 ? 'none' as const : undefined,
    ...(index === 0 && round === 1 ? { journal_mode: 'note' as const, channels: ['trading' as const, 'idea' as const] } : {}),
  })))
}

beforeEach(() => {
  vi.mocked(getRehearsalRuns).mockReset().mockResolvedValue({ runs: [run()], total: 1, limit: 20, offset: 0 })
  vi.mocked(getRehearsalRun).mockReset().mockImplementation(async id => run(id))
  vi.mocked(getRehearsalJobs).mockReset().mockImplementation(async id => ({ run_id: id, jobs: jobs() }))
  vi.mocked(getAgents).mockReset()
  vi.mocked(getAllPositions).mockReset()
  vi.mocked(wakeAgent).mockReset()
})

const show = () => render(<MemoryRouter><Agents /></MemoryRouter>)

describe('Agents on the private host', () => {
  it('shows the seven members of the newest recorded run with their rounds', async () => {
    show()
    expect(screen.getByRole('heading', { level: 1, name: 'Agents' })).toBeTruthy()
    expect(screen.getByText('The seven members in the latest recorded session')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toMatch(/Loading/)
    const tempest = await screen.findByRole('article', { name: 'Tempest' })
    expect(screen.getAllByRole('article')).toHaveLength(7)
    expect(within(tempest).getByText('Assigned model: mock/exact-tempest')).toBeTruthy()
    const rounds = within(tempest).getAllByRole('listitem')
    expect(rounds).toHaveLength(2)
    expect(rounds[0].textContent).toContain('Round 1: Journal (Note · Trading, Idea)')
    expect(rounds[0].textContent).toContain('Status: Completed')
    expect(rounds[0].textContent).toContain('Selection: Model choice')
    expect(rounds[0].textContent).toContain('2 linked private records')
    expect(rounds[1].textContent).toContain('0 linked private records')
    expect(within(screen.getByRole('article', { name: 'Siren' })).getAllByRole('listitem')[0].textContent).toContain('No committed model choice')
    expect(within(screen.getByRole('article', { name: 'Oracle' })).getAllByRole('listitem')[0].textContent).toContain('Unknown (older record)')
    expect(within(tempest).getByRole('link', { name: "Read Tempest's journals" }).getAttribute('href')).toBe('/journals')
    expect(screen.getByRole('link', { name: 'Session details' }).getAttribute('href')).toBe('/rehearsal')
    expect(screen.getByRole('note').textContent).toMatch(/not served on this host/)
    expect(getAgents).not.toHaveBeenCalled()
    expect(getAllPositions).not.toHaveBeenCalled()
  })

  it('renders no write controls', async () => {
    show()
    await screen.findByRole('article', { name: 'Tempest' })
    const buttons = screen.getAllByRole('button').map(button => button.textContent)
    expect(buttons).toEqual(['Refresh reads'])
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByText(/^Wake$/)).toBeNull()
    expect(wakeAgent).not.toHaveBeenCalled()
  })

  it('states an empty server explicitly when no runs are recorded', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [], total: 0, limit: 20, offset: 0 })
    show()
    expect(await screen.findByText('No session runs recorded on this server yet.')).toBeTruthy()
    expect(screen.getByText(/scripts\/rehearsal\.py/)).toBeTruthy()
    expect(screen.queryByRole('article')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('reports a failed run list as a failure, not as empty', async () => {
    vi.mocked(getRehearsalRuns).mockRejectedValue(new Error('500 secret detail'))
    show()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Run list unavailable. A failed read is not an empty run list.')
    expect(screen.queryByText(/No session runs recorded/)).toBeNull()
    expect(screen.queryByText(/secret detail/)).toBeNull()
  })

  it('reports a failed run detail read without inventing members', async () => {
    vi.mocked(getRehearsalJobs).mockRejectedValue(new Error('down'))
    show()
    expect((await screen.findByRole('alert')).textContent).toMatch(/Run details unavailable/)
    expect(screen.queryByRole('article')).toBeNull()
  })

  it('offers a run select when several runs are recorded', async () => {
    const OTHER = '22222222-2222-4222-8222-222222222222'
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [run(), run(OTHER)], total: 2, limit: 20, offset: 0 })
    show()
    await screen.findByRole('article', { name: 'Tempest' })
    const select = screen.getByRole('combobox', { name: 'Run' }) as HTMLSelectElement
    expect(select.value).toBe(ID)
    expect(select.options).toHaveLength(2)
  })
})

import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Rehearsal from '../src/views/Rehearsal'
import { getRehearsalRuns, getRehearsalRun, getRehearsalJobs, getRehearsalRequests, getRehearsalRecord, getRehearsalDecision } from '../src/api'
import { REHEARSAL_AGENTS } from '../src/rehearsal/contracts'
import type { RehearsalAgentId, RehearsalDecisionResponse, RehearsalJob, RehearsalRecordResponse, RehearsalRequestsResponse, RehearsalRun } from '../src/rehearsal/contracts'

vi.mock('../src/api', () => ({ IS_PREVIEW: true, getRehearsalRuns: vi.fn(), getRehearsalRun: vi.fn(), getRehearsalJobs: vi.fn(), getRehearsalRequests: vi.fn(), getRehearsalRecord: vi.fn(), getRehearsalDecision: vi.fn() }))
const ID = '11111111-1111-4111-8111-111111111111'
const OTHER = '22222222-2222-4222-8222-222222222222'
const TIME = '2026-11-12T00:00:00Z'
function run(id = ID): RehearsalRun {
  return { run_id: id, mode: 'offline', status: 'partial', created_at: TIME, started_at: TIME, ended_at: TIME, stop_requested: false,
    limits: { wakes_per_agent: 2, max_requests: 28, max_output_tokens: 1024, max_input_bytes: 24000, max_runtime_seconds: 900, request_timeout_seconds: 60, max_parallelism: 3, budget_usd: '1' },
    agent_models: Object.fromEntries(REHEARSAL_AGENTS.map(owner => [owner.id, `mock/exact-${owner.id}`])) as RehearsalRun['agent_models'],
    request_count: 7, reserved_usd: '0.1', known_cost_usd: '0', unknown_cost_requests: 3, capabilities: ['rest', 'journal', 'inquire', 'library', 'roam'],
    agents: REHEARSAL_AGENTS.map((owner, index) => ({ agent_id: owner.id, pending: index === 1 ? 2 : 0, completed: index === 0 ? 2 : 0, failed: index === 2 ? 2 : 0, stopped: index === 3 ? 2 : 0, uncertain: index === 4 ? 2 : 0 })),
  }
}
function jobs(): RehearsalJob[] {
  return REHEARSAL_AGENTS.flatMap((owner, index) => [1, 2].map(round => ({ wake_id: `${owner.id}-r${round}`, agent_id: owner.id, round,
    status: (['completed', 'pending', 'failed', 'stopped', 'uncertain', 'completed', 'completed'] as const)[index],
    action: index === 0 ? 'journal' as const : index === 5 ? 'rest' as const : null, failure_code: null,
    requested_model: `mock/exact-${owner.id}`, response_model: index === 0 ? 'mock/returned-tempest' : null, provider: index === 0 ? 'Mock upstream' : null,
    request_count: index === 1 ? 0 : 1, duration_ms: index === 0 ? 0 : null, record_refs: round === 1 && index < 2 ? [{ kind: 'journal' as const, id: 1 }] : [], updated_at: TIME,
  })))
}
function requests(owner: string = 'tempest', id = ID): RehearsalRequestsResponse {
  return { run_id: id, total: 1, limit: 50, offset: 0, events: [{ request_id: `mock-${owner}`, wake_id: `${owner}-round-1`, agent_id: owner as RehearsalAgentId, activity: 'choice',
    model: `mock/exact-${owner}`, response_model: owner === 'tempest' ? 'mock/returned-tempest' : null, provider: owner === 'tempest' ? 'Mock upstream' : null,
    outcome: owner === 'tempest' ? 'success' : 'uncertain', duration_ms: owner === 'tempest' ? 0 : null, input_bytes: 0, max_output_tokens: 1024, reserved_usd: '0.01',
    usage: owner === 'tempest' ? { input_tokens: 0, output_tokens: 0, cost_status: 'reported', cost_usd: '0' } : null, failure_code: null }] }
}
function record(owner: string, content: string, id = ID): RehearsalRecordResponse {
  return { run_id: id, agent_id: owner as RehearsalAgentId, kind: 'journal', id: 1, record: { id: 1, content, created_at: TIME } }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
beforeEach(() => {
  vi.mocked(getRehearsalRuns).mockReset().mockResolvedValue({ runs: [run()], total: 1, limit: 20, offset: 0 })
  vi.mocked(getRehearsalRun).mockReset().mockImplementation(async id => run(id))
  vi.mocked(getRehearsalJobs).mockReset().mockImplementation(async id => ({ run_id: id, jobs: jobs() }))
  vi.mocked(getRehearsalRequests).mockReset().mockImplementation(async (id, owner) => requests(owner, id))
  vi.mocked(getRehearsalRecord).mockReset().mockImplementation(async (id, owner) => record(owner, `${owner} private record`, id))
  vi.mocked(getRehearsalDecision).mockReset().mockRejectedValue(new Error('old context unavailable'))
})
const ownerSelect = () => screen.getByRole('combobox', { name: 'Owner' })
async function loaded() { render(<Rehearsal />); await screen.findByRole('region', { name: 'Seven-agent progress' }); await screen.findByRole('region', { name: 'Request telemetry table' }) }
const disabled = (name: string) => (screen.getByRole('button', { name }) as HTMLButtonElement).disabled

describe('read-only after-run rehearsal observability', () => {
  it('labels mock mode, legitimate model variation and CLI control without scoring or launch controls', async () => {
    await loaded()
    expect(screen.getByText('Mock runs · local fixture')).toBeTruthy()
    expect(screen.getByText(/Model names do not verify current real-model availability/)).toBeTruthy()
    expect(screen.getByText(/CLI owns prepare, start, stop and resume/)).toBeTruthy()
    expect(screen.getByText(/Different models, rest and no change are legitimate/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /launch|start|stop|resume/i })).toBeNull()
    expect(getRehearsalRecord).not.toHaveBeenCalled()
    const table = within(screen.getByRole('region', { name: 'Member progress table' }))
    for (const owner of REHEARSAL_AGENTS) expect(table.getByRole('button', { name: owner.name })).toBeTruthy()
    for (const state of ['Pending', 'Completed', 'Failed', 'Stopped', 'Uncertain']) expect(table.getByRole('columnheader', { name: state })).toBeTruthy()
  })
  it('preserves known zero, unknown values, requested/returned differences and bounded coverage', async () => {
    await loaded()
    expect(screen.getByText('7 / 28')).toBeTruthy()
    expect(screen.getByText(/Unknown-cost requests/)).toBeTruthy()
    expect(screen.getByText(/Missing costs are unknown, not free/)).toBeTruthy()
    expect(screen.getByText(/Showing 1 of 1 selected-owner requests · limit 50/)).toBeTruthy()
    expect(screen.getByText(/Reported: \$0/)).toBeTruthy()
    expect(screen.getByText(/Input tokens 0 · Output 0/)).toBeTruthy()
    expect(screen.getAllByText(/0 ms/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/mock\/returned-tempest/).length).toBeGreaterThan(0)
    await userEvent.setup().selectOptions(ownerSelect(), 'oracle')
    await screen.findByText(/Unknown: Unavailable/)
    expect(screen.getByText(/Input tokens Unavailable · Output Unavailable/)).toBeTruthy()
    expect(screen.getByText(/No linked private records/)).toBeTruthy()
    expect(disabled('Next requests')).toBe(true)
  })
  it('clears previous detail immediately on owner change and does not reuse peer integer IDs', async () => {
    await loaded()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read journal #1' }))
    await screen.findByText('tempest private record')
    await user.selectOptions(ownerSelect(), 'siren')
    expect(screen.queryByText('tempest private record')).toBeNull()
    expect(getRehearsalRecord).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Read journal #1' }))
    await screen.findByText('siren private record')
    expect(getRehearsalRecord).toHaveBeenLastCalledWith(ID, 'siren', 'journal', 1)
  })
  it('ignores stale A → B → A private record and request completions, including late failures', async () => {
    const staleRecord = deferred<RehearsalRecordResponse>()
    const staleRequests = deferred<RehearsalRequestsResponse>()
    vi.mocked(getRehearsalRecord).mockImplementationOnce(() => staleRecord.promise)
    vi.mocked(getRehearsalRequests).mockImplementationOnce(() => staleRequests.promise)
    render(<Rehearsal />)
    await screen.findByRole('region', { name: 'Seven-agent progress' })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read journal #1' }))
    await user.selectOptions(ownerSelect(), 'siren')
    await user.selectOptions(ownerSelect(), 'tempest')
    await user.click(screen.getByRole('button', { name: 'Read journal #1' }))
    await screen.findByText('tempest private record')
    await act(async () => {
      staleRecord.resolve(record('tempest', 'STALE first A private record'))
      staleRequests.resolve({ ...requests(), events: [{ ...requests().events[0], provider: 'STALE first A provider' }] })
      await Promise.resolve()
    })
    expect(screen.queryByText(/STALE first A/)).toBeNull()
    expect(screen.getByText('tempest private record')).toBeTruthy()
  })
  it('rejects returned owner mismatches without leaking private bodies', async () => {
    vi.mocked(getRehearsalRecord).mockResolvedValue(record('siren', 'PEER PRIVATE'))
    await loaded()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Read journal #1' }))
    await screen.findByText(/Private record unavailable or outside selected owner/)
    expect(screen.queryByText('PEER PRIVATE')).toBeNull()
  })
  it('separates failed reads from empty histories and supports explicit read retry', async () => {
    vi.mocked(getRehearsalRequests).mockRejectedValueOnce(new Error('no auth'))
    render(<Rehearsal />)
    await screen.findByText(/Owner requests unavailable/)
    expect(screen.queryByText(/No requests recorded/)).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Refresh reads' }))
    await screen.findByRole('region', { name: 'Request telemetry table' })
  })
  it('does not turn unavailable total costs or missing members into zero success', async () => {
    vi.mocked(getRehearsalRun).mockResolvedValue({ ...run(), known_cost_usd: null, agents: [] })
    await loaded()
    const accounting = within(screen.getByRole('region', { name: 'Run limits and accounting' }))
    expect(accounting.getAllByText('Unavailable').length).toBeGreaterThan(0)
    const table = within(screen.getByRole('region', { name: 'Member progress table' }))
    expect(table.getAllByText('Unavailable')).toHaveLength(35)
  })
  it('clears selected record on run change and rejects late previous-run metadata', async () => {
    const old = deferred<RehearsalRecordResponse>()
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [run(), run(OTHER)], total: 2, limit: 20, offset: 0 })
    vi.mocked(getRehearsalRecord).mockImplementationOnce(() => old.promise)
    await loaded()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read journal #1' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Run' }), OTHER)
    await waitFor(() => expect(getRehearsalRun).toHaveBeenLastCalledWith(OTHER))
    await act(async () => { old.resolve(record('tempest', 'OLD RUN PRIVATE')); await Promise.resolve() })
    expect(screen.queryByText('OLD RUN PRIVATE')).toBeNull()
    expect(screen.queryByText(/Loading private record/)).toBeNull()
  })
})

function decision(owner: RehearsalAgentId = 'tempest', body = '<script>literal owner note</script>', wake = `${owner}-r1`, id = ID): RehearsalDecisionResponse {
  return { run_id: id, agent_id: owner, wake_id: wake, decision: {
    metadata: { schema_version: 1, offered_actions: [...run().capabilities], action_costs: run().capabilities.map(action => ({ action, max_requests: action === 'rest' ? 1 : 2, reservation_ceiling_usd: '0.01', basis: 'catalog_upper_bound' })), constraints: run().limits,
      admission_snapshot: { reserved_usd: '0.1', remaining_budget_usd: '0.9', request_count: 7, remaining_requests: 21, is_reservation: false }, model: { requested_model: `mock/exact-${owner}`, context_length: 65536, max_completion_tokens: 1024, catalog_source: 'synthetic' }, continuity: { status: 'empty', refs: [], truncated: false, chars: 0 } },
    private_context: { continuity: { status: 'empty', refs: [], excerpts: [], body }, include_metadata: true, include_continuity: true },
    requests: [{ request_id: 'input-1', agent_id: owner, wake_id: wake, input_sha256: 'abcdef', input_coverage: 'complete', messages: [{ role: 'user', content: `${body} FULL REQUEST INPUT` }] }],
  } }
}
describe('explicit decision evidence continuity', () => {
  it('renders five offers separately from choice/status, admission observations and legacy unknowns', async () => {
    const values = jobs(); values[0] = { ...values[0], decision_context: decision().decision.metadata, selection_origin: 'model' }; values[1] = { ...values[1], action: null, status: 'failed', selection_origin: 'none', failure_code: 'invalid_choice' }
    vi.mocked(getRehearsalJobs).mockResolvedValue({ run_id: ID, jobs: values })
    await loaded()
    expect(screen.getByRole('heading', { name: 'Sessions', level: 1 })).toBeTruthy()
    expect(screen.getByText('Request admissions')).toBeTruthy()
    const wake = within(screen.getByRole('article', { name: 'Round 1 decision' }))
    expect(wake.getAllByRole('listitem')).toHaveLength(5)
    expect(wake.getByText(/Selected action: Journal.*Model choice.*Actual status: Completed/)).toBeTruthy()
    expect(wake.getByText(/Point-in-time admission snapshot/)).toBeTruthy()
    expect(wake.getByText(/An offer is not a reservation/)).toBeTruthy()
    const failed = within(screen.getByRole('article', { name: 'Round 2 decision' }))
    expect(failed.getByText(/Selected action: Not recorded.*No committed model choice.*Actual status: Failed/)).toBeTruthy()
    expect(getRehearsalDecision).not.toHaveBeenCalled()
  })
  it('reads full escaped context only on click and keeps older missing context unavailable', async () => {
    vi.mocked(getRehearsalDecision).mockResolvedValueOnce(decision())
    await loaded(); expect(getRehearsalDecision).not.toHaveBeenCalled()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read decision context · round 1' }))
    const evidence = await screen.findByRole('article', { name: 'Private decision evidence' })
    expect(evidence.textContent).toContain('<script>literal owner note</script> FULL REQUEST INPUT')
    expect(evidence.querySelector('script')).toBeNull()
    expect(evidence.textContent).toContain('abcdef')
    await user.click(screen.getByRole('button', { name: 'Read decision context · round 2' }))
    await screen.findByText(/Decision context unavailable or outside selected owner\/wake/)
    expect(screen.queryByRole('article', { name: 'Private decision evidence' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Sessions', level: 1 })).toBeTruthy()
  })
  it('ignores late first A completion after A → B → A and clears evidence on run change', async () => {
    const stale = deferred<RehearsalDecisionResponse>()
    vi.mocked(getRehearsalDecision).mockImplementationOnce(() => stale.promise).mockResolvedValue(decision('tempest', 'CURRENT EVIDENCE'))
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [run(), run(OTHER)], total: 2, limit: 20, offset: 0 })
    await loaded(); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read decision context · round 1' }))
    await user.selectOptions(ownerSelect(), 'siren'); await user.selectOptions(ownerSelect(), 'tempest')
    await user.click(screen.getByRole('button', { name: 'Read decision context · round 1' }))
    await screen.findByRole('article', { name: 'Private decision evidence' })
    await act(async () => { stale.resolve(decision('tempest', 'STALE EVIDENCE')); await Promise.resolve() })
    expect(screen.queryByText(/STALE EVIDENCE/)).toBeNull()
    expect(screen.getByRole('article', { name: 'Private decision evidence' }).textContent).toContain('CURRENT EVIDENCE')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Run' }), OTHER)
    expect(screen.queryByRole('article', { name: 'Private decision evidence' })).toBeNull()
  })
  it.each(['wrapper', 'wake', 'request', 'private'])('rejects %s owner/wake mismatch before rendering literal private bodies', async attack => {
    const value = decision('tempest', 'PEER SECRET')
    if (attack === 'wrapper') value.agent_id = 'siren'
    if (attack === 'wake') value.wake_id = 'tempest-r2'
    if (attack === 'request') value.decision.requests[0].agent_id = 'siren'
    if (attack === 'private') value.decision.private_context = { agent_id: 'siren', body: 'PEER SECRET' }
    vi.mocked(getRehearsalDecision).mockResolvedValue(value)
    await loaded(); await userEvent.setup().click(screen.getByRole('button', { name: 'Read decision context · round 1' }))
    await screen.findByText(/Decision context unavailable or outside selected owner\/wake/)
    expect(screen.queryByText(/PEER SECRET/)).toBeNull()
  })
})

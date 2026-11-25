import { describe, expect, it, vi } from 'vitest'
import { getRehearsalRuns, getRehearsalRun, getRehearsalJobs, getRehearsalRequests, getRehearsalRecord, getRehearsalDecision } from '../src/api'
import { readRehearsalFixture } from '../src/rehearsal/client'
import { REHEARSAL_AGENTS } from '../src/rehearsal/contracts'
import baseFixture from '../src/rehearsal/fixture.json'

async function firstRun() { return (await getRehearsalRuns()).runs[0] }
describe('rehearsal default fixture read API (all HTTP blocked)', () => {
  it('loads bounded summaries and separately enveloped jobs/requests through parent wrappers', async () => {
    const runs = await getRehearsalRuns(1, 0)
    expect(runs.runs).toHaveLength(1)
    expect(runs).toMatchObject({ limit: 1, offset: 0 })
    const run = runs.runs[0]
    expect(await getRehearsalRun(run.run_id)).toEqual(run)
    const jobs = await getRehearsalJobs(run.run_id)
    expect(jobs.run_id).toBe(run.run_id)
    expect(jobs.jobs).toHaveLength(14)
    expect(new Set(jobs.jobs.map(job => job.agent_id)).size).toBe(7)
    expect(run.limits).toMatchObject({ wakes_per_agent: 2, max_requests: 28, max_parallelism: 1, max_output_tokens: 1024, max_input_bytes: 24000, max_runtime_seconds: 900, request_timeout_seconds: 60 })
    expect(await getRehearsalRuns(20, 1000000)).toMatchObject({ runs: [], total: runs.total })
  })
  it('filters request pages by all seven actual owners without relabeling or fabricating telemetry', async () => {
    const run = await firstRun()
    for (const owner of REHEARSAL_AGENTS) {
      const all = await getRehearsalRequests(run.run_id, owner.id)
      expect(all.run_id).toBe(run.run_id)
      expect(all.events.every(event => event.agent_id === owner.id)).toBe(true)
      const page = await getRehearsalRequests(run.run_id, owner.id, 1, 1)
      expect(page.events).toEqual(all.events.slice(1, 2))
      expect(page.total).toBe(all.total)
      expect(await getRehearsalRequests(run.run_id, owner.id, 50, 1000000)).toMatchObject({ events: [], total: all.total })
    }
  })
  it('reads only owner-linked private records and preserves fresh nested clones', async () => {
    const run = await firstRun()
    const jobs = (await getRehearsalJobs(run.run_id)).jobs
    let observed = 0
    for (const job of jobs) for (const ref of job.record_refs) {
      const first = await getRehearsalRecord(run.run_id, job.agent_id, ref.kind, ref.id)
      expect(first).toMatchObject({ run_id: run.run_id, agent_id: job.agent_id, kind: ref.kind, id: ref.id })
      const second = await getRehearsalRecord(run.run_id, job.agent_id, ref.kind, ref.id)
      expect(second).toEqual(first)
      if ('content' in first.record) first.record.content = 'consumer mutation'
      expect(await getRehearsalRecord(run.run_id, job.agent_id, ref.kind, ref.id)).toEqual(second)
      if (ref.kind === 'inquiry') {
        const wrongOwner = REHEARSAL_AGENTS.find(owner => owner.id !== job.agent_id)!.id
        await expect(getRehearsalRecord(run.run_id, wrongOwner, ref.kind, ref.id)).rejects.toThrow()
      }
      observed++
    }
    expect(observed).toBeGreaterThan(0)
    const first = await getRehearsalRun(run.run_id)
    first.agent_models.tempest = 'consumer mutation'
    expect((await getRehearsalRun(run.run_id)).agent_models.tempest).not.toBe('consumer mutation')
  }, 20_000) // CPU-bound walk over every linked record; exceeds the 5 s default under full-suite parallel load.
  it('keeps operational reads separate from memory bodies, raw model output and secrets', async () => {
    const run = await firstRun()
    for (const value of [await getRehearsalRuns(), await getRehearsalRun(run.run_id), await getRehearsalJobs(run.run_id), await getRehearsalRequests(run.run_id)]) {
      const json = JSON.stringify(value)
      for (const field of ['"content":', '"text":', '"raw_output":', '"api_key":', '"authorization":', '"innermost":']) expect(json).not.toContain(field)
    }
  })
  it.each([
    '/api/rehearsals?limit=0', '/api/rehearsals?limit=21', '/api/rehearsals?limit=1.5', '/api/rehearsals?limit=%2B1',
    '/api/rehearsals?limit=%201', '/api/rehearsals?offset=-1', '/api/rehearsals?offset=2147483648',
    '/api/rehearsals?limit=1&limit=2', '/api/rehearsals?operator=true', '/api/rehearsals#secret',
    '/api/rehearsals/not-a-uuid', '/api/rehearsals/../rehearsals', '/api/rehearsals/%2e%2e/rehearsals',
    '/api/rehearsals/11111111-1111-4111-8111-111111111111/start',
    '/api/rehearsals/11111111-1111-4111-8111-111111111111/records?agent_id=tempest&kind=innermost&id=1',
    '/api/rehearsals/11111111-1111-4111-8111-111111111111/requests?agent_id=outsider',
    '/api/rehearsals/11111111-1111-4111-8111-111111111111/requests?agent_id=tempest&agent_id=siren',
  ])('rejects unsupported reads %s without a network fallback', async path => {
    await expect(readRehearsalFixture(path)).rejects.toThrow()
  })
  it('reports valid missing runs and refs as unavailable, never fake empty records', async () => {
    await expect(getRehearsalRun('00000000-0000-4000-8000-000000000000')).rejects.toThrow('not found')
    const run = await firstRun()
    await expect(getRehearsalRecord(run.run_id, 'tempest', 'journal', 2147483647)).rejects.toThrow('not found')
  })
  it('normalizes actual-store flat cost fields without leaking unexpected fixture content', async () => {
    const fixture = structuredClone(baseFixture) as any
    const id = fixture.runs[0].run_id
    const event = fixture.requests[id][0]
    delete event.usage
    event.input_tokens = 0; event.output_tokens = null; event.cost_usd = '0'; event.cost_status = 'reported'
    for (const value of [fixture.runs[0], fixture.jobs[id][0], event]) {
      value.raw_output = 'PRIVATE_RAW'; value.content = 'PRIVATE_BODY'; value.api_key = 'SECRET_KEY'
    }
    vi.doMock('../src/rehearsal/fixture.json', () => ({ default: fixture }))
    vi.resetModules()
    try {
      const requests = await readRehearsalFixture(`/api/rehearsals/${id}/requests`) as any
      expect(requests.events[0].usage).toMatchObject({ input_tokens: 0, output_tokens: null, cost_usd: '0', cost_status: 'reported' })
      for (const path of ['/api/rehearsals', `/api/rehearsals/${id}`, `/api/rehearsals/${id}/jobs`, `/api/rehearsals/${id}/requests`]) {
        const output = JSON.stringify(await readRehearsalFixture(path))
        for (const secret of ['PRIVATE_RAW', 'PRIVATE_BODY', 'SECRET_KEY']) expect(output).not.toContain(secret)
      }
    } finally { vi.doUnmock('../src/rehearsal/fixture.json'); vi.resetModules() }
  })
  it('refuses a wrapped private record whose actual owner does not match its map key', async () => {
    const fixture = structuredClone(baseFixture) as any
    const id = fixture.runs[0].run_id
    const job = fixture.jobs[id].find((value: any) => value.record_refs.length)
    const ref = job.record_refs[0]
    const key = `${job.agent_id}|${ref.kind}|${ref.id}`
    const value = fixture.records[id][key]
    fixture.records[id][key] = { run_id: id, agent_id: REHEARSAL_AGENTS.find(owner => owner.id !== job.agent_id)!.id, kind: ref.kind, id: ref.id, record: value.record ?? value }
    vi.doMock('../src/rehearsal/fixture.json', () => ({ default: fixture }))
    vi.resetModules()
    try { await expect(readRehearsalFixture(`/api/rehearsals/${id}/records?agent_id=${job.agent_id}&kind=${ref.kind}&id=${ref.id}`)).rejects.toThrow() }
    finally { vi.doUnmock('../src/rehearsal/fixture.json'); vi.resetModules() }
  })
})

function decisionFixture() {
  const fixture = structuredClone(baseFixture) as any
  const run = fixture.runs[0]; const id = run.run_id
  const job = fixture.jobs[id].find((value: any) => value.agent_id === 'tempest')
  const wake = job.wake_id
  const metadata = { schema_version: 1, offered_actions: ['rest', 'journal', 'inquire', 'library', 'roam'], action_costs: ['rest', 'journal', 'inquire', 'library', 'roam'].map(action => ({ action, max_requests: action === 'rest' ? 1 : 2, reservation_ceiling_usd: '0', basis: 'catalog_upper_bound' })), constraints: run.limits, admission_snapshot: { reserved_usd: '0', remaining_budget_usd: '0', request_count: 0, remaining_requests: 28, is_reservation: false }, model: { requested_model: 'synthetic/tempest', context_length: 65536, max_completion_tokens: 1024, catalog_source: 'synthetic' }, continuity: { status: 'empty', refs: [], truncated: false, chars: 0 } }
  job.decision_context = metadata; job.selection_origin = 'model'
  fixture.decisions = { [id]: { [wake]: { run_id: id, agent_id: 'tempest', wake_id: wake, decision: { metadata, private_context: { continuity: { status: 'empty', refs: [], excerpts: [], body: 'LITERAL OWNER PRIVATE' } }, requests: [{ request_id: 'input-1', agent_id: 'tempest', wake_id: wake, input_sha256: 'HASH', input_coverage: 'complete', messages: [{ role: 'user', content: '<b>FULL PRIVATE INPUT</b>' }] }] } } } }
  return { fixture, id, wake, path: `/api/rehearsals/${id}/decisions?agent_id=tempest&wake_id=${wake}` }
}
describe('local decision context owner boundary', () => {
  it('reads explicit owner/wake envelope with complete literal inputs and clone isolation', async () => {
    const { fixture, path, id, wake } = decisionFixture()
    vi.doMock('../src/rehearsal/fixture.json', () => ({ default: fixture })); vi.resetModules()
    try {
      const value = await readRehearsalFixture(path) as any
      expect(value).toMatchObject({ run_id: id, agent_id: 'tempest', wake_id: wake })
      expect(value.decision.requests[0]).toMatchObject({ input_sha256: 'HASH', input_coverage: 'complete', messages: [{ role: 'user', content: '<b>FULL PRIVATE INPUT</b>' }] })
      value.decision.private_context.continuity.body = 'mutated'
      expect(JSON.stringify(await readRehearsalFixture(path))).toContain('LITERAL OWNER PRIVATE')
      const jobs = await readRehearsalFixture(`/api/rehearsals/${id}/jobs`) as any
      expect(jobs.jobs.find((job: any) => job.wake_id === wake).decision_context.offered_actions).toHaveLength(5)
      expect(JSON.stringify(jobs)).not.toContain('LITERAL OWNER PRIVATE')
    } finally { vi.doUnmock('../src/rehearsal/fixture.json'); vi.resetModules() }
  })
  it.each(['wrapper', 'request', 'private', 'public', 'missing'])('fails closed for %s mismatch or older absent decisions', async attack => {
    const { fixture, path, id, wake } = decisionFixture(); const value = fixture.decisions[id][wake]
    if (attack === 'wrapper') value.agent_id = 'siren'
    if (attack === 'request') value.decision.requests[0].wake_id = 'tempest-r2'
    if (attack === 'private') value.decision.private_context.agent_id = 'siren'
    if (attack === 'public') value.decision.metadata.continuity.refs = [{ kind: 'journal', id: 1, agent_id: 'siren' }]
    if (attack === 'missing') delete fixture.decisions
    vi.doMock('../src/rehearsal/fixture.json', () => ({ default: fixture })); vi.resetModules()
    try { await expect(readRehearsalFixture(path)).rejects.toThrow() }
    finally { vi.doUnmock('../src/rehearsal/fixture.json'); vi.resetModules() }
  })
  it('strips arbitrary nested fields from public and private scaffolding without altering quoted text', async () => {
    const { fixture, path, id, wake } = decisionFixture(); const value = fixture.decisions[id][wake]
    value.decision.metadata.model.api_key = 'UNEXPECTED'; value.decision.metadata.continuity.raw_output = 'UNEXPECTED'
    value.decision.private_context.api_key = 'UNEXPECTED'; value.decision.requests[0].authorization = 'UNEXPECTED'; value.decision.requests[0].messages[0].api_key = 'UNEXPECTED'
    vi.doMock('../src/rehearsal/fixture.json', () => ({ default: fixture })); vi.resetModules()
    try {
      expect(JSON.stringify(await readRehearsalFixture(path))).not.toContain('UNEXPECTED')
      expect(JSON.stringify(await readRehearsalFixture(`/api/rehearsals/${id}/jobs`))).not.toContain('UNEXPECTED')
    } finally { vi.doUnmock('../src/rehearsal/fixture.json'); vi.resetModules() }
  })
  it.each(['agent_id=siren&wake_id=tempest-r1', 'agent_id=tempest&wake_id=tempest-r0', 'agent_id=tempest&wake_id=tempest-r121', 'agent_id=tempest&wake_id=tempest-r01', 'agent_id=tempest&wake_id=tempest-r1&wake_id=tempest-r2', 'agent_id=tempest', 'wake_id=tempest-r1'])('rejects invalid owner/wake parameters %s', async query => {
    const run = await firstRun()
    await expect(readRehearsalFixture(`/api/rehearsals/${run.run_id}/decisions?${query}`)).rejects.toThrow()
  })
})

it('reads regenerated actual-store decision snapshots through parent wrapper without HTTP', async () => {
  const run = await firstRun(); const jobs = (await getRehearsalJobs(run.run_id)).jobs
  const recorded = jobs.filter(job => job.decision_context)
  expect(recorded.length).toBeGreaterThan(0)
  for (const job of recorded) {
    const value = await getRehearsalDecision(run.run_id, job.agent_id, job.wake_id)
    expect(value).toMatchObject({ run_id: run.run_id, agent_id: job.agent_id, wake_id: job.wake_id })
    expect(value.decision.metadata).toEqual(job.decision_context)
    for (const event of value.decision.requests) expect(event).toMatchObject({ agent_id: job.agent_id, wake_id: job.wake_id, input_coverage: 'complete' })
  }
})

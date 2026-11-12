import { REHEARSAL_AGENTS } from './contracts'
import type { RehearsalFixture, RehearsalJob, RehearsalRecordResponse, RehearsalRequest, RehearsalRun } from './contracts'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const PREFIX = '/api/rehearsals'
const invalid = () => new Error('Invalid local rehearsal request. No backend fallback was attempted.')
function pick<T extends object, K extends keyof T>(value: T, keys: readonly K[]): Pick<T, K> {
  return Object.fromEntries(keys.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]])) as Pick<T, K>
}
function summary(value: RehearsalRun): RehearsalRun {
  return { ...pick(value, ['run_id', 'mode', 'status', 'created_at', 'started_at', 'ended_at', 'stop_requested', 'request_count', 'reserved_usd', 'known_cost_usd', 'unknown_cost_requests', 'reported_cost_usd', 'estimated_cost_usd']),
    limits: pick(value.limits, ['wakes_per_agent', 'max_requests', 'max_output_tokens', 'max_input_bytes', 'max_runtime_seconds', 'request_timeout_seconds', 'max_parallelism', 'budget_usd']),
    agent_models: Object.fromEntries(REHEARSAL_AGENTS.filter(agent => Object.hasOwn(value.agent_models, agent.id)).map(agent => [agent.id, value.agent_models[agent.id]])) as RehearsalRun['agent_models'],
    agents: value.agents.filter(agent => REHEARSAL_AGENTS.some(owner => owner.id === agent.agent_id)).map(agent => pick(agent, ['agent_id', 'pending', 'completed', 'failed', 'stopped', 'uncertain'])),
    capabilities: value.capabilities.filter(cap => ['rest', 'journal', 'inquire', 'library', 'roam'].includes(cap)) }
}
function operationalJob(value: RehearsalJob): RehearsalJob {
  return { ...pick(value, ['wake_id', 'agent_id', 'round', 'status', 'action', 'failure_code', 'requested_model', 'response_model', 'provider', 'request_count', 'duration_ms', 'updated_at']),
    record_refs: value.record_refs.filter(ref => ['journal', 'episode', 'inquiry', 'library'].includes(ref.kind)).map(ref => pick(ref, ['kind', 'id'])) }
}
function operationalRequest(value: RehearsalRequest): RehearsalRequest {
  const fields = ['input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens', 'cost_usd', 'reported_cost_usd', 'estimated_cost_usd', 'cost_status', 'cost_source'] as const
  const usage = value.usage ?? (fields.some(field => Object.hasOwn(value, field)) ? value : null)
  return { ...pick(value, ['request_id', 'wake_id', 'agent_id', 'activity', 'model', 'requested_model', 'response_model', 'provider', 'outcome', 'duration_ms', 'input_bytes', 'max_output_tokens', 'reserved_usd', 'failure_code', 'created_at', 'submitted_at', 'finished_at']),
    usage: usage ? pick(usage, fields) : null }
}
function integer(params: URLSearchParams, field: string, fallback: number, min: number, max: number) {
  const value = params.get(field)
  if (value === null) return fallback
  if (value.length > 10 || !/^[0-9]+$/.test(value)) throw invalid()
  const number = Number(value)
  if (!Number.isSafeInteger(number) || number < min || number > max) throw invalid()
  return number
}
function validateRecord(record: RehearsalRecordResponse) {
  if ('agent_id' in record.record && record.record.agent_id !== record.agent_id) throw invalid()
  if (record.kind === 'inquiry') {
    const value = record.record
    if (!('inquiry' in value) || value.inquiry.agent_id !== record.agent_id || value.inquiry.inquiry_id !== record.id) throw invalid()
    for (const category of ['entries', 'proposals', 'orders', 'fills', 'positions', 'reviews', 'events'] as const) {
      if (!Array.isArray(value[category]) || value[category].some(item => item.agent_id !== undefined && item.agent_id !== record.agent_id)) throw invalid()
    }
  } else if (record.kind === 'library') {
    if (!('section_id' in record.record) || record.record.section_id !== record.id) throw invalid()
  } else if (!('id' in record.record) || String(record.record.id) !== String(record.id)) throw invalid()
}
/** Local GET reader only; neither credentials nor transport exist at this boundary. */
export async function readRehearsalFixture(path: string): Promise<unknown> {
  if (typeof path !== 'string' || path.length > 1024 || !path.startsWith(PREFIX) || /[\s\\]/.test(path)) throw invalid()
  // Reject traversal before URL normalization can convert it into another route.
  if (path.includes('%') && /%(?:2e|2f|5c)/i.test(path.split('?')[0])) throw invalid()
  if (path.split('?')[0].split('/').some(part => part === '.' || part === '..')) throw invalid()
  const url = new URL(path, 'https://local.invalid')
  const match = /^\/api\/rehearsals(?:\/([0-9a-f-]+)(?:\/(jobs|requests|records))?)?$/.exec(url.pathname)
  if (!match || url.hash) throw invalid()
  const [, runId, route] = match
  if (runId && !UUID.test(runId)) throw invalid()
  const allowed = !runId ? ['limit', 'offset'] : route === 'requests' ? ['limit', 'offset', 'agent_id'] : route === 'jobs' ? ['agent_id'] : route === 'records' ? ['agent_id', 'kind', 'id'] : []
  for (const key of url.searchParams.keys()) if (!allowed.includes(key) || url.searchParams.getAll(key).length !== 1) throw invalid()
  const agentId = url.searchParams.get('agent_id')
  if (agentId !== null && !REHEARSAL_AGENTS.some(agent => agent.id === agentId)) throw invalid()
  const limit = !runId || route === 'requests' ? integer(url.searchParams, 'limit', runId ? 50 : 20, 1, runId ? 50 : 20) : 0
  const offset = !runId || route === 'requests' ? integer(url.searchParams, 'offset', 0, 0, 1_000_000) : 0
  const kind = url.searchParams.get('kind')
  const id = url.searchParams.get('id')
  if (route === 'records') {
    if (!agentId || !kind || !id || !['journal', 'episode', 'inquiry', 'library'].includes(kind)) throw invalid()
    if (kind === 'inquiry' ? !UUID.test(id) : kind === 'library' ? !/^doc-[0-9a-f]{12}-s[0-9]{5}$/.test(id) : !/^[1-9][0-9]{0,9}$/.test(id) || Number(id) > 2 ** 31 - 1) throw invalid()
  }
  const fixture = (await import('./fixture.json')).default as unknown as RehearsalFixture
  if (fixture.kind !== 'fixture' || !Array.isArray(fixture.runs)) throw new Error('Local rehearsal example unavailable.')
  if (!runId) return structuredClone({ runs: fixture.runs.slice(offset, offset + limit).map(summary), total: fixture.runs.length, limit, offset })
  const run = fixture.runs.find(item => item.run_id === runId)
  if (!run) throw new Error('Rehearsal run not found.')
  if (!route) return structuredClone(summary(run))
  const jobs = Object.hasOwn(fixture.jobs, runId) ? fixture.jobs[runId] : undefined
  if (!jobs || jobs.some(job => !REHEARSAL_AGENTS.some(agent => agent.id === job.agent_id))) throw new Error('Local rehearsal jobs unavailable.')
  if (route === 'jobs') return structuredClone({ run_id: runId, jobs: jobs.filter(job => !agentId || job.agent_id === agentId).map(operationalJob) })
  if (route === 'requests') {
    const events = Object.hasOwn(fixture.requests, runId) ? fixture.requests[runId] : undefined
    if (!events || events.some(event => !REHEARSAL_AGENTS.some(agent => agent.id === event.agent_id))) throw new Error('Local rehearsal requests unavailable.')
    const owned = events.filter(event => !agentId || event.agent_id === agentId)
    return structuredClone({ run_id: runId, events: owned.slice(offset, offset + limit).map(operationalRequest), total: owned.length, limit, offset })
  }
  // A matching owner-local job reference is mandatory, including for library reads.
  if (!jobs.some(job => job.agent_id === agentId && job.record_refs.some(ref => ref.kind === kind && String(ref.id) === id))) throw new Error('Rehearsal record not found.')
  const records = Object.hasOwn(fixture.records, runId) ? fixture.records[runId] : undefined
  const key = `${agentId}|${kind}|${id}`
  const value = records && Object.hasOwn(records, key) ? records[key] : undefined
  if (!value) throw new Error('Rehearsal record not found.')
  // Actual-store fixtures must carry the complete owner/run envelope. A missing
  // or malformed wrapper is unavailable, never permission to relabel its body.
  if (!('record' in value) || !value.record || typeof value.record !== 'object') throw invalid()
  const record = value
  if (record.run_id !== runId || record.agent_id !== agentId || record.kind !== kind || String(record.id) !== id) throw invalid()
  validateRecord(record)
  return structuredClone(record)
}

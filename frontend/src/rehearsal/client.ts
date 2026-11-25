import { REHEARSAL_AGENTS, isOwnerWake } from './contracts'
import type { RehearsalDecisionMetadata, RehearsalFixture, RehearsalJob, RehearsalPrivateJSON, RehearsalRecordResponse, RehearsalRequest, RehearsalRun } from './contracts'
import { projectWitnessAccount } from '../journals/client'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const PREFIX = '/api/rehearsals'
const invalid = () => new Error('Invalid local rehearsal request. No backend fallback was attempted.')
function pick<T extends object, K extends keyof T>(value: T, keys: readonly K[]): Pick<T, K> {
  return Object.fromEntries(keys.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]])) as Pick<T, K>
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const number = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000_000
const string = (value: unknown) => typeof value === 'string' && value.length <= 256
const money = (value: unknown) => string(value) && /^[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(value as string)
const actions = ['rest', 'journal', 'inquire', 'library', 'roam']
const limits = ['wakes_per_agent', 'max_requests', 'max_output_tokens', 'max_input_bytes', 'max_runtime_seconds', 'request_timeout_seconds', 'max_parallelism', 'budget_usd']
function checked(value: unknown, fields: Record<string, (item: unknown) => boolean>): Record<string, unknown> {
  if (!object(value) || Object.entries(fields).some(([key, check]) => !Object.hasOwn(value, key) || !check(value[key]))) throw invalid()
  return pick(value, Object.keys(fields))
}
/** Public metadata never forwards dynamic nested fields or malformed context. */
export function projectDecisionMetadata(value: unknown): RehearsalDecisionMetadata | null {
  if (!object(value) || value.schema_version !== 1) return null
  try {
    const offered = value.offered_actions
    if (!Array.isArray(offered) || !offered.length || offered.length > 5 || offered.some(action => typeof action !== 'string' || !actions.includes(action)) || new Set(offered).size !== offered.length) return null
    if (!Array.isArray(value.action_costs) || value.action_costs.length !== offered.length) return null
    const costs = value.action_costs.map(cost => checked(cost, { action: item => typeof item === 'string' && actions.includes(item), max_requests: number, reservation_ceiling_usd: money, basis: item => item === 'catalog_upper_bound' }))
    if (costs.map(cost => cost.action).sort().join() !== [...offered].sort().join()) return null
    const constraints = checked(value.constraints, Object.fromEntries(limits.map(key => [key, key === 'budget_usd' ? money : number])))
    const snapshot = checked(value.admission_snapshot, { reserved_usd: money, remaining_budget_usd: money, request_count: number, remaining_requests: number, is_reservation: item => item === false })
    const model = checked(value.model, { requested_model: string, context_length: number, max_completion_tokens: number, catalog_source: item => item === null || string(item) })
    const continuity = checked(value.continuity, { status: item => typeof item === 'string' && ['empty', 'included', 'available', 'unavailable', 'truncated', 'partial', 'failed'].includes(item), refs: item => Array.isArray(item) && item.length <= 100, truncated: item => typeof item === 'boolean', chars: number })
    continuity.refs = (continuity.refs as unknown[]).map(ref => {
      const result = checked(ref, { kind: item => typeof item === 'string' && ['journal', 'episode', 'inquiry', 'library'].includes(item), id: item => string(item) || number(item) })
      for (const key of ['wake_id', 'agent_id']) if (object(ref) && Object.hasOwn(ref, key)) {
        if (!string(ref[key])) throw invalid()
        result[key] = ref[key]
      }
      return result
    })
    return { schema_version: 1, offered_actions: [...offered], action_costs: costs, constraints, admission_snapshot: snapshot, model, continuity } as unknown as RehearsalDecisionMetadata
  } catch { return null }
}
// Literal owner text remains untouched; only known evidence scaffolding survives.
const privateFields = new Set(['continuity', 'include_metadata', 'include_continuity', 'status', 'refs', 'truncated', 'chars', 'excerpts', 'unavailable', 'records', 'kind', 'id', 'wake_id', 'agent_id', 'body', 'content', 'source', 'account_kind', 'body_truncated', 'inquiry_id', 'title', 'state', 'title_source', 'title_truncated', 'latest_entry', 'entry_status', 'entry_id', 'created_at', 'record'])
function privateContext(value: unknown, owner: string, depth = 0): RehearsalPrivateJSON {
  if (depth > 12) throw invalid()
  if (value === null || typeof value === 'boolean' || typeof value === 'string' || typeof value === 'number' && Number.isFinite(value)) return value
  if (Array.isArray(value)) return value.map(item => privateContext(item, owner, depth + 1))
  if (!object(value)) throw invalid()
  if (Object.hasOwn(value, 'agent_id') && value.agent_id !== owner) throw invalid()
  if (Object.hasOwn(value, 'wake_id') && !isOwnerWake(owner, value.wake_id)) throw invalid()
  if (value.kind === 'innermost') throw invalid()
  return Object.fromEntries(Object.entries(value).filter(([key]) => privateFields.has(key)).map(([key, item]) => [key, privateContext(item, owner, depth + 1)]))
}
function summary(value: RehearsalRun): RehearsalRun {
  return { ...pick(value, ['run_id', 'mode', 'status', 'created_at', 'started_at', 'ended_at', 'stop_requested', 'request_count', 'reserved_usd', 'counted_usd', 'known_cost_usd', 'unknown_cost_requests', 'reported_cost_usd', 'estimated_cost_usd']),
    limits: pick(value.limits, ['wakes_per_agent', 'max_requests', 'max_output_tokens', 'max_input_bytes', 'max_runtime_seconds', 'request_timeout_seconds', 'max_parallelism', 'budget_usd']),
    agent_models: Object.fromEntries(REHEARSAL_AGENTS.filter(agent => Object.hasOwn(value.agent_models, agent.id)).map(agent => [agent.id, value.agent_models[agent.id]])) as RehearsalRun['agent_models'],
    agents: value.agents.filter(agent => REHEARSAL_AGENTS.some(owner => owner.id === agent.agent_id)).map(agent => pick(agent, ['agent_id', 'pending', 'completed', 'failed', 'stopped', 'uncertain'])),
    capabilities: value.capabilities.filter(cap => ['rest', 'journal', 'inquire', 'library', 'roam'].includes(cap)) }
}
function operationalJob(value: RehearsalJob): RehearsalJob {
  const mode = value.action === 'journal' && ['note', 'compost', 'distill', 'witness'].includes(value.journal_mode ?? '') ? value.journal_mode : undefined
  const channels = value.action === 'journal' && Array.isArray(value.channels) && value.channels.length <= 3 && new Set(value.channels).size === value.channels.length && value.channels.every(channel => ['trading', 'idea', 'orientation', 'unclassified'].includes(channel)) && (!value.channels.includes('unclassified') || value.channels.length === 1) ? [...value.channels] : undefined
  return { ...pick(value, ['wake_id', 'agent_id', 'round', 'status', 'action', 'failure_code', 'requested_model', 'response_model', 'provider', 'request_count', 'duration_ms', 'updated_at']),
    ...(mode ? { journal_mode: mode } : {}), ...(channels ? { channels } : {}),
    decision_context: projectDecisionMetadata(value.decision_context), selection_origin: value.selection_origin === 'model' || value.selection_origin === 'none' ? value.selection_origin : null,
    record_refs: value.record_refs.filter(ref => ['journal', 'episode', 'inquiry', 'library'].includes(ref.kind) || ref.kind === 'witness' && typeof ref.id === 'string' && UUID.test(ref.id)).map(ref => pick(ref, ['kind', 'id'])) }
}
function operationalRequest(value: RehearsalRequest): RehearsalRequest {
  const fields = ['input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens', 'cost_usd', 'reported_cost_usd', 'estimated_cost_usd', 'cost_status', 'cost_source'] as const
  const usage = value.usage ?? (fields.some(field => Object.hasOwn(value, field)) ? value : null)
  return { ...pick(value, ['request_id', 'wake_id', 'agent_id', 'activity', 'model', 'requested_model', 'response_model', 'provider', 'outcome', 'duration_ms', 'input_bytes', 'max_output_tokens', 'reserved_usd', 'failure_code', 'created_at', 'submitted_at', 'finished_at', 'finish_reason']),
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
  } else if (record.kind === 'witness') {
    if (!('scope' in record.record) || record.record.scope !== record.agent_id) throw invalid()
    projectWitnessAccount(record.record, record.agent_id)
  } else if (!('id' in record.record) || String(record.record.id) !== String(record.id)) throw invalid()
}
/** Local GET reader only; neither credentials nor transport exist at this boundary. */
export async function readRehearsalFixture(path: string): Promise<unknown> {
  if (typeof path !== 'string' || path.length > 1024 || !path.startsWith(PREFIX) || /[\s\\]/.test(path)) throw invalid()
  // Reject traversal before URL normalization can convert it into another route.
  if (path.includes('%') && /%(?:2e|2f|5c)/i.test(path.split('?')[0])) throw invalid()
  if (path.split('?')[0].split('/').some(part => part === '.' || part === '..')) throw invalid()
  const url = new URL(path, 'https://local.invalid')
  const match = /^\/api\/rehearsals(?:\/([0-9a-f-]+)(?:\/(jobs|requests|records|decisions))?)?$/.exec(url.pathname)
  if (!match || url.hash) throw invalid()
  const [, runId, route] = match
  if (runId && !UUID.test(runId)) throw invalid()
  const allowed = !runId ? ['limit', 'offset'] : route === 'requests' ? ['limit', 'offset', 'agent_id'] : route === 'jobs' ? ['agent_id'] : route === 'records' ? ['agent_id', 'kind', 'id'] : route === 'decisions' ? ['agent_id', 'wake_id'] : []
  for (const key of url.searchParams.keys()) if (!allowed.includes(key) || url.searchParams.getAll(key).length !== 1) throw invalid()
  const agentId = url.searchParams.get('agent_id')
  if (agentId !== null && !REHEARSAL_AGENTS.some(agent => agent.id === agentId)) throw invalid()
  const limit = !runId || route === 'requests' ? integer(url.searchParams, 'limit', runId ? 50 : 20, 1, runId ? 50 : 20) : 0
  const offset = !runId || route === 'requests' ? integer(url.searchParams, 'offset', 0, 0, 1_000_000) : 0
  const kind = url.searchParams.get('kind')
  const id = url.searchParams.get('id')
  const wake = url.searchParams.get('wake_id')
  if (route === 'decisions' && (!agentId || !wake || !isOwnerWake(agentId, wake))) throw invalid()
  if (route === 'records') {
    if (!agentId || !kind || !id || !['journal', 'episode', 'inquiry', 'library', 'witness'].includes(kind)) throw invalid()
    if (kind === 'inquiry' || kind === 'witness' ? !UUID.test(id) : kind === 'library' ? !/^doc-[0-9a-f]{12}-s[0-9]{5}$/.test(id) : !/^[1-9][0-9]{0,9}$/.test(id) || Number(id) > 2 ** 31 - 1) throw invalid()
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
  if (route === 'decisions') {
    const matching = jobs.filter(job => job.wake_id === wake)
    if (matching.length !== 1 || matching[0].agent_id !== agentId) throw invalid()
    const decisions = fixture.decisions && Object.hasOwn(fixture.decisions, runId) ? fixture.decisions[runId] : undefined
    const value = decisions && wake && Object.hasOwn(decisions, wake) ? decisions[wake] : undefined
    if (!value) throw new Error('Decision context unavailable for this recorded wake.')
    if (value.run_id !== runId || value.agent_id !== agentId || value.wake_id !== wake || !object(value.decision)) throw invalid()
    const metadata = projectDecisionMetadata(value.decision.metadata)
    if (!metadata || !Array.isArray(value.decision.requests)) throw invalid()
    if (metadata.continuity.refs.some(ref => ref.agent_id && ref.agent_id !== agentId || ref.wake_id && !isOwnerWake(agentId, ref.wake_id))) throw invalid()
    const events = value.decision.requests.map(event => {
      if (!object(event) || event.agent_id !== agentId || event.wake_id !== wake) throw invalid()
      const result = { ...operationalRequest(event as unknown as RehearsalRequest), ...pick(event, ['input_sha256', 'input_coverage', 'input_status', 'context_status', 'messages']) }
      if (result.messages !== undefined && result.messages !== null) {
        if (!Array.isArray(result.messages)) throw invalid()
        result.messages = result.messages.map(message => checked(message, { role: item => typeof item === 'string' && ['system', 'user', 'assistant', 'tool'].includes(item), content: item => typeof item === 'string' })) as RehearsalPrivateJSON[]
      }
      return result
    })
    return structuredClone({ run_id: runId, agent_id: agentId, wake_id: wake, decision: { metadata, private_context: privateContext(value.decision.private_context, agentId!), requests: events } })
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
  if (kind === 'witness') return structuredClone({ ...record, record: projectWitnessAccount(record.record, record.agent_id) })
  return structuredClone(record)
}

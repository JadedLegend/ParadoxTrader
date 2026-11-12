import { JOURNAL_CHANNELS } from './contracts'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'
import type { JournalChannel, JournalFixture, JournalNote, JournalOwner, JournalResponse, JournalSourceHeader, JournalState, WitnessAccount, WitnessResponse, WitnessScope, WitnessSourceRef } from './contracts'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const integer = (value: unknown, max = 2 ** 31 - 1): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value <= max
const invalid = () => new Error('Invalid local journal request or source scope. No backend fallback was attempted.')
const own = (value: object, key: string) => Object.hasOwn(value, key)
const ownerIds = REHEARSAL_AGENTS.map(agent => agent.id as string)
const wakes = (owner: string) => [`${owner}-r1`, `${owner}-r2`]

function literalPrefix(content: string, maxChars: number, maxBytes = Number.MAX_SAFE_INTEGER): string {
  const encoder = new TextEncoder()
  let chars = 0, bytes = 0, result = ''
  for (const char of content) {
    const size = encoder.encode(char).length
    if (chars === maxChars || bytes + size > maxBytes) break
    result += char; chars += 1; bytes += size
  }
  return result
}

/** Exact field projection. Literal strings are source text, never HTML. */
export function projectJournalNote(value: unknown, owner: JournalOwner): JournalNote {
  if (!object(value) || value.author !== owner || own(value, 'agent_id') && value.agent_id !== owner ||
      !integer(value.id) || typeof value.content !== 'string' || typeof value.created_at !== 'string' ||
      !Array.isArray(value.channels) || value.channels.length < 1 || value.channels.length > 3 ||
      value.channels.some(channel => !JOURNAL_CHANNELS.includes(channel)) || new Set(value.channels).size !== value.channels.length ||
      value.channels.includes('unclassified') && (value.channels.length !== 1 || value.channels[0] !== 'unclassified') ||
      !['note', 'compost', 'distillation'].includes(value.note_kind as string) || !['active', 'released'].includes(value.state as string) ||
      !['real', 'offline', null].includes(value.source_mode as string | null) ||
      value.source_wake_id !== null && !wakes(owner).includes(value.source_wake_id as string) ||
      !Array.isArray(value.source_ids) || value.source_ids.length > 20 || value.source_ids.some(id => !integer(id)) ||
      new Set(value.source_ids).size !== value.source_ids.length) throw invalid()
  const content = literalPrefix(value.content, 12000)
  return { id: value.id, content, channels: [...value.channels], note_kind: value.note_kind,
    state: value.state, author: value.author, source_mode: value.source_mode, created_at: value.created_at,
    source_wake_id: value.source_wake_id, source_ids: [...value.source_ids], truncated: value.truncated === true || content !== value.content } as JournalNote
}
export function projectSourceHeader(value: unknown, owner: JournalOwner): JournalSourceHeader {
  if (!object(value) || value.kind !== 'inquiry' || value.agent_id !== owner || typeof value.id !== 'string' || !UUID.test(value.id) ||
      typeof value.title !== 'string' || typeof value.created_at !== 'string' || !['open', 'paused', 'abandoned'].includes(value.state as string) ||
      !['lineage_inquiries', 'lineage_proposals'].includes(value.provenance as string) || !Array.isArray(value.proposal_ids) ||
      value.proposal_ids.length > 20 || value.proposal_ids.some(id => typeof id !== 'string' || !UUID.test(id))) throw invalid()
  return { kind: 'inquiry', id: value.id, agent_id: owner, title: value.title.slice(0, 500), state: value.state,
    created_at: value.created_at, title_truncated: value.title_truncated === true || value.title.length > 500,
    provenance: value.provenance, proposal_ids: [...value.proposal_ids] } as JournalSourceHeader
}
export function projectWitnessAccount(value: unknown, scope: WitnessScope): WitnessAccount {
  if (!object(value) || value.scope !== scope || value.author !== 'witness' || value.method !== 'mechanical' ||
      typeof value.id !== 'string' || !UUID.test(value.id) || typeof value.content !== 'string' || value.content.length > 24000 ||
      typeof value.created_at !== 'string' || typeof value.source_digest !== 'string' || value.source_digest.length > 256 ||
      !Array.isArray(value.source_refs) || value.source_refs.length > 256) throw invalid()
  const refs = value.source_refs.map((ref: unknown): WitnessSourceRef => {
    if (!object(ref) || !['run', 'wake', 'job', 'request', 'journal', 'episode', 'inquiry', 'library', 'witness'].includes(ref.kind as string) ||
        !(typeof ref.id === 'string' && ref.id.length <= 128 || integer(ref.id, Number.MAX_SAFE_INTEGER)) ||
        own(ref, 'agent_id') && (!ownerIds.includes(ref.agent_id as string) || scope !== 'steward' && ref.agent_id !== scope) ||
        own(ref, 'wake_id') && !(scope === 'steward' ? ownerIds.flatMap(wakes) : wakes(scope)).includes(ref.wake_id as string) ||
        scope !== 'steward' && ['wake', 'job'].includes(ref.kind as string) && !wakes(scope).includes(ref.id as string)) throw invalid()
    return { kind: ref.kind as string, id: ref.id as string | number,
      ...(own(ref, 'agent_id') ? { agent_id: ref.agent_id as JournalOwner } : {}),
      ...(own(ref, 'wake_id') ? { wake_id: ref.wake_id as string } : {}) }
  })
  return { id: value.id, scope, content: value.content, source_refs: refs, source_digest: value.source_digest,
    author: 'witness', method: 'mechanical', created_at: value.created_at }
}
function pageInteger(params: URLSearchParams, field: string, fallback: number, min: number, max: number) {
  const raw = params.get(field)
  if (raw === null) return fallback
  if (!/^[0-9]{1,10}$/.test(raw)) throw invalid()
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < min || value > max) throw invalid()
  return value
}
/** Local data only: no transport, fallback, credentials, writes, or eager import. */
export async function readJournalFixture(path: string): Promise<JournalResponse | WitnessResponse> {
  if (typeof path !== 'string' || path.length > 1024 || /[\s\\]/.test(path)) throw invalid()
  // Match before URL normalization, rejecting host URLs and traversal/encoding.
  const rawRoute = path.split('?')[0]
  const match = /^\/api\/rehearsals\/([0-9a-f-]+)\/(journals|witness)$/.exec(rawRoute)
  if (!match || !UUID.test(match[1])) throw invalid()
  const url = new URL(path, 'https://local.invalid')
  if (url.hash || url.pathname !== rawRoute) throw invalid()
  const [runId, route] = [match[1], match[2]]
  const allowed = route === 'journals' ? ['agent_id', 'channel', 'state', 'limit', 'offset', 'note_id'] : ['agent_id', 'limit', 'offset']
  for (const key of url.searchParams.keys()) if (!allowed.includes(key) || url.searchParams.getAll(key).length !== 1) throw invalid()
  const owner = url.searchParams.get('agent_id')
  if (owner !== null && !ownerIds.includes(owner) || route === 'journals' && owner === null) throw invalid()
  const limit = pageInteger(url.searchParams, 'limit', route === 'journals' ? 20 : 3, 1, 20)
  const offset = pageInteger(url.searchParams, 'offset', 0, 0, 10000)
  const channel = (url.searchParams.get('channel') ?? 'unclassified') as JournalChannel
  const state = (url.searchParams.get('state') ?? 'all') as JournalState
  if (!JOURNAL_CHANNELS.includes(channel) || !['all', 'active', 'released'].includes(state)) throw invalid()
  const noteId = url.searchParams.has('note_id') ? pageInteger(url.searchParams, 'note_id', 0, 1, 2 ** 31 - 1) : null
  const fixture = (await import('./fixture.json')).default as unknown as JournalFixture
  if (!object(fixture) || fixture.kind !== 'fixture' || !Array.isArray(fixture.runs) || !object(fixture.journals) || !object(fixture.witnesses)) throw new Error('Local journal example unavailable.')
  if (!fixture.runs.some(run => run.run_id === runId)) throw new Error('Journal run not found.')
  if (route === 'witness') {
    const scope = (owner ?? 'steward') as WitnessScope
    const run = own(fixture.witnesses, runId) ? fixture.witnesses[runId] : undefined
    const values = run && own(run, scope) ? run[scope] : undefined
    if (values !== undefined && !Array.isArray(values)) throw invalid()
    const accounts = (values ?? []).map(value => projectWitnessAccount(value, scope))
    return structuredClone({ run_id: runId, scope, status: values === undefined ? 'missing' : 'ok', accounts: accounts.slice(offset, offset + limit), total: accounts.length, limit, offset })
  }
  const agent = owner as JournalOwner
  const run = own(fixture.journals, runId) ? fixture.journals[runId] : undefined
  const values = run && own(run, agent) ? run[agent] : undefined
  if (values !== undefined && !Array.isArray(values)) throw invalid()
  const notes = (values ?? []).map(value => projectJournalNote(value, agent)).sort((left, right) => right.id - left.id)
  const note = noteId === null ? null : notes.find(value => value.id === noteId) ?? null
  if (noteId !== null && note === null) throw new Error('Journal original not found.')
  const filtered = notes.filter(value => value.channels.includes(channel) && (state === 'all' || value.state === state)).map(value => {
    const content = literalPrefix(value.content, 4000, 12000)
    return { ...value, content, truncated: value.truncated || content !== value.content }
  })
  let sources: JournalSourceHeader[] = []
  let sourceStatus: JournalResponse['source_status'] = 'not_applicable'
  if (noteId === null && ['idea', 'trading'].includes(channel) && state !== 'released') {
    const sourceRun = fixture.sources && own(fixture.sources, runId) ? fixture.sources[runId] : undefined
    const sourceValues = sourceRun && own(sourceRun, agent) ? sourceRun[agent] : undefined
    if (sourceValues !== undefined && !Array.isArray(sourceValues)) throw invalid()
    sources = (sourceValues ?? []).map(value => projectSourceHeader(value, agent))
      .filter(value => channel === 'idea' || value.provenance === 'lineage_proposals').slice(offset, offset + limit)
    sourceStatus = sourceValues === undefined ? 'missing' : 'ok'
  }
  return structuredClone({ run_id: runId, agent_id: agent, channel, state, status: values === undefined ? 'missing' : 'ok',
    notes: noteId === null ? filtered.slice(offset, offset + limit) : [], note, total: noteId === null ? filtered.length : 1,
    limit, offset, sources, source_status: sourceStatus })
}

import rawFixture from './fixtures.json' with { type: 'json' }
import type { PreviewFixture } from '../data/contracts'

export const fixture = rawFixture as PreviewFixture

export function readFixture(path: string): unknown {
  const url = new URL(path, 'https://preview.invalid')
  const route = url.pathname
  const meta = { kind: 'fixture', observed_at: fixture.observed_at }
  if (route === '/api/rehearsals' || route.startsWith('/api/rehearsals/')) {
    if (/^\/api\/rehearsals\/[^/]+\/(journals|witness)$/.test(route)) {
      return import('../journals/client').then(journals => journals.readJournalFixture(path))
    }
    return import('../rehearsal/client').then(rehearsal => rehearsal.readRehearsalFixture(path))
  }
  if (route.startsWith('/api/lineage/')) {
    if (route !== '/api/lineage/inquiries' && !/^\/api\/lineage\/inquiries\/[^/]+$/.test(route)) {
      throw new Error('No local lineage route is available. No backend fallback was attempted.')
    }
    return import('../lineage/client').then(lineage => lineage.readLineageFixture(path))
  }
  if (route.startsWith('/api/usage/')) {
    if (route !== '/api/usage/summary' && route !== '/api/usage/events') {
      throw new Error('No local usage route is available. No backend fallback was attempted.')
    }
    return import('../usage/fixture').then(usage => usage.readUsageFixture(path))
  }
  if (route.startsWith('/api/library/')) {
    // These are actual imported sources, not invented agent activity. The
    // corpus is loaded only after an explicit library read, never on each wake.
    const section = route.match(/^\/api\/library\/sections\/([^/]+)$/)
    if (route !== '/api/library/documents' && route !== '/api/library/search' && !section) {
      throw new Error('No local library route is available. No backend fallback was attempted.')
    }
    const integer = (name: string, fallback: number) => {
      const value = url.searchParams.get(name)
      if (value === null) return fallback
      if (!/^-?\d+$/.test(value)) throw new Error(`Invalid library ${name}.`)
      const parsed = Number(value)
      if (!Number.isSafeInteger(parsed)) throw new Error(`Invalid library ${name}.`)
      return parsed
    }
    return import('../library/client').then(async (library): Promise<unknown> => {
      if (route === '/api/library/documents') return library.listDocuments(integer('limit', 50), integer('offset', 0))
      if (route === '/api/library/search') return library.queryLibrary(url.searchParams.get('q') ?? '',
        url.searchParams.get('document_id') || undefined, integer('limit', 3), integer('max_chars', 600))
      return library.readSection(decodeURIComponent(section![1]), integer('offset', 0), integer('max_chars', 1200))
    })
  }
  if (route === '/api/status' || route === '/api/agents') return { ...meta, agents: fixture.agents }
  if (route === '/api/agents/positions') return { ...meta, positions: fixture.positions }
  if (route === '/api/snapshot') return { ...meta, error: 'Market feeds are not connected in this preview.' }
  if (route === '/api/announcements') return { ...meta, announcements: [], countdown: null }
  if (route === '/api/config') return { ...meta, config: {
    runtime: { current_phase: 0, wake_interval_seconds: null, wake_duration_seconds: null },
    guardrails: { autonomous_trading_mode: false },
    agent_models: Object.fromEntries(fixture.agents.map(a => [a.agent_id, a.model])),
  } }
  if (route === '/api/forum/threads') return { ...meta, threads: [{ id: 'general', title: 'Community' }] }
  if (route === '/api/forum') return { ...meta, posts: url.searchParams.get('thread_id') === 'council_deliberation' ? [] : [{
    id: 1, author: 'SYSTEM', thread_id: 'general', tags: ['fixture'], created_at: fixture.observed_at,
    content: 'UI example only. The community can share questions and findings when communication is available. This post was not written by an agent.',
  }] }
  if (route === '/api/queue') return { ...meta, trades: [{
    id: 1, agent_id: 'tempest', created_at: fixture.observed_at,
    proposal: { symbol: 'DEMO', side: 'buy', qty: 2, estimated_value: 20,
      thesis: 'Fixture only: a sample review card, not a recommendation or pending order.',
      risk_note: 'No portfolio is affected by this example.' },
  }] }
  const inbox = route.match(/^\/api\/inbox\/([^/]+)$/)
  if (inbox && (inbox[1] === 'user' || fixture.agents.some(a => a.agent_id === inbox[1]))) {
    return { ...meta, messages: [], unread_count: 0 }
  }
  const agent = route.match(/^\/api\/agents\/([^/]+)\/(journal|episodes|self-definition)$/)
  if (agent && fixture.agents.some(a => a.agent_id === agent[1])) {
    if (agent[2] === 'journal') return { ...meta, agent_id: agent[1], entries: [] }
    if (agent[2] === 'episodes') return { ...meta, agent_id: agent[1], episodes: [] }
    return { ...meta, agent_id: agent[1], ...fixture.definitions[agent[1]] }
  }
  throw new Error(`No fixture is available for ${route}. No backend fallback was attempted.`)
}

import type { UsageEvent, UsageEventsResponse, UsageFilters, UsageSummary, UsageSummaryResponse } from './contracts'

// Entirely invented examples, not provider prices, requests, or actual spend.
// The token-only example uses synthetic USD-per-million rates: input 0.5,
// output 1, cached input 0.25. 1,000 input + 500 output => USD 0.001.
// No provider/account lookup, network access, or private content is involved.
const BASE: UsageEvent = {
  event_id: 'example-request-1', call_id: 'example-call-1', wake_id: 'example-wake-1',
  agent_id: 'tempest', activity: 'activity_picker', provider: 'example-router',
  model: 'synthetic-text-model', response_model: 'synthetic-text-model', attempt: 1,
  created_at: '2026-01-02T12:05:00Z', duration_ms: 240, outcome: 'success', http_status: 200,
  input_tokens: 120, output_tokens: 30, cached_input_tokens: null, reasoning_tokens: null,
  total_tokens: 150, cost_usd: '0.002', cost_status: 'reported', cost_scope: 'provider_reported',
  cost_reason: null, pricing_source: null, pricing_as_of: null, pricing_snapshot: null,
}
const EVENTS: UsageEvent[] = [
  BASE,
  {
    ...BASE, event_id: 'example-request-2', call_id: 'example-call-2', wake_id: 'example-wake-2',
    agent_id: 'siren', activity: 'reflection', created_at: '2026-01-02T12:04:00Z',
    input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, reasoning_tokens: 0,
    total_tokens: 0, cost_usd: '0', duration_ms: 80,
  },
  {
    ...BASE, event_id: 'example-request-3', call_id: 'example-call-3', wake_id: 'example-wake-3',
    agent_id: 'oracle', activity: 'research', provider: 'example-research', model: 'synthetic-search-model',
    response_model: null, created_at: '2026-01-02T12:03:00Z', input_tokens: 1000, output_tokens: 500,
    total_tokens: 1500, cost_usd: '0.001', cost_status: 'estimated', cost_scope: 'token_only',
    cached_input_tokens: 0, pricing_source: null, pricing_as_of: null,
    pricing_snapshot: { schema_version: 1, provider: 'example-research', model: 'synthetic-search-model',
      source: 'fixture-only-synthetic-rates-v1', as_of: '2026-01-01',
      input_usd_per_million: '0.5', output_usd_per_million: '1', cached_input_usd_per_million: '0.25' },
  },
  {
    ...BASE, event_id: 'example-request-4', call_id: 'example-call-4', attempt: 2,
    activity: 'reflection', created_at: '2026-01-02T12:02:00Z', outcome: 'http_error', http_status: 429,
    input_tokens: null, output_tokens: null, cached_input_tokens: null, reasoning_tokens: null,
    total_tokens: null, cost_usd: null, cost_status: 'unknown', cost_scope: null, cost_reason: 'missing_usage',
  },
  {
    ...BASE, event_id: 'example-request-5', call_id: 'example-call-5', wake_id: null,
    agent_id: 'oracle', activity: 'council', created_at: '2026-01-02T12:01:00Z',
    input_tokens: null, output_tokens: null, cached_input_tokens: null, reasoning_tokens: null,
    total_tokens: null, cost_usd: null, cost_status: 'unknown', cost_scope: null, cost_reason: 'missing_usage',
  },
]

const TOKEN_FIELDS = ['input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'] as const
const SCALE = 1_000_000_000_000n
function picodollars(value: string): bigint {
  if (!/^\d+(?:\.\d{1,12})?$/.test(value)) throw new Error('Invalid synthetic USD decimal.')
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * SCALE + BigInt(fraction.padEnd(12, '0'))
}
function decimal(value: bigint): string {
  const fraction = (value % SCALE).toString().padStart(12, '0').replace(/0+$/, '')
  return `${value / SCALE}${fraction ? `.${fraction}` : ''}`
}
function summarize(events: UsageEvent[]): UsageSummary {
  const reported = events.filter(event => event.cost_status === 'reported' && event.cost_usd !== null)
  const estimated = events.filter(event => event.cost_status === 'estimated' && event.cost_usd !== null)
  const usageKnown = events.filter(event => event.input_tokens !== null && event.output_tokens !== null).length
  const totalCost = (items: UsageEvent[]) => items.length
    ? decimal(items.reduce((total, event) => total + picodollars(event.cost_usd!), 0n)) : null
  const tokenTotal = (field: typeof TOKEN_FIELDS[number]) => {
    const values = events.map(event => event[field]).filter((value): value is number => value !== null)
    return values.length ? values.reduce((total, value) => total + value, 0) : null
  }
  return {
    requests: events.length,
    successful_requests: events.filter(event => event.outcome === 'success').length,
    failed_requests: events.filter(event => event.outcome !== 'success').length,
    reported_cost_usd: totalCost(reported), estimated_cost_usd: totalCost(estimated),
    reported_cost_requests: reported.length, estimated_cost_requests: estimated.length,
    unknown_cost_requests: events.length - reported.length - estimated.length,
    input_tokens: tokenTotal('input_tokens'), output_tokens: tokenTotal('output_tokens'),
    cached_input_tokens: tokenTotal('cached_input_tokens'), reasoning_tokens: tokenTotal('reasoning_tokens'),
    usage_known_requests: usageKnown, usage_unknown_requests: events.length - usageKnown,
  }
}
function integer(params: URLSearchParams, name: string, fallback: number, minimum: number, maximum: number): number {
  const value = params.get(name)
  if (value === null) return fallback
  if (value.length > 10 || !/^[0-9]+$/.test(value)) throw new Error('Invalid usage pagination.')
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) throw new Error('Invalid usage pagination.')
  return parsed
}
function timestamp(value: string | null): number | null {
  if (value === null) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value)
  if (!match) throw new Error('Invalid timezone-aware usage timestamp.')
  const [, year, month, day, hour, minute, second, , zone, , zoneHour, zoneMinute] = match
  const y = Number(year), m = Number(month), d = Number(day)
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > days[m - 1] || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59
      || (zone !== 'Z' && (Number(zoneHour) > 23 || Number(zoneMinute) > 59))) throw new Error('Invalid usage timestamp.')
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) throw new Error('Invalid usage timestamp.')
  return parsed
}

/** Only the two fixed read routes are supported; missing routes never fall back. */
export function readUsageFixture(path: string): UsageSummaryResponse | UsageEventsResponse {
  if (!path.startsWith('/api/usage/')) throw new Error('No local usage route. No backend fallback was attempted.')
  const url = new URL(path, 'https://local.invalid')
  const route = url.pathname
  if (url.hash || (route !== '/api/usage/summary' && route !== '/api/usage/events')) {
    throw new Error('No local usage route. No backend fallback was attempted.')
  }
  const allowed = route === '/api/usage/events' ? ['agent_id', 'since', 'until', 'limit', 'offset'] : ['agent_id', 'since', 'until']
  for (const key of url.searchParams.keys()) {
    if (!allowed.includes(key) || url.searchParams.getAll(key).length !== 1) throw new Error('Invalid usage filter.')
  }
  const filters: UsageFilters = {
    agent_id: url.searchParams.get('agent_id'), since: url.searchParams.get('since'), until: url.searchParams.get('until'),
  }
  if (filters.agent_id !== null && !/^[a-zA-Z0-9_.:-]{1,80}$/.test(filters.agent_id)) throw new Error('Invalid usage agent filter.')
  const since = timestamp(filters.since), until = timestamp(filters.until)
  if (since !== null && until !== null && since > until) throw new Error('Invalid usage time range.')
  // The ledger returns normalized UTC microseconds, with [since, until) bounds.
  const normalized = (value: string | null, parsed: number | null) => {
    if (value === null || parsed === null) return null
    const fraction = /\.(\d{1,6})/.exec(value)?.[1] || ''
    const iso = new Date(parsed).toISOString()
    if (!/^[0-9]{4}-/.test(iso) || iso.startsWith('0000-')) throw new Error('Invalid usage timestamp.')
    return iso.slice(0, 19) + `.${fraction.padEnd(6, '0')}+00:00`
  }
  filters.since = normalized(filters.since, since)
  filters.until = normalized(filters.until, until)
  if (filters.since !== null && filters.until !== null && filters.since > filters.until) throw new Error('Invalid usage time range.')
  const events = EVENTS.filter(event => (filters.agent_id === null || event.agent_id === filters.agent_id)
    && (filters.since === null || normalized(event.created_at, Date.parse(event.created_at))! >= filters.since)
    && (filters.until === null || normalized(event.created_at, Date.parse(event.created_at))! < filters.until))
  if (route === '/api/usage/events') {
    const limit = integer(url.searchParams, 'limit', 50, 1, 100)
    const offset = integer(url.searchParams, 'offset', 0, 0, 2 ** 31 - 1)
    return structuredClone({ kind: 'fixture', status: 'ok', events: events.slice(offset, offset + limit), total: events.length, offset, limit, filters })
  }
  const groups = <K extends 'agent_id' | 'provider' | 'activity'>(key: K) =>
    [...new Set(events.map(event => event[key]))].sort().slice(0, 100).map(value => ({
      [key]: value, ...summarize(events.filter(event => event[key] === value)),
    })) as (UsageSummary & Pick<UsageEvent, K>)[]
  return structuredClone({ kind: 'fixture', status: 'ok', currency: 'USD', filters, summary: summarize(events),
    by_agent: groups('agent_id'), by_provider: groups('provider'), by_activity: groups('activity') })
}

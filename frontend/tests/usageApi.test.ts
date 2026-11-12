import { describe, expect, it } from 'vitest'
import { getUsageSummary, getUsageEvents } from '../src/api'
import { readFixture } from '../src/preview/readFixture'
import { readUsageFixture } from '../src/usage/fixture'
import type { UsageEventsResponse, UsageSummaryResponse } from '../src/usage/contracts'

const localSummary = (params = '') => readUsageFixture(`/api/usage/summary${params}`) as UsageSummaryResponse
const localEvents = (params = '') => readUsageFixture(`/api/usage/events${params}`) as UsageEventsResponse
const SUMMARY_FIELDS = [
  'requests', 'successful_requests', 'failed_requests', 'reported_cost_usd', 'estimated_cost_usd',
  'reported_cost_requests', 'estimated_cost_requests', 'unknown_cost_requests', 'input_tokens', 'output_tokens',
  'cached_input_tokens', 'reasoning_tokens', 'usage_known_requests', 'usage_unknown_requests',
]

describe('read-only synthetic usage preview API', () => {
  it('returns five labeled synthetic attempts, exact known subtotals, and partial coverage', async () => {
    const summary = await getUsageSummary()
    const events = await getUsageEvents()
    expect(summary.kind).toBe('fixture')
    expect(events.kind).toBe('fixture')
    expect(summary.status).toBe('ok')
    expect(summary.currency).toBe('USD')
    expect(summary.filters).toEqual({ agent_id: null, since: null, until: null })
    expect(Object.keys(summary.summary).sort()).toEqual(SUMMARY_FIELDS.sort())
    expect(summary.summary).toEqual({
      requests: 5, successful_requests: 4, failed_requests: 1,
      reported_cost_usd: '0.002', estimated_cost_usd: '0.001',
      reported_cost_requests: 2, estimated_cost_requests: 1, unknown_cost_requests: 2,
      input_tokens: 1120, output_tokens: 530, cached_input_tokens: 0, reasoning_tokens: 0,
      usage_known_requests: 3, usage_unknown_requests: 2,
    })
    expect(events.events).toHaveLength(5)
    expect(events.total).toBe(5)
    expect(events.limit).toBe(50)
    expect(events.offset).toBe(0)
  })

  it('keeps valid reported zero, unknown costs, failed attempts, and an empty ledger distinct', async () => {
    const zero = await getUsageSummary('siren')
    expect(zero.summary.reported_cost_usd).toBe('0')
    expect(zero.summary.reported_cost_requests).toBe(1)
    expect(zero.summary.estimated_cost_usd).toBeNull()
    expect(zero.summary.input_tokens).toBe(0)
    const empty = await getUsageSummary('alchemist')
    expect(empty.summary.requests).toBe(0)
    expect(empty.summary.reported_cost_usd).toBeNull()
    expect(empty.summary.estimated_cost_usd).toBeNull()
    expect(empty.summary.input_tokens).toBeNull()
    expect(empty.by_agent).toEqual([])
    expect((await getUsageEvents('alchemist')).events).toEqual([])
    const events = await getUsageEvents('tempest')
    const failed = events.events.find(event => event.outcome === 'http_error')!
    expect(failed.attempt).toBe(2)
    expect(failed.http_status).toBe(429)
    expect(failed.cost_usd).toBeNull()
    expect(failed.input_tokens).toBeNull()
    const unknownSuccess = (await getUsageEvents('oracle')).events.find(event => event.cost_status === 'unknown')!
    expect(unknownSuccess.outcome).toBe('success')
    expect(unknownSuccess.cost_usd).toBeNull()
  })

  it('uses identical filters for summaries and events, preserving provenance and all group totals', async () => {
    const summary = await getUsageSummary('oracle')
    const events = await getUsageEvents('oracle', 1, 0)
    expect(summary.filters.agent_id).toBe('oracle')
    expect(events.filters).toEqual(summary.filters)
    expect(summary.summary.requests).toBe(2)
    expect(summary.summary.estimated_cost_usd).toBe('0.001')
    expect(summary.summary.reported_cost_usd).toBeNull()
    expect(summary.summary.unknown_cost_requests).toBe(1)
    expect(summary.by_agent).toEqual([{ agent_id: 'oracle', ...summary.summary }])
    expect(summary.by_provider.reduce((n, group) => n + group.requests, 0)).toBe(2)
    expect(summary.by_activity.reduce((n, group) => n + group.requests, 0)).toBe(2)
    const estimated = events.events[0]
    expect(estimated.cost_scope).toBe('token_only')
    expect(estimated.cached_input_tokens).toBe(0)
    expect(estimated.pricing_snapshot).toEqual({ schema_version: 1, provider: 'example-research', model: 'synthetic-search-model',
      source: 'fixture-only-synthetic-rates-v1', as_of: '2026-01-01',
      input_usd_per_million: '0.5', output_usd_per_million: '1', cached_input_usd_per_million: '0.25' })
  })

  it('paginates bounded local attempts and preserves totals on an out-of-range page', async () => {
    expect((await getUsageEvents(undefined, 2, 2)).events.map(event => event.event_id)).toEqual(['example-request-3', 'example-request-4'])
    const beyond = await getUsageEvents(undefined, 100, 2147483647)
    expect(beyond.events).toEqual([])
    expect(beyond.total).toBe(5)
    expect(beyond.offset).toBe(2147483647)
  })

  it('filters timezone-aware ranges with inclusive since and exclusive until endpoints', () => {
    const params = '?since=2026-01-02T12%3A02%3A00Z&until=2026-01-02T13%3A04%3A00%2B01%3A00'
    expect(localSummary(params).summary.requests).toBe(2)
    expect(localEvents(params).events).toHaveLength(2)
    expect(localSummary(params).filters).toEqual({ agent_id: null, since: '2026-01-02T12:02:00.000000+00:00', until: '2026-01-02T12:04:00.000000+00:00' })
    expect(localSummary('?since=2026-01-02T12:02:00Z&until=2026-01-02T12:02:00Z').summary.requests).toBe(0)
    expect(localSummary('?since=2026-01-02T12:02:00Z&until=2026-01-02T12:03:00Z').summary.unknown_cost_requests).toBe(1)
    expect(localSummary('?since=2027-01-01T00:00:00Z').summary.requests).toBe(0)
    expect(localSummary('?since=2026-01-02T12:05:00.000000Z').summary.requests).toBe(1)
  })

  it('preserves microsecond filter precision rather than treating submillisecond timestamps as equal', () => {
    expect(localSummary('?since=2026-01-02T12:05:00.000001Z').summary.requests).toBe(0)
    expect(localSummary('?until=2026-01-02T12:01:00.000001Z').summary.requests).toBe(1)
    expect(() => localSummary('?since=2026-01-02T12:05:00.000002Z&until=2026-01-02T12:05:00.000001Z')).toThrow()
  })

  it('clones every local response, including nested provenance, arrays, and filters', async () => {
    const events = await getUsageEvents('oracle')
    events.events[0].pricing_snapshot!.input_usd_per_million = 'consumer mutation'
    events.events[0].agent_id = 'mutation'
    events.filters.agent_id = 'mutation'
    expect((await getUsageEvents('oracle')).events[0].pricing_snapshot!.input_usd_per_million).toBe('0.5')
    const summary = localSummary()
    summary.summary.reported_cost_usd = '999'
    summary.by_agent[0].requests = 999
    expect(localSummary().summary.reported_cost_usd).toBe('0.002')
    expect(localSummary().by_agent[0].requests).not.toBe(999)
  })

  it.each([
    '/api/usage/unknown', '/api/usage/events/private', '/api/usage/summary?limit=1',
    '/api/usage/events?limit=0', '/api/usage/events?limit=101', '/api/usage/events?limit=true',
    '/api/usage/events?limit=1.5', '/api/usage/events?limit=%2B1', '/api/usage/events?limit=%201',
    '/api/usage/events?limit=NaN', '/api/usage/events?limit=١', '/api/usage/events?offset=-1',
    '/api/usage/events?offset=2147483648', '/api/usage/events?offset=1.0',
    '/api/usage/events?limit=999999999999999999999999', '/api/usage/events?limit=1&limit=2',
    '/api/usage/summary?agent_id=../tempest', '/api/usage/summary?agent_id=',
    '/api/usage/events?agent_id=tempest&agent_id=siren', '/api/usage/events?unknown=1',
    '/api/usage/events?since=2026-01-01', '/api/usage/events?since=2026-01-01T00:00:00',
    '/api/usage/events?since=2026-02-30T00:00:00Z', '/api/usage/events?since=2026-13-01T00:00:00Z',
    '/api/usage/events?since=2026-01-01T24:00:00Z', '/api/usage/events?since=2026-01-01T00:00:00%2B25:00',
    '/api/usage/events?since=2026-01-01T00:00:00%2B00:99',
    '/api/usage/events?since=2026-01-02T00:00:00Z&until=2026-01-01T00:00:00Z',
    '/api/usage/summary#private',
  ])('fails closed for invalid or unsupported route %s without transport', async path => {
    await expect(Promise.resolve().then(() => readFixture(path))).rejects.toThrow()
    expect(() => readUsageFixture(path)).toThrow()
  })

  it('has no prompts, queries, response content, keys, headers, or raw-error fields', async () => {
    const response = await getUsageEvents()
    for (const event of response.events) {
      expect(event.event_id).toMatch(/^example-/)
      expect(event.model).toMatch(/^synthetic-/)
      expect(event.created_at).toMatch(/Z$/)
      expect(Object.keys(event)).not.toEqual(expect.arrayContaining(['prompt', 'query', 'response_text', 'api_key', 'headers', 'error']))
      for (const forbidden of ['prompt', 'query', 'response_text', 'api_key', 'headers', 'error', 'content', 'messages']) expect(event).not.toHaveProperty(forbidden)
    }
  })
})

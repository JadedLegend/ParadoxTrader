import { describe, expect, it } from 'vitest'
import { getLineageInquiries, getLineageInquiry } from '../src/api'
import { readFixture } from '../src/preview/readFixture'
import { readLineageFixture } from '../src/lineage/client'
import type { LineageDetailResponse, LineageListResponse } from '../src/lineage/contracts'

const list = (params = '') => readLineageFixture(`/api/lineage/inquiries${params}`) as Promise<LineageListResponse>
const detail = (id: string, params = '') => readLineageFixture(`/api/lineage/inquiries/${id}${params}`) as Promise<LineageDetailResponse>
const METADATA = ['inquiry_id', 'agent_id', 'title', 'state', 'phase', 'visibility', 'created_at', 'updated_at'].sort()
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

describe('local generated lineage read API', () => {
  it('loads one-agent metadata through the default wrapper without backend transport', async () => {
    const response = await getLineageInquiries()
    expect(response).toEqual(await list('?agent_id=alchemist&limit=50&offset=0'))
    expect(response.status).toBe('ok')
    expect(response.total).toBe(4)
    expect(response.limit).toBe(50)
    expect(response.offset).toBe(0)
    for (const inquiry of response.inquiries) {
      expect(inquiry.agent_id).toBe('alchemist')
      expect(inquiry.inquiry_id).toMatch(UUID)
      expect(Object.keys(inquiry).sort()).toEqual(METADATA)
      expect(inquiry.phase).toBe(0)
      expect(inquiry.visibility).toBe('owner')
    }
    expect(response.inquiries.map(inquiry => inquiry.state)).toContain('paused')
  })
  it('reads full lifecycle detail separately with stable fill, proposal, order, and position links', async () => {
    const response = await getLineageInquiries()
    const histories = await Promise.all(response.inquiries.map(inquiry => getLineageInquiry(inquiry.inquiry_id)))
    const completed = histories.find(history => history.fills.length > 0)!
    expect(completed).toBeTruthy()
    expect(completed.orders).toHaveLength(2)
    expect(completed.fills).toHaveLength(4)
    expect(completed.proposals).toHaveLength(2)
    expect(completed.positions).toHaveLength(1)
    expect(completed.orders.map(order => order.status)).toEqual(['filled', 'filled'])
    expect(completed.proposals.every(proposal => proposal.review_status === 'approved')).toBe(true)
    expect(completed.positions[0]).toMatchObject({ qty: 0, status: 'closed', gross_realized_pnl: '50', fees: null, market_value: null, unrealized_pnl: null, mark_status: 'unavailable' })
    expect(completed.reviews).toHaveLength(1)
    for (const fill of completed.fills) {
      expect(fill.fill_id).toMatch(UUID)
      expect(fill.authority).toBe('mock_broker')
      expect(completed.orders.some(order => order.order_id === fill.order_id)).toBe(true)
      expect(completed.proposals.some(proposal => proposal.proposal_id === fill.proposal_id)).toBe(true)
      expect(fill.position_id).toBe(completed.positions[0].position_id)
    }
    expect(completed.events.some(event => event.kind === 'order_issue' && (event.payload as { category?: string }).category === 'submission_unknown')).toBe(true)
    expect(completed.events.some(event => (event.payload as { status?: string }).status === 'partially_filled')).toBe(true)
    expect(completed.events.every(event => UUID.test(event.event_id))).toBe(true)
  })
  it('preserves open, paused, and revisited no-trade inquiries without manufacturing empty holdings or actions', async () => {
    const response = await list()
    const histories = await Promise.all(response.inquiries.map(inquiry => detail(inquiry.inquiry_id)))
    const noTrade = histories.filter(history => history.proposals.length === 0)
    expect(noTrade).toHaveLength(3)
    expect(noTrade.some(history => history.inquiry.state === 'paused')).toBe(true)
    expect(noTrade.some(history => history.events.some(event => event.kind === 'inquiry_revisited'))).toBe(true)
    for (const history of noTrade) {
      expect(history.orders).toEqual([])
      expect(history.fills).toEqual([])
      expect(history.positions).toEqual([])
      expect(history.reviews).toEqual([])
    }
  })
  it('bounds list pagination, preserves totals, and supplies metadata only', async () => {
    const first = await getLineageInquiries('alchemist', 1, 0)
    const second = await getLineageInquiries('alchemist', 2, 1)
    const all = await list()
    expect(first.inquiries).toEqual(all.inquiries.slice(0, 1))
    expect(second.inquiries).toEqual(all.inquiries.slice(1, 3))
    expect(second.total).toBe(4)
    const beyond = await getLineageInquiries('alchemist', 50, 2147483647)
    expect(beyond).toMatchObject({ inquiries: [], total: 4, limit: 50, offset: 2147483647 })
  })
  it('returns fresh clones through both reader boundaries, including nested structures and payloads', async () => {
    const first = await getLineageInquiries()
    const id = first.inquiries[0].inquiry_id
    const original = await getLineageInquiry(id)
    const mutated = await getLineageInquiry(id)
    first.inquiries[0].title = 'consumer mutation'
    mutated.inquiry.title = 'consumer mutation'
    mutated.proposals[0].structure.limit_price = '999'
    mutated.entries[0].content = 'consumer mutation'
    mutated.events[0].payload = { private: 'consumer mutation' }
    mutated.fills.splice(0)
    expect(await getLineageInquiry(id)).toEqual(original)
    expect((await getLineageInquiries()).inquiries[0].title).not.toBe('consumer mutation')
    const resolved = await readFixture(`/api/lineage/inquiries/${id}`) as LineageDetailResponse
    expect(resolved).toEqual(original)
  })
  it.each([
    '/api/lineage/unknown', '/api/lineage/inquiries/private/not-a-uuid', '/api/lineage/inquiries/not-a-uuid',
    '/api/lineage/inquiries?limit=0', '/api/lineage/inquiries?limit=51', '/api/lineage/inquiries?limit=true',
    '/api/lineage/inquiries?limit=1.5', '/api/lineage/inquiries?limit=%2B1', '/api/lineage/inquiries?limit=%201',
    '/api/lineage/inquiries?limit=١', '/api/lineage/inquiries?offset=-1', '/api/lineage/inquiries?offset=2147483648',
    '/api/lineage/inquiries?offset=0.0', '/api/lineage/inquiries?limit=99999999999999999999',
    '/api/lineage/inquiries?limit=1&limit=2', '/api/lineage/inquiries?agent_id=alchemist&agent_id=siren',
    '/api/lineage/inquiries?agent_id=siren', '/api/lineage/inquiries?agent_id=', '/api/lineage/inquiries?operator=true',
    '/api/lineage/inquiries?viewer_agent_id=siren', '/api/lineage/inquiries?phase=3', '/api/lineage/inquiries?unknown=1',
    '/api/lineage/inquiries#private', '/api/lineage/inquiries?offset=1%0A',
  ])('rejects unsupported or impersonating reads %s without transport', async path => {
    await expect(readLineageFixture(path)).rejects.toThrow()
    await expect(Promise.resolve().then(() => readFixture(path))).rejects.toThrow()
  })
  it('reports missing valid IDs rather than manufacturing an empty detail and rejects extra detail parameters', async () => {
    await expect(detail('00000000-0000-4000-8000-000000000000')).rejects.toThrow('Lineage inquiry not found')
    const response = await list()
    const id = response.inquiries[0].inquiry_id
    for (const params of ['?limit=1', '?offset=0', '?operator=true', '?phase=3', '?viewer_agent_id=siren', '?agent_id=siren']) {
      await expect(detail(id, params)).rejects.toThrow()
    }
  })
  it('contains only explicit shared records, with no imported journals, memory, credentials, or account fields', async () => {
    const response = await list()
    for (const inquiry of response.inquiries) {
      const history = await detail(inquiry.inquiry_id)
      for (const key of ['journal', 'memories', 'episodes', 'checkpoint', 'api_key', 'authorization', 'account']) expect(history).not.toHaveProperty(key)
      expect(history.truncated).toBe(false)
      for (const category of ['entries', 'proposals', 'orders', 'fills', 'positions', 'reviews', 'events'] as const) expect(history[category].length).toBeLessThanOrEqual(100)
    }
  })
})

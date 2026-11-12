import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InquiryHistory from '../src/views/InquiryHistory'
import { getLineageInquiries, getLineageInquiry } from '../src/api'
import type { InquiryMetadata, LineageDetailResponse, LineageListResponse, OptionStructure } from '../src/lineage/contracts'

vi.mock('../src/api', () => ({ IS_PREVIEW: true, getLineageInquiries: vi.fn(), getLineageInquiry: vi.fn() }))
const ID = '12345678-1234-4234-8234-123456789abc'
const OTHER = '22345678-1234-4234-8234-123456789abc'
const TIME = '2026-01-02T12:00:00Z'
const inquiry = (id = ID, title = 'Wait for a clearer question'): InquiryMetadata => ({
  inquiry_id: id, agent_id: 'alchemist', title, state: 'open', phase: 0, visibility: 'owner', created_at: TIME, updated_at: TIME,
})
const list = (): LineageListResponse => ({ status: 'ok', inquiries: [inquiry(), { ...inquiry(OTHER, 'Liquidity question'), state: 'paused' }], total: 2, limit: 50, offset: 0 })
const detail = (id = ID): LineageDetailResponse => ({ status: 'ok', inquiry: inquiry(id), entries: [], proposals: [], orders: [], fills: [], positions: [], reviews: [], events: [], truncated: false })
const structure: OptionStructure = { symbol: 'DEMO270115C00100000', underlying: 'DEMO', expiry: '2027-01-15', option_type: 'call', strike: '100', side: 'buy', intent: 'open', qty: 2, order_type: 'limit', limit_price: '2', multiplier: 100 }
function trading(): LineageDetailResponse {
  return { ...detail(), entries: [
    { entry_id: 'entry-1', kind: 'observation', content: 'An explicitly recorded observation.', source: 'external', created_at: TIME },
    { entry_id: 'entry-2', kind: 'interpretation', content: 'An uncertain possible explanation.', source: 'agent', created_at: TIME },
  ], proposals: [{ proposal_id: 'proposal-1', inquiry_id: ID, agent_id: 'alchemist', queue_id: 42, structure, thesis: 'Tentative thesis', horizon: 'Two weeks', uncertainty: 'Could be wrong', review_status: 'approved' }],
  orders: [{ order_id: 'order-1', proposal_id: 'proposal-1', inquiry_id: ID, agent_id: 'alchemist', queue_id: 42, client_order_id: 'client-1', broker_order_id: 'broker-1', broker: 'mock', status: 'partially_filled', sync_state: 'unavailable', broker_revision: 2, qty: 2, filled_qty: 1, structure, created_at: TIME, updated_at: TIME }],
  fills: [{ fill_id: 'fill-1', broker_fill_id: 'broker-fill-1', order_id: 'order-1', proposal_id: 'proposal-1', inquiry_id: ID, position_id: 'position-1', agent_id: 'alchemist', qty: 1, price: '1.25', side: 'buy', created_at: TIME, authority: 'mock_broker' }],
  positions: [{ position_id: 'position-1', agent_id: 'alchemist', symbol: structure.symbol, qty: 1, average_entry_price: '1.25', gross_realized_pnl: '0', market_value: null, unrealized_pnl: null, fees: null, mark_status: 'unavailable', status: 'open', multiplier: 100 }],
  events: [{ event_id: 'event-1', kind: 'order_snapshot_applied', authority: 'mock_broker', created_at: TIME, payload: { status: 'partially_filled', filled_qty: 1 } }],
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
beforeEach(() => {
  vi.mocked(getLineageInquiries).mockReset().mockResolvedValue(list())
  vi.mocked(getLineageInquiry).mockReset().mockImplementation(async id => detail(id))
})
async function selectFirst() {
  render(<InquiryHistory />)
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Wait for a clearer question' }))
  await screen.findByRole('region', { name: 'Inquiry notes' })
}
const region = (name: string) => within(screen.getByRole('region', { name }))
const disabled = (name: string) => (screen.getByRole('button', { name }) as HTMLButtonElement).disabled

describe('Inquiry History read-only pilot', () => {
  it('loads only one-agent metadata until a detail is selected and labels the mock example', async () => {
    render(<InquiryHistory />)
    await screen.findByRole('button', { name: 'Wait for a clearer question' })
    expect(screen.getByRole('heading', { level: 1, name: 'Inquiry History' })).toBeTruthy()
    expect(screen.getByText('Alchemist · Mock lifecycle example')).toBeTruthy()
    expect(screen.getByText('Select an inquiry to read its history.')).toBeTruthy()
    expect(screen.getByText(/Paused · Updated/)).toBeTruthy()
    expect(getLineageInquiries).toHaveBeenCalledExactlyOnceWith('alchemist', 50, 0)
    expect(getLineageInquiry).not.toHaveBeenCalled()
    expect(screen.queryByRole('combobox')).toBeNull()
  })
  it('keeps no notes, proposal, order, fill, holding, review, and event distinct without forced actions', async () => {
    await selectFirst()
    expect(region('Inquiry notes').getByText('No inquiry notes recorded.')).toBeTruthy()
    expect(region('Optional proposals').getByText('No trade proposed.')).toBeTruthy()
    expect(region('Mock orders').getByText('No order recorded.')).toBeTruthy()
    expect(region('Individual fills').getByText('No broker-confirmed fills recorded.')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText(/No fill-linked position recorded/)).toBeTruthy()
    expect(region('Optional later reviews').getByText('No later review recorded. Reviews are optional.')).toBeTruthy()
    expect(region('Event timeline').getByText('No lifecycle events recorded.')).toBeTruthy()
    expect(screen.getByText(/Phase 0 · Owner visibility/)).toBeTruthy()
    expect(getLineageInquiry).toHaveBeenCalledExactlyOnceWith(ID, 'alchemist')
    expect(screen.queryByRole('button', { name: /approve|execute|cancel|broker|login|settings|wake|trade/i })).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })
  it('separates observation, interpretation, queue review, broker state, synchronization, and confirmed fills', async () => {
    vi.mocked(getLineageInquiry).mockResolvedValue(trading())
    await selectFirst()
    expect(region('Inquiry notes').getByRole('heading', { name: 'Observation' })).toBeTruthy()
    expect(region('Inquiry notes').getByRole('heading', { name: 'Interpretation' })).toBeTruthy()
    expect(region('Inquiry notes').getByText(/Observations and interpretations remain separate, with recorded sources and times/)).toBeTruthy()
    expect(region('Inquiry notes').getByText(/Source: External/)).toBeTruthy()
    expect(region('Optional proposals').getByText(/Existing queue review:/).textContent).toContain('Approved')
    expect(region('Optional proposals').getByText('Uncertainty: Could be wrong')).toBeTruthy()
    expect(region('Mock orders').getByText('Partially filled')).toBeTruthy()
    expect(region('Mock orders').getByText('Unavailable')).toBeTruthy()
    expect(region('Mock orders').getByText(/Last broker-confirmed state and fills are retained/)).toBeTruthy()
    expect(region('Individual fills').getByText('$1.25')).toBeTruthy()
    expect(region('Individual fills').getByText('Mock broker confirmed')).toBeTruthy()
    expect(region('Event timeline').getByText('Order snapshot applied')).toBeTruthy()
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThan(2)
    expect(screen.getByRole('region', { name: 'Scrollable confirmed fills' }).getAttribute('tabindex')).toBe('0')
  })
  it('shows gross realized zero without inventing zero fees or unrealized P&L', async () => {
    vi.mocked(getLineageInquiry).mockResolvedValue(trading())
    await selectFirst()
    expect(region('Positions and gross outcomes').getByText('$0')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText(/Gross, not net of fees/)).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText('Fees: Unavailable · Market mark: Unavailable · Market value: Unavailable · Unrealized P&L: Unavailable')).toBeTruthy()
  })
  it.each(['pending', 'approved', 'rejected'] as const)('renders %s queue review independently of accepted mock order with no holding', async status => {
    const custom = trading()
    custom.proposals[0].review_status = status
    custom.orders[0].status = 'accepted'
    custom.orders[0].sync_state = 'ok'
    custom.orders[0].filled_qty = 0
    custom.fills = []; custom.positions = []
    vi.mocked(getLineageInquiry).mockResolvedValue(custom)
    await selectFirst()
    expect(region('Optional proposals').getByText(/Existing queue review:/).textContent?.toLowerCase()).toContain(status)
    expect(region('Mock orders').getByText('Accepted')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText(/Acceptance alone does not establish a holding/)).toBeTruthy()
  })
  it.each(['pending_submission', 'submission_unknown', 'rejected', 'filled', 'canceled'] as const)('preserves explicit %s order state with failed synchronization', async status => {
    const custom = trading(); custom.orders[0].status = status; custom.orders[0].sync_state = 'failed'
    vi.mocked(getLineageInquiry).mockResolvedValue(custom)
    await selectFirst()
    expect(region('Mock orders').getByText(status.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase()))).toBeTruthy()
    expect(region('Mock orders').getByText('Failed')).toBeTruthy()
    expect(region('Individual fills').getByText('$1.25')).toBeTruthy()
  })
  it('records optional later interpretation without replacing the original thesis', async () => {
    const custom = trading()
    custom.reviews = [{ review_id: 'review-1', content: 'Later explanation remains uncertain.', proposal_id: 'proposal-1', created_at: TIME }]
    custom.positions[0].status = 'closed'; custom.positions[0].qty = 0; custom.positions[0].average_entry_price = null; custom.positions[0].gross_realized_pnl = '25'
    vi.mocked(getLineageInquiry).mockResolvedValue(custom)
    await selectFirst()
    expect(region('Optional proposals').getByText('Thesis: Tentative thesis')).toBeTruthy()
    expect(region('Optional later reviews').getByText('Later explanation remains uncertain.')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText('$25')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText(/Average entry per share: Unavailable/)).toBeTruthy()
  })
  it('shows list failure as unavailable, hides raw errors, and retries only the list', async () => {
    vi.mocked(getLineageInquiries).mockRejectedValueOnce(new Error('secret token /private/db'))
    render(<InquiryHistory />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText(/secret token/)).toBeNull()
    expect(screen.queryByText('No inquiries recorded on this page.')).toBeNull()
    expect(disabled('Next inquiries')).toBe(true)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry inquiries' }))
    await screen.findByRole('button', { name: 'Wait for a clearer question' })
    expect(getLineageInquiry).not.toHaveBeenCalled()
  })
  it('keeps the list available during detail failure and retries the same detail only', async () => {
    vi.mocked(getLineageInquiry).mockRejectedValueOnce(new Error('private database failure'))
    render(<InquiryHistory />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Wait for a clearer question' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('No trade proposed.')).toBeNull()
    expect(screen.queryByText(/private database/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Liquidity question' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Retry history' }))
    await screen.findByText('No trade proposed.')
    expect(getLineageInquiries).toHaveBeenCalledTimes(1)
    expect(getLineageInquiry).toHaveBeenLastCalledWith(ID, 'alchemist')
  })
  it.each(['success', 'failure'])('ignores stale detail %s after switching inquiries', async outcome => {
    const old = deferred<LineageDetailResponse>()
    vi.mocked(getLineageInquiry).mockReturnValueOnce(old.promise)
    render(<InquiryHistory />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Wait for a clearer question' }))
    expect(screen.getByText('Loading inquiry history…')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Liquidity question' }))
    await screen.findByText('No trade proposed.')
    await act(async () => { if (outcome === 'success') old.resolve(trading()); else old.reject(new Error('stale secret')) })
    expect(screen.queryByText('Tentative thesis')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('button', { name: 'Liquidity question' }).getAttribute('aria-pressed')).toBe('true')
  })
  it('pages metadata by fifty, resets selected detail and disables controls while loading', async () => {
    const first = { ...list(), total: 51, inquiries: Array.from({ length: 50 }, (_, index) => inquiry(`test-id-${index}`, `Question ${index}`)) }
    vi.mocked(getLineageInquiries).mockResolvedValueOnce(first)
    render(<InquiryHistory />)
    const user = userEvent.setup()
    await screen.findByText('1–50 of 51')
    await user.click(screen.getByRole('button', { name: 'Question 0' }))
    await screen.findByText('No trade proposed.')
    const pending = deferred<LineageListResponse>()
    vi.mocked(getLineageInquiries).mockReturnValueOnce(pending.promise)
    await user.click(screen.getByRole('button', { name: 'Next inquiries' }))
    expect(screen.queryByText('No trade proposed.')).toBeNull()
    expect(disabled('Previous inquiries')).toBe(true)
    expect(disabled('Next inquiries')).toBe(true)
    await act(async () => { pending.resolve({ ...list(), inquiries: [inquiry(OTHER, 'Last question')], total: 51, offset: 50 }) })
    await screen.findByText('51–51 of 51')
    expect(getLineageInquiries).toHaveBeenLastCalledWith('alchemist', 50, 50)
    expect(disabled('Next inquiries')).toBe(true)
    expect(disabled('Previous inquiries')).toBe(false)
    expect(screen.getByText('Select an inquiry to read its history.')).toBeTruthy()
  })
  it('marks bounded detail and metadata truncation, escapes text and handles unknown event payloads safely', async () => {
    vi.mocked(getLineageInquiries).mockResolvedValue({ ...list(), truncated: true })
    const custom = trading(); custom.truncated = true
    custom.entries[0].content = '<script>alert(1)</script>'
    custom.entries[1].content = 'x'.repeat(3000)
    custom.events[0].payload = { source: '<img onerror=alert(1)>', nested: { private: 'not rendered recursively' } }
    vi.mocked(getLineageInquiry).mockResolvedValue(custom)
    await selectFirst()
    expect(screen.getByText(/Inquiry metadata is truncated/)).toBeTruthy()
    expect(screen.getByText(/each record category is limited to 100 items/)).toBeTruthy()
    expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy()
    expect(screen.getByText(/\[text truncated\]/)).toBeTruthy()
    expect(region('Event timeline').getByText(/Source: <img onerror=alert\(1\)> · Nested: Structured record/)).toBeTruthy()
    expect(document.querySelector('script')).toBeNull()
    expect(document.querySelector('img')).toBeNull()
    expect(screen.queryByText(/not rendered recursively/)).toBeNull()
  })
  it('does not round tiny positive or negative known Decimal USD projections to zero', async () => {
    const custom = trading(); custom.fills[0].price = '0.00000000000000000001'; custom.positions[0].gross_realized_pnl = '-0.00000000000000000001'
    vi.mocked(getLineageInquiry).mockResolvedValue(custom)
    await selectFirst()
    expect(region('Individual fills').getByText('<$0.000000000001')).toBeTruthy()
    expect(region('Positions and gross outcomes').getByText('−<$0.000000000001')).toBeTruthy()
  })
  it('cleans up both pending reads on unmount', async () => {
    const pending = deferred<LineageDetailResponse>()
    vi.mocked(getLineageInquiry).mockReturnValueOnce(pending.promise)
    const mounted = render(<InquiryHistory />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Wait for a clearer question' }))
    mounted.unmount()
    await act(async () => { pending.reject(new Error('late')) })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('heading')).toBeNull()
    const pendingList = deferred<LineageListResponse>()
    vi.mocked(getLineageInquiries).mockReturnValueOnce(pendingList.promise)
    const next = render(<InquiryHistory />); next.unmount()
    await act(async () => { pendingList.resolve(list()) })
    await waitFor(() => expect(screen.queryByRole('heading')).toBeNull())
  })
})

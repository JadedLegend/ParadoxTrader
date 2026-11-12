import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Costs from '../src/views/Costs'
import { getUsageSummary, getUsageEvents } from '../src/api'
import { readUsageFixture } from '../src/usage/fixture'
import type { UsageEventsResponse, UsageSummaryResponse } from '../src/usage/contracts'

vi.mock('../src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../src/api')>(), getUsageSummary: vi.fn(), getUsageEvents: vi.fn(),
}))
const summary = (agent?: string) => readUsageFixture(`/api/usage/summary${agent ? `?agent_id=${agent}` : ''}`) as UsageSummaryResponse
const events = (agent?: string, limit = 50, offset = 0) => readUsageFixture(`/api/usage/events?limit=${limit}&offset=${offset}${agent ? `&agent_id=${agent}` : ''}`) as UsageEventsResponse
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function paged(offset = 0): UsageEventsResponse {
  const first = events().events[0]
  return { ...events(), total: 55, offset, events: Array.from({ length: offset === 0 ? 50 : 5 }, (_, index) => ({ ...first, event_id: `page-event-${offset + index}` })) }
}
beforeEach(() => {
  vi.mocked(getUsageSummary).mockReset().mockImplementation(async agent => summary(agent))
  vi.mocked(getUsageEvents).mockReset().mockImplementation(async (agent, limit = 50, offset = 0) => events(agent, limit, offset))
})
async function renderCosts() {
  render(<Costs />)
  await screen.findByRole('region', { name: 'Reported subtotal' })
  await screen.findByRole('region', { name: 'Scrollable request metadata' })
  return userEvent.setup()
}
const agentSelect = () => screen.getByRole('combobox', { name: 'Agent' })
const buttonDisabled = (name: string) => (screen.getByRole('button', { name }) as HTMLButtonElement).disabled

describe('Operating costs read-only view', () => {
  it('labels simulated examples and distinguishes subtotals from incomplete operating costs', async () => {
    await renderCosts()
    expect(screen.getByRole('heading', { name: 'Operating costs', level: 1 })).toBeTruthy()
    expect(screen.getByText('Simulated request examples — no actual spend is shown.')).toBeTruthy()
    expect(screen.getByText(/subscriptions, data-feed charges, infrastructure, and final account invoices are not included/)).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Reported subtotal' })).getByText('$0.002')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Estimated token-only subtotal' })).getByText('$0.001')).toBeTruthy()
    expect(screen.getByText('3 of 5 requests have provider-reported or estimated costs; 2 unknown.')).toBeTruthy()
    expect(screen.getByText('Usage reported for 3 of 5 requests; 2 have unknown usage.')).toBeTruthy()
    expect(screen.getByText(/4 successful · 1 failed · Retries counted separately/)).toBeTruthy()
    expect(screen.getByText(/Known token subtotals only — partial coverage/)).toBeTruthy()
    expect(getUsageSummary).toHaveBeenCalledExactlyOnceWith(undefined)
    expect(getUsageEvents).toHaveBeenCalledExactlyOnceWith(undefined, 50, 0)
  })

  it('renders unknown and valid zero differently, with failed outcomes and nullable tokens', async () => {
    await renderCosts()
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    const zero = rows.find(row => row.textContent?.includes('The Siren'))!
    expect(within(zero).getByText('$0')).toBeTruthy()
    expect(within(zero).getByText('Reported · provider total')).toBeTruthy()
    expect(within(zero).getAllByText('0')).toHaveLength(4)
    const failed = rows.find(row => row.textContent?.includes('http_error'))!
    expect(within(failed).getByText('Attempt 2')).toBeTruthy()
    expect(within(failed).getByText('HTTP 429')).toBeTruthy()
    expect(within(failed).getAllByText('Unknown')).toHaveLength(5)
    expect(within(failed).queryByText('$0')).toBeNull()
    expect(within(failed).getByText('missing_usage')).toBeTruthy()
    const estimate = rows.find(row => row.textContent?.includes('Estimated · token-only'))!
    expect(within(estimate).getByText(/fixture-only-synthetic-rates-v1/)).toBeTruthy()
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThan(1)
    expect(screen.getByRole('region', { name: 'Scrollable request metadata' }).getAttribute('tabindex')).toBe('0')
  })

  it('filters both read methods using accessible agent labels and resets to offset zero', async () => {
    const user = await renderCosts()
    await user.selectOptions(agentSelect(), 'siren')
    await waitFor(() => expect(getUsageEvents).toHaveBeenLastCalledWith('siren', 50, 0))
    expect(getUsageSummary).toHaveBeenLastCalledWith('siren')
    expect(within(screen.getByRole('region', { name: 'Reported subtotal' })).getByText('$0')).toBeTruthy()
    expect(screen.getByText('1 of 1 requests have provider-reported or estimated costs; 0 unknown.')).toBeTruthy()
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
    await user.selectOptions(agentSelect(), '')
    await screen.findByText('3 of 5 requests have provider-reported or estimated costs; 2 unknown.')
    expect(getUsageSummary).toHaveBeenLastCalledWith(undefined)
  })

  it('shows provider, activity, and agent breakdowns with separate known subtotals', async () => {
    await renderCosts()
    expect(within(screen.getByRole('region', { name: 'By provider' })).getByRole('heading', { name: 'example-research' })).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'By activity' })).getByRole('heading', { name: 'council' })).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'By agent' })).getByRole('heading', { name: 'The Tempest' })).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'By provider' })).getAllByText(/Reported subtotal:/).length).toBe(2)
  })

  it('distinguishes an empty recorded filter from unknown costs or a load error', async () => {
    const user = await renderCosts()
    await user.selectOptions(agentSelect(), 'alchemist')
    await screen.findByText(/No request events recorded for this filter/)
    expect(screen.getByText('No request events on this page.')).toBeTruthy()
    expect(screen.getByText('0 of 0 requests have provider-reported or estimated costs; 0 unknown.')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Reported subtotal' })).getByText('Unknown')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(buttonDisabled('Previous events')).toBe(true)
    expect(buttonDisabled('Next events')).toBe(true)
  })

  it('shows partial nullable token categories without converting unknown subtotals to zero', async () => {
    const custom = summary()
    custom.summary.cached_input_tokens = null
    custom.summary.reasoning_tokens = null
    vi.mocked(getUsageSummary).mockResolvedValueOnce(custom)
    await renderCosts()
    expect(screen.getByText('Input: 1,120 · Output: 530 · Cached input: Unknown · Reasoning: Unknown')).toBeTruthy()
    expect(screen.getByText(/Individual token categories can be missing/)).toBeTruthy()
  })

  it('announces independent loading states while each read can complete separately', async () => {
    const pendingSummary = deferred<UsageSummaryResponse>()
    const pendingEvents = deferred<UsageEventsResponse>()
    vi.mocked(getUsageSummary).mockReturnValueOnce(pendingSummary.promise)
    vi.mocked(getUsageEvents).mockReturnValueOnce(pendingEvents.promise)
    render(<Costs />)
    expect(screen.getAllByRole('status')).toHaveLength(2)
    expect(buttonDisabled('Next events')).toBe(true)
    await act(async () => { pendingEvents.resolve(events()) })
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Loading usage summary…')
    await act(async () => { pendingSummary.resolve(summary()) })
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('reports a bounded summary error without hiding events or presenting zero costs', async () => {
    vi.mocked(getUsageSummary).mockRejectedValueOnce(new Error('/private/price-secret.json'))
    render(<Costs />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    await screen.findByRole('table')
    expect(screen.queryByText(/private\/price-secret/)).toBeNull()
    expect(screen.queryByText(/No request events recorded/)).toBeNull()
    expect(screen.queryByRole('region', { name: 'Reported subtotal' })).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry summary' }))
    await screen.findByRole('region', { name: 'Reported subtotal' })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(getUsageEvents).toHaveBeenCalledTimes(1)
  })

  it('reports an independent events error without calling it an empty ledger or hiding summary', async () => {
    vi.mocked(getUsageEvents).mockRejectedValueOnce(new Error('raw provider failure secret'))
    render(<Costs />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    await screen.findByRole('region', { name: 'Reported subtotal' })
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('No request events on this page.')).toBeNull()
    expect(screen.queryByText(/raw provider failure secret/)).toBeNull()
    expect(buttonDisabled('Next events')).toBe(true)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry events' }))
    await screen.findByRole('table')
    expect(getUsageSummary).toHaveBeenCalledTimes(1)
  })

  it('discards old summary successes and old events failures after changing the agent', async () => {
    const pendingSummary = deferred<UsageSummaryResponse>()
    const pendingEvents = deferred<UsageEventsResponse>()
    vi.mocked(getUsageSummary).mockReturnValueOnce(pendingSummary.promise)
    vi.mocked(getUsageEvents).mockReturnValueOnce(pendingEvents.promise)
    render(<Costs />)
    await userEvent.setup().selectOptions(agentSelect(), 'siren')
    await screen.findByText('1 of 1 requests have provider-reported or estimated costs; 0 unknown.')
    await act(async () => {
      pendingSummary.resolve(summary())
      pendingEvents.reject(new Error('stale private error'))
    })
    expect(screen.queryByText('3 of 5 requests have provider-reported or estimated costs; 2 unknown.')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
  })

  it('cannot restore old events or summary errors after rapid filter changes', async () => {
    const oldSummary = deferred<UsageSummaryResponse>()
    const oldEvents = deferred<UsageEventsResponse>()
    vi.mocked(getUsageSummary).mockReturnValueOnce(oldSummary.promise)
    vi.mocked(getUsageEvents).mockReturnValueOnce(oldEvents.promise)
    render(<Costs />)
    const user = userEvent.setup()
    await user.selectOptions(agentSelect(), 'tempest')
    await user.selectOptions(agentSelect(), 'oracle')
    await screen.findByText('1 of 2 requests have provider-reported or estimated costs; 1 unknown.')
    await act(async () => {
      oldSummary.reject(new Error('stale'))
      oldEvents.resolve(events())
    })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(within(screen.getByRole('table')).queryByText('The Siren')).toBeNull()
    expect((agentSelect() as HTMLSelectElement).value).toBe('oracle')
    expect(getUsageEvents).toHaveBeenLastCalledWith('oracle', 50, 0)
  })

  it('bounds previous/next pagination and reads pages independently of the summary', async () => {
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged())
    const user = await renderCosts()
    expect(buttonDisabled('Previous events')).toBe(true)
    expect(buttonDisabled('Next events')).toBe(false)
    expect(screen.getByText('1–50 of 55')).toBeTruthy()
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged(50))
    await user.click(screen.getByRole('button', { name: 'Next events' }))
    await screen.findByText('51–55 of 55')
    expect(getUsageEvents).toHaveBeenLastCalledWith(undefined, 50, 50)
    expect(buttonDisabled('Next events')).toBe(true)
    expect(buttonDisabled('Previous events')).toBe(false)
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged())
    await user.click(screen.getByRole('button', { name: 'Previous events' }))
    await screen.findByText('1–50 of 55')
    expect(getUsageEvents).toHaveBeenLastCalledWith(undefined, 50, 0)
    expect(getUsageSummary).toHaveBeenCalledTimes(1)
  })

  it('hides prior-page rows and bounds controls during loading and errors; retry preserves requested offset', async () => {
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged())
    const user = await renderCosts()
    const pending = deferred<UsageEventsResponse>()
    vi.mocked(getUsageEvents).mockReturnValueOnce(pending.promise)
    await user.click(screen.getByRole('button', { name: 'Next events' }))
    expect(screen.queryByRole('table')).toBeNull()
    expect(buttonDisabled('Previous events')).toBe(true)
    expect(buttonDisabled('Next events')).toBe(true)
    await act(async () => { pending.reject(new Error('offline')) })
    expect(screen.getByRole('alert')).toBeTruthy()
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged(50))
    await user.click(screen.getByRole('button', { name: 'Retry events' }))
    await screen.findByText('51–55 of 55')
    expect(getUsageEvents).toHaveBeenLastCalledWith(undefined, 50, 50)
    await user.selectOptions(agentSelect(), 'tempest')
    await waitFor(() => expect(getUsageEvents).toHaveBeenLastCalledWith('tempest', 50, 0))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('ignores a stale page response after selecting a different agent', async () => {
    vi.mocked(getUsageEvents).mockResolvedValueOnce(paged())
    const user = await renderCosts()
    const oldPage = deferred<UsageEventsResponse>()
    vi.mocked(getUsageEvents).mockReturnValueOnce(oldPage.promise)
    await user.click(screen.getByRole('button', { name: 'Next events' }))
    await user.selectOptions(agentSelect(), 'siren')
    await screen.findByText('1 of 1 requests have provider-reported or estimated costs; 0 unknown.')
    await act(async () => { oldPage.resolve(paged(50)) })
    expect(screen.queryByText('51–55 of 55')).toBeNull()
    expect(screen.getByText('1–1 of 1')).toBeTruthy()
    expect(buttonDisabled('Previous events')).toBe(true)
  })

  it('displays very small known USD amounts without rounding them to zero', async () => {
    const smallSummary = summary()
    smallSummary.summary.reported_cost_usd = '0.0000012'
    const smallEvents = events()
    smallEvents.events[0].cost_usd = '0.0000012'
    vi.mocked(getUsageSummary).mockResolvedValueOnce(smallSummary)
    vi.mocked(getUsageEvents).mockResolvedValueOnce(smallEvents)
    await renderCosts()
    expect(within(screen.getByRole('region', { name: 'Reported subtotal' })).getByText('$0.0000012')).toBeTruthy()
    expect(within(screen.getByRole('table')).getByText('$0.0000012')).toBeTruthy()
  })

  it('reads source and as-of from the real ledger pricing snapshot without flattened fields', async () => {
    const snapshotEvents = events()
    const estimated = snapshotEvents.events[2]
    delete estimated.pricing_source
    delete estimated.pricing_as_of
    estimated.pricing_snapshot!.source = 'operator-local-rates-v1'
    estimated.pricing_snapshot!.as_of = '2026-02-03'
    vi.mocked(getUsageEvents).mockResolvedValueOnce(snapshotEvents)
    await renderCosts()
    expect(within(screen.getByRole('table')).getByText('operator-local-rates-v1 · as of 2026-02-03')).toBeTruthy()
    expect(within(screen.getByRole('table')).queryByText('Source not recorded')).toBeNull()
    expect(screen.getByRole('table').className).toBe('usage-table')
    expect(screen.getByRole('region', { name: 'Scrollable request metadata' }).className).toBe('usage-table-wrap')
  })

  it('warns when group breakdowns are truncated rather than implying complete categories', async () => {
    vi.mocked(getUsageSummary).mockResolvedValueOnce({ ...summary(), groups_truncated: true })
    await renderCosts()
    expect(screen.getByText(/Breakdowns are limited to 100 groups per category/)).toBeTruthy()
    expect(screen.getByText(/overall summary still covers all matching requests/)).toBeTruthy()
  })

  it('renders metadata literally and exposes no trading, provider, pricing, or scheduler mutation controls', async () => {
    const literal = events()
    literal.events[0].model = '<script>alert(1)</script>'
    literal.events[0].agent_id = null
    literal.events[0].http_status = null
    vi.mocked(getUsageEvents).mockResolvedValueOnce(literal)
    await renderCosts()
    expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy()
    expect(document.querySelector('script')).toBeNull()
    expect(screen.getByText('Unattributed')).toBeTruthy()
    expect(screen.getByText('HTTP status unknown')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /start|connect|fund|trade|wake|trigger|save|price|allowance|quota/i })).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(screen.queryByText(/P&L|HRV balance|paper balance/i)).toBeNull()
  })

  it('cancels both pending reads on unmount without restoring state', async () => {
    const pendingSummary = deferred<UsageSummaryResponse>()
    const pendingEvents = deferred<UsageEventsResponse>()
    vi.mocked(getUsageSummary).mockReturnValueOnce(pendingSummary.promise)
    vi.mocked(getUsageEvents).mockReturnValueOnce(pendingEvents.promise)
    const mounted = render(<Costs />)
    mounted.unmount()
    await act(async () => { pendingSummary.resolve(summary()); pendingEvents.reject(new Error('late')) })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('heading')).toBeNull()
  })
})

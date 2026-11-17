import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../src/api'
import Forum from '../src/views/Forum'
import Inbox from '../src/views/Inbox'
import TradeQueue from '../src/views/TradeQueue'
import Config from '../src/views/Config'
import InquiryHistory from '../src/views/InquiryHistory'
import WakeChoices from '../src/views/WakeChoices'
import Library from '../src/views/Library'
import Rehearsal from '../src/views/Rehearsal'

vi.mock('../src/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  IS_PREVIEW: false, IS_PRIVATE_HOST: true,
  getRehearsalRuns: vi.fn(), getRehearsalRun: vi.fn(), getRehearsalJobs: vi.fn(), getRehearsalRequests: vi.fn(),
  getRehearsalRecord: vi.fn(), getRehearsalDecision: vi.fn(),
  getForum: vi.fn(), postToForum: vi.fn(), getThreads: vi.fn(), getSelfDefinition: vi.fn(),
  getInbox: vi.fn(), sendDM: vi.fn(), getQueue: vi.fn(), approveTrade: vi.fn(), rejectTrade: vi.fn(),
  getConfig: vi.fn(), updateConfig: vi.fn(), setCountdown: vi.fn(),
  getLineageInquiries: vi.fn(), getLineageInquiry: vi.fn(),
  getLibraryDocuments: vi.fn(), searchLibrary: vi.fn(), getLibrarySection: vi.fn(),
}))

// Every read or write a legacy page could make. On the private host none may be called.
const LEGACY = ['getForum', 'postToForum', 'getThreads', 'getSelfDefinition', 'getInbox', 'sendDM', 'getQueue',
  'approveTrade', 'rejectTrade', 'getConfig', 'updateConfig', 'setCountdown', 'getLineageInquiries', 'getLineageInquiry'] as const

beforeEach(() => {
  for (const name of LEGACY) vi.mocked(api[name]).mockReset().mockRejectedValue(new Error(`${name} must not be called`))
  vi.mocked(api.getRehearsalRuns).mockReset().mockResolvedValue({ runs: [], total: 0, limit: 20, offset: 0 })
  vi.mocked(api.getLibraryDocuments).mockReset().mockResolvedValue({ status: 'ok', documents: [], total: 0, limit: 50, offset: 0 } as never)
})

function renderPage(page: ReactElement) {
  return render(<MemoryRouter>{page}</MemoryRouter>)
}

const PAGES: [string, () => ReactElement, string, RegExp][] = [
  ['Forum', () => <Forum />, 'Community', /do not post to a shared forum/],
  ['Inbox', () => <Inbox />, 'Messages', /do not include direct messages/],
  ['TradeQueue', () => <TradeQueue />, 'Trade Queue', /No orders are placed from this site/],
  ['Config', () => <Config />, 'Configuration', /changed on the server, not here/],
  ['InquiryHistory', () => <InquiryHistory />, 'Inquiry History', /serves no inquiry lineage records/],
]

describe('pages without a data source on the private host', () => {
  it.each(PAGES)('%s explains itself, links to session pages, and makes no request', async (_name, page, title, explanation) => {
    renderPage(page())
    expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
    const note = screen.getByRole('note')
    expect(within(note).getByText('Not available on this host')).toBeTruthy()
    expect(within(note).getByText(explanation)).toBeTruthy()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
    expect(screen.queryAllByRole('combobox')).toHaveLength(0)
    expect(screen.getByRole('link', { name: 'Open Sessions' }).getAttribute('href')).toBe('/rehearsal')
    expect(screen.getByRole('link', { name: 'Open Journals' }).getAttribute('href')).toBe('/journals')
    expect(screen.queryByRole('alert')).toBeNull()
    await Promise.resolve()
    for (const name of LEGACY) expect(api[name]).not.toHaveBeenCalled()
  })

  it('Wake Choices points to the decision context recorded under Sessions', () => {
    renderPage(<WakeChoices />)
    expect(screen.getByRole('heading', { level: 1, name: 'Wake Choices' })).toBeTruthy()
    expect(screen.getByText(/Read decision context/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open Sessions' }).getAttribute('href')).toBe('/rehearsal')
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.queryByRole('dialog')).toBeNull()
    for (const name of LEGACY) expect(api[name]).not.toHaveBeenCalled()
  })
})

describe('pages that read on the private host', () => {
  it('Library says its source text is bundled and read in the browser', async () => {
    renderPage(<Library />)
    expect(screen.getByText(/Imported source text bundled with this site, read in your browser/)).toBeTruthy()
    expect(await screen.findByText('0 documents in the library')).toBeTruthy()
    expect(api.getLibraryDocuments).toHaveBeenCalledOnce()
  })

  it('Sessions says the server adds the operator token, not the browser', async () => {
    renderPage(<Rehearsal />)
    expect(screen.getByText(/Owner-protected reads: the server adds the operator token; your browser never holds it or any model key\./)).toBeTruthy()
    expect(screen.queryByText(/deliberately integrated operator authentication/)).toBeNull()
    expect(api.getRehearsalRuns).toHaveBeenCalled()
  })
})

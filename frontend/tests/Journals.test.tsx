import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Journals from '../src/views/Journals'
import { getJournalNotes, getRehearsalRuns, getRehearsalRecord, getWitnessAccounts } from '../src/api'
import { readJournalFixture } from '../src/journals/client'
import rawFixture from '../src/journals/fixture.json'
import type { JournalFixture, JournalParams, JournalResponse, WitnessParams, WitnessResponse } from '../src/journals/contracts'
vi.mock('../src/api', () => ({ IS_PREVIEW: true, getJournalNotes: vi.fn(), getRehearsalRuns: vi.fn(), getRehearsalRecord: vi.fn(), getWitnessAccounts: vi.fn() }))
const fixture = rawFixture as unknown as JournalFixture
const ID = fixture.runs[0].run_id
const OTHER = '22222222-2222-4222-8222-222222222222'
const digest = fixture.journals[ID].tempest!.find(note => note.note_kind === 'distillation')!
function query(params: object) { return new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])) }
const notes = async (id: string, params: JournalParams): Promise<JournalResponse> => readJournalFixture(`/api/rehearsals/${id}/journals?${query(params)}`) as Promise<JournalResponse>
const accounts = async (id: string, params: WitnessParams = {}): Promise<WitnessResponse> => readJournalFixture(`/api/rehearsals/${id}/witness?${query(params)}`) as Promise<WitnessResponse>
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
beforeEach(() => {
  vi.mocked(getRehearsalRuns).mockReset().mockResolvedValue({ runs: fixture.runs, total: fixture.runs.length, limit: 20, offset: 0 })
  vi.mocked(getJournalNotes).mockReset().mockImplementation((id, params) => notes(id, params as JournalParams))
  vi.mocked(getWitnessAccounts).mockReset().mockImplementation((id, params) => accounts(id, params as WitnessParams))
  vi.mocked(getRehearsalRecord).mockReset().mockRejectedValue(new Error('unavailable original source'))
})
const owner = () => screen.getByRole('combobox', { name: 'Owner' })
const state = () => screen.getByRole('combobox', { name: 'Source state' })
async function loaded() { render(<Journals />); await screen.findByRole('region', { name: 'Selected-owner journal notes' }) }
async function idea() {
  await userEvent.setup().click(screen.getByRole('tab', { name: 'Idea' }))
  await screen.findByRole('button', { name: `Read original note #${digest.id}` })
}
const detail = () => within(screen.getByRole('region', { name: 'Selected original' }))
describe('quiet optional read-only Journals', () => {
  it('shows seven owners and four destinations, no mutations, and no automatic original or witness bodies', async () => {
    await loaded()
    expect(screen.getByRole('heading', { name: 'Journals', level: 1 })).toBeTruthy()
    expect(screen.getByText('Scripted local examples · no live activity')).toBeTruthy()
    expect(within(owner()).getAllByRole('option')).toHaveLength(7)
    expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Trading', 'Idea', 'Orientation', 'Unclassified'])
    expect(screen.queryByRole('button', { name: /launch|write|distill|release|login|start|trade/i })).toBeNull()
    expect(getWitnessAccounts).not.toHaveBeenCalled()
    expect(getRehearsalRecord).not.toHaveBeenCalled()
    expect(vi.mocked(getJournalNotes).mock.calls.every(([, params]) => params.note_id === undefined)).toBe(true)
  })
  it('reads an explicit agent-authored digest, then follows a preserved released original even through active filtering', async () => {
    await loaded(); await idea()
    const user = userEvent.setup()
    await user.selectOptions(state(), 'active')
    await screen.findByRole('button', { name: `Read original note #${digest.id}` })
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByRole('region', { name: 'Selected original' })
    expect(detail().getByText(`Agent-authored distillation #${digest.id}`)).toBeTruthy()
    const id = digest.source_ids[0]
    await user.click(detail().getByRole('button', { name: `Read source note #${id}` }))
    await waitFor(() => expect(detail().getByRole('heading', { name: `Original note #${id}` })).toBeTruthy())
    expect(detail().getByText(/Released · preserved original/)).toBeTruthy()
    expect(detail().getByText(fixture.journals[ID].tempest!.find(note => note.id === id)!.content)).toBeTruthy()
    expect(getJournalNotes).toHaveBeenLastCalledWith(ID, { agent_id: 'tempest', channel: 'idea', state: 'active', limit: 20, offset: 0, note_id: id })
  })
  it('renders literal markup as text rather than injected HTML, while retaining source IDs and author labels', async () => {
    const literal = '<img src=x onerror=alert(1)> literal <script>do not execute</script>'
    vi.mocked(getJournalNotes).mockImplementation(async (id, params) => {
      const value = await notes(id, params as JournalParams)
      return { ...value, notes: value.notes.map(note => ({ ...note, content: literal })), note: value.note && { ...value.note, content: literal } }
    })
    await loaded(); await idea()
    await userEvent.setup().click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByRole('region', { name: 'Selected original' })
    expect(detail().getByText(literal)).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Selected original' }).querySelector('img,script')).toBeNull()
    expect(detail().getByText(/Author: Tempest/)).toBeTruthy()
    expect(detail().getAllByRole('button', { name: /Read source note/ })).toHaveLength(6)
  })
  it('clears private detail on owner and destination changes and cannot reuse a peer integer ID', async () => {
    await loaded(); await idea()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByRole('region', { name: 'Selected original' })
    await user.selectOptions(owner(), 'siren')
    expect(screen.queryByRole('region', { name: 'Selected original' })).toBeNull()
    await screen.findByText(/No notes in this destination/)
    await user.click(screen.getByRole('tab', { name: 'Unclassified' }))
    await screen.findByRole('region', { name: 'Selected-owner journal notes' })
    expect(vi.mocked(getJournalNotes).mock.calls.filter(([, params]) => params.note_id !== undefined)).toHaveLength(1)
    expect(getWitnessAccounts).not.toHaveBeenCalled()
  })
  it('rejects mismatched wrapper or nested author without displaying private source bodies', async () => {
    vi.mocked(getJournalNotes).mockImplementation(async (id, params) => {
      const value = await notes(id, params as JournalParams)
      if (params.note_id !== undefined && value.note) return { ...value, note: { ...value.note, author: 'siren', content: 'PEER PRIVATE BODY' } }
      return value
    })
    await loaded(); await idea()
    await userEvent.setup().click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByText(/Original unavailable or outside selected owner/)
    expect(screen.queryByText('PEER PRIVATE BODY')).toBeNull()
  })
  it('guards A → B → A original selection against late first-A results and late failures', async () => {
    const old = deferred<JournalResponse>()
    let first = true
    vi.mocked(getJournalNotes).mockImplementation((id, params) => {
      if (params.note_id === digest.id && first) { first = false; return old.promise }
      return notes(id, params as JournalParams)
    })
    await loaded(); await idea()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await user.selectOptions(owner(), 'siren')
    await user.selectOptions(owner(), 'tempest')
    await screen.findByRole('button', { name: `Read original note #${digest.id}` })
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByRole('region', { name: 'Selected original' })
    const stale = await notes(ID, { agent_id: 'tempest', channel: 'idea', state: 'all', limit: 20, offset: 0, note_id: digest.id })
    await act(async () => { old.resolve({ ...stale, note: { ...stale.note!, content: 'STALE FIRST A PRIVATE' } }); await Promise.resolve() })
    expect(screen.queryByText('STALE FIRST A PRIVATE')).toBeNull()
    expect(detail().getByText(digest.content)).toBeTruthy()
  })
  it('guards source-selection A → B → A within the same run and owner', async () => {
    const old = deferred<JournalResponse>()
    let first = true
    vi.mocked(getJournalNotes).mockImplementation((id, params) => {
      if (params.note_id === digest.source_ids[0] && first) { first = false; return old.promise }
      return notes(id, params as JournalParams)
    })
    await loaded(); await idea()
    const user = userEvent.setup()
    const openDigest = async () => { await user.click(await screen.findByRole('button', { name: `Read original note #${digest.id}` })); await screen.findByRole('region', { name: 'Selected original' }) }
    await openDigest()
    await user.click(detail().getByRole('button', { name: `Read source note #${digest.source_ids[0]}` }))
    await openDigest()
    await user.click(detail().getByRole('button', { name: `Read source note #${digest.source_ids[0]}` }))
    await waitFor(() => expect(detail().getByRole('heading', { name: `Original note #${digest.source_ids[0]}` })).toBeTruthy())
    await act(async () => { old.reject(new Error('late first source failure')); await Promise.resolve() })
    expect(screen.queryByText(/Original unavailable/)).toBeNull()
  })
  it('guards run A → B → A late originals and clears on source-state/destination changes', async () => {
    vi.mocked(getRehearsalRuns).mockResolvedValue({ runs: [fixture.runs[0], { ...fixture.runs[0], run_id: OTHER }], total: 2, limit: 20, offset: 0 })
    const old = deferred<JournalResponse>()
    let first = true
    vi.mocked(getJournalNotes).mockImplementation((id, params) => {
      if (params.note_id !== undefined && first) { first = false; return old.promise }
      return notes(id, params as JournalParams)
    })
    await loaded(); await idea()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Run' }), OTHER)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Run' }), ID)
    await screen.findByRole('button', { name: `Read original note #${digest.id}` })
    await user.click(screen.getByRole('button', { name: `Read original note #${digest.id}` }))
    await screen.findByRole('region', { name: 'Selected original' })
    await act(async () => { old.reject(new Error('late previous run')); await Promise.resolve() })
    expect(screen.queryByText(/Original unavailable/)).toBeNull()
    await user.selectOptions(state(), 'released')
    expect(screen.queryByRole('region', { name: 'Selected original' })).toBeNull()
    await user.click(screen.getByRole('tab', { name: 'Orientation' }))
    expect(screen.queryByRole('region', { name: 'Selected original' })).toBeNull()
  })
  it('reads owner/steward witness only on explicit separate buttons, showing digest and mechanical attribution', async () => {
    await loaded()
    const user = userEvent.setup()
    expect(getWitnessAccounts).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Read owner witness' }))
    await screen.findByRole('heading', { name: 'Tempest private account' })
    expect(getWitnessAccounts).toHaveBeenLastCalledWith(ID, { agent_id: 'tempest', limit: 20, offset: 0 })
    expect(screen.getAllByText(/Author: witness · Method: mechanical/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Source digest:/).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: 'Read steward witness' }))
    await screen.findByRole('heading', { name: 'Steward-facing account' })
    expect(getWitnessAccounts).toHaveBeenLastCalledWith(ID, { limit: 20, offset: 0 })
    await user.selectOptions(owner(), 'siren')
    expect(screen.queryByRole('heading', { name: 'Steward-facing account' })).toBeNull()
    expect(getWitnessAccounts).toHaveBeenCalledTimes(2)
  })
  it('rejects wrong-scope witness bodies and late A → steward → A witness completions', async () => {
    const old = deferred<WitnessResponse>()
    vi.mocked(getWitnessAccounts).mockImplementationOnce(() => old.promise)
    await loaded()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Read owner witness' }))
    await user.click(screen.getByRole('button', { name: 'Read steward witness' }))
    await screen.findByRole('heading', { name: 'Steward-facing account' })
    await user.click(screen.getByRole('button', { name: 'Read owner witness' }))
    await screen.findByRole('heading', { name: 'Tempest private account' })
    await act(async () => { old.reject(new Error('late witness A')); await Promise.resolve() })
    expect(screen.queryByText(/Witness unavailable/)).toBeNull()
    vi.mocked(getWitnessAccounts).mockImplementationOnce(async () => ({ ...(await accounts(ID, { agent_id: 'siren', limit: 20, offset: 0 })), scope: 'tempest' }))
    await user.click(screen.getByRole('button', { name: 'Read owner witness' }))
    await screen.findByText(/Witness unavailable or outside requested scope/)
    expect(screen.queryByRole('heading', { name: 'Tempest private account' })).toBeNull()
  })
  it('distinguishes unavailable, missing and empty histories with explicit read retry', async () => {
    vi.mocked(getJournalNotes).mockRejectedValueOnce(new Error('authentication unavailable'))
    render(<Journals />)
    await screen.findByText(/Journal unavailable or outside selected owner/)
    expect(screen.queryByText(/No notes in this destination/)).toBeNull()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Refresh reads' }))
    await screen.findByRole('region', { name: 'Selected-owner journal notes' })
    vi.mocked(getJournalNotes).mockImplementationOnce(async (id, params) => ({ ...(await notes(id, params as JournalParams)), status: 'missing', notes: [], total: 0 }))
    await user.selectOptions(owner(), 'oracle')
    await screen.findByText(/Journal store missing/)
    vi.mocked(getWitnessAccounts).mockImplementationOnce(async (id, params) => ({ ...(await accounts(id, params as WitnessParams)), status: 'missing', accounts: [], total: 0 }))
    await user.click(screen.getByRole('button', { name: 'Read owner witness' }))
    await screen.findByText(/Witness store missing/)
  })
})

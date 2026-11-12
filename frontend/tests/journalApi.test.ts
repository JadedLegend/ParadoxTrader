import { describe, expect, it, vi } from 'vitest'
import { getJournalNotes, getWitnessAccounts } from '../src/api'
import { readJournalFixture } from '../src/journals/client'
import rawFixture from '../src/journals/fixture.json'
import { REHEARSAL_AGENTS } from '../src/rehearsal/contracts'
import type { JournalFixture, JournalResponse, WitnessResponse } from '../src/journals/contracts'
const fixture = rawFixture as unknown as JournalFixture
const ID = fixture.runs[0].run_id
const route = (query = '') => `/api/rehearsals/${ID}/journals?agent_id=tempest${query}`
async function withFixture(value: JournalFixture, callback: () => Promise<void>) {
  vi.doMock('../src/journals/fixture.json', () => ({ default: value }))
  vi.resetModules()
  try { await callback() } finally { vi.doUnmock('../src/journals/fixture.json'); vi.resetModules() }
}
describe('local journal API with every HTTP transport blocked', () => {
  it('uses parent wrappers and preserves all seven actual fixture owners', async () => {
    for (const owner of REHEARSAL_AGENTS) {
      const value = await getJournalNotes(ID, { agent_id: owner.id })
      expect(value).toMatchObject({ run_id: ID, agent_id: owner.id, channel: 'unclassified', state: 'all', status: 'ok', limit: 20, offset: 0, note: null })
      expect(value.notes.every(note => note.author === owner.id)).toBe(true)
    }
    expect(fixture.runs[0].mode).toBe('offline')
  })
  it('filters destinations and active/released states, and retrieves archived originals independently of current filters', async () => {
    const notes = fixture.journals[ID].tempest!
    const digest = notes.find(note => note.note_kind === 'distillation')!
    expect(digest.source_ids).toHaveLength(6)
    for (const channel of ['trading', 'idea', 'orientation', 'unclassified'] as const) {
      for (const state of ['active', 'released', 'all'] as const) {
        const expected = notes.filter(note => note.channels.includes(channel) && (state === 'all' || note.state === state)).sort((left, right) => right.id - left.id)
        const value = await getJournalNotes(ID, { agent_id: 'tempest', channel, state })
        expect(value.notes.map(note => note.id)).toEqual(expected.map(note => note.id))
        expect(value.total).toBe(expected.length)
      }
    }
    for (const id of digest.source_ids) {
      const detail = await getJournalNotes(ID, { agent_id: 'tempest', channel: 'unclassified', state: 'active', note_id: id })
      expect(detail.note).toMatchObject({ id, state: 'released', author: 'tempest', content: notes.find(note => note.id === id)!.content })
      expect(detail.notes).toEqual([])
    }
    const other = await getJournalNotes(ID, { agent_id: 'siren', note_id: notes[0].id }).catch(() => null)
    expect(other?.note?.author).not.toBe('tempest')
  })
  it('paginates filtered notes with max20 and offset10000, using independent deep clones', async () => {
    const all = await getJournalNotes(ID, { agent_id: 'tempest', channel: 'idea' })
    const page = await getJournalNotes(ID, { agent_id: 'tempest', channel: 'idea', limit: 1, offset: 1 })
    expect(page.notes).toEqual(all.notes.slice(1, 2))
    expect(page.total).toBe(all.total)
    expect(await getJournalNotes(ID, { agent_id: 'tempest', channel: 'idea', offset: 10000 })).toMatchObject({ notes: [], total: all.total })
    all.notes[0].content = 'Consumer mutation'
    all.notes[0].source_ids.push(999)
    expect(JSON.stringify(await getJournalNotes(ID, { agent_id: 'tempest', channel: 'idea' }))).not.toContain('Consumer mutation')
  })
  it('matches store literal-prefix character/UTF-8 bounds without truncating explicitly requested originals', async () => {
    const modified = structuredClone(fixture)
    const source = modified.journals[ID].tempest!.find(note => note.channels.includes('idea'))!
    source.content = '界'.repeat(5000)
    source.truncated = false
    await withFixture(modified, async () => {
      const value = await readJournalFixture(route('&channel=idea')) as JournalResponse
      const excerpt = value.notes.find(note => note.id === source.id)!
      expect(excerpt.content).toBe('界'.repeat(4000))
      expect(new TextEncoder().encode(excerpt.content).length).toBe(12000)
      expect(excerpt.truncated).toBe(true)
      const original = await readJournalFixture(route(`&note_id=${source.id}`)) as JournalResponse
      expect(original.note!.content).toBe(source.content)
      expect(original.note!.truncated).toBe(false)
    })
  })
  it('reads owner and separately requested steward accounts only from their own scope', async () => {
    for (const owner of REHEARSAL_AGENTS) {
      const value = await getWitnessAccounts(ID, { agent_id: owner.id, limit: 1 })
      expect(value).toMatchObject({ scope: owner.id, status: 'ok', limit: 1, offset: 0 })
      expect(value.accounts.every(account => account.scope === owner.id && account.author === 'witness' && account.method === 'mechanical')).toBe(true)
      expect(value.accounts.flatMap(account => account.source_refs).every(ref => !ref.agent_id || ref.agent_id === owner.id)).toBe(true)
    }
    const broad = await getWitnessAccounts(ID)
    expect(broad.scope).toBe('steward')
    expect(broad.accounts.every(account => account.scope === 'steward')).toBe(true)
    expect(await getWitnessAccounts(ID, { offset: 10000 })).toMatchObject({ accounts: [], total: broad.total })
  })
  it.each([
    '', '&limit=0', '&limit=21', '&limit=1.5', '&offset=-1', '&offset=10001', '&offset=%2B1',
    '&agent_id=siren', '&channel=innermost', '&state=published', '&note_id=0', '&note_id=2147483648',
    '&note_id=1&note_id=2', '&source_mode=offline', '&operator=true', '&wake_id=tempest-r1',
  ].filter(value => value !== ''))('rejects unsupported journal query %s without fallback', async query => {
    await expect(readJournalFixture(route(query))).rejects.toThrow()
  })
  it.each([
    `/api/rehearsals/${ID}/journals`, `/api/rehearsals/${ID}/innermost?agent_id=tempest`,
    `/api/rehearsals/${ID}/witness?agent_id=steward`, `/api/rehearsals/${ID}/witness?limit=3&limit=4`,
    `/api/rehearsals/${ID}/witness?note_id=1`, `/api/rehearsals/${ID}/witness?offset=10001`,
    `/api/rehearsals/${ID}/journals?agent_id=outsider`, `/api/rehearsals/${ID}/journals#private`,
    `/api/rehearsals/${ID}/../${ID}/journals?agent_id=tempest`, `/api/rehearsals/${ID}/%2e%2e/${ID}/journals?agent_id=tempest`,
    `https://example.invalid/api/rehearsals/${ID}/journals?agent_id=tempest`, `/api/rehearsals/not-uuid/journals?agent_id=tempest`,
  ])('rejects malformed/unknown path %s', async path => { await expect(readJournalFixture(path)).rejects.toThrow() })
  it('keeps missing stores distinct from empty filtered pages and missing originals', async () => {
    const modified = structuredClone(fixture)
    delete modified.journals[ID].tempest
    delete modified.witnesses[ID].steward
    await withFixture(modified, async () => {
      expect(await readJournalFixture(route())).toMatchObject({ status: 'missing', notes: [], total: 0 })
      expect(await readJournalFixture(`/api/rehearsals/${ID}/witness`)).toMatchObject({ status: 'missing', accounts: [], total: 0 })
      await expect(readJournalFixture(route('&note_id=1'))).rejects.toThrow('not found')
    })
  })
  it('drops unknown private fields but rejects malformed source attribution rather than relabeling it', async () => {
    const modified = structuredClone(fixture)
    Object.assign(modified.journals[ID].tempest![0], { innermost: 'PRIVATE UNKNOWN', api_key: 'PRIVATE UNKNOWN', source_links: [{ content: 'PRIVATE UNKNOWN' }] })
    Object.assign(modified.witnesses[ID].tempest![0], { raw_context: 'PRIVATE UNKNOWN', api_key: 'PRIVATE UNKNOWN' })
    modified.witnesses[ID].tempest![0].source_refs[0] = { ...modified.witnesses[ID].tempest![0].source_refs[0], ...{ content: 'PRIVATE UNKNOWN' } }
    await withFixture(modified, async () => {
      const journal = await readJournalFixture(route()) as JournalResponse
      const witness = await readJournalFixture(`/api/rehearsals/${ID}/witness?agent_id=tempest`) as WitnessResponse
      expect(JSON.stringify([journal, witness])).not.toContain('PRIVATE UNKNOWN')
    })
    for (const poison of [{ author: 'siren' }, { source_wake_id: 'siren-r1' }, { source_mode: 'invented' }]) {
      const poisoned = structuredClone(fixture)
      Object.assign(poisoned.journals[ID].tempest![0], poison)
      await withFixture(poisoned, async () => { await expect(readJournalFixture(route())).rejects.toThrow() })
    }
    const poisoned = structuredClone(fixture)
    poisoned.witnesses[ID].tempest![0].scope = 'steward'
    await withFixture(poisoned, async () => { await expect(readJournalFixture(`/api/rehearsals/${ID}/witness?agent_id=tempest`)).rejects.toThrow() })
  })
})

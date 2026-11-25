import { describe, expect, it } from 'vitest'
import { projectJournalNote, projectWitnessAccount } from '../src/journals/client'
import { MAX_WAKES_PER_AGENT, isOwnerWake } from '../src/rehearsal/contracts'

// A day run stores each move as its own round (up to MAX_WAKES_PER_AGENT), so
// pages must accept an agent's third move and later, not only r1 and r2.
const ID = '11111111-2222-4333-8444-555555555555'
function account(refs: Record<string, unknown>[], content = 'I keep only recorded facts.') {
  return { id: ID, scope: 'oracle', author: 'witness', method: 'mechanical', content,
    created_at: '2026-11-25T10:00:00+00:00', source_digest: 'a'.repeat(64), source_refs: refs }
}

describe('wake IDs past round two', () => {
  it('matches the server rule: <owner>-r<n>, 1 <= n <= 120, same owner only', () => {
    expect(MAX_WAKES_PER_AGENT).toBe(120)
    for (const wake of ['oracle-r1', 'oracle-r2', 'oracle-r3', 'oracle-r120']) expect(isOwnerWake('oracle', wake)).toBe(true)
    for (const wake of ['oracle-r0', 'oracle-r01', 'oracle-r121', 'oracle-r1000', 'oracle-r', 'oracle-r3x', 'siren-r3', 3, null])
      expect(isOwnerWake('oracle', wake)).toBe(false)
  })

  it("shows an agent's witness account from a full day of moves", () => {
    const refs = [{ kind: 'run', id: ID }]
    for (let round = 1; round <= MAX_WAKES_PER_AGENT; round += 1) {
      refs.push({ kind: 'wake', id: `oracle-r${round}`, agent_id: 'oracle' } as never)
      refs.push({ kind: 'request', id: ID, agent_id: 'oracle' } as never, { kind: 'request', id: ID, agent_id: 'oracle' } as never)
      refs.push({ kind: 'journal', id: round, agent_id: 'oracle', wake_id: `oracle-r${round}` } as never)
    }
    const content = Array.from({ length: MAX_WAKES_PER_AGENT }, (_, i) => `oracle-r${i + 1}: selected journal; outcome: completed.`).join('\n')
    const projected = projectWitnessAccount(account(refs, content), 'oracle')
    expect(projected.content).toBe(content)
    expect(projected.source_refs).toHaveLength(refs.length)
    expect(projected.source_refs.at(-1)).toMatchObject({ kind: 'journal', wake_id: 'oracle-r120' })
  })

  it("still refuses another agent's wake and wakes past the day's limit", () => {
    for (const ref of [{ kind: 'wake', id: 'siren-r3' }, { kind: 'wake', id: 'oracle-r121' }, { kind: 'journal', id: 1, wake_id: 'siren-r3' }])
      expect(() => projectWitnessAccount(account([ref]), 'oracle')).toThrow()
  })

  it('keeps a journal note written on a later move', () => {
    const note = { id: 7, author: 'oracle', content: 'A later note.', created_at: '2026-11-25T10:00:00+00:00', channels: ['unclassified'],
      note_kind: 'note', state: 'active', source_mode: 'offline', source_wake_id: 'oracle-r37', source_ids: [] }
    expect(projectJournalNote(note, 'oracle').source_wake_id).toBe('oracle-r37')
    expect(() => projectJournalNote({ ...note, source_wake_id: 'oracle-r121' }, 'oracle')).toThrow()
  })
})

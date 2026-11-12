import { describe, expect, it } from 'vitest'
import { getRehearsalJobs, getRehearsalRecord } from '../src/api'

const RUN = '88888888-8888-4888-8888-888888888888'

describe('Sessions preserves a chosen private witness encounter', () => {
  it('retains the submode and source reference without leaking the source body in jobs', async () => {
    const data = await getRehearsalJobs(RUN)
    const job = data.jobs.find(value => value.agent_id === 'siren' && value.round === 2)!
    expect(job.journal_mode).toBe('witness')
    expect(job.action).toBe('journal')
    expect(job.record_refs).toHaveLength(1)
    const ref = job.record_refs[0]
    expect(ref.kind).toBe('witness')
    const source = await getRehearsalRecord(RUN, 'siren', ref.kind, ref.id)
    expect(source.kind).toBe('witness')
    expect(source.record).toMatchObject({ scope: 'siren', author: 'witness', method: 'mechanical' })
    expect(source.record).not.toHaveProperty('source_facts')
    expect(JSON.stringify(job)).not.toContain((source.record as { content: string }).content)
    await expect(getRehearsalRecord(RUN, 'tempest', ref.kind, ref.id)).rejects.toThrow()
  })
})

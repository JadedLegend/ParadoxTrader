import { describe, expect, it } from 'vitest'
import * as api from '../src/api'
import { fixture, readFixture } from '../src/preview/readFixture'

const ids = fixture.agents.map(agent => agent.agent_id)
const readCases: [string, () => Promise<unknown>, string][] = [
  ['getStatus', api.getStatus, '/api/status'],
  ['getAgents', api.getAgents, '/api/agents'],
  ['getSnapshot', api.getSnapshot, '/api/snapshot'],
  ['getAllPositions', api.getAllPositions, '/api/agents/positions'],
  ['getForum default', () => api.getForum(), '/api/forum?limit=50'],
  ['getForum filtered', () => api.getForum(3, 'council_deliberation'), '/api/forum?limit=3&thread_id=council_deliberation'],
  ['getForum encoded thread', () => api.getForum(2, 'questions & ideas'), '/api/forum?limit=2&thread_id=questions%20%26%20ideas'],
  ['getThreads', api.getThreads, '/api/forum/threads'],
  ['getInbox user', () => api.getInbox('user'), '/api/inbox/user?unread_only=false'],
  ['getQueue', api.getQueue, '/api/queue'],
  ['getConfig', api.getConfig, '/api/config'],
  ['getAnnouncements', api.getAnnouncements, '/api/announcements'],
  ...ids.flatMap((id): [string, () => Promise<unknown>, string][] => [
    [`getAgentJournal ${id} default`, () => api.getAgentJournal(id), `/api/agents/${id}/journal?limit=20`],
    [`getAgentJournal ${id} limit`, () => api.getAgentJournal(id, 2), `/api/agents/${id}/journal?limit=2`],
    [`getAgentEpisodes ${id} default`, () => api.getAgentEpisodes(id), `/api/agents/${id}/episodes?limit=20`],
    [`getAgentEpisodes ${id} limit`, () => api.getAgentEpisodes(id, 2), `/api/agents/${id}/episodes?limit=2`],
    [`getSelfDefinition ${id}`, () => api.getSelfDefinition(id), `/api/agents/${id}/self-definition`],
    [`getInbox ${id}`, () => api.getInbox(id), `/api/inbox/${id}?unread_only=false`],
    [`getInbox ${id} unread`, () => api.getInbox(id, true), `/api/inbox/${id}?unread_only=true`],
  ]),
]

const writeCases: [string, () => Promise<unknown>][] = [
  ['wakeAgent', () => api.wakeAgent('tempest')],
  ['initSystem', api.initSystem],
  ['setPhase', () => api.setPhase(3)],
  ['updateConfig', () => api.updateConfig('runtime.current_phase', 3)],
  ['setCountdown', () => api.setCountdown('2030-01-01T00:00:00Z')],
  ['approveTrade default', () => api.approveTrade(1)],
  ['approveTrade notes', () => api.approveTrade(1, 'fixture review')],
  ['rejectTrade default', () => api.rejectTrade(1)],
  ['rejectTrade notes', () => api.rejectTrade(1, 'fixture review')],
  ['writeJournalEntry', () => api.writeJournalEntry('tempest', 'Do not write this')],
  ['writeInnermostEntry', () => api.writeInnermostEntry('tempest', 'Do not write this')],
  ['updateSelfDefinition', () => api.updateSelfDefinition('tempest', 'Do not write this')],
  ['postToForum default', () => api.postToForum('tempest', 'Do not post this')],
  ['postToForum thread', () => api.postToForum('tempest', 'Do not post this', 'general')],
  ['sendDM', () => api.sendDM('tempest', 'siren', 'Do not send this')],
]

describe('fixture-only public API wrappers', () => {
  it('defaults to preview with no connected configuration', () => {
    expect(import.meta.env.VITE_RUNTIME_MODE).toBe('')
    expect(import.meta.env.VITE_API_URL).toBe('')
    expect(api.API_MODE).toBe('preview')
    expect(api.IS_PREVIEW).toBe(true)
  })

  it.each(readCases)('%s returns a labeled compatible fixture', async (_name, read, path) => {
    const result = await read()
    expect(result).toEqual(readFixture(path))
    expect(result).toMatchObject({ kind: 'fixture', observed_at: fixture.observed_at })
    expect(result).not.toBe(readFixture(path))
  })

  it('keeps all seven individual identities and nullable activity timestamps', async () => {
    const status = await api.getStatus()
    const agents = await api.getAgents()
    expect(status.agents).toHaveLength(7)
    expect(status.agents).toEqual(agents.agents)
    expect(new Set(status.agents.map(agent => agent.agent_id)).size).toBe(7)
    for (const agent of status.agents) {
      expect(agent).toMatchObject({ last_tick_at: null, in_interval: false, hrv_status: 'ok' })
      expect(typeof agent.name).toBe('string')
      expect(typeof agent.hrv).toBe('number')
      expect(Array.isArray(agent.curiosity_questions)).toBe(true)
    }
  })

  it('preserves errors, unavailable broker states, and confirmed empty as different states', async () => {
    const market = await api.getSnapshot()
    expect(market.error).toMatch(/not connected/i)
    expect(market).not.toHaveProperty('quotes')
    const { positions } = await api.getAllPositions()
    expect(Object.keys(positions).sort()).toEqual([...ids].sort())
    expect(positions.siren).toMatchObject({ status: 'ok', positions: [] })
    expect(positions.alchemist).toMatchObject({ status: 'not_configured', positions: [] })
    expect(positions.weaver).toMatchObject({ status: 'error', positions: [] })
    expect(positions.shadow.status).toBe('not_configured')
    expect(positions.tempest.positions[0]).toMatchObject({ symbol: 'DEMO', qty: '2' })
    for (const snapshot of Object.values(positions)) {
      expect(snapshot.observed_at).toBe(fixture.observed_at)
    }
  })

  it('provides expected collection shapes without pretending agents created records', async () => {
    expect(await api.getAgentJournal('tempest')).toMatchObject({ agent_id: 'tempest', entries: [] })
    expect(await api.getAgentEpisodes('tempest')).toMatchObject({ agent_id: 'tempest', episodes: [] })
    expect(await api.getSelfDefinition('tempest')).toMatchObject({ self_definition_history: [] })
    expect(await api.getInbox('tempest')).toMatchObject({ messages: [], unread_count: 0 })
    expect(await api.getThreads()).toMatchObject({ threads: [{ id: 'general', title: 'Community' }] })
    expect(await api.getForum(50, 'council_deliberation')).toMatchObject({ posts: [] })
    expect((await api.getForum()).posts[0]).toMatchObject({ author: 'SYSTEM', tags: ['fixture'] })
    expect((await api.getForum()).posts[0].content).toMatch(/not written by an agent/i)
    expect((await api.getQueue()).trades[0].proposal.thesis).toMatch(/not a recommendation or pending order/i)
    expect(await api.getAnnouncements()).toMatchObject({ announcements: [], countdown: null })
    expect(await api.getConfig()).toMatchObject({ config: {
      runtime: { current_phase: 0, wake_interval_seconds: null, wake_duration_seconds: null },
      guardrails: { autonomous_trading_mode: false },
    } })
  })

  it.each(writeCases)('%s rejects preview writes instead of reporting fake success', async (_name, write) => {
    const before = structuredClone(fixture)
    await expect(write()).rejects.toThrow(/Preview is read-only\. No backend action was sent\./)
    expect(fixture).toEqual(before)
  })

  it.each([
    ['journal', () => api.getAgentJournal('unknown_agent')],
    ['episodes', () => api.getAgentEpisodes('unknown_agent')],
    ['self-definition', () => api.getSelfDefinition('unknown_agent')],
    ['inbox', () => api.getInbox('unknown_agent')],
  ] as [string, () => Promise<unknown>][])('unknown %s identity rejects rather than falling back', async (_name, read) => {
    await expect(read()).rejects.toThrow(/No fixture is available.*No backend fallback was attempted/)
  })

  it('returns independent nested clones so consumer mutation never poisons later reads', async () => {
    const before = structuredClone(fixture)
    const first = await api.getAgents()
    first.agents[0].name = 'Changed by a consumer'
    first.agents[0].curiosity_questions.push('Changed by a consumer')
    const positions = await api.getAllPositions()
    positions.positions.tempest.positions[0].symbol = 'CHANGED'
    const definition = await api.getSelfDefinition('tempest')
    definition.self_definition_history.push({ fake: true })
    expect((await api.getAgents()).agents).toEqual(before.agents)
    expect((await api.getAllPositions()).positions).toEqual(before.positions)
    expect((await api.getSelfDefinition('tempest')).self_definition_history).toEqual([])
    expect(fixture).toEqual(before)
  })
})

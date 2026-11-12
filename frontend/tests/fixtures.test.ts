import { describe, expect, it } from 'vitest'
import { fixture, readFixture } from '../src/preview/readFixture'

const expectedIds = ['tempest', 'siren', 'alchemist', 'weaver', 'oracle', 'shadow', 'paradox_hunter']
const menus = Object.entries(fixture.windows).flatMap(([agentId, windows]) =>
  Object.entries(windows).map(([scenario, window]) => ({ agentId, scenario, window })),
)
const peerActions = ['forum_post', 'direct_message', 'analyze_consensus']

describe('clearly scoped runtime-derived fixtures', () => {
  it('contains exactly the seven individual identities and no started wake timestamps', () => {
    expect(fixture.schema_version).toBe(1)
    expect(fixture.kind).toBe('fixture')
    expect(Number.isNaN(Date.parse(fixture.observed_at))).toBe(false)
    expect(fixture.agents.map(agent => agent.agent_id)).toEqual(expectedIds)
    expect(new Set(fixture.agents.map(agent => agent.name)).size).toBe(7)
    for (const agent of fixture.agents) {
      expect(agent.name.trim()).not.toBe('')
      expect(agent.epistemic_role.trim()).not.toBe('')
      expect(agent.core_drive.trim()).not.toBe('')
      expect(agent.last_tick_at).toBeNull()
      expect(agent.hrv_status).toBe('ok')
      expect(agent.hrv).toBeGreaterThanOrEqual(0)
      expect(agent.hrv).toBeLessThanOrEqual(agent.max_hrv!)
      expect(Object.keys(fixture.windows[agent.agent_id]).sort()).toEqual(['interval', 'phase0', 'phase1', 'phase3'])
      expect(fixture.definitions[agent.agent_id].self_definition.trim()).not.toBe('')
      expect(fixture.definitions[agent.agent_id].self_definition_history).toEqual([])
    }
    expect(Object.keys(fixture.positions).sort()).toEqual([...expectedIds].sort())
    expect(Object.keys(fixture.windows).sort()).toEqual([...expectedIds].sort())
    expect(Object.keys(fixture.definitions).sort()).toEqual([...expectedIds].sort())
  })

  it.each(menus)('$agentId / $scenario offers unique affordable human-labeled choices including rest', ({ scenario, window }) => {
    expect(window.choices.length).toBeGreaterThan(0)
    expect(window.choices.length).toBeLessThanOrEqual(5)
    const actions = window.choices.map(choice => choice.action)
    expect(new Set(actions).size).toBe(actions.length)
    expect(actions).toContain('rest')
    for (const choice of window.choices) {
      expect(choice.label.trim()).not.toBe('')
      expect(choice.label).not.toBe(choice.action)
      expect(Number.isFinite(choice.hrv_cost)).toBe(true)
      if (choice.action === 'rest') {
        expect(choice.label).toBe('Quiet rest — no reflection required')
        expect(choice.hrv_cost).toBeLessThanOrEqual(0)
      } else {
        expect(choice.hrv_cost).toBeGreaterThanOrEqual(0)
        expect(choice.hrv_cost).toBeLessThanOrEqual(window.hrv)
      }
    }
    if (window.phase === 0) {
      for (const action of peerActions) expect(actions).not.toContain(action)
    }
    if (actions.includes('analyze_consensus')) expect(window.phase).toBe(3)
    if (scenario === 'interval') {
      expect(window.in_interval).toBe(true)
      expect(actions).toEqual(['rest'])
      expect(actions).not.toContain('journal')
    } else {
      expect(window.in_interval).toBe(false)
      expect(window.phase).toBe(Number(scenario.replace('phase', '')))
    }
  })

  it('labels optional reflection, curiosity, exploration, and trading as choices rather than forced quotas', () => {
    const allChoices = menus.flatMap(({ window }) => window.choices)
    const labels = Object.fromEntries(allChoices.map(choice => [choice.action, choice.label]))
    expect(labels.journal).toBe('Choose a private reflection')
    expect(labels.roam).toMatch(/follow your curiosity/)
    expect(labels.research).toMatch(/of your choosing/)
    expect(labels.propose_trade).toBe('Develop a trade idea')
    expect(labels.rest).toMatch(/no reflection required/)
    expect(allChoices.every(choice => !/must|quota|mandatory/i.test(choice.label))).toBe(true)
  })

  it('contains only public example data, no credentials or personal runtime collections', () => {
    expect(JSON.stringify(fixture).toLowerCase()).not.toMatch(/api_key|api_secret|secret_key|authorization|bearer |paper-api\.alpaca/)
    expect(fixture).not.toHaveProperty('episodes')
    expect(fixture).not.toHaveProperty('journal')
    expect(fixture).not.toHaveProperty('orders')
    expect(fixture).not.toHaveProperty('receipts')
  })

  it.each(['/api/missing', '/api/agents/unknown/self-definition', '/api/inbox/unknown', '/api/agents/tempest/not-supported'])('unrecognized fixture path %s explicitly rejects without a fallback', path => {
    expect(() => readFixture(path)).toThrow(/No fixture is available.*No backend fallback was attempted/)
  })
})

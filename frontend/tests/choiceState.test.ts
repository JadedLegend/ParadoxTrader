import { describe, expect, it } from 'vitest'
import { describeCost, makeReceipt } from '../src/preview/choiceState'
import { fixture } from '../src/preview/readFixture'
import type { ActionChoice, ChoiceWindow } from '../src/data/contracts'

const selectedAt = '2026-11-12T12:00:00.000Z'

describe('operator-only demonstration receipts', () => {
  it('uses authoritative numeric costs for every action in every fixture menu', () => {
    const before = structuredClone(fixture)
    for (const [agentId, scenarios] of Object.entries(fixture.windows)) {
      for (const window of Object.values(scenarios)) {
        for (const choice of window.choices) {
          const receipt = makeReceipt(agentId, window, choice, selectedAt)
          expect(receipt).toMatchObject({
            kind: 'operator_demonstration', agent_id: agentId,
            action: choice.action, label: choice.label, hrv_before: window.hrv,
            hrv_estimate_after: Math.max(0, Math.min(window.max_hrv, window.hrv - choice.hrv_cost)),
          })
          expect(Number.isFinite(receipt.hrv_estimate_after)).toBe(true)
        }
      }
    }
    expect(fixture).toEqual(before)
  })

  it.each(fixture.agents.map(agent => [agent.agent_id]))('%s records only the offered rest estimate without changing runtime-derived fixtures', agentId => {
    const before = structuredClone(fixture)
    const window = fixture.windows[agentId].phase0
    const rest = window.choices.find(choice => choice.action === 'rest')!
    const receipt = makeReceipt(agentId, window, rest, selectedAt)
    expect(receipt).toEqual({
      kind: 'operator_demonstration', agent_id: agentId, action: 'rest', label: rest.label,
      selected_at: selectedAt, hrv_before: window.hrv,
      hrv_estimate_after: Math.min(window.max_hrv, window.hrv - rest.hrv_cost),
    })
    expect(receipt).not.toHaveProperty('order_id')
    expect(receipt).not.toHaveProperty('journal')
    expect(fixture).toEqual(before)
  })

  it('debits an offered active action only in the local estimate', () => {
    const window = fixture.windows.tempest.phase0
    const offered = window.choices.find(choice => choice.action !== 'rest')!
    const before = structuredClone(window)
    expect(makeReceipt('tempest', window, offered, selectedAt)).toMatchObject({
      kind: 'operator_demonstration', action: offered.action,
      hrv_before: window.hrv, hrv_estimate_after: window.hrv - offered.hrv_cost,
    })
    expect(window).toEqual(before)
  })

  it('ignores a caller-forged cost and label for an otherwise offered action', () => {
    const window = fixture.windows.tempest.phase0
    const offered = window.choices.find(choice => choice.action === 'monitor')!
    const forged = { ...offered, label: 'Fake execution confirmed', hrv_cost: -99999 }
    const receipt = makeReceipt('tempest', window, forged, selectedAt)
    expect(receipt.label).toBe(offered.label)
    expect(receipt.hrv_estimate_after).toBe(window.hrv - offered.hrv_cost)
    expect(receipt.label).not.toBe(forged.label)
  })

  it('rejects unoffered actions instead of fabricating a receipt', () => {
    const window = fixture.windows.tempest.phase0
    const choice: ActionChoice = { action: 'run_broker_order', label: 'Not offered', hrv_cost: 0 }
    const before = structuredClone(window)
    expect(() => makeReceipt('tempest', window, choice, selectedAt)).toThrow(/not offered/)
    expect(window).toEqual(before)
  })

  it('rejects a non-rest action in an interval even if a corrupt menu offers it', () => {
    const choice: ActionChoice = { action: 'journal', label: 'Should never be forced', hrv_cost: 1 }
    const window: ChoiceWindow = { ...structuredClone(fixture.windows.tempest.interval), choices: [choice] }
    const before = structuredClone(window)
    expect(() => makeReceipt('tempest', window, choice, selectedAt)).toThrow(/only permits quiet rest/)
    expect(window).toEqual(before)
  })

  it.each([
    ['floor', 1, 4, 0], ['ceiling', 99, -1.5, 100], ['already full', 100, -1.5, 100],
  ] as [string, number, number, number][])('clamps the simulated HRV %s', (_label, hrv, cost, expected) => {
    const action = cost < 0 ? 'rest' : 'monitor'
    const choice: ActionChoice = { action, label: 'Bounded example', hrv_cost: cost }
    const window: ChoiceWindow = { phase: 0, hrv, max_hrv: 100, in_interval: false, choices: [choice] }
    expect(makeReceipt('tempest', window, choice, selectedAt).hrv_estimate_after).toBe(expected)
    expect(window.hrv).toBe(hrv)
  })

  it('describes a simulated resource, not money or provider credits', () => {
    expect(describeCost({ action: 'rest', label: 'Quiet rest', hrv_cost: -1.5 })).toBe('Recover 1.5 simulated HRV')
    expect(describeCost({ action: 'monitor', label: 'Monitor', hrv_cost: 0.5 })).toBe('0.5 simulated HRV')
  })
})

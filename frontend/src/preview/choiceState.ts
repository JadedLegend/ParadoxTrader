import type { ActionChoice, ChoiceWindow } from '../data/contracts'

export interface DemonstrationReceipt {
  agent_id: string
  action: string
  label: string
  selected_at: string
  hrv_before: number
  hrv_estimate_after: number
  kind: 'operator_demonstration'
}

export function makeReceipt(agentId: string, window: ChoiceWindow, choice: ActionChoice, selectedAt: string): DemonstrationReceipt {
  const offered = window.choices.find(item => item.action === choice.action)
  if (!offered) throw new Error('This action was not offered in the current example window.')
  if (window.in_interval && offered.action !== 'rest') throw new Error('An interval example only permits quiet rest.')
  return {
    kind: 'operator_demonstration', agent_id: agentId, action: offered.action,
    label: offered.label, selected_at: selectedAt, hrv_before: window.hrv,
    hrv_estimate_after: Math.max(0, Math.min(window.max_hrv, window.hrv - offered.hrv_cost)),
  }
}

export function describeCost(choice: ActionChoice): string {
  if (choice.action === 'rest') return `Recover ${Math.abs(choice.hrv_cost).toFixed(1)} simulated HRV`
  return `${choice.hrv_cost.toFixed(1)} simulated HRV`
}

export interface BrokerPosition {
  symbol: string
  qty: string
  avg_entry_price?: string
  unrealized_pl?: string
}

export interface PositionSnapshot {
  status: 'ok' | 'not_configured' | 'error'
  positions: BrokerPosition[]
  observed_at: string
}

export interface AgentSummary {
  agent_id: string
  name: string
  epistemic_role: string
  core_drive: string
  model: string
  current_focus: string
  curiosity_questions: string[]
  hrv: number | null
  max_hrv: number | null
  in_interval: boolean
  last_tick_at: string | null
  hrv_status: 'ok' | 'not_initialized'
}

export interface ActionChoice {
  action: string
  label: string
  hrv_cost: number
}

export interface ChoiceWindow {
  phase: number
  hrv: number
  max_hrv: number
  in_interval: boolean
  choices: ActionChoice[]
}

export interface PreviewFixture {
  schema_version: number
  kind: 'fixture'
  observed_at: string
  agents: AgentSummary[]
  positions: Record<string, PositionSnapshot>
  windows: Record<string, Record<string, ChoiceWindow>>
  definitions: Record<string, { self_definition: string; self_definition_history: unknown[] }>
}

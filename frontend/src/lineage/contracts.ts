// Stable private-history owners; display labels do not grant execution authority.
export const LINEAGE_AGENTS = [
  { id: 'tempest', name: 'Tempest' },
  { id: 'siren', name: 'Siren' },
  { id: 'alchemist', name: 'Alchemist' },
  { id: 'weaver', name: 'Weaver' },
  { id: 'oracle', name: 'Oracle' },
  { id: 'shadow', name: 'Shadow' },
  { id: 'paradox_hunter', name: 'ParadoxHunter' },
] as const
export type LineageAgentId = typeof LINEAGE_AGENTS[number]['id']

// Decimal USD strings are projections from the store; the UI never sums them.
export type DecimalUSD = string
export type InquiryState = 'open' | 'paused' | 'abandoned'
export interface InquiryMetadata {
  inquiry_id: string
  agent_id: string
  title: string
  state: InquiryState
  phase: number
  visibility: 'owner' | 'community'
  created_at: string
  updated_at: string
}
export interface InquiryEntry {
  entry_id: string
  inquiry_id?: string
  agent_id?: string
  kind: 'observation' | 'interpretation'
  content: string
  source: 'agent' | 'operator' | 'external'
  created_at: string
}
export interface OptionStructure {
  symbol: string
  underlying: string
  expiry: string
  option_type: 'call' | 'put'
  strike: DecimalUSD
  side: 'buy' | 'sell'
  intent: 'open' | 'close'
  qty: number
  order_type: 'limit'
  limit_price: DecimalUSD
  multiplier: 100
}
export interface LineageProposal {
  proposal_id: string
  inquiry_id: string
  agent_id: string
  queue_id: number
  structure: OptionStructure
  thesis: string
  horizon: string
  uncertainty: string
  review_status: 'pending' | 'approved' | 'rejected'
  created_at?: string
}
export type OrderStatus = 'pending_submission' | 'submission_unknown' | 'accepted' | 'rejected' | 'partially_filled' | 'filled' | 'canceled'
export interface LineageOrder {
  order_id: string
  proposal_id: string
  inquiry_id: string
  agent_id: string
  queue_id: number
  client_order_id: string
  broker_order_id: string | null
  broker: 'mock'
  status: OrderStatus
  sync_state: 'pending' | 'ok' | 'submission_unknown' | 'unavailable' | 'failed'
  broker_revision: number
  qty: number
  filled_qty: number
  structure: OptionStructure
  created_at: string
  updated_at: string
}
export interface LineageFill {
  fill_id: string
  broker_fill_id: string
  order_id: string
  proposal_id: string
  inquiry_id: string
  position_id: string
  agent_id: string
  qty: number
  price: DecimalUSD
  side: 'buy' | 'sell'
  created_at: string
  authority: 'mock_broker'
}
export interface LineagePosition {
  position_id: string
  agent_id: string
  symbol: string
  qty: number
  average_entry_price: DecimalUSD | null
  gross_realized_pnl: DecimalUSD
  market_value: null
  unrealized_pnl: null
  fees: null
  mark_status: 'unavailable'
  status: 'open' | 'closed'
  multiplier: 100
}
export interface LineageReview {
  review_id: string
  inquiry_id?: string
  agent_id?: string
  content: string
  proposal_id?: string | null
  order_id?: string | null
  position_id?: string | null
  created_at: string
}
export interface LineageEvent {
  event_id: string
  inquiry_id?: string
  agent_id?: string
  kind: string
  authority?: string
  payload: unknown
  created_at: string
  proposal_id?: string | null
  order_id?: string | null
  position_id?: string | null
}
export interface LineageListResponse {
  status: 'ok'
  inquiries: InquiryMetadata[]
  total: number
  limit: number
  offset: number
  truncated?: boolean
}
export interface LineageDetailResponse {
  status: 'ok'
  inquiry: InquiryMetadata
  entries: InquiryEntry[]
  proposals: LineageProposal[]
  orders: LineageOrder[]
  fills: LineageFill[]
  positions: LineagePosition[]
  reviews: LineageReview[]
  events: LineageEvent[]
  truncated: boolean
}
export interface LineageFixture {
  mode: 'mock_demo'
  agent_id: 'alchemist'
  list: LineageListResponse
  // Older examples only contain Alchemist's list; never reuse it for another owner.
  agent_lists?: Record<LineageAgentId, LineageListResponse>
  details: Record<string, LineageDetailResponse>
}

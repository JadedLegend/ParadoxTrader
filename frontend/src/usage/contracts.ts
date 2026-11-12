// Read-only request metadata. Dollar values remain decimal strings, never totals
// accumulated in binary floating point. Null means unknown, not free.
export interface UsageSummary {
  requests: number
  successful_requests: number
  failed_requests: number
  reported_cost_usd: string | null
  estimated_cost_usd: string | null
  reported_cost_requests: number
  estimated_cost_requests: number
  unknown_cost_requests: number
  input_tokens: number | null
  output_tokens: number | null
  cached_input_tokens: number | null
  reasoning_tokens: number | null
  usage_known_requests: number
  usage_unknown_requests: number
}

export interface UsageFilters {
  agent_id: string | null
  since: string | null
  until: string | null
}

export interface UsageSummaryResponse {
  status: 'ok'
  currency: 'USD'
  filters: UsageFilters
  summary: UsageSummary
  by_agent: (UsageSummary & { agent_id: string | null })[]
  by_provider: (UsageSummary & { provider: string })[]
  by_activity: (UsageSummary & { activity: string })[]
  groups_truncated?: boolean
  kind?: 'fixture'
}

export interface UsagePricingSnapshot {
  schema_version?: number
  provider?: string
  model?: string
  source: string
  as_of: string
  input_usd_per_million?: string
  output_usd_per_million?: string
  cached_input_usd_per_million?: string | null
}

export interface UsageEvent {
  event_id: string
  call_id: string
  wake_id: string | null
  agent_id: string | null
  activity: string
  provider: string
  model: string
  response_model?: string | null
  attempt: number
  created_at: string
  duration_ms: number
  outcome: 'success' | 'http_error' | 'transport_error' | 'invalid_response'
  http_status: number | null
  input_tokens: number | null
  output_tokens: number | null
  cached_input_tokens: number | null
  reasoning_tokens: number | null
  total_tokens: number | null
  cost_usd: string | null
  cost_status: 'reported' | 'estimated' | 'unknown'
  cost_scope: 'provider_reported' | 'token_only' | null
  cost_reason: string | null
  pricing_source?: string | null
  pricing_as_of?: string | null
  pricing_snapshot?: UsagePricingSnapshot | null
}

export interface UsageEventsResponse {
  status: 'ok'
  events: UsageEvent[]
  total: number
  offset: number
  limit: number
  filters: UsageFilters
  kind?: 'fixture'
}

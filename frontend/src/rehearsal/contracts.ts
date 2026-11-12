import type { LineageDetailResponse } from '../lineage/contracts'

export const REHEARSAL_AGENTS = [
  { id: 'tempest', name: 'Tempest' }, { id: 'siren', name: 'Siren' },
  { id: 'alchemist', name: 'Alchemist' }, { id: 'weaver', name: 'Weaver' },
  { id: 'oracle', name: 'Oracle' }, { id: 'shadow', name: 'Shadow' },
  { id: 'paradox_hunter', name: 'ParadoxHunter' },
] as const
export type RehearsalAgentId = typeof REHEARSAL_AGENTS[number]['id']
export type RehearsalStatus = 'prepared' | 'running' | 'completed' | 'partial' | 'stopped' | 'uncertain'
export type RehearsalJobStatus = 'pending' | 'running' | 'claimed' | 'completed' | 'failed' | 'stopped' | 'uncertain'
export type RehearsalAction = 'rest' | 'journal' | 'inquire' | 'library' | 'roam'
export type RehearsalRecordKind = 'journal' | 'episode' | 'inquiry' | 'library' | 'witness'
export interface RehearsalLimits {
  wakes_per_agent: number; max_requests: number; max_output_tokens: number; max_input_bytes: number
  max_runtime_seconds: number; request_timeout_seconds: number; max_parallelism: number; budget_usd: string
}
export interface RehearsalAgentProgress {
  agent_id: RehearsalAgentId; pending: number; completed: number; failed: number; stopped: number; uncertain: number
}
export interface RehearsalRun {
  run_id: string; mode: 'offline' | 'real'; status: RehearsalStatus
  created_at: string; started_at: string | null; ended_at: string | null; stop_requested: boolean
  limits: RehearsalLimits; agent_models: Record<RehearsalAgentId, string>; capabilities: RehearsalAction[]
  request_count: number; reserved_usd: string; known_cost_usd: string | null; unknown_cost_requests: number
  reported_cost_usd?: string | null; estimated_cost_usd?: string | null
  agents: RehearsalAgentProgress[]
}
export interface RehearsalRecordRef { kind: RehearsalRecordKind; id: string | number }
export interface RehearsalJob {
  wake_id: string; agent_id: RehearsalAgentId; round: number; status: RehearsalJobStatus
  action: RehearsalAction | null; failure_code: string | null; requested_model: string | null
  response_model: string | null; provider: string | null; request_count: number; duration_ms: number | null
  record_refs: RehearsalRecordRef[]; updated_at: string
  decision_context?: RehearsalDecisionMetadata | null; selection_origin?: 'none' | 'model' | null
  journal_mode?: 'note' | 'compost' | 'distill' | 'witness'
  channels?: ('trading' | 'idea' | 'orientation' | 'unclassified')[]
}
export interface RehearsalUsage {
  input_tokens?: number | null; output_tokens?: number | null; total_tokens?: number | null
  prompt_tokens?: number | null; completion_tokens?: number | null
  cost_usd?: string | null; reported_cost_usd?: string | null; estimated_cost_usd?: string | null
  cost_status?: 'reported' | 'estimated' | 'unknown'; cost_source?: string | null
}
// Actual-store fixtures contain flat coverage; API/local reader normalize usage.
export interface RehearsalRequest extends RehearsalUsage {
  request_id: string; wake_id: string; agent_id: RehearsalAgentId; activity: string
  model?: string; requested_model?: string; response_model: string | null; provider: string | null
  outcome: string; duration_ms: number | null; input_bytes: number; max_output_tokens: number
  reserved_usd: string; usage?: RehearsalUsage | null; failure_code: string | null
  created_at?: string; submitted_at?: string; finished_at?: string | null
  finish_reason?: string | null
}
export interface RehearsalRunsResponse { runs: RehearsalRun[]; total: number; limit: number; offset: number }
// GET /{run_id} returns a summary directly; list routes use bounded envelopes.
export type RehearsalRunResponse = RehearsalRun
export interface RehearsalJobsResponse { run_id: string; jobs: RehearsalJob[] }
export interface RehearsalRequestsResponse { run_id: string; events: RehearsalRequest[]; total: number; limit: number; offset: number }
export interface RehearsalMemoryRecord { id: number; content: string; title?: string; phase?: string; created_at: string; truncated?: boolean }
export interface RehearsalLibraryRecord { section_id: string; document_id?: string; locator?: string; text: string; truncated?: boolean }
export interface RehearsalWitnessRecord extends Omit<RehearsalMemoryRecord, 'id'> { id: string; scope: RehearsalAgentId; author: 'witness'; method: 'mechanical'; source_refs: unknown[]; source_digest: string }
export interface RehearsalRecordResponse {
  run_id: string; agent_id: RehearsalAgentId; kind: RehearsalRecordKind; id: string | number
  record: RehearsalMemoryRecord | RehearsalLibraryRecord | RehearsalWitnessRecord | LineageDetailResponse
}
export interface RehearsalDecisionMetadata {
  schema_version: 1; offered_actions: RehearsalAction[]
  action_costs: { action: RehearsalAction; max_requests: number; reservation_ceiling_usd: string; basis: 'catalog_upper_bound' }[]
  constraints: RehearsalLimits
  admission_snapshot: { reserved_usd: string; remaining_budget_usd: string; request_count: number; remaining_requests: number; is_reservation: false }
  model: { requested_model: string; context_length: number; max_completion_tokens: number; catalog_source: string | null }
  continuity: { status: string; refs: (RehearsalRecordRef & { wake_id?: string; agent_id?: RehearsalAgentId })[]; truncated: boolean; chars: number }
}
export type RehearsalPrivateJSON = null | boolean | number | string | RehearsalPrivateJSON[] | { [key: string]: RehearsalPrivateJSON }
export interface RehearsalDecisionResponse {
  run_id: string; agent_id: RehearsalAgentId; wake_id: string
  decision: { metadata: RehearsalDecisionMetadata; private_context: RehearsalPrivateJSON; requests: { [key: string]: RehearsalPrivateJSON }[] }
}
// Mock labeling is independent of a run's mode and exact-model live availability.
export interface RehearsalFixture {
  kind: 'fixture'; observed_at?: string; provenance?: string; runs: RehearsalRun[]
  jobs: Record<string, RehearsalJob[]>; requests: Record<string, RehearsalRequest[]>
  records: Record<string, Record<string, RehearsalRecordResponse>>
  decisions?: Record<string, Record<string, RehearsalDecisionResponse>>
}
export type RunSummary = RehearsalRun
export type RunListResponse = RehearsalRunsResponse
export type JobListResponse = RehearsalJobsResponse
export type RequestListResponse = RehearsalRequestsResponse
export type PrivateRecordResponse = RehearsalRecordResponse
export type DecisionResponse = RehearsalDecisionResponse

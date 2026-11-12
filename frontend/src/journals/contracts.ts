import type { RehearsalAgentId, RehearsalRun } from '../rehearsal/contracts'

export const JOURNAL_CHANNELS = ['trading', 'idea', 'orientation', 'unclassified'] as const
export type JournalChannel = typeof JOURNAL_CHANNELS[number]
export type JournalState = 'all' | 'active' | 'released'
export type JournalOwner = RehearsalAgentId
export type WitnessScope = JournalOwner | 'steward'
export interface JournalParams {
  agent_id: JournalOwner; channel?: JournalChannel; state?: JournalState
  limit?: number; offset?: number; note_id?: number
}
export interface WitnessParams { agent_id?: JournalOwner; limit?: number; offset?: number }
export interface JournalNote {
  id: number; content: string; channels: JournalChannel[]; note_kind: 'note' | 'compost' | 'distillation'
  state: 'active' | 'released'; author: JournalOwner; source_mode: 'real' | 'offline' | null
  created_at: string; source_wake_id: string | null; source_ids: number[]; truncated: boolean
}
export interface JournalSourceHeader {
  kind: 'inquiry'; id: string; agent_id: JournalOwner; title: string
  state: 'open' | 'paused' | 'abandoned'; created_at: string; title_truncated: boolean
  provenance: 'lineage_inquiries' | 'lineage_proposals'; proposal_ids: string[]
}
export interface JournalResponse {
  run_id: string; agent_id: JournalOwner; channel: JournalChannel; state: JournalState
  status: 'ok' | 'missing'; notes: JournalNote[]; total: number; limit: number; offset: number
  note: JournalNote | null; sources: JournalSourceHeader[]; source_status: 'ok' | 'missing' | 'not_applicable'
}
export interface WitnessSourceRef {
  kind: string; id: string | number; agent_id?: JournalOwner; wake_id?: string
}
export interface WitnessAccount {
  id: string; scope: WitnessScope; content: string; source_refs: WitnessSourceRef[]
  source_digest: string; author: 'witness'; method: 'mechanical'; created_at: string
}
export interface WitnessResponse {
  run_id: string; scope: WitnessScope; status: 'ok' | 'missing'
  accounts: WitnessAccount[]; total: number; limit: number; offset: number
}
export interface JournalFixture {
  schema_version?: 1; kind?: 'fixture'; provenance?: string; runs: RehearsalRun[]
  journals: Record<string, Partial<Record<JournalOwner, JournalNote[]>>>
  witnesses: Record<string, Partial<Record<WitnessScope, WitnessAccount[]>>>
  sources?: Record<string, Partial<Record<JournalOwner, JournalSourceHeader[]>>>
}

import axios from 'axios'
import { createApiClient, resolveApiMode, resolveHostProfile } from './data/client'
import { readFixture } from './preview/readFixture'
import type { AgentSummary, PositionSnapshot } from './data/contracts'
import type { LibraryDocumentsResponse, LibrarySearchResponse, LibrarySectionResponse } from './library/contracts'
import type { UsageSummaryResponse, UsageEventsResponse } from './usage/contracts'
import type { LineageListResponse, LineageDetailResponse } from './lineage/contracts'
import type { RunSummary, RunListResponse, JobListResponse, RequestListResponse, PrivateRecordResponse, DecisionResponse } from './rehearsal/contracts'
import type { JournalResponse, WitnessResponse } from './journals/contracts'

export const API_MODE = resolveApiMode(import.meta.env.VITE_RUNTIME_MODE)
export const IS_PREVIEW = API_MODE === 'preview'
// Set at build time for deploy/private_dashboard.py; ignored in fixture preview.
export const HOST_PROFILE = resolveHostProfile(import.meta.env.VITE_HOST_PROFILE)
export const IS_PRIVATE_HOST = !IS_PREVIEW && HOST_PROFILE === 'private'
const BASE = import.meta.env.VITE_API_URL || ''
const api = axios.create({ baseURL: BASE, timeout: 15000 })
const request = createApiClient(API_MODE, readFixture, async (method, path, payload) => {
  const response = method === 'GET' ? await api.get(path) : await api.post(path, payload)
  return response.data
}, IS_PRIVATE_HOST ? 'private' : 'full')

// Existing views retain their response shapes. The central boundary blocks every
// preview mutation, even if a disabled UI control is invoked programmatically.
export const getStatus = () => request<{ agents: AgentSummary[] }>('GET', '/api/status')
export const getSnapshot = () => request<any>('GET', '/api/snapshot')
export const getAgents = () => request<{ agents: AgentSummary[] }>('GET', '/api/agents')
export const getAgentJournal = (id: string, limit = 20) => request<any>('GET', `/api/agents/${id}/journal?limit=${limit}`)
export const getAgentEpisodes = (id: string, limit = 20) => request<any>('GET', `/api/agents/${id}/episodes?limit=${limit}`)
export const getForum = (limit = 50, thread?: string) => request<any>('GET', `/api/forum?limit=${limit}${thread ? `&thread_id=${encodeURIComponent(thread)}` : ''}`)
export const postToForum = (author: string, content: string, thread_id = 'general') => request<any>('POST', '/api/forum', { author, content, thread_id })
export const getThreads = () => request<any>('GET', '/api/forum/threads')
export const getInbox = (agent: string, unread = false) => request<any>('GET', `/api/inbox/${agent}?unread_only=${unread}`)
export const sendDM = (sender: string, recipient: string, content: string) => request<any>('POST', '/api/dm', { sender, recipient, content })
export const getQueue = () => request<any>('GET', '/api/queue')
export const approveTrade = (id: number, notes = '') => request<any>('POST', `/api/queue/${id}/approve`, { notes })
export const rejectTrade = (id: number, notes = '') => request<any>('POST', `/api/queue/${id}/reject`, { notes })
export const getConfig = () => request<any>('GET', '/api/config')
export const updateConfig = (key_path: string, value: unknown) => request<any>('POST', '/api/config', { key_path, value })
export const setPhase = (phase: number) => request<any>('POST', '/api/phase', { phase })
export const setCountdown = (target_iso: string) => request<any>('POST', '/api/countdown', { target_iso })
export const getAnnouncements = () => request<any>('GET', '/api/announcements')
export const initSystem = () => request<any>('POST', '/api/init')
export const wakeAgent = (agent_id: string) => request<any>('POST', `/api/wake/${agent_id}`)
export const getSelfDefinition = (id: string) => request<any>('GET', `/api/agents/${id}/self-definition`)
export const updateSelfDefinition = (id: string, definition: string) => request<any>('POST', `/api/agents/${id}/self-definition`, { definition })
export const getAllPositions = () => request<{ positions: Record<string, PositionSnapshot> }>('GET', '/api/agents/positions')
export const writeJournalEntry = (id: string, content: string) => request<any>('POST', `/api/agents/${id}/journal`, { content })
export const writeInnermostEntry = (id: string, content: string) => request<any>('POST', `/api/agents/${id}/innermost`, { content })

export const getLibraryDocuments = (limit = 50, offset = 0) => request<LibraryDocumentsResponse>('GET', `/api/library/documents?limit=${limit}&offset=${offset}`)
export const searchLibrary = (q: string, document_id?: string, limit = 3, max_chars = 600) => request<LibrarySearchResponse>('GET',
  `/api/library/search?q=${encodeURIComponent(q)}&limit=${limit}&max_chars=${max_chars}${document_id ? `&document_id=${encodeURIComponent(document_id)}` : ''}`)
export const getLibrarySection = (section_id: string, offset = 0, max_chars = 1200) => request<LibrarySectionResponse>('GET',
  `/api/library/sections/${encodeURIComponent(section_id)}?offset=${offset}&max_chars=${max_chars}`)

export const getUsageSummary = (agent_id?: string) => request<UsageSummaryResponse>('GET',
  `/api/usage/summary${agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : ''}`)
export const getUsageEvents = (agent_id?: string, limit = 50, offset = 0) => request<UsageEventsResponse>('GET',
  `/api/usage/events?limit=${limit}&offset=${offset}${agent_id ? `&agent_id=${encodeURIComponent(agent_id)}` : ''}`)

export const getLineageInquiries = (agent_id = 'alchemist', limit = 50, offset = 0) => request<LineageListResponse>('GET',
  `/api/lineage/inquiries?agent_id=${encodeURIComponent(agent_id)}&limit=${limit}&offset=${offset}`)
export const getLineageInquiry = (inquiry_id: string, agent_id = 'alchemist') => request<LineageDetailResponse>('GET',
  `/api/lineage/inquiries/${encodeURIComponent(inquiry_id)}?agent_id=${encodeURIComponent(agent_id)}`)

export const getRehearsalRuns = (limit = 20, offset = 0) => request<RunListResponse>('GET',
  `/api/rehearsals?limit=${limit}&offset=${offset}`)
export const getRehearsalRun = (run_id: string) => request<RunSummary>('GET', `/api/rehearsals/${encodeURIComponent(run_id)}`)
export const getRehearsalJobs = (run_id: string) => request<JobListResponse>('GET', `/api/rehearsals/${encodeURIComponent(run_id)}/jobs`)
export const getRehearsalRequests = (run_id: string, agent_id?: string, limit = 50, offset = 0) => request<RequestListResponse>('GET',
  `/api/rehearsals/${encodeURIComponent(run_id)}/requests?limit=${limit}&offset=${offset}${agent_id ? `&agent_id=${encodeURIComponent(agent_id)}` : ''}`)
export const getRehearsalRecord = (run_id: string, agent_id: string, kind: string, id: string | number) => request<PrivateRecordResponse>('GET',
  `/api/rehearsals/${encodeURIComponent(run_id)}/records?agent_id=${encodeURIComponent(agent_id)}&kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(String(id))}`)
export const getRehearsalDecision = (run_id: string, agent_id: string, wake_id: string) => request<DecisionResponse>('GET',
  `/api/rehearsals/${encodeURIComponent(run_id)}/decisions?agent_id=${encodeURIComponent(agent_id)}&wake_id=${encodeURIComponent(wake_id)}`)

export const getJournalNotes = (run_id: string, params: { agent_id: string, channel?: string, state?: string, limit?: number, offset?: number, note_id?: number }) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))
  return request<JournalResponse>('GET', `/api/rehearsals/${encodeURIComponent(run_id)}/journals?${query}`)
}
export const getWitnessAccounts = (run_id: string, params: { agent_id?: string, limit?: number, offset?: number } = {}) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))
  return request<WitnessResponse>('GET', `/api/rehearsals/${encodeURIComponent(run_id)}/witness?${query}`)
}

import axios from 'axios'
import { createApiClient, resolveApiMode } from './data/client'
import { readFixture } from './preview/readFixture'
import type { AgentSummary, PositionSnapshot } from './data/contracts'

export const API_MODE = resolveApiMode(import.meta.env.VITE_RUNTIME_MODE)
export const IS_PREVIEW = API_MODE === 'preview'
const BASE = import.meta.env.VITE_API_URL || ''
const api = axios.create({ baseURL: BASE, timeout: 15000 })
const request = createApiClient(API_MODE, readFixture, async (method, path, payload) => {
  const response = method === 'GET' ? await api.get(path) : await api.post(path, payload)
  return response.data
})

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

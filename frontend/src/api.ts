import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({ baseURL: BASE })

export const getStatus = () => api.get('/api/status').then(r => r.data)
export const getSnapshot = () => api.get('/api/snapshot').then(r => r.data)
export const getAgents = () => api.get('/api/agents').then(r => r.data)
export const getAgentJournal = (id: string, limit = 20) => api.get(`/api/agents/${id}/journal?limit=${limit}`).then(r => r.data)
export const getAgentEpisodes = (id: string, limit = 20) => api.get(`/api/agents/${id}/episodes?limit=${limit}`).then(r => r.data)

export const getForum = (limit = 50, thread?: string) =>
  api.get(`/api/forum?limit=${limit}${thread ? `&thread_id=${thread}` : ''}`).then(r => r.data)
export const postToForum = (author: string, content: string, thread_id = 'general') =>
  api.post('/api/forum', { author, content, thread_id }).then(r => r.data)
export const getThreads = () => api.get('/api/forum/threads').then(r => r.data)

export const getInbox = (agent: string, unread = false) =>
  api.get(`/api/inbox/${agent}?unread_only=${unread}`).then(r => r.data)
export const sendDM = (sender: string, recipient: string, content: string) =>
  api.post('/api/dm', { sender, recipient, content }).then(r => r.data)

export const getQueue = () => api.get('/api/queue').then(r => r.data)
export const approveTrade = (id: number, notes = '') =>
  api.post(`/api/queue/${id}/approve`, { notes }).then(r => r.data)
export const rejectTrade = (id: number, notes = '') =>
  api.post(`/api/queue/${id}/reject`, { notes }).then(r => r.data)

export const getConfig = () => api.get('/api/config').then(r => r.data)
export const updateConfig = (key_path: string, value: unknown) =>
  api.post('/api/config', { key_path, value }).then(r => r.data)

export const setPhase = (phase: number) => api.post('/api/phase', { phase }).then(r => r.data)
export const setCountdown = (target_iso: string) =>
  api.post('/api/countdown', { target_iso }).then(r => r.data)
export const getAnnouncements = () => api.get('/api/announcements').then(r => r.data)

export const initSystem = () => api.post('/api/init').then(r => r.data)
export const wakeAgent = (agent_id: string) => api.post(`/api/wake/${agent_id}`).then(r => r.data)

export const getSelfDefinition = (id: string) => api.get(`/api/agents/${id}/self-definition`).then(r => r.data)
export const updateSelfDefinition = (id: string, definition: string) =>
  api.post(`/api/agents/${id}/self-definition`, { definition }).then(r => r.data)

export const getAllPositions = () => api.get('/api/agents/positions').then(r => r.data)

export const writeJournalEntry = (id: string, content: string) =>
  api.post(`/api/agents/${id}/journal`, { content }).then(r => r.data)
export const writeInnermostEntry = (id: string, content: string) =>
  api.post(`/api/agents/${id}/innermost`, { content }).then(r => r.data)

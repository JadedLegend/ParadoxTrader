import { useEffect, useState } from 'react'
import { getRehearsalJobs, getRehearsalRun, getRehearsalRuns } from '../api'
import { REHEARSAL_AGENTS } from './contracts'
import type { RehearsalJob, RehearsalRun, RehearsalRunsResponse } from './contracts'

type ReadState<T> = { key: string; data: T | null; loading: boolean; error: boolean }
const empty = <T,>(): ReadState<T> => ({ key: '', data: null, loading: false, error: false })
const RUN_LIMIT = 20

export interface RecordedRun {
  /** The most recent page of recorded runs, newest first, or null while loading or after a failure. */
  runs: RehearsalRunsResponse | null
  runsLoading: boolean
  runsError: boolean
  runId: string | null
  selectRun: (runId: string | null) => void
  /** The selected run's summary and jobs, checked to belong to that run. */
  detail: { run: RehearsalRun; jobs: RehearsalJob[] } | null
  detailLoading: boolean
  detailError: boolean
  refresh: () => void
}

// Reads the recorded session runs (GET /api/rehearsals, then /{run} and /{run}/jobs)
// and selects the newest by default. A failed read is reported, never shown as empty.
export function useRecordedRun(): RecordedRun {
  const [runId, setRunId] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const listKey = JSON.stringify([retry])
  const runKey = JSON.stringify([runId, retry])
  const [listState, setListState] = useState<ReadState<RehearsalRunsResponse>>(empty)
  const [runState, setRunState] = useState<ReadState<{ run: RehearsalRun; jobs: RehearsalJob[] }>>(empty)

  useEffect(() => {
    let cancelled = false
    setListState({ key: listKey, data: null, loading: true, error: false })
    getRehearsalRuns(RUN_LIMIT, 0).then(data => {
      if (cancelled) return
      setListState({ key: listKey, data, loading: false, error: false })
      setRunId(current => current && data.runs.some(run => run.run_id === current) ? current : data.runs[0]?.run_id ?? null)
    }).catch(() => { if (!cancelled) setListState({ key: listKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [listKey])

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    setRunState({ key: runKey, data: null, loading: true, error: false })
    Promise.all([getRehearsalRun(runId), getRehearsalJobs(runId)]).then(([run, jobs]) => {
      if (run.run_id !== runId || jobs.run_id !== runId || jobs.jobs.some(job => !REHEARSAL_AGENTS.some(agent => agent.id === job.agent_id))) throw new Error('Run scope mismatch')
      if (!cancelled) setRunState({ key: runKey, data: { run, jobs: jobs.jobs }, loading: false, error: false })
    }).catch(() => { if (!cancelled) setRunState({ key: runKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, runKey])

  const listCurrent = listState.key === listKey
  // A failed list read hides the previous run too: nothing is shown as current after a failure.
  const runCurrent = runState.key === runKey && !(listCurrent && listState.error)
  return {
    runs: listCurrent && !listState.error ? listState.data : null,
    runsLoading: !listCurrent || listState.loading,
    runsError: listCurrent && listState.error,
    runId,
    selectRun: setRunId,
    detail: runId && runCurrent && !runState.error ? runState.data : null,
    detailLoading: !!runId && (!runCurrent || runState.loading),
    detailError: !!runId && runCurrent && runState.error,
    refresh: () => setRetry(value => value + 1),
  }
}

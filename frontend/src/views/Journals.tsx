import { useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getJournalNotes, getWitnessAccounts, getRehearsalRuns, getRehearsalRecord } from '../api'
import { REHEARSAL_AGENTS } from '../rehearsal/contracts'
import { JOURNAL_CHANNELS } from '../journals/contracts'
import { projectJournalNote, projectSourceHeader, projectWitnessAccount } from '../journals/client'
import type { JournalChannel, JournalNote, JournalOwner, JournalResponse, JournalState, WitnessResponse, WitnessScope } from '../journals/contracts'
import type { RehearsalRunsResponse } from '../rehearsal/contracts'

type Read<T> = { key: string; data: T | null; loading: boolean; error: boolean }
const empty = <T,>(): Read<T> => ({ key: '', data: null, loading: false, error: false })
const label = (value: string) => value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase())
const LIMIT = 20
const MAX_OFFSET = 10000
type Selection = { kind: 'journal'; id: number } | { kind: 'inquiry'; id: string }
type Original = { note: JournalNote } | { title: string; entries: { id: string; content: string; source: string }[] }
function checkedJournal(data: JournalResponse, run: string, owner: JournalOwner, channel: JournalChannel, state: JournalState, offset: number, noteId?: number): JournalResponse {
  if (data.run_id !== run || data.agent_id !== owner || data.channel !== channel || data.state !== state ||
      !['ok', 'missing'].includes(data.status) || data.limit !== LIMIT || data.offset !== offset ||
      !Number.isSafeInteger(data.total) || data.total < 0 || !Array.isArray(data.notes) || data.notes.length > LIMIT ||
      !Array.isArray(data.sources) || data.sources.length > LIMIT || !['ok', 'missing', 'not_applicable'].includes(data.source_status)) throw new Error('Journal scope mismatch')
  const notes = data.notes.map(value => projectJournalNote(value, owner))
  const note = data.note === null ? null : projectJournalNote(data.note, owner)
  if (noteId !== undefined ? note?.id !== noteId : note !== null || notes.some(value => !value.channels.includes(channel) || state !== 'all' && value.state !== state)) throw new Error('Journal source mismatch')
  const sources = data.sources.map(value => projectSourceHeader(value, owner))
  if ((channel === 'orientation' || channel === 'unclassified' || state === 'released') && sources.length || channel === 'trading' && sources.some(value => value.provenance !== 'lineage_proposals')) throw new Error('Source destination mismatch')
  return { ...data, notes, note, sources }
}
function Note({ note, onSource }: { note: JournalNote; onSource: (id: number) => void }) {
  return <article className="journal-source" aria-label={`Original journal note ${note.id}`}>
    <h3>{note.note_kind === 'distillation' ? 'Agent-authored distillation' : 'Original note'} #{note.id}</h3>
    <p className="journal-labels">Author: {label(note.author)} · {note.channels.map(label).join(', ')} · {note.state === 'released' ? 'Released · preserved original' : 'Active'} · {note.source_mode ?? 'Source mode unknown'}</p>
    <p className="rehearsal-meta">{note.created_at} · Source wake: {note.source_wake_id ?? 'Not recorded'}</p>
    <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{note.content}</p>
    {note.truncated && <p>Literal source is truncated; no summary is substituted.</p>}
    {note.source_ids.length > 0 && <><h4>Preserved source originals</h4><div className="rehearsal-record-links">{note.source_ids.map(id => <button className="btn btn-ghost" type="button" key={id} onClick={() => onSource(id)}>Read source note #{id}</button>)}</div></>}
  </article>
}
export default function Journals() {
  const [runId, setRunId] = useState<string | null>(null)
  const [owner, setOwner] = useState<JournalOwner>('tempest')
  const [channel, setChannel] = useState<JournalChannel>('unclassified')
  const [state, setState] = useState<JournalState>('all')
  const [offset, setOffset] = useState(0)
  const [runOffset, setRunOffset] = useState(0)
  const [selected, setSelected] = useState<Selection | null>(null)
  const [witnessScope, setWitnessScope] = useState<WitnessScope | null>(null)
  const [witnessOffset, setWitnessOffset] = useState(0)
  const [retry, setRetry] = useState(0)
  const sequence = useRef(0)
  const [generation, setGeneration] = useState(0)
  const [runs, setRuns] = useState<Read<RehearsalRunsResponse>>(empty)
  const [journal, setJournal] = useState<Read<JournalResponse>>(empty)
  const [original, setOriginal] = useState<Read<Original>>(empty)
  const [witness, setWitness] = useState<Read<WitnessResponse>>(empty)
  const runKey = JSON.stringify([runOffset, retry])
  const listKey = JSON.stringify([runId, owner, channel, state, offset, retry, generation])
  const originalKey = JSON.stringify([runId, owner, channel, state, selected, retry, generation])
  const witnessKey = JSON.stringify([runId, owner, witnessScope, witnessOffset, retry, generation])
  function clear() {
    sequence.current += 1; setGeneration(sequence.current)
    setSelected(null); setWitnessScope(null); setOffset(0); setWitnessOffset(0)
    setOriginal(empty()); setWitness(empty())
  }
  function select(value: Selection) {
    sequence.current += 1; setGeneration(sequence.current)
    setSelected(value); setOriginal(empty()); setWitnessScope(null); setWitness(empty())
  }
  useEffect(() => {
    let cancelled = false
    setRuns({ key: runKey, data: null, loading: true, error: false })
    getRehearsalRuns(LIMIT, runOffset).then(data => {
      if (cancelled) return
      if (!Array.isArray(data.runs) || data.runs.length > LIMIT) throw new Error('Run list unavailable')
      setRuns({ key: runKey, data, loading: false, error: false })
      setRunId(current => current && data.runs.some(run => run.run_id === current) ? current : data.runs[0]?.run_id ?? null)
    }).catch(() => { if (!cancelled) setRuns({ key: runKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runKey, runOffset])
  useEffect(() => {
    if (!runId) return
    let cancelled = false
    const version = sequence.current
    setJournal({ key: listKey, data: null, loading: true, error: false })
    getJournalNotes(runId, { agent_id: owner, channel, state, limit: LIMIT, offset }).then(data => {
      const checked = checkedJournal(data, runId, owner, channel, state, offset)
      if (!cancelled && version === sequence.current) setJournal({ key: listKey, data: checked, loading: false, error: false })
    }).catch(() => { if (!cancelled && version === sequence.current) setJournal({ key: listKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, owner, channel, state, offset, listKey])
  useEffect(() => {
    if (!runId || !selected) return
    let cancelled = false
    const version = sequence.current
    setOriginal({ key: originalKey, data: null, loading: true, error: false })
    const request = selected.kind === 'journal' ? getJournalNotes(runId, { agent_id: owner, channel, state, limit: LIMIT, offset: 0, note_id: selected.id }).then(data => {
      const checked = checkedJournal(data, runId, owner, channel, state, 0, selected.id as number)
      return { note: checked.note! } as Original
    }) : getRehearsalRecord(runId, owner, 'inquiry', selected.id).then(data => {
      if (data.run_id !== runId || data.agent_id !== owner || data.kind !== 'inquiry' || data.id !== selected.id || !('inquiry' in data.record) ||
          data.record.inquiry.agent_id !== owner || data.record.inquiry.inquiry_id !== selected.id || !Array.isArray(data.record.entries)) throw new Error('Inquiry scope mismatch')
      const entries = data.record.entries.slice(0, 100).map(entry => {
        if (entry.agent_id !== owner || entry.inquiry_id !== selected.id || typeof entry.content !== 'string' || !['agent', 'operator', 'external'].includes(entry.source)) throw new Error('Inquiry source mismatch')
        return { id: entry.entry_id, content: entry.content.slice(0, 12000), source: entry.source }
      })
      return { title: data.record.inquiry.title.slice(0, 500), entries } as Original
    })
    request.then(data => { if (!cancelled && version === sequence.current) setOriginal({ key: originalKey, data, loading: false, error: false }) })
      .catch(() => { if (!cancelled && version === sequence.current) setOriginal({ key: originalKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, owner, channel, state, selected, originalKey])
  useEffect(() => {
    if (!runId || !witnessScope) return
    let cancelled = false
    const version = sequence.current
    setWitness({ key: witnessKey, data: null, loading: true, error: false })
    getWitnessAccounts(runId, { ...(witnessScope === 'steward' ? {} : { agent_id: owner }), limit: LIMIT, offset: witnessOffset }).then(data => {
      if (data.run_id !== runId || data.scope !== witnessScope || !['ok', 'missing'].includes(data.status) ||
          data.limit !== LIMIT || data.offset !== witnessOffset || !Array.isArray(data.accounts) || data.accounts.length > LIMIT ||
          !Number.isSafeInteger(data.total) || data.total < 0) throw new Error('Witness scope mismatch')
      const accounts = data.accounts.map(value => projectWitnessAccount(value, witnessScope))
      if (!cancelled && version === sequence.current) setWitness({ key: witnessKey, data: { ...data, accounts }, loading: false, error: false })
    }).catch(() => { if (!cancelled && version === sequence.current) setWitness({ key: witnessKey, data: null, loading: false, error: true }) })
    return () => { cancelled = true }
  }, [runId, owner, witnessScope, witnessOffset, witnessKey])
  const runList = runs.key === runKey ? runs.data : null
  const list = journal.key === listKey ? journal.data : null
  const detail = selected && original.key === originalKey ? original.data : null
  const account = witnessScope && witness.key === witnessKey ? witness.data : null
  const readWitness = (scope: WitnessScope) => {
    sequence.current += 1; setGeneration(sequence.current)
    setSelected(null); setOriginal(empty()); setWitness(empty()); setWitnessOffset(0); setWitnessScope(scope)
  }
  return <div className="journals-page rehearsal-page">
    <header className="page-header"><h1 className="page-title">Journals</h1><p className="page-sub">Owner-private notes and preserved sources · read only, when useful.</p></header>
    <div className="notice"><strong>{IS_PREVIEW ? 'Scripted local examples · no live activity' : 'Operator-protected private reads'}</strong><p>{IS_PREVIEW ? 'Examples come from temporary offline stores. No HTTP fallback or model calls.' : 'No browser secrets or launch controls. These reads require integrated operator authentication.'}</p><p>Notes and witness accounts are optional. Release archives routine context; it does not delete or share an original.</p></div>
    <div className="rehearsal-toolbar"><label htmlFor="journal-run">Run</label><select id="journal-run" className="select" value={runId ?? ''} disabled={!runList?.runs.length} onChange={event => { clear(); setRunId(event.target.value || null) }}>
      {!runList?.runs.length && <option value="">No run selected</option>}{runList?.runs.map(run => <option key={run.run_id} value={run.run_id}>{run.run_id.slice(0, 8)} · {run.mode} · {run.status}</option>)}
    </select><label htmlFor="journal-owner">Owner</label><select id="journal-owner" className="select" value={owner} onChange={event => { clear(); setOwner(event.target.value as JournalOwner) }}>{REHEARSAL_AGENTS.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select><button type="button" className="btn btn-ghost" onClick={() => { clear(); setRetry(value => value + 1) }}>Refresh reads</button></div>
    {(runs.key !== runKey || runs.loading) && <p role="status">Loading runs…</p>}{runs.key === runKey && runs.error && <p role="alert">Run list unavailable. A failed read is not an empty history.</p>}{runList?.runs.length === 0 && <p>No recorded runs on this page.</p>}
    {runList && <div className="rehearsal-toolbar" aria-label="Run pagination"><button type="button" className="btn btn-ghost" disabled={runOffset === 0} onClick={() => { clear(); setRunId(null); setRunOffset(Math.max(0, runOffset - LIMIT)) }}>Previous runs</button><button type="button" className="btn btn-ghost" disabled={runOffset + LIMIT >= runList.total || runOffset > MAX_OFFSET - LIMIT} onClick={() => { clear(); setRunId(null); setRunOffset(runOffset + LIMIT) }}>Next runs</button></div>}
    {runId && <>
      <div className="journal-tabs" role="tablist" aria-label="Journal destinations">{JOURNAL_CHANNELS.map(destination => <button className="btn btn-ghost" role="tab" aria-selected={channel === destination} type="button" key={destination} onClick={() => { clear(); setChannel(destination) }}>{label(destination)}</button>)}</div>
      <div className="rehearsal-toolbar"><label htmlFor="journal-state">Source state</label><select className="select" id="journal-state" value={state} onChange={event => { clear(); setState(event.target.value as JournalState) }}><option value="all">All sources</option><option value="active">Active</option><option value="released">Released / archived</option></select></div>
      <p>Only {label(owner)}’s selected-run notes are shown. Existing inquiry/trading headers link to their original lineage, not a second execution ledger.</p>
      {(journal.key !== listKey || journal.loading) && <p role="status">Loading selected-owner notes…</p>}{journal.key === listKey && journal.error && <p role="alert">Journal unavailable or outside selected owner. No empty history inferred.</p>}
      {list && <section className="journal-list card" aria-label="Selected-owner journal notes"><h2>{label(channel)}</h2>
        {list.status === 'missing' ? <p>Journal store missing. No journal was created by this read.</p> : list.notes.length === 0 ? <p>No notes in this destination and source state on this page.</p> : list.notes.map(note => <article className="journal-entry" key={note.id}><h3>#{note.id} · {label(note.note_kind)}</h3><p className="journal-labels">{note.state === 'released' ? 'Released · preserved' : 'Active'} · {note.channels.map(label).join(', ')} · Author: {label(note.author)}</p><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{note.content}</p>{note.truncated && <p>Literal excerpt truncated.</p>}<button type="button" className="btn btn-ghost journal-entry-button" onClick={() => select({ kind: 'journal', id: note.id })}>Read original note #{note.id}</button></article>)}
        <p className="rehearsal-meta">{list.total} matching notes · offset {list.offset} · limit {list.limit}</p><div className="rehearsal-toolbar" aria-label="Journal pagination"><button type="button" className="btn btn-ghost" disabled={offset === 0} onClick={() => { clear(); setOffset(Math.max(0, offset - LIMIT)) }}>Previous notes</button><button type="button" className="btn btn-ghost" disabled={offset + LIMIT >= list.total || offset > MAX_OFFSET - LIMIT} onClick={() => { clear(); setOffset(offset + LIMIT) }}>Next notes</button></div>
        {list.source_status !== 'not_applicable' && <><h3>Existing lineage source links</h3>{list.source_status === 'missing' ? <p>Lineage sources missing; no execution data inferred.</p> : list.sources.length === 0 ? <p>No linked lineage headers on this page.</p> : list.sources.map(source => <article key={source.id}><p>{source.title} · {source.state}</p><p className="rehearsal-meta">Original inquiry {source.id} · {source.provenance}{source.proposal_ids.length ? ` · Proposal source IDs: ${source.proposal_ids.join(', ')}` : ''}</p><button className="btn btn-ghost" type="button" onClick={() => select({ kind: 'inquiry', id: source.id })}>Read original inquiry {source.id.slice(0, 8)}</button></article>)}</>}
      </section>}
      {selected && (original.key !== originalKey || original.loading) && <p role="status">Loading selected original…</p>}{selected && original.key === originalKey && original.error && <p role="alert">Original unavailable or outside selected owner. No replacement text inferred.</p>}
      {detail && <section className="journal-detail card" aria-label="Selected original">{'note' in detail ? <Note note={detail.note} onSource={id => select({ kind: 'journal', id })} /> : <><h3>Original inquiry · {detail.title}</h3><p>Literal source entries; proposal, order and fill records remain in their existing lineage.</p>{detail.entries.length === 0 ? <p>No source entries recorded.</p> : detail.entries.map(entry => <article key={entry.id}><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{entry.content}</p><p className="rehearsal-meta">Source: {entry.source} · {entry.id}</p></article>)}</>}</section>}
      <section className="journal-witness card" aria-label="Optional witness"><h2>Optional witness account</h2><p>Source-backed mechanical account, not agent-authored notes or an assessment. Steward accounts are separately scoped to the authenticated operator.</p><div className="rehearsal-toolbar"><button className="btn btn-ghost" type="button" onClick={() => readWitness(owner)}>Read owner witness</button><button className="btn btn-ghost" type="button" onClick={() => readWitness('steward')}>Read steward witness</button>{witnessScope && <button className="btn btn-ghost" type="button" onClick={clear}>Close witness</button>}</div>
        {witnessScope && (witness.key !== witnessKey || witness.loading) && <p role="status">Loading optional witness…</p>}{witnessScope && witness.key === witnessKey && witness.error && <p role="alert">Witness unavailable or outside requested scope. No account inferred.</p>}
        {account && <><h3>{account.scope === 'steward' ? 'Steward-facing account' : `${label(account.scope)} private account`}</h3>{account.status === 'missing' ? <p>Witness store missing. No account was created by this read.</p> : account.accounts.length === 0 ? <p>No witness accounts recorded on this scope page.</p> : account.accounts.map(value => <article key={value.id}><p className="journal-labels">Author: witness · Method: mechanical · {value.created_at}</p><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{value.content}</p><p className="rehearsal-meta">Source digest: {value.source_digest}</p><ul>{value.source_refs.map((ref, index) => <li key={`${ref.kind}|${ref.id}|${index}`}>{ref.kind}: {ref.id}{ref.agent_id ? ` · ${ref.agent_id}` : ''}{ref.kind === 'journal' && typeof ref.id === 'number' && ref.agent_id === owner && <button className="btn btn-ghost" type="button" onClick={() => select({ kind: 'journal', id: ref.id as number })}>Read source note #{ref.id}</button>}</li>)}</ul></article>)}<div className="rehearsal-toolbar" aria-label="Witness pagination"><button className="btn btn-ghost" type="button" disabled={witnessOffset === 0} onClick={() => setWitnessOffset(Math.max(0, witnessOffset - LIMIT))}>Previous accounts</button><button className="btn btn-ghost" type="button" disabled={witnessOffset + LIMIT >= account.total || witnessOffset > MAX_OFFSET - LIMIT} onClick={() => setWitnessOffset(witnessOffset + LIMIT)}>Next accounts</button></div></>}
      </section>
    </>}
  </div>
}

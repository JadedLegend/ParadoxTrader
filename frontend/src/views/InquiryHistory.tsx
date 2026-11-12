import { useEffect, useState } from 'react'
import { IS_PREVIEW, getLineageInquiries, getLineageInquiry } from '../api'
import type { LineageDetailResponse, LineageEvent, LineageListResponse, OptionStructure } from '../lineage/contracts'

const LIMIT = 50
const MAX_OFFSET = 2 ** 31 - 1
const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 12 })
const bounded = (value: unknown, max = 2000) => typeof value === 'string' ? (value.length > max ? `${value.slice(0, max)}… [text truncated]` : value) : ''
const label = (value: string) => bounded(value, 100).replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
const shortId = (id: string) => id.slice(0, 8)
function dollars(value: string | null) {
  if (value === null) return 'Unavailable'
  const numeric = Number(value) // Presentation only: no JS accounting arithmetic.
  if (!Number.isFinite(numeric)) return `$${bounded(value, 100)}`
  if ((numeric !== 0 && Math.abs(numeric) < 0.000000000001) || (numeric === 0 && /[1-9]/.test(value))) {
    return value.startsWith('-') ? '−<$0.000000000001' : '<$0.000000000001'
  }
  return USD.format(numeric)
}
function createdAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? bounded(value, 100) : `${date.toLocaleString('en-US', {
    timeZone: 'UTC', year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })} UTC`
}
function Timestamp({ value }: { value: string }) {
  return <time dateTime={value}>{createdAt(value)}</time>
}
function Structure({ value }: { value: OptionStructure }) {
  return <p className="lineage-meta">{label(value.side)} to {value.intent} · {value.qty} whole contract{value.qty === 1 ? '' : 's'} · {bounded(value.symbol, 80)}<br />
    {bounded(value.underlying, 40)} {value.option_type} · Strike {dollars(value.strike)} · Expiry {bounded(value.expiry, 40)}<br />
    Limit {dollars(value.limit_price)} per share · Multiplier {value.multiplier}</p>
}
function eventAuthority(event: LineageEvent) {
  const payloadAuthority = event.payload && typeof event.payload === 'object' && !Array.isArray(event.payload) && 'authority' in event.payload
    ? event.payload.authority : undefined
  const authority = event.authority ?? payloadAuthority
  return authority === 'mock_broker' ? 'Mock broker confirmed' : typeof authority === 'string' ? label(authority) : 'Local lifecycle record'
}
function EventPayload({ event }: { event: LineageEvent }) {
  // Unknown payloads are not injected as HTML or dumped as unbounded JSON.
  if (typeof event.payload === 'string') return <p>{bounded(event.payload, 500)}</p>
  if (!event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload)) return null
  const fields = Object.entries(event.payload).filter(([key]) => !key.endsWith('_id')).slice(0, 6)
  return fields.length ? <p className="lineage-meta">{fields.map(([key, value]) => {
    const text = typeof value === 'string' ? bounded(value, 160) : typeof value === 'number' || typeof value === 'boolean' ? String(value) : value === null ? 'Not recorded' : 'Structured record'
    return `${label(key)}: ${text}`
  }).join(' · ')}</p> : null
}
function HistoryDetail({ data }: { data: LineageDetailResponse }) {
  const { inquiry } = data
  return <div className="lineage-detail">
    <header className="card">
      <h2>{bounded(inquiry.title, 240)}</h2>
      <p>Inquiry state: <strong>{label(inquiry.state)}</strong></p>
      <p className="lineage-meta">Alchemist · Phase {inquiry.phase} · {label(inquiry.visibility)} visibility<br />
        Created <Timestamp value={inquiry.created_at} /> · Updated <Timestamp value={inquiry.updated_at} /></p>
      <p className="lineage-meta" title={inquiry.inquiry_id}>Inquiry {shortId(inquiry.inquiry_id)}</p>
    </header>
    {data.truncated && <p className="notice">History is truncated: each record category is limited to 100 items. Omitted records are not shown.</p>}
    <section className="card lineage-section" aria-label="Inquiry notes">
      <h2 className="card-title">Inquiry notes</h2>
      <p className="lineage-meta">Observations and interpretations remain separate, with recorded sources and times.</p>
      {data.entries.length === 0 ? <p>No inquiry notes recorded.</p> : data.entries.slice(0, 100).map(entry => <article className="lineage-event" key={entry.entry_id}>
        <h3>{label(entry.kind)}</h3><p>{bounded(entry.content)}</p>
        <p className="lineage-meta">Source: {label(entry.source)} · <Timestamp value={entry.created_at} /></p>
      </article>)}
    </section>
    <section className="card lineage-section" aria-label="Optional proposals">
      <h2 className="card-title">Optional proposals</h2>
      {data.proposals.length === 0 ? <p>No trade proposed.</p> : data.proposals.slice(0, 100).map((proposal, index) => <article className="lineage-event" key={proposal.proposal_id}>
        <h3 title={proposal.proposal_id}>Proposal {index + 1} · {shortId(proposal.proposal_id)}</h3>
        <p>Thesis: {bounded(proposal.thesis) || 'Not recorded'}</p>
        <p>Horizon: {bounded(proposal.horizon) || 'Not recorded'}</p>
        <p>Uncertainty: {bounded(proposal.uncertainty) || 'Not recorded'}</p>
        <Structure value={proposal.structure} />
        <p>Existing queue review: <strong>{label(proposal.review_status)}</strong> · Queue #{proposal.queue_id}</p>
        <p className="lineage-meta">Queue review is separate from broker submission and fills.</p>
      </article>)}
    </section>
    <section className="card lineage-section" aria-label="Mock orders">
      <h2 className="card-title">Mock orders</h2>
      {data.orders.length === 0 ? <p>No order recorded.</p> : data.orders.slice(0, 100).map((order, index) => <article className="lineage-event" key={order.order_id}>
        <h3 title={order.order_id}>Order {index + 1} · {shortId(order.order_id)}</h3>
        <p>Broker state: <strong>{label(order.status)}</strong></p>
        <p>Synchronization: <strong>{label(order.sync_state)}</strong></p>
        {(order.sync_state === 'unavailable' || order.sync_state === 'failed') && <p className="notice">Current synchronization {order.sync_state}. Last broker-confirmed state and fills are retained; current broker state is not verified.</p>}
        {order.status === 'submission_unknown' && <p>Submission outcome unknown. No broker acceptance inferred.</p>}
        <p>{order.broker_revision > 0 ? 'Mock broker confirmed' : 'Local submission record · Broker confirmation not recorded'} · {order.filled_qty} of {order.qty} contracts filled</p>
        <Structure value={order.structure} />
        <p className="lineage-meta">Linked queue #{order.queue_id} · Updated <Timestamp value={order.updated_at} /></p>
      </article>)}
    </section>
    <section className="card lineage-section" aria-label="Individual fills">
      <h2 className="card-title">Individual fills</h2>
      {data.fills.length === 0 ? <p>No broker-confirmed fills recorded.</p> : <div className="usage-table-wrap" role="region" aria-label="Scrollable confirmed fills" tabIndex={0}>
        <table className="usage-table"><thead><tr><th scope="col">Time (UTC)</th><th scope="col">Fill / order</th><th scope="col">Side</th><th scope="col">Contracts</th><th scope="col">Price per share (USD)</th><th scope="col">Source</th></tr></thead>
          <tbody>{data.fills.slice(0, 100).map(fill => <tr key={fill.fill_id}>
            <td><Timestamp value={fill.created_at} /></td><td title={fill.fill_id}>{shortId(fill.fill_id)}<div className="lineage-meta" title={fill.order_id}>Order {shortId(fill.order_id)}</div></td>
            <td>{label(fill.side)}</td><td>{fill.qty}</td><td>{dollars(fill.price)}</td><td>Mock broker confirmed</td>
          </tr>)}</tbody></table>
      </div>}
    </section>
    <section className="card lineage-section" aria-label="Positions and gross outcomes">
      <h2 className="card-title">Positions and gross outcomes</h2>
      {data.positions.length === 0 ? <p>No fill-linked position recorded. Acceptance alone does not establish a holding.</p> : data.positions.slice(0, 100).map(position => <article className="lineage-event" key={position.position_id}>
        <h3>{bounded(position.symbol, 80)} · {label(position.status)}</h3>
        <p>Confirmed quantity: {position.qty} contracts · Average entry per share: {dollars(position.average_entry_price)}</p>
        <p>Gross realized P&amp;L: <strong>{dollars(position.gross_realized_pnl)}</strong></p>
        <p className="lineage-meta">Mock fill-linked projection · Multiplier {position.multiplier}. Gross, not net of fees.</p>
        <p>Fees: Unavailable · Market mark: Unavailable · Market value: Unavailable · Unrealized P&amp;L: Unavailable</p>
      </article>)}
    </section>
    <section className="card lineage-section" aria-label="Optional later reviews">
      <h2 className="card-title">Optional later reviews</h2>
      {data.reviews.length === 0 ? <p>No later review recorded. Reviews are optional.</p> : data.reviews.slice(0, 100).map(review => <article className="lineage-event" key={review.review_id}>
        <p>{bounded(review.content)}</p><p className="lineage-meta">Later interpretation · <Timestamp value={review.created_at} /></p>
        {(review.proposal_id || review.order_id || review.position_id) && <p className="lineage-meta">References: {[review.proposal_id ? `Proposal ${shortId(review.proposal_id)}` : '', review.order_id ? `Order ${shortId(review.order_id)}` : '', review.position_id ? `Position ${shortId(review.position_id)}` : ''].filter(Boolean).join(' · ')}</p>}
      </article>)}
    </section>
    <section className="card lineage-section" aria-label="Event timeline">
      <h2 className="card-title">Event timeline</h2>
      {data.events.length === 0 ? <p>No lifecycle events recorded.</p> : <ol className="lineage-timeline">{data.events.slice(0, 100).map(event => <li className="lineage-event" key={event.event_id}>
        <strong>{label(event.kind)}</strong><p className="lineage-meta"><Timestamp value={event.created_at} /> · {eventAuthority(event)}</p>
        <EventPayload event={event} />
      </li>)}</ol>}
    </section>
  </div>
}

type ReadState<T> = { key: string; data: T | null; loading: boolean; error: boolean }
export default function InquiryHistory() {
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [listRetry, setListRetry] = useState(0)
  const [detailRetry, setDetailRetry] = useState(0)
  const [listState, setListState] = useState<ReadState<LineageListResponse>>({ key: '0', data: null, loading: true, error: false })
  const [detailState, setDetailState] = useState<ReadState<LineageDetailResponse>>({ key: '', data: null, loading: false, error: false })
  useEffect(() => {
    let cancelled = false
    setListState({ key: String(offset), data: null, loading: true, error: false })
    getLineageInquiries('alchemist', LIMIT, offset).then(data => {
      if (!cancelled) setListState({ key: String(offset), data, loading: false, error: false })
    }).catch(() => {
      if (!cancelled) setListState({ key: String(offset), data: null, loading: false, error: true })
    })
    return () => { cancelled = true }
  }, [offset, listRetry])
  useEffect(() => {
    if (!selected) return
    let cancelled = false
    setDetailState({ key: selected, data: null, loading: true, error: false })
    getLineageInquiry(selected, 'alchemist').then(data => {
      if (!cancelled) setDetailState({ key: selected, data, loading: false, error: false })
    }).catch(() => {
      if (!cancelled) setDetailState({ key: selected, data: null, loading: false, error: true })
    })
    return () => { cancelled = true }
  }, [selected, detailRetry])
  // Key matching hides stale content immediately, before effect cleanup runs.
  const listCurrent = listState.key === String(offset)
  const listLoading = !listCurrent || listState.loading
  const listError = listCurrent && listState.error
  const list = listCurrent && !listLoading && !listError ? listState.data : null
  const detailCurrent = detailState.key === selected
  const detailLoading = selected !== null && (!detailCurrent || detailState.loading)
  const detailError = selected !== null && detailCurrent && detailState.error
  const detail = detailCurrent && !detailLoading && !detailError ? detailState.data : null
  const nextDisabled = listLoading || !list || list.offset + LIMIT >= list.total || list.offset > MAX_OFFSET - LIMIT
  function changePage(nextOffset: number) { setSelected(null); setOffset(nextOffset) }
  return <div>
    <div className="page-header"><h1 className="page-title">Inquiry History</h1>
      <p className="page-sub">Optional inquiry, proposal, and mock execution records — read only.</p></div>
    <div className="notice">{IS_PREVIEW ? 'Alchemist · Mock lifecycle example' : 'Alchemist · Recorded mock lifecycle'}
      <p>Inquiries can remain open, pause, or be abandoned without proposing a trade. No live broker activity is shown.</p></div>
    <div className="lineage-layout">
      <section className="card lineage-sidebar" aria-label="Inquiries" aria-busy={listLoading}>
        <h2 className="card-title">Inquiries</h2>
        {listLoading && <p role="status">Loading inquiries…</p>}
        {listError && <div className="error-msg" role="alert">Inquiry list unavailable. Connected reads require operator authorization; browser login is not configured in this pilot.
          {' '}<button className="btn btn-ghost" type="button" onClick={() => setListRetry(value => value + 1)}>Retry inquiries</button></div>}
        {list && <>
          {list.truncated && <p className="notice">Inquiry metadata is truncated. Only recorded items available in this example are shown.</p>}
          {list.inquiries.length === 0 ? <p>No inquiries recorded on this page.</p> : <ul className="lineage-list">{list.inquiries.slice(0, LIMIT).map(inquiry => <li key={inquiry.inquiry_id}>
            <button type="button" className="btn btn-ghost lineage-inquiry" aria-pressed={selected === inquiry.inquiry_id} onClick={() => setSelected(inquiry.inquiry_id)}>{bounded(inquiry.title, 240)}</button>
            <p className="lineage-meta">{label(inquiry.state)} · Updated <Timestamp value={inquiry.updated_at} /></p>
          </li>)}</ul>}
          <p className="lineage-meta">{list.inquiries.length ? list.offset + 1 : 0}–{list.inquiries.length ? Math.min(list.offset + list.inquiries.length, list.total) : 0} of {list.total}</p>
        </>}
        <div className="usage-toolbar" aria-label="Inquiry pagination">
          <button type="button" className="btn btn-ghost" disabled={listLoading || !list || list.offset === 0} onClick={() => { if (list) changePage(Math.max(0, list.offset - LIMIT)) }}>Previous inquiries</button>
          <button type="button" className="btn btn-ghost" disabled={nextDisabled} onClick={() => { if (list) changePage(Math.min(MAX_OFFSET, list.offset + LIMIT)) }}>Next inquiries</button>
        </div>
      </section>
      <section aria-label="Inquiry detail" aria-busy={detailLoading}>
        {!selected && <p className="card">Select an inquiry to read its history.</p>}
        {detailLoading && <p role="status">Loading inquiry history…</p>}
        {detailError && <div className="error-msg" role="alert">Inquiry history unavailable. A failed read is not an empty history.
          {' '}<button className="btn btn-ghost" type="button" onClick={() => setDetailRetry(value => value + 1)}>Retry history</button></div>}
        {detail && <HistoryDetail data={detail} />}
      </section>
    </div>
  </div>
}

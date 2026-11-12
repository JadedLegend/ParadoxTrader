import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getQueue, approveTrade, rejectTrade } from '../api'

export default function TradeQueue() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [acting, setActing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const alive = useRef(true)
  const request = useRef(0)

  const load = useCallback(async () => {
    const current = ++request.current
    try {
      const d = await getQueue()
      if (!alive.current || current !== request.current) return
      setTrades((d.trades || []).map((entry: any) => {
        const proposal = entry.proposal && typeof entry.proposal === 'object' ? entry.proposal : entry
        return { ...proposal, id: entry.id, agent_id: entry.agent_id, created_at: entry.created_at,
          quantity: proposal.qty ?? proposal.quantity }
      }))
      setLoaded(true)
      setError('')
    } catch { if (alive.current && current === request.current) setError('Could not load the trade queue. Displayed trades may be stale; use Refresh to retry before making a decision.') }
    finally { if (alive.current && current === request.current) setLoading(false) }
  }, [])

  useEffect(() => {
    alive.current = true
    void load()
    const timer = IS_PREVIEW ? null : setInterval(load, 20000)
    return () => { alive.current = false; if (timer) clearInterval(timer) }
  }, [load])

  const handleApprove = async (id: number) => {
    if (IS_PREVIEW || acting !== null || error) return
    setActing(id)
    try { await approveTrade(id, notes[id] || ''); if (alive.current) await load() }
    catch { if (alive.current) setError('Approval failed or could not be confirmed. Refresh the queue and verify trade status before retrying.') }
    finally { if (alive.current) setActing(null) }
  }
  const handleReject = async (id: number) => {
    if (IS_PREVIEW || acting !== null || error) return
    setActing(id)
    try { await rejectTrade(id, notes[id] || ''); if (alive.current) await load() }
    catch { if (alive.current) setError('Rejection failed or could not be confirmed. Refresh the queue and verify trade status before retrying.') }
    finally { if (alive.current) setActing(null) }
  }

  return (
    <div>
      <div className="page-header flex-between">
        <div><div className="page-title">Trade Queue</div><div className="page-sub">Pending trades awaiting your review</div></div>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </div>
      {IS_PREVIEW && <div className="notice">Fixture trade proposals only — these are not broker orders. Approval, rejection, and review-note submission are disabled in preview; no trade is executed.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}
      {loading ? <div className="loading">Loading...</div> : !loaded ? null : trades.length === 0 ? <div className="card"><div className="empty-state">No trades pending review.<br /><span style={{fontSize:12, marginTop:8, display:'block'}}>When autonomous_trading_mode is off, the Paradox Hunter's trade ideas will appear here for your approval.</span></div></div> : trades.map(t => <div key={t.id} className="trade-item">
        <div className="trade-header"><div><span className="trade-symbol">{t.symbol}</span><span className="trade-agent" style={{marginLeft:10}}>via {t.agent_id?.replace(/_/g,' ')}</span></div><span className={`trade-side ${t.side?.toLowerCase()}`}>{t.side}</span></div>
        <div style={{display:'flex', gap:20, flexWrap:'wrap', fontSize:13, color:'var(--text2)', marginBottom:8}}>
          {t.quantity != null && <span><strong>Qty:</strong> {t.quantity}</span>}
          {t.order_type && <span><strong>Type:</strong> {t.order_type}</span>}
          {t.limit_price != null && <span><strong>Limit:</strong> ${t.limit_price}</span>}
          {t.stop_price != null && <span><strong>Stop:</strong> ${t.stop_price}</span>}
          {t.expiry && <span><strong>Expiry:</strong> {t.expiry}</span>}
          {t.strike != null && <span><strong>Strike:</strong> ${t.strike}</span>}
          {t.option_type && <span><strong>Option:</strong> {t.option_type}</span>}
        </div>
        {t.thesis && <div className="trade-thesis">"{t.thesis}"</div>}
        {t.council_summary && <div style={{background:'var(--bg)', borderRadius:6, padding:'10px 14px', marginTop:8, fontSize:12, color:'var(--text2)', lineHeight:1.7}}><div style={{fontSize:11, color:'var(--text3)', marginBottom:4, textTransform:'uppercase', letterSpacing:'0.5px'}}>Council Summary</div>{t.council_summary}</div>}
        <div style={{marginTop:12}}>
          <input className="input" aria-label={`Review notes for ${t.symbol}`} placeholder={IS_PREVIEW ? 'Review notes disabled in preview' : 'Optional notes...'} value={notes[t.id] || ''} disabled={IS_PREVIEW || acting !== null} onChange={e => setNotes(n => ({...n, [t.id]:e.target.value}))} style={{marginBottom:8}} />
          <div className="trade-actions">
            <button className="btn btn-success" onClick={() => handleApprove(t.id)} disabled={IS_PREVIEW || acting !== null || Boolean(error)}>{acting === t.id ? 'Working...' : 'Approve'}</button>
            <button className="btn btn-danger" onClick={() => handleReject(t.id)} disabled={IS_PREVIEW || acting !== null || Boolean(error)}>{acting === t.id ? 'Working...' : 'Reject'}</button>
          </div>
        </div>
      </div>)}
    </div>
  )
}

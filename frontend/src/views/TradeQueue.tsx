import { useEffect, useState } from 'react'
import { getQueue, approveTrade, rejectTrade } from '../api'

export default function TradeQueue() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [acting, setActing] = useState<number | null>(null)

  const load = async () => {
    try {
      const d = await getQueue()
      setTrades(d.trades || [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t) }, [])

  const handleApprove = async (id: number) => {
    setActing(id)
    try { await approveTrade(id, notes[id] || ''); load() }
    finally { setActing(null) }
  }

  const handleReject = async (id: number) => {
    setActing(id)
    try { await rejectTrade(id, notes[id] || ''); load() }
    finally { setActing(null) }
  }

  return (
    <div>
      <div className="page-header flex-between">
        <div>
          <div className="page-title">Trade Queue</div>
          <div className="page-sub">Pending trades awaiting your review</div>
        </div>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </div>

      {loading ? <div className="loading">Loading...</div> :
       trades.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            No trades pending review.<br />
            <span style={{fontSize:12, marginTop:8, display:'block'}}>When autonomous_trading_mode is off, the Paradox Hunter's trade ideas will appear here for your approval.</span>
          </div>
        </div>
       ) : trades.map(t => (
        <div key={t.id} className="trade-item">
          <div className="trade-header">
            <div>
              <span className="trade-symbol">{t.symbol}</span>
              <span className="trade-agent" style={{marginLeft:10}}>via {t.agent_id?.replace('_',' ')}</span>
            </div>
            <span className={`trade-side ${t.side?.toLowerCase()}`}>{t.side}</span>
          </div>

          <div style={{display:'flex', gap:20, flexWrap:'wrap', fontSize:13, color:'var(--text2)', marginBottom:8}}>
            {t.quantity && <span><strong>Qty:</strong> {t.quantity}</span>}
            {t.order_type && <span><strong>Type:</strong> {t.order_type}</span>}
            {t.limit_price && <span><strong>Limit:</strong> ${t.limit_price}</span>}
            {t.stop_price && <span><strong>Stop:</strong> ${t.stop_price}</span>}
            {t.expiry && <span><strong>Expiry:</strong> {t.expiry}</span>}
            {t.strike && <span><strong>Strike:</strong> ${t.strike}</span>}
            {t.option_type && <span><strong>Option:</strong> {t.option_type}</span>}
          </div>

          {t.thesis && <div className="trade-thesis">"{t.thesis}"</div>}

          {t.council_summary && (
            <div style={{background:'var(--bg)', borderRadius:6, padding:'10px 14px', marginTop:8, fontSize:12, color:'var(--text2)', lineHeight:1.7}}>
              <div style={{fontSize:11, color:'var(--text3)', marginBottom:4, textTransform:'uppercase', letterSpacing:'0.5px'}}>Council Summary</div>
              {t.council_summary}
            </div>
          )}

          <div style={{marginTop:12}}>
            <input
              className="input"
              placeholder="Optional notes..."
              value={notes[t.id] || ''}
              onChange={e => setNotes(n => ({...n, [t.id]: e.target.value}))}
              style={{marginBottom:8}}
            />
            <div className="trade-actions">
              <button className="btn btn-success" onClick={() => handleApprove(t.id)} disabled={acting === t.id}>
                {acting === t.id ? '...' : 'Approve'}
              </button>
              <button className="btn btn-danger" onClick={() => handleReject(t.id)} disabled={acting === t.id}>
                {acting === t.id ? '...' : 'Reject'}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

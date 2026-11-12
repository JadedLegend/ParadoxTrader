import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getInbox, sendDM, getSelfDefinition } from '../api'

const AGENTS = ['tempest','siren','alchemist','weaver','oracle','shadow','paradox_hunter']

const AGENT_COLORS: Record<string, string> = {
  tempest: '#7c6af7',
  siren: '#f6ad55',
  alchemist: '#68d391',
  weaver: '#4fd1c5',
  oracle: '#90cdf4',
  shadow: '#fc8181',
  paradox_hunter: '#b794f4',
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ─── Clickable agent name with definition dropdown ────────────────────────────

function AgentNameBadge({ name }: { name: string }) {
  const [open, setOpen] = useState(false)
  const [defData, setDefData] = useState<{ self_definition: string } | null>(null)
  const [error, setError] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const agentId = name.toLowerCase().replace(/ /g, '_')
  const isAgent = AGENTS.includes(agentId)
  const color = AGENT_COLORS[agentId] || 'var(--text)'

  useEffect(() => {
    if (!open || !isAgent) return
    let cancelled = false
    setDefData(null)
    setError('')
    getSelfDefinition(agentId).then(d => { if (!cancelled) setDefData(d) })
      .catch(() => { if (!cancelled) setError('Could not load this definition. Close and reopen to retry.') })
    return () => { cancelled = true }
  }, [open, agentId, isAgent])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!isAgent) {
    return <span className="msg-from">{name.replace('_', ' ')}</span>
  }

  return (
    <div ref={ref} style={{position:'relative', display:'inline-block'}}>
      <button
        className="msg-from"
        style={{color, cursor:'pointer', textDecoration:'underline dotted', textUnderlineOffset:3, background:'none', border:0, padding:0, fontFamily:'inherit'}}
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        title="Click to see definition"
      >
        {name.replace('_', ' ')}
      </button>
      {open && (
        <div style={{
          position:'absolute', top:'100%', left:0, zIndex:100,
          background:'var(--bg2)', border:`1px solid ${color}`,
          borderRadius:8, padding:'12px 14px', minWidth:260, maxWidth:340,
          boxShadow:'0 4px 24px rgba(0,0,0,0.4)',
        }}>
          <div style={{fontSize:11, fontWeight:700, color, marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>
            {name.replace('_', ' ')}
          </div>
          {error ? <div className="error-msg" role="alert">{error}</div> : !defData ? <div className="loading">Loading definition...</div> : defData.self_definition ? (
            <div style={{fontSize:12, color:'var(--text)', lineHeight:1.7, fontStyle:'italic'}}>
              {defData.self_definition}
            </div>
          ) : (
            <div style={{fontSize:12, color:'var(--text3)', fontStyle:'italic'}}>No self-definition set yet.</div>
          )}
          <button
            style={{marginTop:8, fontSize:10, color:'var(--text3)', background:'none', border:'none', cursor:'pointer', padding:0}}
            onClick={() => setOpen(false)}
          >
            close
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Inbox() {
  const [selected, setSelected] = useState('user')
  const [msgs, setMsgs] = useState<any[]>([])
  const [unread, setUnread] = useState(0)
  const [content, setContent] = useState('')
  const [recipient, setRecipient] = useState('tempest')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [loadedInbox, setLoadedInbox] = useState<string | null>(null)
  const alive = useRef(true)
  const request = useRef(0)
  const selectedRef = useRef(selected)
  selectedRef.current = selected

  const load = useCallback(async () => {
    const current = ++request.current
    try {
      const data = await getInbox(selected)
      if (!alive.current || current !== request.current || selectedRef.current !== selected) return
      setMsgs(data.messages || [])
      setUnread(data.unread_count || 0)
      setLoadedInbox(selected)
      setError('')
    } catch { if (alive.current && current === request.current && selectedRef.current === selected) setError('Could not load this inbox. Displayed messages may be stale; use Refresh to retry.') }
    finally { if (alive.current && current === request.current && selectedRef.current === selected) setLoading(false) }
  }, [selected])

  useEffect(() => {
    alive.current = true
    setLoading(true)
    setMsgs([])
    setUnread(0)
    setLoadedInbox(null)
    setError('')
    void load()
    const timer = IS_PREVIEW ? null : setInterval(load, 20000)
    return () => { alive.current = false; if (timer) clearInterval(timer) }
  }, [load])

  const handleSend = async () => {
    if (IS_PREVIEW || !content.trim() || sending) return
    setSending(true)
    try {
      await sendDM('user', recipient, content)
      if (!alive.current || selectedRef.current !== selected) return
      setContent('')
      await load()
    } catch { if (alive.current) setError('Could not confirm message delivery. Your draft is retained; refresh the inbox before retrying to avoid duplicates.') }
    finally { if (alive.current) setSending(false) }
  }

  return (
    <div>
      <div className="page-header flex-between">
        <div>
          <div className="page-title">Messages</div>
          <div className="page-sub">Direct messages — click an agent name to see their self-definition</div>
        </div>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </div>

      {IS_PREVIEW && <div className="notice">Fixture messages only. Sending is disabled in preview; no direct message is delivered.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}

      {/* Inbox selector */}
      <div className="flex gap-8 mb-16" style={{flexWrap:'wrap'}}>
        <button className={`btn ${selected === 'user' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} disabled={sending} onClick={() => setSelected('user')}>
          My Inbox {unread > 0 && selected === 'user' && <span className="msg-unread" style={{marginLeft:6}}>{unread}</span>}
        </button>
        {AGENTS.map(a => (
          <button key={a} className={`btn ${selected === a ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} disabled={sending} onClick={() => setSelected(a)}>
            {a.replace('_',' ')}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="card mb-16" style={{minHeight:200, maxHeight:400, overflowY:'auto'}}>
        {loading ? <div className="loading">Loading...</div> :
         loadedInbox !== selected ? null :
         msgs.length === 0 ? <div className="empty-state">No messages.</div> :
         msgs.map(m => (
          <div key={m.id} className="msg-item">
            <div className="msg-meta">
              <AgentNameBadge key={`from-${m.sender}`} name={m.sender} />
              <span style={{color:'var(--text3)', fontSize:11}}>→</span>
              <AgentNameBadge key={`to-${m.recipient}`} name={m.recipient} />
              <span className="msg-time">{timeAgo(m.created_at)}</span>
              {!m.read && <span className="msg-unread">unread</span>}
            </div>
            <div className="msg-content">{m.content}</div>
          </div>
        ))}
      </div>

      {/* Compose */}
      <div className="card">
        <div className="card-title">Send a Message</div>
        <div className="input-group">
          <label className="input-label">To</label>
          <select aria-label="Message recipient" className="select" value={recipient} disabled={IS_PREVIEW || sending} onChange={e => setRecipient(e.target.value)}>
            {AGENTS.map(a => <option key={a} value={a}>{a.replace('_',' ')}</option>)}
          </select>
        </div>
        <div className="input-group">
          <label className="input-label">Message</label>
          <textarea
            className="input"
            rows={4}
            aria-label="Message content"
            disabled={IS_PREVIEW || sending}
            placeholder={IS_PREVIEW ? 'Sending disabled in preview' : 'Write your message...'}
            value={content}
            onChange={e => setContent(e.target.value)}
          />
        </div>
        <button className="btn btn-primary" onClick={handleSend} disabled={IS_PREVIEW || sending || !content.trim()}>
          {sending ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

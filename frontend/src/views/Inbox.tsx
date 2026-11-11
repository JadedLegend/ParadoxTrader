import { useEffect, useRef, useState } from 'react'
import { getInbox, sendDM, getSelfDefinition } from '../api'

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
  const ref = useRef<HTMLDivElement>(null)

  const agentId = name.toLowerCase().replace(/ /g, '_')
  const isAgent = AGENTS.includes(agentId)
  const color = AGENT_COLORS[agentId] || 'var(--text)'

  const handleClick = async () => {
    if (!isAgent) return
    if (!open && !defData) {
      try {
        const d = await getSelfDefinition(agentId)
        setDefData(d)
      } catch { setDefData({ self_definition: '' }) }
    }
    setOpen(o => !o)
  }

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
      <span
        className="msg-from"
        style={{color, cursor:'pointer', textDecoration:'underline dotted', textUnderlineOffset:3}}
        onClick={handleClick}
        title="Click to see definition"
      >
        {name.replace('_', ' ')}
      </span>
      {open && defData && (
        <div style={{
          position:'absolute', top:'100%', left:0, zIndex:100,
          background:'var(--bg2)', border:`1px solid ${color}`,
          borderRadius:8, padding:'12px 14px', minWidth:260, maxWidth:340,
          boxShadow:'0 4px 24px rgba(0,0,0,0.4)',
        }}>
          <div style={{fontSize:11, fontWeight:700, color, marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>
            {name.replace('_', ' ')}
          </div>
          {defData.self_definition ? (
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

  const load = async () => {
    try {
      const data = await getInbox(selected)
      setMsgs(data.messages || [])
      setUnread(data.unread_count || 0)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t) }, [selected])

  const handleSend = async () => {
    if (!content.trim()) return
    setSending(true)
    try {
      await sendDM('user', recipient, content)
      setContent('')
      load()
    } finally { setSending(false) }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Messages</div>
        <div className="page-sub">Direct messages — click an agent name to see their self-definition</div>
      </div>

      {/* Inbox selector */}
      <div className="flex gap-8 mb-16" style={{flexWrap:'wrap'}}>
        <button className={`btn ${selected === 'user' ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setSelected('user')}>
          My Inbox {unread > 0 && selected === 'user' && <span className="msg-unread" style={{marginLeft:6}}>{unread}</span>}
        </button>
        {AGENTS.map(a => (
          <button key={a} className={`btn ${selected === a ? 'btn-primary' : 'btn-ghost'}`} style={{fontSize:12}} onClick={() => setSelected(a)}>
            {a.replace('_',' ')}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="card mb-16" style={{minHeight:200, maxHeight:400, overflowY:'auto'}}>
        {loading ? <div className="loading">Loading...</div> :
         msgs.length === 0 ? <div className="empty-state">No messages.</div> :
         msgs.map(m => (
          <div key={m.id} className="msg-item">
            <div className="msg-meta">
              <AgentNameBadge name={m.sender} />
              <span style={{color:'var(--text3)', fontSize:11}}>→</span>
              <AgentNameBadge name={m.recipient} />
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
          <select className="select" value={recipient} onChange={e => setRecipient(e.target.value)}>
            {AGENTS.map(a => <option key={a} value={a}>{a.replace('_',' ')}</option>)}
          </select>
        </div>
        <div className="input-group">
          <label className="input-label">Message</label>
          <textarea
            className="input"
            rows={4}
            placeholder="Write your message..."
            value={content}
            onChange={e => setContent(e.target.value)}
          />
        </div>
        <button className="btn btn-primary" onClick={handleSend} disabled={sending || !content.trim()}>
          {sending ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

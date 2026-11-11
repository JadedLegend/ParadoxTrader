import { useEffect, useRef, useState } from 'react'
import { getForum, postToForum, getThreads, getSelfDefinition } from '../api'

const AGENT_COLORS: Record<string, string> = {
  tempest: '#7c6af7',
  siren: '#f6ad55',
  alchemist: '#68d391',
  weaver: '#4fd1c5',
  oracle: '#90cdf4',
  shadow: '#fc8181',
  paradox_hunter: '#b794f4',
}

const AGENT_IDS = ['tempest', 'siren', 'alchemist', 'weaver', 'oracle', 'shadow', 'paradox_hunter']

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

function AgentNameBadge({ author }: { author: string }) {
  const [open, setOpen] = useState(false)
  const [defData, setDefData] = useState<{ self_definition: string } | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  const agentId = author.toLowerCase().replace(/ /g, '_')
  const isAgent = AGENT_IDS.includes(agentId)
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

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!isAgent) {
    return (
      <span className={`post-author ${author === 'SYSTEM' ? 'system' : ''}`}>
        {author.replace('_', ' ')}
      </span>
    )
  }

  return (
    <div ref={ref} style={{position:'relative', display:'inline-block'}}>
      <span
        className="post-author"
        style={{color, cursor:'pointer', textDecoration:'underline dotted', textUnderlineOffset:3}}
        onClick={handleClick}
        title="Click to see definition"
      >
        {author.replace('_', ' ')}
      </span>
      {open && defData && (
        <div style={{
          position:'absolute', top:'100%', left:0, zIndex:100,
          background:'var(--bg2)', border:`1px solid ${color}`,
          borderRadius:8, padding:'12px 14px', minWidth:260, maxWidth:340,
          boxShadow:'0 4px 24px rgba(0,0,0,0.4)',
        }}>
          <div style={{fontSize:11, fontWeight:700, color, marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>
            {author.replace('_', ' ')}
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

export default function Forum() {
  const [posts, setPosts] = useState<any[]>([])
  const [threads, setThreads] = useState<any[]>([])
  const [activeThread, setActiveThread] = useState('general')
  const [content, setContent] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    try {
      const [p, t] = await Promise.all([getForum(100, activeThread), getThreads()])
      setPosts(p.posts || [])
      setThreads(t.threads || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [activeThread])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [posts])

  const handlePost = async () => {
    if (!content.trim()) return
    setSending(true)
    try {
      await postToForum('user', content, activeThread)
      setContent('')
      load()
    } finally {
      setSending(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handlePost()
  }

  return (
    <div style={{display:'flex', flexDirection:'column', height:'calc(100vh - 56px)'}}>
      <div className="page-header flex-between">
        <div>
          <div className="page-title">Forum</div>
          <div className="page-sub">The shared council chamber — click an agent name to see their self-definition</div>
        </div>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </div>

      {/* Thread tabs */}
      <div className="flex gap-8 mb-16" style={{flexWrap:'wrap'}}>
        {['general', 'council_deliberation', ...(threads.filter(t => t.id !== 'general' && t.id !== 'council_deliberation').map((t: any) => t.id))].map(tid => (
          <button
            key={tid}
            className={`btn ${activeThread === tid ? 'btn-primary' : 'btn-ghost'}`}
            style={{fontSize:12}}
            onClick={() => setActiveThread(tid)}
          >
            {tid.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Posts */}
      <div className="card" style={{flex:1, overflowY:'auto', marginBottom:16}}>
        {loading ? <div className="loading">Loading...</div> :
         posts.length === 0 ? <div className="empty-state">No posts yet. The chamber is quiet.</div> :
         posts.map(p => (
          <div key={p.id} className="forum-post">
            <div className="post-meta">
              <AgentNameBadge author={p.author} />
              <span className="post-time">{timeAgo(p.created_at)}</span>
              {p.thread_id !== 'general' && <span className="post-thread">{p.thread_id.replace(/_/g,' ')}</span>}
              {p.tags?.map((tag: string) => <span key={tag} className="tag">{tag}</span>)}
            </div>
            <div className="post-content">{p.content}</div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Compose */}
      <div className="forum-input-wrap">
        <textarea
          className="forum-input"
          rows={3}
          placeholder="Post to the forum... (Ctrl+Enter to send)"
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={handleKey}
        />
        <button className="btn btn-primary" onClick={handlePost} disabled={sending || !content.trim()}>
          {sending ? '...' : 'Post'}
        </button>
      </div>
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, IS_PRIVATE_HOST, getForum, postToForum, getThreads, getSelfDefinition } from '../api'
import HostUnavailable from '../components/HostUnavailable'

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
  const [error, setError] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const agentId = author.toLowerCase().replace(/ /g, '_')
  const isAgent = AGENT_IDS.includes(agentId)
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
      <button
        className="post-author"
        style={{color, cursor:'pointer', textDecoration:'underline dotted', textUnderlineOffset:3, background:'none', border:0, padding:0, fontFamily:'inherit'}}
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        title="Click to see definition"
      >
        {author.replace('_', ' ')}
      </button>
      {open && (
        <div style={{
          position:'absolute', top:'100%', left:0, zIndex:100,
          background:'var(--bg2)', border:`1px solid ${color}`,
          borderRadius:8, padding:'12px 14px', minWidth:260, maxWidth:340,
          boxShadow:'0 4px 24px rgba(0,0,0,0.4)',
        }}>
          <div style={{fontSize:11, fontWeight:700, color, marginBottom:6, textTransform:'uppercase', letterSpacing:1}}>
            {author.replace('_', ' ')}
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

function FullForum() {
  const [posts, setPosts] = useState<any[]>([])
  const [threads, setThreads] = useState<any[]>([])
  const [activeThread, setActiveThread] = useState('general')
  const [content, setContent] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [loadedThread, setLoadedThread] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const alive = useRef(true)
  const request = useRef(0)
  const threadRef = useRef(activeThread)
  threadRef.current = activeThread

  const load = useCallback(async () => {
    const current = ++request.current
    try {
      const [p, t] = await Promise.all([getForum(100, activeThread), getThreads()])
      if (!alive.current || current !== request.current || threadRef.current !== activeThread) return
      setPosts(p.posts || [])
      setThreads(t.threads || [])
      setLoadedThread(activeThread)
      setError('')
    } catch {
      if (alive.current && current === request.current && threadRef.current === activeThread) setError('Could not load this forum thread. Displayed posts may be stale; use Refresh to retry.')
    } finally {
      if (alive.current && current === request.current && threadRef.current === activeThread) setLoading(false)
    }
  }, [activeThread])

  useEffect(() => {
    alive.current = true
    setLoading(true)
    setPosts([])
    setLoadedThread(null)
    setError('')
    void load()
    const timer = IS_PREVIEW ? null : setInterval(load, 15000)
    return () => { alive.current = false; if (timer) clearInterval(timer) }
  }, [load])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [posts])

  const handlePost = async () => {
    if (IS_PREVIEW || !content.trim() || sending) return
    setSending(true)
    try {
      await postToForum('user', content, activeThread)
      if (!alive.current || threadRef.current !== activeThread) return
      setContent('')
      await load()
    } catch {
      if (alive.current) setError('Could not confirm the forum post. Your draft is retained; refresh the thread before retrying to avoid duplicates.')
    } finally {
      if (alive.current) setSending(false)
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

      {IS_PREVIEW && <div className="notice">Fixture conversations only. Posting is disabled in preview; no message is sent to the council.</div>}
      {error && <div className="error-msg" role="alert">{error}</div>}

      {/* Thread tabs */}
      <div className="flex gap-8 mb-16" style={{flexWrap:'wrap'}}>
        {['general', 'council_deliberation', ...(threads.filter(t => t.id !== 'general' && t.id !== 'council_deliberation').map((t: any) => t.id))].map(tid => (
          <button
              key={tid}
              className={`btn ${activeThread === tid ? 'btn-primary' : 'btn-ghost'}`}
              style={{fontSize:12}}
              disabled={sending}
              onClick={() => setActiveThread(tid)}
          >
            {tid.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Posts */}
      <div className="card" style={{flex:1, overflowY:'auto', marginBottom:16}}>
        {loading ? <div className="loading">Loading...</div> :
         loadedThread !== activeThread ? null :
         posts.length === 0 ? <div className="empty-state">No posts yet. The chamber is quiet.</div> :
         posts.map(p => (
          <div key={p.id} className="forum-post">
            <div className="post-meta">
              <AgentNameBadge key={p.author} author={p.author} />
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
          aria-label="Forum post"
          disabled={IS_PREVIEW || sending}
          placeholder={IS_PREVIEW ? 'Posting disabled in preview' : 'Post to the forum... (Ctrl+Enter to send)'}
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={handleKey}
        />
        <button className="btn btn-primary" onClick={handlePost} disabled={IS_PREVIEW || sending || !content.trim()}>
          {sending ? '...' : 'Post'}
        </button>
      </div>
    </div>
  )
}

// The private host serves session records only; this page has no data source there,
// so nothing is requested and no write control is rendered.
function PrivateForum() {
  return <HostUnavailable title="Community" sub="The shared council chamber" links={[{ to: '/rehearsal', label: 'Open Sessions' }, { to: '/journals', label: 'Open Journals' }]}>
    <p>Agents do not post to a shared forum in recorded sessions, and this host serves no forum. Each session’s runs are read under Sessions, and any notes the agents kept under Journals.</p>
  </HostUnavailable>
}

export default function Forum() {
  return IS_PRIVATE_HOST ? <PrivateForum /> : <FullForum />
}

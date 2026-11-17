import { Component, lazy, Suspense } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Link } from 'react-router-dom'
import Dashboard from './views/Dashboard'
import Forum from './views/Forum'
import Inbox from './views/Inbox'
import TradeQueue from './views/TradeQueue'
import Agents from './views/Agents'
import Config from './views/Config'
import WakeChoices from './views/WakeChoices'
import { IS_PREVIEW, IS_PRIVATE_HOST } from './api'
import './styles.css'

const Library = lazy(() => import('./views/Library'))
const Costs = lazy(() => import('./views/Costs'))
const InquiryHistory = lazy(() => import('./views/InquiryHistory'))
const Rehearsal = lazy(() => import('./views/Rehearsal'))
const Journals = lazy(() => import('./views/Journals'))

class ScreenBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Screen rendering failed', error, info.componentStack) }
  render() {
    if (this.state.failed) return <div className="card" role="alert"><h1 className="page-title">This screen could not be displayed</h1><p className="page-sub">No action was triggered by this rendering error.</p><button className="btn btn-ghost mt-16" onClick={() => window.location.reload()}>Reload preview</button></div>
    return this.props.children
  }
}

const NAV = [
  ['/', 'Dashboard'], ['/choices', 'Wake Choices'], ['/agents', 'Agents'],
  ['/rehearsal', 'Sessions'], ['/journals', 'Journals'], ['/inquiries', 'Inquiry History'], ['/library', 'Library'], ['/costs', 'Costs'], ['/forum', 'Community'], ['/inbox', 'Messages'], ['/queue', 'Trade Queue'], ['/config', 'Configuration'],
]

export default function App() {
  return (
    <BrowserRouter>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="app">
        <nav className="sidebar" aria-label="Main navigation">
          <div className="logo"><span className="logo-symbol" aria-hidden="true">⬡</span><div className="logo-text"><span className="logo-title">Paradox Edge</span><span className="logo-sub">Trader · community</span></div></div>
          <div className="nav-links">{NAV.map(([path, label]) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>{label}</NavLink>)}</div>
          <div className="sidebar-footnote">Individual perspectives.<br />A shared purpose.</div>
        </nav>
        <main className="main-content" id="main" tabIndex={-1}>
          <div className={`mode-banner ${IS_PREVIEW ? 'preview-mode' : IS_PRIVATE_HOST ? 'private-host-mode' : 'connected-mode'}`} role="note">
            <strong>{IS_PREVIEW ? 'Fixture preview' : IS_PRIVATE_HOST ? 'Private host · read only' : 'Connected frontend'}</strong>
            <span>{IS_PREVIEW ? 'Local agent and portfolio examples; Library reads imported source text. No agents, providers, accounts, or schedules are running through this preview.'
              : IS_PRIVATE_HOST ? 'Recorded session runs from this server; Library reads the bundled source text. Pages with no data source here say so. Nothing on this site starts, wakes, or changes anything.'
              : 'Backend requests enabled by build configuration. Backend permissions and scheduler behavior apply.'}</span>
          </div>
          <ScreenBoundary>
            <Suspense fallback={<div className="loading" role="status">Loading screen...</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/choices" element={<WakeChoices />} />
              <Route path="/library" element={<Library />} />
              <Route path="/costs" element={<Costs />} />
              <Route path="/inquiries" element={<InquiryHistory />} />
              <Route path="/rehearsal" element={<Rehearsal />} />
              <Route path="/journals" element={<Journals />} />
              <Route path="/forum" element={<Forum />} />
              <Route path="/inbox" element={<Inbox />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/queue" element={<TradeQueue />} />
              <Route path="/config" element={<Config />} />
              <Route path="*" element={<div className="card"><h1 className="page-title">Page not found</h1><Link to="/" className="btn btn-ghost mt-16">Return to dashboard</Link></div>} />
            </Routes>
            </Suspense>
          </ScreenBoundary>
        </main>
      </div>
    </BrowserRouter>
  )
}

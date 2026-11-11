import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './views/Dashboard'
import Forum from './views/Forum'
import Inbox from './views/Inbox'
import TradeQueue from './views/TradeQueue'
import Agents from './views/Agents'
import Config from './views/Config'
import './styles.css'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="logo">
            <span className="logo-symbol">⬡</span>
            <div className="logo-text">
              <span className="logo-title">Paradox Edge</span>
              <span className="logo-sub">Trader v2</span>
            </div>
          </div>
          <NavLink to="/" end className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ◈ Dashboard
          </NavLink>
          <NavLink to="/forum" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ◉ Forum
          </NavLink>
          <NavLink to="/inbox" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ◎ Messages
          </NavLink>
          <NavLink to="/agents" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ◆ Agents
          </NavLink>
          <NavLink to="/queue" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ◇ Trade Queue
          </NavLink>
          <NavLink to="/config" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
            ⊕ Config
          </NavLink>
        </nav>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/forum" element={<Forum />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/queue" element={<TradeQueue />} />
            <Route path="/config" element={<Config />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

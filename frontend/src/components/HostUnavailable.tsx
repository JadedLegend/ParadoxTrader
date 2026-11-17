import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface Props {
  title: string
  sub?: string
  /** Why this page has no data source on the private host, in the page's own words. */
  children: ReactNode
  links?: { to: string; label: string }[]
}

// Shown instead of a page whose backend is not served by the private host
// (deploy/private_dashboard.py serves session records only). No request is made.
export default function HostUnavailable({ title, sub, children, links = [] }: Props) {
  return (
    <section aria-labelledby="host-unavailable-title">
      <header className="page-header">
        <h1 className="page-title" id="host-unavailable-title">{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </header>
      <div className="notice host-unavailable" role="note">
        <strong>Not available on this host</strong>
        {children}
      </div>
      {links.length > 0 && <div className="host-unavailable-links">
        {links.map(link => <Link key={link.to} className="btn btn-ghost" to={link.to}>{link.label}</Link>)}
      </div>}
    </section>
  )
}

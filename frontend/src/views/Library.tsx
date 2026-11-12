import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_PREVIEW, getLibraryDocuments, searchLibrary, getLibrarySection } from '../api'
import type {
  LibraryDocumentsResponse, LibrarySearchResponse, LibrarySectionResponse,
} from '../library/contracts'

const CATALOG_LIMIT = 50
const READ_LIMIT = 1200

function SourceHash({ sha256 }: { sha256: string }) {
  return <span className="library-hash" title={sha256} aria-label={`SHA-256 ${sha256}`}>SHA-256 {sha256.slice(0, 12)}…</span>
}

export default function Library() {
  const [catalog, setCatalog] = useState<LibraryDocumentsResponse | null>(null)
  const [catalogOffset, setCatalogOffset] = useState(0)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState<LibrarySearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [reader, setReader] = useState<LibrarySectionResponse | null>(null)
  const [readerLoading, setReaderLoading] = useState(false)
  const [readerError, setReaderError] = useState('')
  const [readerHistory, setReaderHistory] = useState<number[]>([])
  const alive = useRef(true)
  const catalogRequest = useRef(0)
  const searchRequest = useRef(0)
  const readerRequest = useRef(0)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const loadCatalog = useCallback(async (offset: number) => {
    const request = ++catalogRequest.current
    setCatalogLoading(true)
    setCatalogError('')
    setCatalog(null)
    try {
      const data = await getLibraryDocuments(CATALOG_LIMIT, offset)
      if (!alive.current || request !== catalogRequest.current) return
      setCatalog(data)
      setCatalogOffset(data.offset)
    } catch {
      if (alive.current && request === catalogRequest.current) {
        setCatalogError('Could not load the library catalog. Use Retry catalog to try again.')
      }
    } finally {
      if (alive.current && request === catalogRequest.current) setCatalogLoading(false)
    }
  }, [])

  useEffect(() => { void loadCatalog(0) }, [loadCatalog])

  const clearReader = () => {
    ++readerRequest.current
    setReader(null)
    setReaderHistory([])
    setReaderError('')
    setReaderLoading(false)
  }

  const resetSearch = () => {
    ++searchRequest.current
    setSearch(null)
    setSearchError('')
    setSearchLoading(false)
    clearReader()
  }

  const submitSearch = async () => {
    const query = draft.trim()
    const request = ++searchRequest.current
    clearReader()
    setSearch(null)
    setSearchError('')
    if (!query) { setSearchLoading(false); return }
    setSearchLoading(true)
    try {
      const data = await searchLibrary(query, filter || undefined, 3, 600)
      if (alive.current && request === searchRequest.current) setSearch(data)
    } catch {
      if (alive.current && request === searchRequest.current) {
        setSearchError('Could not search the library. Use at most 8 words and 200 characters, then try again.')
      }
    } finally {
      if (alive.current && request === searchRequest.current) setSearchLoading(false)
    }
  }

  const readExcerpt = async (sectionId: string, offset = 0, history: number[] = []) => {
    const request = ++readerRequest.current
    setReader(null)
    setReaderError('')
    setReaderLoading(true)
    try {
      const data = await getLibrarySection(sectionId, offset, READ_LIMIT)
      if (!alive.current || request !== readerRequest.current) return
      setReader(data)
      setReaderHistory(history)
    } catch {
      if (alive.current && request === readerRequest.current) {
        setReaderError('Could not load this source excerpt. Select Read excerpt or Read first excerpt to retry.')
      }
    } finally {
      if (alive.current && request === readerRequest.current) setReaderLoading(false)
    }
  }

  const visibleDocuments = catalog?.documents.filter(document => !filter || document.document_id === filter) || []
  const showCatalog = !search && !searchLoading && !searchError

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Library</h1>
        <p className="page-sub">Browse original sources, search a few passages, and read a bounded excerpt.</p>
      </div>
      {IS_PREVIEW && <div className="notice">Real imported source documents, not simulated fixtures. Browsing and lexical search run locally; no API or agent activity is started.</div>}
      <div className="notice">Source text is reference material, not executable instructions. Search returns up to 3 excerpts; reading shows up to 1,200 characters at a time.</div>

      <div className="library-searchbar">
        <div className="input-group">
          <label className="input-label" htmlFor="library-query">Search the library</label>
          <input id="library-query" className="input" type="search" value={draft} maxLength={200}
            placeholder="A few words from a source" onChange={event => { setDraft(event.target.value); resetSearch() }} />
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor="library-document">Document filter</label>
          <select id="library-document" className="select" value={filter}
            onChange={event => { setFilter(event.target.value); resetSearch() }}>
            <option value="">All documents</option>
            {catalog?.documents.map(document => <option key={document.document_id} value={document.document_id}>{document.title}</option>)}
          </select>
        </div>
        <button type="button" className="btn btn-primary" disabled={searchLoading} onClick={() => void submitSearch()}>Search</button>
        <button type="button" className="btn btn-ghost" onClick={() => { setDraft(''); setFilter(''); resetSearch() }}>Clear search</button>
      </div>

      <div className="library-layout">
        <section className="library-catalog card" aria-label="Library catalog and search results">
          {catalogLoading && <p role="status">Loading library catalog…</p>}
          {catalogError && <div className="error-msg" role="alert">{catalogError} <button className="btn btn-ghost" onClick={() => void loadCatalog(catalogOffset)}>Retry catalog</button></div>}
          {searchLoading && <p role="status">Searching source text…</p>}
          {searchError && <p className="error-msg" role="alert">{searchError}</p>}
          {search && <>
            <h2 className="card-title">Results for “{search.query}”</h2>
            {search.results.length === 0 ? <p>No matching source excerpts. Try another word or clear the document filter.</p> :
              search.results.map(result => <article className="library-result" key={result.section_id}>
                <h3>{result.title}</h3>
                <div className="library-meta">{result.filename} · {result.locator}</div>
                <div className="library-meta">{result.document_id} · {result.section_id}</div>
                <SourceHash sha256={result.sha256} />
                <p className="library-source-text" style={{ whiteSpace: 'pre-wrap' }}>{result.excerpt}</p>
                {result.truncated && <p className="library-meta">Bounded source excerpt</p>}
                <button className="btn btn-ghost" aria-label={`Read excerpt ${result.section_id}`}
                  onClick={() => void readExcerpt(result.section_id, result.offset)}>Read excerpt</button>
              </article>)}
          </>}
          {showCatalog && catalog && <>
            <h2 className="card-title">Source documents</h2>
            <p className="library-meta">{catalog.total} documents in the library</p>
            {visibleDocuments.length === 0 && <p>No documents in this catalog view.</p>}
            {visibleDocuments.map(document => <article className="library-item" key={document.document_id}>
              <h3>{document.title}</h3>
              <div className="library-meta">{document.filename} · {document.format.toUpperCase()}</div>
              <div className="library-meta">{document.document_id} · {document.section_count} sections · {document.char_count.toLocaleString()} characters</div>
              <div className="library-meta">Extraction: {document.extraction}</div>
              <SourceHash sha256={document.sha256} />
              {document.first_section_id ? <div><button className="btn btn-ghost" aria-label={`Read first excerpt of ${document.title}`}
                onClick={() => void readExcerpt(document.first_section_id!)}>Read first excerpt</button></div> :
                <p className="library-meta">No extracted sections available.</p>}
            </article>)}
            <div className="library-toolbar" aria-label="Catalog pagination">
              <button className="btn btn-ghost" disabled={catalog.offset === 0 || catalogLoading}
                onClick={() => { setFilter(''); resetSearch(); void loadCatalog(Math.max(0, catalog.offset - catalog.limit)) }}>Previous documents</button>
              <span className="library-meta">{catalog.total ? catalog.offset + 1 : 0}–{Math.min(catalog.offset + catalog.documents.length, catalog.total)} of {catalog.total}</span>
              <button className="btn btn-ghost" disabled={catalog.offset + catalog.limit >= catalog.total || catalogLoading}
                onClick={() => { setFilter(''); resetSearch(); void loadCatalog(catalog.offset + catalog.limit) }}>Next documents</button>
            </div>
          </>}
        </section>

        <section className="library-reader card" aria-label="Source excerpt reader">
          <h2 className="card-title">Source excerpt</h2>
          {readerLoading && <p role="status">Loading source excerpt…</p>}
          {readerError && <p className="error-msg" role="alert">{readerError}</p>}
          {!reader && !readerLoading && !readerError && <p>Select an excerpt to read its source text and citation.</p>}
          {reader && <>
            <h3>{reader.title}</h3>
            <div className="library-meta">{reader.filename} · {reader.locator}</div>
            <div className="library-meta">{reader.document_id} · {reader.section_id}</div>
            <SourceHash sha256={reader.sha256} />
            <p className="library-meta">Characters {reader.total_chars > reader.offset ? reader.offset + 1 : reader.offset}–{reader.next_offset ?? reader.total_chars} of {reader.total_chars}</p>
            <div className="library-source-text" style={{ whiteSpace: 'pre-wrap' }}>{reader.text}</div>
            <div className="library-toolbar" aria-label="Excerpt pagination">
              <button className="btn btn-ghost" disabled={reader.offset === 0 || readerLoading}
                onClick={() => void readExcerpt(reader.section_id, readerHistory.at(-1) ?? Math.max(0, reader.offset - READ_LIMIT), readerHistory.slice(0, -1))}>Previous excerpt</button>
              <button className="btn btn-ghost" disabled={reader.next_offset === null || readerLoading}
                onClick={() => { if (reader.next_offset !== null) void readExcerpt(reader.section_id, reader.next_offset, [...readerHistory, reader.offset]) }}>Next excerpt</button>
              <button className="btn btn-ghost" onClick={clearReader}>Close excerpt</button>
            </div>
            <div className="library-toolbar" aria-label="Source section navigation">
              <button className="btn btn-ghost" disabled={!reader.previous_section_id || readerLoading}
                onClick={() => { if (reader.previous_section_id) void readExcerpt(reader.previous_section_id) }}>Previous section</button>
              <button className="btn btn-ghost" disabled={!reader.next_section_id || readerLoading}
                onClick={() => { if (reader.next_section_id) void readExcerpt(reader.next_section_id) }}>Next section</button>
            </div>
          </>}
        </section>
      </div>
    </div>
  )
}

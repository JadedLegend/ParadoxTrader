import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Library from '../src/views/Library'
import { getLibraryDocuments, searchLibrary, getLibrarySection } from '../src/api'
import type { LibraryDocumentsResponse, LibrarySearchResponse, LibrarySectionResponse } from '../src/library/contracts'

vi.mock('../src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../src/api')>(),
  getLibraryDocuments: vi.fn(), searchLibrary: vi.fn(), getLibrarySection: vi.fn(),
}))

const DOC = 'doc-000000000001'
const SECTION = `${DOC}-s00001`
const OTHER = 'doc-000000000002-s00001'
const SHA = 'a'.repeat(64)
const metadata = {
  document_id: DOC, title: 'Original source', filename: 'original.md', format: 'md' as const,
  sha256: SHA, extraction: 'markdown-lines', section_count: 2, char_count: 1400, first_section_id: SECTION,
}
const catalog: LibraryDocumentsResponse = { status: 'ok', documents: [metadata], total: 42, offset: 0, limit: 50 }
const source: LibrarySectionResponse = {
  status: 'ok', section_id: SECTION, document_id: DOC, title: metadata.title, filename: metadata.filename,
  locator: 'lines 1–8', sha256: SHA, text: 'Literal <script>alert(1)</script> & source text',
  offset: 0, next_offset: 1200, total_chars: 1400, truncated: true,
  previous_section_id: null, next_section_id: `${DOC}-s00002`,
}
const results: LibrarySearchResponse = {
  status: 'ok', query: 'source', results: [{
    section_id: SECTION, document_id: DOC, title: metadata.title, filename: metadata.filename,
    locator: source.locator, sha256: SHA, excerpt: 'Literal <script>alert(1)</script> & source text',
    offset: 0, next_offset: 600, truncated: true,
  }],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.mocked(getLibraryDocuments).mockReset().mockResolvedValue(structuredClone(catalog))
  vi.mocked(searchLibrary).mockReset().mockResolvedValue(structuredClone(results))
  vi.mocked(getLibrarySection).mockReset().mockResolvedValue(structuredClone(source))
})

async function renderLibrary() {
  render(<Library />)
  await screen.findByRole('heading', { name: 'Source documents' })
  return userEvent.setup()
}

async function search(user: ReturnType<typeof userEvent.setup>, text = 'source') {
  await user.type(screen.getByRole('searchbox', { name: 'Search the library' }), text)
  await user.click(screen.getByRole('button', { name: 'Search', exact: true }))
}

describe('Library source reader', () => {
  it('shows the real-source local notice, catalog metadata, full accessible hash, and initial pagination', async () => {
    await renderLibrary()
    expect(screen.getByRole('heading', { level: 1, name: 'Library' })).toBeTruthy()
    expect(screen.getByText(/Real imported source documents, not simulated fixtures/)).toBeTruthy()
    expect(screen.getByText(/no API or agent activity is started/)).toBeTruthy()
    expect(screen.getByText('original.md · MD')).toBeTruthy()
    expect(screen.getByLabelText(`SHA-256 ${SHA}`).getAttribute('title')).toBe(SHA)
    expect(screen.getByText(/42 documents in the library/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Previous documents' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Next documents' }) as HTMLButtonElement).disabled).toBe(true)
    expect(getLibraryDocuments).toHaveBeenCalledWith(50, 0)
    expect(searchLibrary).not.toHaveBeenCalled()
    expect(getLibrarySection).not.toHaveBeenCalled()
  })

  it('searches only on explicit click, trims the draft, and never replaces results while typing', async () => {
    const user = await renderLibrary()
    const input = screen.getByRole('searchbox', { name: 'Search the library' })
    await user.type(input, '  source  ')
    await user.keyboard('{Enter}')
    expect(searchLibrary).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Search', exact: true }))
    await screen.findByRole('heading', { name: 'Results for “source”' })
    expect(searchLibrary).toHaveBeenCalledExactlyOnceWith('source', undefined, 3, 600)
    expect(screen.getByText(source.locator, { exact: false })).toBeTruthy()
    await user.type(input, 'draft')
    expect(searchLibrary).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('heading', { name: /Results for/ })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Source documents' })).toBeTruthy()
  })

  it('filters catalog and submitted search without initiating automatic requests', async () => {
    const user = await renderLibrary()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Document filter' }), DOC)
    expect(searchLibrary).not.toHaveBeenCalled()
    await search(user)
    await screen.findByRole('heading', { name: 'Results for “source”' })
    expect(searchLibrary).toHaveBeenCalledWith('source', DOC, 3, 600)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Document filter' }), '')
    expect(screen.queryByRole('heading', { name: /Results for/ })).toBeNull()
  })

  it('renders HTML-like text literally in results and reader, with exact citations', async () => {
    const user = await renderLibrary()
    await search(user)
    await screen.findByRole('heading', { name: 'Results for “source”' })
    const result = screen.getByRole('region', { name: 'Library catalog and search results' })
    expect(within(result).getByText(source.text)).toBeTruthy()
    expect(result.querySelector('script')).toBeNull()
    await user.click(screen.getByRole('button', { name: `Read excerpt ${SECTION}` }))
    const reader = screen.getByRole('region', { name: 'Source excerpt reader' })
    await within(reader).findByText(source.text)
    expect(reader.querySelector('script')).toBeNull()
    expect(within(reader).getByText(`${DOC} · ${SECTION}`)).toBeTruthy()
    expect(within(reader).getByLabelText(`SHA-256 ${SHA}`)).toBeTruthy()
    expect(getLibrarySection).toHaveBeenCalledWith(SECTION, 0, 1200)
  })

  it('reads the first indexed excerpt and moves next/previous using source offsets', async () => {
    const user = await renderLibrary()
    await user.click(screen.getByRole('button', { name: 'Read first excerpt of Original source' }))
    await screen.findByText(source.text)
    expect((screen.getByRole('button', { name: 'Previous excerpt' }) as HTMLButtonElement).disabled).toBe(true)
    vi.mocked(getLibrarySection).mockResolvedValueOnce({ ...source, text: 'The final source window.', offset: 1200, next_offset: null })
    await user.click(screen.getByRole('button', { name: 'Next excerpt' }))
    await screen.findByText('The final source window.')
    expect(getLibrarySection).toHaveBeenLastCalledWith(SECTION, 1200, 1200)
    expect((screen.getByRole('button', { name: 'Next excerpt' }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Previous excerpt' }))
    await screen.findByText(source.text)
    expect(getLibrarySection).toHaveBeenLastCalledWith(SECTION, 0, 1200)
    await user.click(screen.getByRole('button', { name: 'Close excerpt' }))
    expect(screen.queryByText(source.text)).toBeNull()
  })

  it('moves through known source sections at offset zero without mixing excerpt history', async () => {
    const user = await renderLibrary()
    const secondSection = `${DOC}-s00002`
    await user.click(screen.getByRole('button', { name: 'Read first excerpt of Original source' }))
    await screen.findByText(source.text)
    expect((screen.getByRole('button', { name: 'Previous section' }) as HTMLButtonElement).disabled).toBe(true)
    vi.mocked(getLibrarySection).mockResolvedValueOnce({ ...source, text: 'Tail of section one.', offset: 1200, next_offset: null })
    await user.click(screen.getByRole('button', { name: 'Next excerpt' }))
    await screen.findByText('Tail of section one.')
    vi.mocked(getLibrarySection).mockResolvedValueOnce({
      ...source, section_id: secondSection, text: 'Section two starts here.',
      offset: 0, next_offset: null, total_chars: 24, previous_section_id: SECTION, next_section_id: null,
    })
    await user.click(screen.getByRole('button', { name: 'Next section' }))
    await screen.findByText('Section two starts here.')
    expect(getLibrarySection).toHaveBeenLastCalledWith(secondSection, 0, 1200)
    expect((screen.getByRole('button', { name: 'Previous excerpt' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Next section' }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Previous section' }))
    await screen.findByText(source.text)
    expect(getLibrarySection).toHaveBeenLastCalledWith(SECTION, 0, 1200)
  })

  it('keeps no-results, failed-search, and blank catalog states distinct', async () => {
    const user = await renderLibrary()
    vi.mocked(searchLibrary).mockResolvedValueOnce({ status: 'ok', query: 'missing', results: [] })
    await search(user, 'missing')
    await screen.findByText(/No matching source excerpts/)
    expect(screen.queryByRole('alert')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Clear search' }))
    vi.mocked(searchLibrary).mockRejectedValueOnce(new Error('unavailable'))
    await search(user)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText(/No matching source excerpts/)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Clear search' }))
    await user.click(screen.getByRole('button', { name: 'Search', exact: true }))
    expect(searchLibrary).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('heading', { name: 'Source documents' })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('announces catalog loading and errors, and retries without presenting an empty library', async () => {
    const pending = deferred<LibraryDocumentsResponse>()
    vi.mocked(getLibraryDocuments).mockReturnValueOnce(pending.promise)
    render(<Library />)
    expect(screen.getByRole('status').textContent).toContain('Loading library catalog')
    await act(async () => { pending.reject(new Error('offline')) })
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText(/No documents in this catalog view/)).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry catalog' }))
    await screen.findByRole('heading', { name: 'Source documents' })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('paginates metadata independently of queries using returned total and offsets', async () => {
    vi.mocked(getLibraryDocuments).mockResolvedValueOnce({ ...catalog, total: 55 })
    const user = await renderLibrary()
    vi.mocked(getLibraryDocuments).mockResolvedValueOnce({ ...catalog, total: 55, offset: 50 })
    await user.click(screen.getByRole('button', { name: 'Next documents' }))
    await waitFor(() => expect(getLibraryDocuments).toHaveBeenLastCalledWith(50, 50))
    await screen.findByRole('button', { name: 'Previous documents' })
    expect((screen.getByRole('button', { name: 'Next documents' }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Previous documents' }))
    await waitFor(() => expect(getLibraryDocuments).toHaveBeenLastCalledWith(50, 0))
    expect(searchLibrary).not.toHaveBeenCalled()
  })

  it('discards a stale search when the draft or filter changes, preserving focus', async () => {
    const user = await renderLibrary()
    const pending = deferred<LibrarySearchResponse>()
    vi.mocked(searchLibrary).mockReturnValueOnce(pending.promise)
    await search(user)
    expect(screen.getByRole('status').textContent).toContain('Searching source text')
    const input = screen.getByRole('searchbox', { name: 'Search the library' })
    await user.type(input, ' changed')
    await act(async () => { pending.resolve(results) })
    expect(screen.queryByRole('heading', { name: /Results for/ })).toBeNull()
    expect(document.activeElement).toBe(input)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('ignores stale reader responses and errors after selecting another excerpt or changing filter', async () => {
    const user = await renderLibrary()
    const pending = deferred<LibrarySectionResponse>()
    vi.mocked(getLibrarySection).mockReturnValueOnce(pending.promise)
    await user.click(screen.getByRole('button', { name: 'Read first excerpt of Original source' }))
    vi.mocked(searchLibrary).mockResolvedValueOnce({ ...results, results: [{ ...results.results[0], section_id: OTHER }] })
    await search(user)
    await screen.findByRole('button', { name: `Read excerpt ${OTHER}` })
    vi.mocked(getLibrarySection).mockResolvedValueOnce({ ...source, section_id: OTHER, text: 'New selected excerpt.' })
    await user.click(screen.getByRole('button', { name: `Read excerpt ${OTHER}` }))
    await screen.findByText('New selected excerpt.')
    await act(async () => { pending.resolve(source) })
    const reader = screen.getByRole('region', { name: 'Source excerpt reader' })
    expect(within(reader).queryByText(source.text)).toBeNull()
    expect(within(reader).getByText('New selected excerpt.')).toBeTruthy()
    const late = deferred<LibrarySectionResponse>()
    vi.mocked(getLibrarySection).mockReturnValueOnce(late.promise)
    await user.click(screen.getByRole('button', { name: `Read excerpt ${OTHER}` }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Document filter' }), DOC)
    await act(async () => { late.reject(new Error('late')) })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(within(reader).getByText(/Select an excerpt/)).toBeTruthy()
  })

  it('reports a reader failure, and does not expose upload, mutation, or arbitrary-file controls', async () => {
    const user = await renderLibrary()
    vi.mocked(getLibrarySection).mockRejectedValueOnce(new Error('missing'))
    await user.click(screen.getByRole('button', { name: 'Read first excerpt of Original source' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(document.querySelector('a[download]')).toBeNull()
    expect(screen.queryByRole('button', { name: /upload|delete|wake|execute/i })).toBeNull()
  })
})

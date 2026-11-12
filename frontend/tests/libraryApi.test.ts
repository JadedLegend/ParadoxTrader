import { describe, expect, it } from 'vitest'
import { getLibraryDocuments, getLibrarySection, searchLibrary } from '../src/api'
import { readFixture } from '../src/preview/readFixture'

describe('actual source-library preview API boundary', () => {
  it('lists the forty-two real sources without source text or fabricated activity', async () => {
    const catalog = await getLibraryDocuments()
    expect(catalog.status).toBe('ok')
    expect(catalog.total).toBe(42)
    expect(catalog.documents).toHaveLength(42)
    expect(catalog).not.toHaveProperty('kind', 'fixture')
    expect(catalog).not.toHaveProperty('sections')
    expect(catalog.documents.every((d: any) => typeof d.sha256 === 'string' && d.sha256.length === 64)).toBe(true)
    expect(catalog.documents.find((d: any) => d.filename === 'opte.md')).toBeTruthy()
  })

  it('searches a source by opaque ID and preserves real excerpt references', async () => {
    const catalog = await getLibraryDocuments()
    const document = catalog.documents.find((d: any) => d.filename === 'TheOptionsParadox.docx')!
    const result = await searchLibrary('options', document.document_id)
    expect(result.status).toBe('ok')
    expect(result.results.length).toBeGreaterThan(0)
    expect(result.results.length).toBeLessThanOrEqual(3)
    for (const hit of result.results) {
      expect(hit.document_id).toBe(document.document_id)
      expect(hit.filename).toBe(document.filename)
      expect(hit.sha256).toBe(document.sha256)
      expect(hit.excerpt.length).toBeLessThanOrEqual(600)
      expect(hit.locator).toMatch(/DOCX paragraph/)
      const section = await getLibrarySection(hit.section_id, hit.offset, 600)
      expect(section.text).toBe(hit.excerpt)
      expect(section.sha256).toBe(hit.sha256)
    }
  })

  it('reads bounded source windows and clones local data on each response', async () => {
    const catalog = await getLibraryDocuments()
    const original = catalog.documents[0].title
    catalog.documents[0].title = 'client mutation'
    expect((await getLibraryDocuments()).documents[0].title).toBe(original)
    const first = await getLibrarySection(catalog.documents[0].first_section_id, 0, 100)
    expect(first.text.length).toBeLessThanOrEqual(100)
    expect(first.offset).toBe(0)
    expect(first.total_chars).toBeGreaterThan(0)
    first.text = 'consumer mutation'
    expect((await getLibrarySection(first.section_id, 0, 100)).text).not.toBe('consumer mutation')
  })

  it.each([
    '/api/library/secrets', '/api/library/originals/opte.md',
    '/api/library/documents?limit=1000', '/api/library/documents?offset=-1',
    '/api/library/search?q=x&limit=6', '/api/library/search?q=x&max_chars=1001',
    '/api/library/sections/../../.env', '/api/library/sections/%2Fetc%2Fpasswd',
    '/api/library/sections/unknown?max_chars=2001', '/api/library/sections/unknown?offset=-1',
    '/api/library/documents?limit=NaN', '/api/library/documents?limit=1.5',
    '/api/library/documents?limit=99999999999999999999999',
  ])('rejects unsupported, out-of-budget, or arbitrary-file route %s without transport', async path => {
    await expect(Promise.resolve().then(() => readFixture(path))).rejects.toThrow()
  })

  it('returns no matches for a made-up keyword without inventing an excerpt', async () => {
    const result = await searchLibrary('zznonexistentparadoxsourcetermzz')
    expect(result.results).toEqual([])
    expect(result).not.toHaveProperty('content')
  })
})

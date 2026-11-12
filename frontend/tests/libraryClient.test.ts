import { describe, expect, it, vi } from 'vitest'
import { createLocalLibrary, listDocuments, queryLibrary, readSection } from '../src/library/client'
import type { LibraryCorpus } from '../src/library/contracts'

const A = 'doc-000000000001'
const B = 'doc-000000000002'
const C = 'doc-000000000003'
const S1 = `${A}-s00001`
const S2 = `${A}-s00002`
const S3 = `${B}-s00001`

function sample(): LibraryCorpus {
  return {
    schema_version: 1,
    documents: [A, B, C].map((document_id, index) => ({
      document_id, title: `Source ${index + 1}`, filename: `source-${index + 1}.md`,
      format: 'md', sha256: String(index + 1).repeat(64), extraction: 'markdown-lines',
      section_count: index === 0 ? 2 : index === 1 ? 1 : 0, char_count: 100,
    })),
    // Deliberately unsorted so ties must be resolved by exact section ID.
    sections: [
      { section_id: S3, document_id: B, locator: 'lines 20–22', text: 'alpha beta <script>alert(1)</script>' },
      { section_id: S2, document_id: A, locator: 'lines 5–6', text: 'ALPHA gamma' },
      { section_id: S1, document_id: A, locator: 'lines 1–4', text: 'alpha beta Straße Σίσυφος café 中文 😀' },
    ],
  }
}

describe('pure frontend library retrieval', () => {
  it('lists only metadata with source-derived first sections, bounded pagination, and detached objects', async () => {
    const corpus = sample()
    const before = structuredClone(corpus)
    const library = createLocalLibrary(corpus)
    const page = await library.listDocuments(2, 0)
    expect(page).toMatchObject({ status: 'ok', total: 3, offset: 0, limit: 2 })
    expect(page.documents.map(document => document.first_section_id)).toEqual([S1, S3])
    expect(page.documents[0]).not.toHaveProperty('text')
    page.documents[0].title = 'changed'
    expect((await library.listDocuments()).documents[0].title).toBe('Source 1')
    expect((await library.listDocuments(2, 2)).documents[0].first_section_id).toBeNull()
    expect((await library.listDocuments(2, 20)).documents).toEqual([])
    expect(corpus).toEqual(before)
  })

  it('uses casefolded Unicode words, OR matching, lexical hit counts, and deterministic ID ties', async () => {
    const library = createLocalLibrary(sample())
    expect((await library.queryLibrary('beta gamma')).results.map(result => result.section_id)).toEqual([S1, S2, S3])
    expect((await library.queryLibrary('alpha beta')).results.map(result => result.section_id)).toEqual([S1, S3, S2])
    for (const query of ['STRASSE', 'ΣΊΣΥΦΟΣ', 'CAFÉ', '中文']) {
      expect((await library.queryLibrary(query)).results.map(result => result.section_id)).toEqual([S1])
    }
    expect((await library.queryLibrary('alpha', B)).results.map(result => result.section_id)).toEqual([S3])
    expect((await library.queryLibrary('alpha', undefined, 1)).results).toHaveLength(1)
    expect((await library.queryLibrary('alp')).results).toEqual([])
  })

  it('treats query operators and regex punctuation as ordinary text, without expanding results', async () => {
    const library = createLocalLibrary(sample())
    expect((await library.queryLibrary('"alpha" * [beta]')).results.map(result => result.section_id)).toEqual([S1, S3, S2])
    expect((await library.queryLibrary('((.*))')).results).toEqual([])
    expect((await library.queryLibrary('   ')).results).toEqual([])
    expect((await library.queryLibrary('nonexistent')).results).toEqual([])
    expect((await library.queryLibrary('one two three four five six seven eight alpha')).results).toEqual([])
    expect((await library.queryLibrary('alpha alpha alpha alpha alpha alpha alpha alpha beta')).results).toHaveLength(3)
    expect((await library.queryLibrary('  alpha  ')).query).toBe('  alpha  ')
  })

  it('returns exact metadata, locators, IDs, hashes, and unmodified source text', async () => {
    const corpus = sample()
    const library = createLocalLibrary(corpus)
    const result = (await library.queryLibrary('script')).results[0]
    expect(result).toMatchObject({
      section_id: S3, document_id: B, title: 'Source 2', filename: 'source-2.md',
      locator: 'lines 20–22', sha256: '2'.repeat(64),
      excerpt: corpus.sections[0].text, offset: 0, next_offset: null, truncated: false,
    })
    expect((await library.readSection(S3)).text).toBe('alpha beta <script>alert(1)</script>')
  })

  it('returns previous/next section IDs only from the same indexed document', async () => {
    const library = createLocalLibrary(sample())
    expect(await library.readSection(S1)).toMatchObject({ previous_section_id: null, next_section_id: S2 })
    expect(await library.readSection(S2)).toMatchObject({ previous_section_id: S1, next_section_id: null })
    expect(await library.readSection(S3)).toMatchObject({ previous_section_id: null, next_section_id: null })
    expect((await library.readSection(S2)).text).toBe('ALPHA gamma')
  })

  it('counts Unicode code points and supports offset continuation, including end-of-section', async () => {
    const corpus = sample()
    corpus.sections[0].text = '😀'.repeat(1200) + ' alpha ' + '😀'.repeat(193)
    const library = createLocalLibrary(corpus)
    const result = (await library.queryLibrary('alpha', B, 3, 100)).results[0]
    expect(Array.from(result.excerpt)).toHaveLength(100)
    expect(result.excerpt).toContain('alpha')
    expect(result.offset).toBeGreaterThan(0)
    const first = await library.readSection(S3)
    expect(Array.from(first.text)).toHaveLength(1200)
    expect(first).toMatchObject({ offset: 0, next_offset: 1200, total_chars: 1400, truncated: true })
    const next = await library.readSection(S3, first.next_offset!)
    expect(Array.from(next.text)).toHaveLength(200)
    expect(next.next_offset).toBeNull()
    expect(first.text + next.text).toBe(corpus.sections[0].text)
    expect(await library.readSection(S3, 1400)).toMatchObject({ text: '', next_offset: null })
    await expect(library.readSection(S3, 1401)).rejects.toThrow('offset')
  })

  it('never exceeds the total result or character budgets', async () => {
    const corpus = sample()
    corpus.sections = Array.from({ length: 12 }, (_, index) => ({
      section_id: `${A}-s${String(index + 1).padStart(5, '0')}`, document_id: A,
      locator: `chunk ${index + 1}`, text: `alpha ${'x'.repeat(1394)}`,
    }))
    const library = createLocalLibrary(corpus)
    const results = (await library.queryLibrary('alpha', undefined, 5, 1000)).results
    expect(results).toHaveLength(5)
    expect(results.every(result => Array.from(result.excerpt).length <= 1000)).toBe(true)
    expect(Array.from((await library.readSection(S1, 0, 2000)).text).length).toBeLessThanOrEqual(2000)
  })

  it('rejects invalid arguments and unknown identifiers with bounded errors, not path reads', async () => {
    const library = createLocalLibrary(sample())
    for (const limit of [0, -1, 101, 1.5, NaN, Infinity]) await expect(library.listDocuments(limit)).rejects.toThrow('limit')
    for (const offset of [-1, 0.5, NaN, Infinity]) await expect(library.listDocuments(50, offset)).rejects.toThrow('offset')
    for (const limit of [0, 6, 2.5]) await expect(library.queryLibrary('alpha', undefined, limit)).rejects.toThrow('limit')
    for (const budget of [0, 1001, 1.5]) await expect(library.queryLibrary('alpha', undefined, 3, budget)).rejects.toThrow('max_chars')
    await expect(library.queryLibrary('x'.repeat(201))).rejects.toThrow('200')
    await expect(library.queryLibrary('alpha\0beta')).rejects.toThrow('Query')
    await expect(library.queryLibrary(null as unknown as string)).rejects.toThrow('Query')
    await expect(library.queryLibrary('alpha', 'doc-ffffffffffff')).rejects.toThrow('Unknown document identifier')
    await expect(library.readSection('doc-ffffffffffff-s00001')).rejects.toThrow('Unknown section identifier')
    for (const id of ['../../secrets', '/api/config', 'https://example.com', '<script>', 'x'.repeat(10000)]) {
      await expect(library.readSection(id)).rejects.toThrow('Invalid section identifier.')
      await expect(library.queryLibrary('alpha', id)).rejects.toThrow('Invalid document identifier.')
    }
    for (const budget of [0, 2001, 0.5]) await expect(library.readSection(S1, 0, budget)).rejects.toThrow('max_chars')
    await expect(library.readSection(S1, -1)).rejects.toThrow('offset')
  })

  it('verifies corpus version, uniqueness, section identity, and source bounds', () => {
    expect(() => createLocalLibrary({ ...sample(), schema_version: 2 } as unknown as LibraryCorpus)).toThrow('Unsupported')
    const duplicate = sample()
    duplicate.sections.push({ ...duplicate.sections[0] })
    expect(() => createLocalLibrary(duplicate)).toThrow('Duplicate')
    const tooLong = sample()
    tooLong.sections[0].text = 'x'.repeat(1401)
    expect(() => createLocalLibrary(tooLong)).toThrow('Invalid library section')
  })
})

describe('actual corpus and lazy boundary', () => {
  it('reads the real imported catalog and source locally, not simulated examples', async () => {
    const catalog = await listDocuments()
    expect(catalog.total).toBe(42)
    expect(catalog.documents).toHaveLength(42)
    expect(catalog.documents.every(document => /^[a-f0-9]{64}$/.test(document.sha256))).toBe(true)
    expect(catalog.documents.every(document => /^[a-f0-9]{64}$/.test(document.text_sha256!))).toBe(true)
    expect(catalog.documents.every(document => ['extracted', 'no_extractable_text'].includes(document.status!))).toBe(true)
    const source = catalog.documents.find(document => document.first_section_id)!
    const section = await readSection(source.first_section_id!)
    expect(section.document_id).toBe(source.document_id)
    expect(section.sha256).toBe(source.sha256)
    expect(section.text.length).toBeGreaterThan(0)
    expect(Array.from(section.text).length).toBeLessThanOrEqual(1200)
    expect((await queryLibrary('')).results).toEqual([])
  })

  it('does not import source text at client import time, and lazily imports once for concurrent calls', async () => {
    vi.resetModules()
    let imports = 0
    vi.doMock('../../library/corpus.json', () => { imports++; return { default: sample() } })
    try {
      const lazy = await import('../src/library/client')
      expect(imports).toBe(0)
      const responses = await Promise.all([lazy.listDocuments(), lazy.queryLibrary('alpha'), lazy.readSection(S1)])
      expect(imports).toBe(1)
      expect(responses.every(response => response.status === 'ok')).toBe(true)
      await lazy.listDocuments()
      expect(imports).toBe(1)
    } finally {
      vi.doUnmock('../../library/corpus.json')
      vi.resetModules()
    }
  })
})

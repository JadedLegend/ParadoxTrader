import type {
  LibraryCorpus, LibraryDocument, LibraryDocumentsResponse, LibrarySearchResponse,
  LibrarySection, LibrarySectionResponse, LibrarySourceReference,
} from './contracts'

// Fixed lexical grammar, never a regular expression constructed from a query.
const WORDS = /[\p{L}\p{N}\p{M}]+/gu
const DOCUMENT_ID = /^doc-[a-f0-9]{12}$/
const SECTION_ID = /^doc-[a-f0-9]{12}-s\d{5}$/

function casefold(value: string) {
  return value.normalize('NFKC').toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ')
}

function integer(value: number, name: string, min: number, max: number) {
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new Error(`${name} must be an integer between ${min} and ${max}.`)
  }
}

function identifier(value: string, pattern: RegExp, name: string) {
  if (typeof value !== 'string' || !pattern.test(value)) throw new Error(`Invalid ${name}.`)
}

function queryTokens(query: string) {
  if (typeof query !== 'string' || query.includes('\0') || Array.from(query).length > 200) {
    throw new Error('Query must be text of at most 200 characters.')
  }
  const tokens = casefold(query).match(WORDS) || []
  return new Set(Array.from(new Set(tokens)).slice(0, 8))
}

function reference(section: LibrarySection, document: LibraryDocument): LibrarySourceReference {
  return {
    section_id: section.section_id, document_id: document.document_id,
    title: document.title, filename: document.filename,
    locator: section.locator, sha256: document.sha256,
  }
}

function windowText(text: string, offset: number, maxChars: number) {
  // Offsets and budgets count Unicode code points, not UTF-16 code units.
  const characters = Array.from(text)
  integer(offset, 'offset', 0, characters.length)
  const end = Math.min(characters.length, offset + maxChars)
  return {
    text: characters.slice(offset, end).join(''), offset,
    next_offset: end < characters.length ? end : null,
    total_chars: characters.length,
    truncated: offset > 0 || end < characters.length,
  }
}

/** Pure, injectable local retrieval. It never accepts a filename or filesystem path. */
export function createLocalLibrary(corpus: LibraryCorpus) {
  if (corpus.schema_version !== 1 || !Array.isArray(corpus.documents) || !Array.isArray(corpus.sections)) {
    throw new Error('Unsupported library corpus.')
  }
  const documents = corpus.documents.map(document => ({
    document_id: document.document_id, title: document.title, filename: document.filename,
    format: document.format, sha256: document.sha256, extraction: document.extraction,
    ...(document.text_sha256 !== undefined ? { text_sha256: document.text_sha256 } : {}),
    ...(document.status !== undefined ? { status: document.status } : {}),
    ...Object.fromEntries((['room', 'kind', 'authors', 'year', 'area', 'evidence', 'review_depth', 'url'] as const)
      .filter(key => typeof document[key] === 'string').map(key => [key, document[key]])),
    section_count: document.section_count, char_count: document.char_count,
    first_section_id: null as string | null,
  })).sort((a, b) => a.document_id < b.document_id ? -1 : a.document_id > b.document_id ? 1 : 0)
  const byDocument = new Map(documents.map(document => [document.document_id, document]))
  const sections = corpus.sections.map(section => ({ ...section }))
    .sort((a, b) => a.section_id < b.section_id ? -1 : a.section_id > b.section_id ? 1 : 0)
  const bySection = new Map(sections.map(section => [section.section_id, section]))
  if (byDocument.size !== documents.length || bySection.size !== sections.length) {
    throw new Error('Duplicate library identifiers.')
  }
  for (const document of documents) identifier(document.document_id, DOCUMENT_ID, 'document identifier')
  for (const section of sections) {
    identifier(section.section_id, SECTION_ID, 'section identifier')
    const document = byDocument.get(section.document_id)
    if (!document || !section.section_id.startsWith(`${section.document_id}-s`) ||
        typeof section.text !== 'string' || Array.from(section.text).length > 1400) {
      throw new Error('Invalid library section.')
    }
    if (document.first_section_id === null) document.first_section_id = section.section_id
  }
  const neighbors = new Map<string, { previous_section_id: string | null; next_section_id: string | null }>(
    sections.map((section, index) => {
      const previous = sections[index - 1]
      const next = sections[index + 1]
      return [section.section_id, {
        previous_section_id: previous?.document_id === section.document_id ? previous.section_id : null,
        next_section_id: next?.document_id === section.document_id ? next.section_id : null,
      }]
    }),
  )
  const index = sections.map(section => ({
    section,
    words: Array.from(section.text.matchAll(WORDS), match => ({
      token: casefold(match[0]),
      offset: Array.from(section.text.slice(0, match.index)).length,
    })),
  }))

  return {
    async listDocuments(limit = 50, offset = 0): Promise<LibraryDocumentsResponse> {
      integer(limit, 'limit', 1, 100)
      integer(offset, 'offset', 0, 2 ** 31 - 1)
      return {
        status: 'ok', documents: documents.slice(offset, offset + limit).map(document => ({ ...document })),
        total: documents.length, offset, limit,
      }
    },

    async queryLibrary(query: string, documentId?: string, limit = 3, maxChars = 600): Promise<LibrarySearchResponse> {
      integer(limit, 'limit', 1, 5)
      integer(maxChars, 'max_chars', 1, 1000)
      const tokens = queryTokens(query)
      if (documentId !== undefined) {
        identifier(documentId, DOCUMENT_ID, 'document identifier')
        if (!byDocument.has(documentId)) throw new Error('Unknown document identifier.')
      }
      if (!tokens.size) return { status: 'ok', query, results: [] }
      const matches = index.filter(entry => documentId === undefined || entry.section.document_id === documentId)
        .map(entry => {
          const hits = entry.words.filter(word => tokens.has(word.token))
          return { section: entry.section, score: hits.length, first: hits[0]?.offset ?? 0 }
        }).filter(entry => entry.score > 0)
        .sort((a, b) => b.score - a.score || (a.section.section_id < b.section.section_id ? -1 : a.section.section_id > b.section.section_id ? 1 : 0))
      return {
        status: 'ok', query,
        results: matches.slice(0, limit).map(({ section, first }) => {
          const context = Math.min(80, Math.floor(maxChars / 4))
          const offset = Math.min(Math.max(0, first - context), Math.max(0, Array.from(section.text).length - maxChars))
          const window = windowText(section.text, offset, maxChars)
          return {
            ...reference(section, byDocument.get(section.document_id)!),
            excerpt: window.text, offset: window.offset,
            next_offset: window.next_offset, truncated: window.truncated,
          }
        }),
      }
    },

    async readSection(sectionId: string, offset = 0, maxChars = 1200): Promise<LibrarySectionResponse> {
      identifier(sectionId, SECTION_ID, 'section identifier')
      integer(maxChars, 'max_chars', 1, 2000)
      const section = bySection.get(sectionId)
      if (!section) throw new Error('Unknown section identifier.')
      return {
        status: 'ok', ...reference(section, byDocument.get(section.document_id)!),
        ...windowText(section.text, offset, maxChars),
        ...neighbors.get(sectionId)!,
      }
    },
  }
}

// This module is safe to import with App/api: source text is not part of that
// initial dependency graph. The real, private corpus is loaded once on demand.
// Two rooms (docs/specs/LIBRARY_ROOMS.md): each shelf loads only when it is opened.
export type LibraryRoom = 'writings' | 'research'
const shelves: Partial<Record<LibraryRoom, Promise<ReturnType<typeof createLocalLibrary>>>> = {}
function loadLibrary(room: LibraryRoom = 'writings') {
  shelves[room] ??= (room === 'research'
    ? import('../../../library/research-corpus.json')
    : import('../../../library/corpus.json')).then(module => createLocalLibrary(module.default as LibraryCorpus))
  return shelves[room]!
}

export async function listDocuments(limit = 50, offset = 0, room: LibraryRoom = 'writings') {
  return (await loadLibrary(room)).listDocuments(limit, offset)
}

export async function queryLibrary(query: string, documentId?: string, limit = 3, maxChars = 600, room: LibraryRoom = 'writings') {
  return (await loadLibrary(room)).queryLibrary(query, documentId, limit, maxChars)
}

export async function readSection(sectionId: string, offset = 0, maxChars = 1200, room: LibraryRoom = 'writings') {
  return (await loadLibrary(room)).readSection(sectionId, offset, maxChars)
}

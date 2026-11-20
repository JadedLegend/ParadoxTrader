export type LibraryFormat = 'md' | 'txt' | 'docx' | 'pdf'

export interface LibraryDocument {
  document_id: string
  title: string
  filename: string
  format: LibraryFormat
  sha256: string
  text_sha256?: string
  status?: 'extracted' | 'no_extractable_text'
  extraction: string
  section_count: number
  char_count: number
  first_section_id?: string | null
  // Research-room labels: what the note is and what kind of evidence its paper holds.
  room?: string
  kind?: string
  authors?: string
  year?: string
  area?: string
  evidence?: string
  review_depth?: string
  url?: string
}

export interface LibrarySection {
  section_id: string
  document_id: string
  locator: string
  text: string
}

export interface LibraryCorpus {
  schema_version: 1
  documents: LibraryDocument[]
  sections: LibrarySection[]
}

export interface LibraryDocumentsResponse {
  status: 'ok'
  documents: LibraryDocument[]
  total: number
  offset: number
  limit: number
}

export interface LibrarySourceReference {
  section_id: string
  document_id: string
  title: string
  filename: string
  locator: string
  sha256: string
}

export interface LibrarySearchResult extends LibrarySourceReference {
  excerpt: string
  offset: number
  next_offset: number | null
  truncated: boolean
}

export interface LibrarySearchResponse {
  status: 'ok'
  query: string
  results: LibrarySearchResult[]
}

export interface LibrarySectionResponse extends LibrarySourceReference {
  status: 'ok'
  text: string
  offset: number
  next_offset: number | null
  total_chars: number
  truncated: boolean
  previous_section_id: string | null
  next_section_id: string | null
}

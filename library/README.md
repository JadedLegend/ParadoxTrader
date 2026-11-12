# Original-document library

This collection contains the creator's **42 explicitly supplied originals**, preserved byte-for-byte in `originals/`. Duplicate attachment mentions were consolidated; downloaded third-party research, images, API credentials, project backups, and private agent records were not imported. The repository is private. These sources and the extracted corpus are not authorized for public publication by this development slice.

Repository attributes disable text normalization for `library/originals/**` so Git preserves source line endings and bytes. Original Markdown hard-break spaces and other existing source whitespace are retained rather than lint-rewritten. Ordinary implementation files still receive the normal whitespace checks.

`corpus.json` records each filename, immutable original SHA-256, extracted-text SHA-256, extraction method, first section, section count, and character count. Its 1,422 text sections carry opaque stable document/section identifiers and line, paragraph, or physical-page locators plus within-unit extracted-character ranges. Search and read offsets are character positions within the extracted section, not coordinates on a rendered original page.

## Extraction scope

Markdown/text preserve content with BOM removal and line-ending normalization in the extracted copy only. Word extraction reads main-document paragraphs and tables in document order; it does not render pagination or include headers, footnotes, images, and embedded objects. PDF extraction uses `pdftotext -layout`; it does not perform OCR or reconstruct image-based text, diagrams, formulas, or reading order beyond that extraction. Exact original files remain available for fuller reading and verification.

Import and extraction do not execute macros, embedded objects, source instructions, or code samples. No model rewrites or summarizes the source corpus. Search matches are excerpts of the extracted text; interpretive output by an agent is recorded separately.

## Reproduce and verify

From the repository root, run `python3 -B scripts/import_library.py --check` to compare current original hashes and reproducible extracted content with the stored corpus. Poppler's `pdftotext` is required for PDF extraction. First import uses `--source-dir /path/to/the/supplied/originals`; the command imports only its hardcoded source list and refuses to overwrite a differing preserved original. A future source revision should be an explicit reviewed change, not an automatic edit to these originals.

Python library indexes are rebuildable SQLite files outside this folder, ignored by Git. The frontend loads extracted source text lazily on library reads. A static frontend build therefore **contains this private extracted collection**, even though the dashboard does not preload it. Do not publicly distribute that build without deciding which sources may be shared. No public deployment or original-file download service is created here.

# Shared original-document library

The next library slice preserves **42 user-supplied originals** in this private repository and makes their extracted text inexpensive to browse. There are **1,422 bounded sections**, with filenames, SHA-256 hashes, and page, paragraph, or line locators. The originals are intact; no model rewrote them or generated replacement summaries.

## What you can use

Open the **Library** page in the default frontend-only preview. It reads the actual imported source collection locally, clearly distinguished from the simulated agent and portfolio examples elsewhere. Search a few words, filter by document, inspect bounded passages, and follow their source references. The short installed working orientation remains separate. No whole-library injection accompanies normal agent wakes.

The reader distinguishes **Previous/Next excerpt** within one section from **Previous/Next section** through the document. Adjacent-section references come from the actual same-document index rather than guessed filenames or suffixes. You can therefore keep browsing beyond the first passage while every read retains its source locator and character limit.

Agents have an ordinary rotating option: **Browse shared library — follow a question**. It is available in every phase when affordable, without a reserved menu slot, assignment to a particular document, or reward for agreeing with a source. Quiet rest and phase restrictions remain as before. The agent can choose its question, consider an alternative, propose a test, keep a question open, or leave the passages without an interpretation.

## Retrieval and resource budgets

| Operation | Default | Hard bound |
| --- | --- | --- |
| Catalog listing | 50 document metadata records | 100 per page; no section text |
| Search query | A short query | 200 Unicode characters; first 8 distinct lexical terms |
| Search results | 3 excerpts, up to 600 characters each | 5 excerpts, up to 1,000 characters each |
| Section reading | 1,200 characters | 2,000 characters per window |
| Agent browsing | 3 excerpts, up to 600 characters each | Source prompt stays below 6,000 characters |
| Agent model output | Query selection up to 100 tokens; optional interpretation up to 400 tokens | At most two action-model calls after the existing picker |

Python retrieval uses a dedicated rebuildable SQLite FTS5 index. Frontend-only preview uses deterministic local lexical matching. Both are paid-search- and embedding-free; their lexical ranking can differ. Search never runs code, source instructions, external queries, or financial API calls. A normal active wake still has its existing model picker and account-context behavior when independently operated; this work does not start it.

A browse attempt uses the existing default **2 simulated HRV points**, including an unavailable or unmatched query. HRV is not money. The current project does not yet measure actual provider costs; accountable operating-cost tracking remains the next integration slice. No funding allowance, reward policy, or specialty schedule is changed here.

## Source provenance and agent records

Every retrieved passage identifies its original filename, original SHA-256, section ID, and extraction locator. Search/read offsets are Unicode-character positions inside the extracted section, not coordinates in the original rendered page. Returned source references come from retrieval, not model-generated citation claims. An interpretation can be saved separately as a small unscored episode alongside those references; original sources never become new agent-written journal history.

Markdown/text extraction normalizes line endings and removes an optional BOM only in the derived copy. Word extraction includes main-document paragraphs and tables, with paragraph—not rendered-page—locators. PDF extraction uses physical-page `pdftotext -layout` text, without OCR or reconstructing images, diagrams, or mathematical layout. Each document's metadata explains its extraction scope. The exact original files remain in `library/originals/` for fuller verification.

Only the explicit attachment list in `scripts/import_library.py` is imported. Research downloads, images, API credentials, project backups, and private agent records are excluded. Import refuses to overwrite a differing preserved original. Reproducible hashes and corpus sections can be checked with `python3 -B scripts/import_library.py --check`.

## Run and boundary

On this development branch, use `cd frontend`, `npm ci`, and `npm run dev`, then open the printed local Vite address. **Do not start the Python API or engine for local library preview**: the existing backend lifecycle starts its scheduler if independently launched. Default frontend mode keeps all backend requests blocked and loads local library source text on demand. Only an explicitly connected build enables the read-only backend library routes; no connected build or service is deployed here.

The repository and source collection are private. A static frontend build contains the extracted corpus in an on-demand chunk; public distribution would expose that material. No public deployment, original download service, arbitrary-path read, upload, editing, or deletion feature is added.

## Validation

Run `python3 -B -m unittest discover -s tests -v`, `python3 -B scripts/import_library.py --check`, and `python3 -B scripts/build_ui_fixtures.py --check` from the repository root. In `frontend/`, use `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`. Python tests isolate index and agent state in temporary directories and block network/model/account work. Frontend tests exercise source browsing and the fail-closed client in a network-blocked DOM, not a real-browser visual audit.

Validation on this branch: **158 Python tests and 237 frontend tests pass**. Original/corpus and menu-fixture checks, TypeScript checking, and the production build pass; lint reports **zero warnings and zero errors**. The build gives one size advisory for the separately loaded corpus chunk (about 816 kB minified, 232 kB gzip), not an error. Source content is verified absent from the initial application bundle.

Independent review identified the first-section browsing limit. Same-document section navigation is implemented and regression-covered in Python and frontend tests. A real-corpus integration test also verifies that actual excerpts fit the agent's prompt budget and preserve exact references in unscored memory with mocked models and no account/provider activity.

The next useful work remains actual operating-cost accounting and the paper-order lifecycle, followed by protected binding of the prepared accounts and information sources. Main, credentials, funding, personas, installed orientation, HRV policy, scheduler settings, and trading permissions are unchanged by this slice.

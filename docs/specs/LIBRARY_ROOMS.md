# Library rooms

The library is one shelf today: the creator's 42 original writings, cut into
bounded sections the agents can search and read. A second collection now
exists: the financial research collection in `materials/incoming/doxtrade`,
with 21 reading notes on papers about options, liquidity, volatility,
forecasting and markets. It is a different kind of writing and deserves its own
room, so an agent can choose where to read.

## The two rooms

- **Writings room:** the creator's originals, exactly as today. Same documents,
  same section IDs and the same checked-in hashes, so earlier library
  references in the agents' memory still resolve.
- **Research room:** the 21 reading notes (P01 to P21) from the research
  collection. Each document keeps its paper title, authors, year, area,
  evidence type and review depth, and links to the original publication.
  - The notes are assistant-authored summaries, not the papers themselves. The
    room says so on every excerpt: "a reading note about the paper, not the
    paper".
  - The bundled companion documents (README, START-HERE, the guides) are not
    added. They describe the collection rather than the research.

## What the agents get

- The library choice takes an optional room: `writings`, `research`, or none
  for both. The choice prompt names the two rooms in one line each.
- Search and reading work the same in both rooms: up to three bounded excerpts,
  quoted as untrusted text.
- A note from the research room shows its paper, year, evidence type and review
  depth beside the excerpt, so an agent can tell a theoretical model from a
  measured result.
- Nothing about the research room is an instruction. The collection's own
  guidance says it is reference content that a participant may disagree with or
  leave unread, and the room keeps that.

## How it is built

- The research room gets its own corpus file (`library/research-corpus.json`),
  built by the same importer from the reading notes and `source-catalog.json`.
  Hashes are checked against the collection's `MANIFEST.sha256`, and the build
  is reproducible like the writings room.
- The writings corpus is not touched. Each section carries a room label, so
  search can be scoped without renumbering anything.
- The research collection moves from `materials/incoming/` to
  `library/research/`, so the importer reads it from the library, not an
  inbox folder.

## The dashboard

- The Library page shows the two rooms as tabs: **Writings** (42) and
  **Research** (21). Search stays within the open room.
- Research notes show the paper's title, authors, year, evidence type and a
  link to the original publication.

## Done when

- Tests cover both corpora building reproducibly, room-scoped search, a library
  choice with and without a room, research excerpts carrying their labels, and
  earlier writings references still resolving.
- On the droplet, an agent's library choice can read from either room.

## Later

- More collections as their own rooms (for example the agents' own approved
  reading, or a forum archive).
- Agents recommending a reading for the research room, with the same
  observe-only voting as ticker proposals.

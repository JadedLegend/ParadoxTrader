# Optional compost, journal destinations and environmental witness

## Intended environment

An owner can leave a quick compost note, return to its own notes, or read the witness's account if curious. Roughly five to ten notes is a useful collection size, not a quota or timed promotion. Distillation is a chosen activity. Release removes selected source compost from routine active context after a nonempty distillation; originals remain available by their source links. None of these adds a journal, recap, enthusiasm or productivity obligation.

Trading, idea and orientation are separate journal destinations; unclassified remains available. Old freeform notes stay unclassified. A note can name multiple destinations. Existing inquiry/trading lineage remains the source of its own observations, proposals, reviews, orders and fills rather than being copied into another execution ledger.

## Implementation and reuse

Extend the existing owner memory journal with sidecar metadata and compost/distillation links in the same SQLite database. Originals use the existing journal rows. Apply each chosen write and its durable operation identity in one transaction; freeze selected distillation sources before the model request. Release is archival context state, not deletion or community publication. Preserve literal sources, explicit authorship and original classification.

Within the current finite private Sessions controller, keep the five top-level capabilities and existing limits. Journal gains optional note, compost, distill and witness-read modes and explicit channels. Old journal choices retain their existing behavior. A witness-read mode requires no second model request. A chosen distillation uses at most the already-budgeted second activity request. No automatic distillation call is made at a note count. Exact request inputs continue to capture the offered subchoices and selected source context.

The quiet witness renders only source facts from consistent control-store snapshots: offered menu, committed choice/mode, outcome, failure/uncertainty and record references. It writes its own append-only database, never an agent memory, action, score, permission or trading record. Its warm, humble seed is a voice asset rather than another paid model. Owner accounts remain private; broad accounts are steward-facing. Exact agent words remain in separately attributed source notes, not flattened into a witness characterization.

## Interface and serving

Reuse the dark responsive dashboard and protected scheduler-free API. Add a Journals page with run/owner selection, three destinations plus Unclassified, active/archive filters, literal source notes, distillation links and an optional witness account. Existing inquiry/trading lineage appears through bounded source headers/links with original identity and provenance. No browser write, release, model, login-secret or launch controls are added. Preview loads clearly scripted data from actual temporary stores without transport fallback.

## Structure

- `core/memory/compost.py`: journal metadata, optional compost, immutable source selection, atomic distillation/release and read-only source views.
- `core/runtime/rehearsal/witness.py`: mechanical append-only owner/steward account and private reads; humble voice asset.
- Existing session controller/store/continuity: journal subchoices, factual source snapshots, recovery and exclusion of released compost from routine context.
- Existing protected API and `frontend/src/journals/`, `frontend/src/views/Journals.tsx`: private bounded reads and local-only examples.
- `scripts/build_compost_fixture.py`: scripted collection, chosen distillation/release and all-seven source-backed accounts in temporary databases.

## Limits of this slice

This installs the layer in existing isolated session stores. Sharing, deletion, longer-running launch/timer orchestration, cross-session memory adoption and real-provider commissioning remain separate work. No accounts, providers, schedules or trading authority are activated during development.

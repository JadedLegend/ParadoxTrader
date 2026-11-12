# Optional compost, journals and quiet witness

## What is being added

A place to leave a short note, return to an original, distill a collection when useful, or read a quiet account of the surrounding activity. Trading, idea and orientation are distinct destinations. There is also Unclassified, so an older note does not acquire an identity or purpose it was never given.

The witness is a separate housekeeping component. It writes its own factual account and links to the underlying records. Agent words remain their own words in their own journal. It does not turn brevity, rest, failure, uncertainty or a chosen activity into a personality description.

## Compost and preservation

The new `CompostStore` reuses existing journal rows in each owner's memory database. Its metadata, durable operations, frozen selections and source links are additive. A note can name multiple journal destinations. Existing unlabeled rows stay unclassified, with their unknown source mode left unknown.

Roughly five to ten notes is a useful opportunity, not a threshold. Nothing runs because a collection reaches a count. An owner choosing distillation can explicitly select one to twenty owned compost originals; the default selection is up to ten active notes. The selected IDs and bounded literal source excerpts are frozen before the chosen activity request. A completed distillation is a separate agent-authored note with links to every selected source.

Release is optional and atomic with a nonempty distillation. It excludes those sources from subsequent routine active-context builds; it does not delete, share or overwrite them. Original notes and previous captured request inputs remain reachable. Source text is stored literally, while bounded previews and request excerpts disclose truncation. The whole original is still available through its source read.

Identical operations return their previous results. Conflicting content, classification, source selection, attribution or release instructions cannot replace a committed result. Empty text at the storage boundary produces no change and releases nothing. Provider/protocol failure likewise cannot archive a collection. There is no automatic glyph compression or developmental score.

## Optional session choices

The existing five top-level capabilities and request limits remain in place. Journal now has optional note, compost, distill and witness modes, with explicit journal destinations. Existing plain journal choices retain their previous behavior. The offered subchoices and actual final request inputs are preserved, so their availability and constraints can be inspected independently of what was selected.

A chosen distillation uses the already-budgeted activity request, rather than a new background model. Witness mode reads an owner's prior accounts and needs no second model request or new agent-memory entry. No full collection or witness body is automatically placed into every wake. Reading an account is not an instruction to agree with it or write a response.

## Environmental witness

The writer obtains a consistent metadata snapshot from the control store. Its factual account separates prepared spaces, started wakes, completed rounds, uncertain requests, offered actions, committed selections and linked records. The primary account is intentionally short; source identifiers and structured facts remain alongside it.

Accounts are append-only in the run's private `witness.sqlite3`. The writer does not write agent memory, edit a decision, change a permission, submit an order or call a model. Exact repeat operations are idempotent. A reporting failure leaves the completed agent work intact and cannot replay a model request. Missing accounts are shown as missing or unavailable rather than evidence that nothing happened.

Owner accounts are private. A broad account is available to the steward through operator-authenticated reads; an agent's witness-read mode cannot select another owner or the steward account. The humble voice is a small asset and a mechanical renderer, not an additional trading agent or a psychologist.

Full mechanical source facts are retained in the witness database alongside each account. The read-only interface exposes the short account and safely projected references, rather than the whole internal snapshot. Existing protected Sessions reads provide the related decision, job, request and owned source evidence. There is no new raw-snapshot UI.

## Separate destinations and private inspection

The read-only Journals screen provides run and owner selection, the three destinations plus Unclassified, active/released/all filtering, original notes, distillation source links and optional witness reads. Existing idea/trading lineage is shown through bounded original source headers rather than copied into a competing execution ledger. Trading-tagged prose remains prose; broker-confirmed records keep their separate provenance.

Protected routes are `GET /api/rehearsals/{run_id}/journals` and `GET /api/rehearsals/{run_id}/witness`. Authentication and owner validation precede source access. The default preview resolves all reads locally. It contains no login secret, write, release, model, schedule or trading control. Switching run, owner or selected source clears stale private detail.

## Scripted example and checks

The Sessions and Journals examples use the same actual temporary source dataset. A clearly scripted pre-existing collection contains six originals, an explicit distillation releases those six, and one return note remains active. These fixture operations are not claimed as model turns. The actual scripted seven-owner controller supplies the surrounding job, request and witness facts. Example identifiers, timestamps and hashes are explicitly normalized.

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_rehearsal_fixture.py --check
python3 -B scripts/build_compost_fixture.py --check
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

Final verification passed: **662 Python tests**, **495 network-blocked frontend tests**, TypeScript checks, lint with zero warnings/errors, production build, and five source/example reproducibility checks. The build retains the existing nonblocking warning for the lazily imported library corpus.

Independent review corrections preserve journal submodes and witness references in Sessions and populate Journals with the same actual owned inquiry headers as the session. A scripted second wake genuinely chooses witness mode, retains the encounter as its owned reference and reads without a second activity request. Source-selection race tests wait for asynchronous list reads while still rejecting stale private results. The scripted steward's primary account is 772 characters; its detailed facts remain separate.

## Current scope

This is installed in the existing isolated private Sessions controller and its memory stores. Ongoing launch/timer orchestration, cross-session memory adoption, community publication, deletion policy and real-provider commissioning remain separate work. Original profiles, model assignments, existing phase restrictions, ordinary schedules and trading authority are unchanged. Development does not start agents, connect providers or brokers, deploy the app or merge main.

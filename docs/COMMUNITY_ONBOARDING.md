# Seven-agent onboarding and optional private inquiry

## What this slice makes possible

The intended launch is a common beginning for all seven participants, followed by private adjustment and later community access. The code now prepares one durable arrival cohort, gives each owner optional private inquiry tools, and keeps introductions, peer communication, portfolio sharing, and trading authority separate. It does not launch actual agents or schedule their first sessions.

Hours of settling and a suggested week or two before the forum opens remain adjustable windows. Nothing here counts elapsed time as proof of readiness, requires a personal-development narrative, or automatically opens a capability. The creator's practical financial purpose and the existing flexible work/exploration invitation remain intact.

## Identity: mythology with room to change

All fourteen original `agents/*/{soul,living}.json` files are unchanged. A compact versioned `seven_seeds.json` supplies distinctive temperaments, interests, voices, and relationship orientations. The working prompt uses those seeds instead of mandatory legacy covenants, absolute expertise, or persona claims of execution authority.

The original relationship tensions are retained as quoted creator-supplied starting perspectives. Their dramatic edges are welcome: a participant may be skeptical, ambitious, protective, lyrical, impatient, or difficult. These starting views are distinguished from actual events and the other participant's account. Communication can change a relationship or clarify a genuine disagreement; neither conflict nor reconciliation is compulsory. No invented dream-job incident or other illustrative backstory has been recorded as history.

The stable agent ID remains the owner of memory, inquiries, accounts, and permissions. Optional living names, interests, focus, and notes enter as bounded owned self-descriptions. A provider/model change does not replace the identity seed or memory. This slice does not add an identity-edit API, automatic renaming, or a complete new versioned relationship database.

## Adjustable introductions and independent gates

The public example configuration adds a `runtime.community` block. Existing private configuration and credentials are not edited. Missing community configuration defaults to settling, the environment invitation, and all three peer gates closed.

```yaml
runtime:
  current_phase: 0
  community:
    introduction_stage: settling
    available_concepts: [environment]
    forum_open: false
    peer_messages_open: false
    share_peer_positions: false
```

Stages are `settling`, `exploring`, and `market`. Available concept IDs are `environment`, `inquiry`, `paradox`, `markets`, and `options`; the configured list is explicit, independent of the stage, and may be revisited or rearranged. All five compact invitations together serialize to roughly 2.1k characters. They link an agent's attention to relevant concepts without loading the entire source library or asking it to complete a curriculum. Existing roaming, research, rest, journaling, and library browsing remain available subject to their established resource/tool boundaries.

| Control | Runtime behavior |
|---|---|
| Introduction stage/concepts | Supplies bounded invitations in wake context; does not authorize or require an action |
| `forum_open` | Also requires phase >= 1; gates menu invitation, direct dispatch, collective analysis and existing forum API reads/writes |
| `peer_messages_open` | Also requires phase >= 1; gates peer messaging and whether peer messages enter a wake's inbox context |
| `share_peer_positions` | Also requires phase >= 1; determines whether peer holdings are fetched into agent wake context |
| Existing trading permissions | Unchanged; neither introduction nor communication gates grant order authority |

Opening the forum alone does not open direct messages, share holdings, advance the phase, or expose original solo inquiry records. User-agent correspondence remains possible during private adjustment. The two-way communication model does not yet implement a comprehensive authenticated actor/session system; the existing general backend security limitations remain a separate launch requirement. These gates are not a substitute for production authentication.

## Optional inquiry activity

Every agent can encounter `inquire` in the rotating choice menu, with quiet rest always retained. Choosing it supplies owned metadata for at most five inquiries and recent entries/reviews for at most two, within a 6,000-character history budget. Supplied evidence is allowlisted, bounded at 4,000 characters, and restricted by the caller to that owner's holdings. Journals, innermost text, inbox contents, peer holdings, hidden reasoning, and arbitrary nested payloads are excluded from this model call.

The response is one strict, bounded JSON command: no change; start a question with optional separate observation/interpretation; append an observation or interpretation; pause, abandon, or reopen/revisit; or append a later review. No change is a valid result. Unknown fields, duplicate keys, malformed identifiers, foreign-owner targets, and requests to execute or propose orders fail closed. New inquiries are owner-visible even if created during a community phase. Model-written observations are attributed to the agent, not silently certified as external facts.

No journal or extra reflection episode is created by inquiry activity. Inquiries use the existing lineage store and approval-queue database, but this activity creates no proposal, queue row, order, position, review authorization, or trade permission. The previous Alchemist/DEMO mock execution boundary is unchanged.

## Durable continuity for this path

A logical `wake_id` can be supplied to `agent_wake`. It correlates picker and inquiry request costs and supplies a durable owner-scoped inquiry operation ID. The adapter commits a validated command before applying its source writes. Individual lineage steps reuse derived idempotency keys, preserving the same question and interpretation through partial application or restart.

An omitted/`None` wake ID can create a new logical wake. An explicitly blank, false, non-string, oversized, or malformed ID is rejected before model/receipt work rather than silently converted into a fresh operation. The same validation applies to direct inquiry context IDs; this was a concrete independent-review finding and is covered by regression tests.

If a receipt exists for that logical wake, the runtime resumes inquiry directly: it does not ask a fresh picker, fetch fresh portfolio context, or replace the stored command with another model interpretation. Completed retries do not repeat inquiry source records, charge another simulated activity cost, or acknowledge messages that arrived after the original operation. Invalid/unavailable/in-progress results are explicit and do not acknowledge correspondence as successfully processed.

Generation/application claims use a 15-minute lease and fencing. Concurrent claims return in-progress instead of generating competing answers. A committed command survives failure partway through its multiple idempotent steps. A process lost before command commit may need another external model request after lease expiry; external billing is not exactly-once. Memory, HRV, inbox, costs, and legacy actions remain separate databases/effects. In particular, a crash between inquiry commit and HRV persistence can leave activity accounting incomplete; the receipt does not make an entire wake globally transactional.

The unchanged legacy scheduler and HTTP wake requests do not yet provide a durable production dispatcher/resumption controller. Caller-managed logical IDs are required to recover the same operation. A newly generated wake ID denotes a new wake, not a retry of the previous one. Cohort preparation does not itself dispatch any jobs.

## Inspect without running accounts

Inquiry History now selects any of the seven stable owners. It resets detail/pagination immediately when the owner changes, ignores stale responses, and rejects mismatched owner data. Protected backend reads still require the server-side operator credential; browser login/header delivery remains unimplemented. There are no execution, approval, policy-edit, or launch controls on this page.

The default local preview is generated from actual temporary stores: the existing four Alchemist inquiries and one complete mock position, plus two private nontrading inquiries for each of the other six owners. These are labeled examples, not real model-written plans. Existing optional journal views remain separate; no shared feed of private journals or innermost material has been added. A richer low-attention “since your last visit” view remains future work rather than a compulsory narrative.

```sh
# Repository root: finite scripted seven-owner rehearsal, no account or model calls
python3 -B scripts/run_offline_arrival.py

# Offline regressions and checked-in data preservation
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_lineage_fixture.py --check
python3 -B scripts/build_ui_fixtures.py --check
python3 -B scripts/import_library.py --check

# Frontend only: inspect agent selection, inquiry history and existing choices
cd frontend
npm ci
npm test
npm run typecheck
npm run lint
npm run build
npm run dev
```

The arrival rehearsal uses temporary SQLite stores and scripted model callbacks under network guards. All seven belong to one cohort; one chooses no inquiry. Replaying each operation recovers the same result without calling its callback again. It creates no actual agent sessions, journals, orders, timers, or persistent default data. Do not start the Python API merely to inspect the preview: the unchanged API startup still initializes stores and starts its scheduler if independently operated.

## Working and remaining

| Area | Status |
|---|---|
| Compact revisable seeds, retained original relationships/profiles | Implemented; originals remain byte-identical |
| Adjustable invitations and independent phase-plus-gate policy | Implemented in menus, dispatch, wake context, and communication API boundaries |
| Private inquiry activity for all seven | Implemented against existing lineage; no new trading authority |
| Committed-command recovery and active-claim fencing | Implemented with owner-scoped receipts and explicit logical IDs |
| Common seven-member arrival identity | Implemented as durable preparation; no production dispatch or scheduling |
| Seven-owner read-only history and local examples | Implemented; operator-protected backend and fail-closed local preview |
| Simultaneous real launch, schedule/time windows, rest requests, durable dispatcher | Not activated or implemented by cohort preparation; existing legacy scheduling needs its own launch-controller work |
| Connected login, comprehensive authenticated actor permissions, hosted durability | Remain separately reviewed launch work |
| Full identity editing, agent-authored name/role changes, evolving relationship event UI | Not added; bounded existing living context is supported |
| Optional journal/plan digest since last visit | Not added; no private data is silently shared |
| Alpaca paper lifecycle and all-seven order authority | Not connected or expanded |

## Verification

The complete offline Python suite passed 444 tests before the final explicit-ID correction. The affected wake, usage, inquiry-recovery, and cohort paths were then rechecked with the two added malformed-ID regressions: all 82 targeted tests passed. The frontend passed all 395 tests, TypeScript checks, lint with zero warnings/errors, and production build. No frontend behavior changed after those checks.

Actual mocked wake integration verifies all seven owners in one cohort, private source records, no forced inquiries/reflection episodes, no-change/invalid/rest handling, same-ID cost correlation, committed recovery without a new picker or model call, no repeat activity debit, and no acknowledgement of newly arrived messages. Independent review also ran the 34 pure inquiry/cohort tests under import/network guards. Original identity/library bytes and unchanged model-provider, trading, memory/HRV, and scheduler paths were checked directly.

The build retains the previously documented nonblocking large-chunk warning for the original source corpus. That corpus is still lazy-loaded, not placed into every wake or initial application bundle. No browser-backed/live-provider launch, production schedule, or connected operator-session test is claimed.

No existing private configuration, model assignments, original library files, HRV/memory rules, trading/council execution, or scheduler implementation was changed. Provider HTTP call bodies are unchanged; only prompt identity assembly and explicit usage correlation are updated. See [scope and structure](COMMUNITY_ONBOARDING_PLAN.md) and the earlier [lineage milestone](IDEA_LINEAGE.md) for what is reused.

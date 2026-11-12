# Operating-cost visibility

This slice gives the community an accountable request record without changing its funding, HRV, personalities, activities, or schedule. The new **Costs** screen shows provider-request attempts by agent, provider, and activity. It separates provider-reported USD subtotals, explicit-rate token estimates, and requests whose costs are unknown.

## What is recorded

Each outbound OpenRouter or Perplexity HTTP attempt receives its own event ID and UTC timestamp, with elapsed time, outcome, HTTP status when available, requested/returned model, nullable token counts, and optional cost. Retries have separate events under one logical call ID. Wake and activity scopes connect the picker and chosen activity without altering their prompts or decisions. Sidebar and council model calls have their own activity labels.

No prompt, answer, query, journal, source passage, citation, request header, API key, or raw exception text enters this ledger. Missing configuration before an outbound request produces no pretend request event. Quiet rest and cooldowns do not themselves incur provider requests. A picker preceding an active choice to rest is still counted if it actually called a provider.

The ledger is a dedicated private `usage.sqlite3` in the existing persistent data directory. It opens only on explicit recording or reading, is ignored by Git, and prevents ordinary updates/deletions to recorded rows. Repeated delivery of the same event or provider/call/attempt key does not overwrite or double-count it. This is application-level append-only behavior, not a tamper-proof external audit service.

## Reading the figures

| Classification | Meaning |
| --- | --- |
| Reported | A supported provider response explicitly supplied a USD total. A reported zero remains zero. |
| Estimated | Known token counts were priced with an explicit local operator-rate snapshot. This is a token-only estimate, separately labeled. |
| Unknown | Usage, required cache details, suitable rates, or valid pricing were unavailable. A failed or timed-out request may still have incurred a charge. |

Input, output, cache, and reasoning counts remain separately nullable. Reasoning tokens are not added twice to completion counts. Token sums and cost sums are known subtotals with coverage counts, not silent replacements for missing data. Decimal arithmetic is used for ledger estimates and dollar aggregation. The screen formats very small positive amounts without displaying them as free.

Provider totals and token estimates do not replace final account invoices. Subscription plans, data-feed fees, infrastructure, and other outside spending are not yet integrated. This is the first operating-cost slice, focused on the application's existing model/research calls.

## Optional operator rates

The repository ships an empty `config/usage_pricing.example.json`, not assumed current prices. To use estimates later, supply the same schema in local `config/usage_pricing.json`; otherwise the loader checks `DATA_DIR/usage_pricing.json`. These actual pricing files are ignored by Git. The root file takes precedence. Pricing never reads API-key configuration or fetches rates automatically.

A rate entry names a provider/model, input and output USD per million tokens, an optional cached-input rate, a plain source label, and an `as_of` date. Cache counts must be known for estimates; positive cached usage requires an explicit cache rate. Rates and provenance are stored with each estimate at recording time, so editing the local table does not reprice historical requests. Invalid/missing pricing leaves coverage unknown instead of affecting provider execution.

When a response identifies a model, that returned model takes precedence for matching estimate rates. A missing matching rate leaves the estimate unknown rather than applying a different requested model's price. Supported provider-reported totals still take precedence over estimates.

## Failure behavior

An accounting write failure emits the bounded `usage_recording_failed` warning without exposing content or credentials. It does not replay the paid request. Such a warning signals a reporting gap; this first slice does not remotely recover lost usage or claim complete billing coverage.

Tracing setup can fall back before a provider call begins. A tracing failure after a completed provider response returns that completed result rather than making another request; a provider failure propagates with the existing retry count rather than being replayed by tracing. Every actual attempt is recorded independently where accounting succeeds.

## Operator screen and API

The Costs page has agent filtering, separate subtotal/coverage cards, provider/activity/agent breakdowns, and paginated request metadata. Each category is capped at 100 breakdown groups and events at 100 per API page (50 in the screen). Overall summary coverage includes all matching recorded events even if a breakdown is truncated. Read-only API filters support timezone-aware `since` inclusive and `until` exclusive timestamps.

Default frontend preview shows **clearly labeled simulated request examples**, not actual spend, and never contacts the backend. To inspect the screen locally, use `cd frontend`, `npm ci`, and `npm run dev` and open Vite's printed local address. Do not launch the Python API/engine just to inspect this screen: the existing backend lifecycle starts its scheduler when independently operated. No providers, accounts, agents, or timers were started for this development slice.

The prepared accounts and keys can be bound later through protected server-side configuration. Never put private provider keys in frontend `VITE_*` variables. The next implementation slice remains the paper-order lifecycle: proposals, orders, fills, positions, and results.

## Validation

Offline tests cover private metadata and deduplication, exact partial cost sums, explicit-rate provenance, cache/reasoning distinctions, failed attempts, tracing/accounting failure behavior, activity correlation, bounded API reads, and default preview isolation. Real temporary ledger integration uses mocked HTTP responses, not live provider calls. Frontend tests run in a network-blocked DOM; no real-browser visual audit is claimed.

Final validation passed **275 Python tests** and **294 frontend tests across 11 files**. TypeScript checks passed; lint reported zero warnings/errors; the production build succeeded. Persona/menu fixture checks and original-source hash/extraction checks also passed. The existing on-demand private corpus remains a separate lazy chunk and retains its non-blocking size warning.

Review fixes align actual stored pricing-snapshot provenance with the screen, make cache details in simulated estimates match real pricing rules, and use identical inclusive-start/exclusive-end date filtering in preview and backend. Malformed optional cache/reasoning counts remain unknown without discarding an otherwise usable provider cost. Returned-model rate matching and bounded decimal inputs prevent misleading estimates and unbounded pricing arithmetic.

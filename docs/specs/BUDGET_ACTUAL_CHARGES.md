# Budget counts actual charges, not worst cases

Status: approved 2026-11-21 (step 1 of `docs/REVIEW_2026-11-20.md`). One phase.

## The problem

Before every request, the guard sets aside the most it could cost: every input byte
priced as a token, plus the full output allowance. That set-aside was never given
back. On Nov 20 the guard had set aside $2.99 of the $3.00 budget by 1:30 PM Eastern
and stopped every later wake, while OpenRouter had actually charged $0.42.

## The rule

Each request counts against the budget as:

| The request | Counts |
|---|---|
| Succeeded, and the provider **reported** its charge | that reported charge |
| Anything else: in flight, uncertain, failed, never sent, or a charge that's unknown or only estimated | its full set-aside |

Failures never release their set-aside, even when they report $0. An error can still
be billed, and that was a deliberate earlier rule (see
`test_atomic_budget_race_and_never_release_failure_or_unknown`). Still safe: anything
not confirmed by a successful, reported charge counts at worst case. A request
is set aside in full before it's sent, so the guard can never admit more than the
budget allows, even with several requests in flight. A reported charge above its
set-aside counts at the higher, reported figure.

## Where it applies

One helper in the store decides what each request counts, and every budget decision
uses it:

- admitting a request (`reserve_request`)
- the run summary (new `counted_usd`; `reserved_usd` stays as the raw history)
- the heartbeat's "today's budget is spent" check, and the budget a new segment of
  the day gets
- the remaining budget the agents are told about in their choice
- the Heartbeat page: the "Set aside" tile becomes "Counted against the budget"
  (actual charges plus holds still waiting to be charged). "Spent today" stays.

## Tests

- A reported charge replaces the set-aside, and a later request is admitted that
  would have been refused before.
- In flight, uncertain, failed (even reporting $0), unknown-cost and estimated-cost
  requests all count in full.
- The budget still refuses a request that would pass it.
- The heartbeat keeps waking after the old set-aside total would have stopped it.

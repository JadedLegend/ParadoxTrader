# Community orientation and quiet rest

This patch builds on the offline wake foundation. It installs the agreed short Work and Exploration invitation and Practical Inquiry orientation in the actual prompt builder, rather than asking every agent to maximize the legacy Joy Equation.

## What now happens in code

| Area | Behavior |
|---|---|
| Shared orientation | Versioned text in `core/runtime/orientations/` is loaded by `core/runtime/orientation.py` and included in action, picker, sidebar, and council system prompts. |
| Trading and exploration | The short invitation says roughly half active attention goes toward trading work, with the remaining share available for exploration. It says “Treat this as a flexible balance.” No weekly quota or financial allowance is created. |
| Personal perspective | All seven existing persona files remain intact. Prompts frame their aspirations and metaphors as starting perspectives, not mandatory expressions or permission grants. |
| Available choices | Generic analysis and free roaming remain available alongside specialty variants. Private reflection becomes an explicit rotating-menu option. Rest remains available in every menu; communication still follows the existing phase permissions. |
| Quiet rest | The rest handler recovers simulated HRV without a model call, journal entry, or episode. An interval wake also skips the picker, inbox, and position reads. Choosing rest from an active menu still uses the picker and any preceding read-only context work. Unread messages remain pending on both chosen and fallback rest. |
| Activity prompts | Market work asks for evidence and alternatives without assuming a paradox, trap, mispricing, opportunity, or changed worldview must be found. Research selects its own question; external research results remain attributed user data rather than system policy. |
| New episode metadata | Automatic action records no longer receive preset coherence gains or effort numbers. Unknown values are stored as SQL NULL, and their generated legacy joy value is also NULL. Explicit historical values remain intact. |
| Retrieval | Ordinary lexical retrieval no longer adds hidden phase weights. A caller can explicitly request a phase preference. Legacy numerical metadata never ranks the results; returned legacy values are labeled as supplied, not measured learning. |
| Initialization | CLI, API initialization, and startup seed working guidance idempotently alongside the retained original OPTE/LtC excerpts. They no longer write fabricated first-person journal entries. Existing journals and canon remain untouched. |

## Funding and HRV

Actual funding is what the creator chooses and is able to provide. HRV remains the existing simulated action/recovery mechanism. Its cost table, specialty discounts, thresholds, and persistence are unchanged; the prompt now explains these points are not dollars, provider credits, biological measurements, or accomplishment scores. This patch does not introduce a replacement resource engine, a spending meter, per-agent financial allowances, or budget enforcement.

Original philosophy is preserved as source material. The prompt makes room for examining it without requiring adoption. Legacy canon still contains its original wording; it is not deleted or rewritten to manufacture a different history.

## Validation

Run `python3 -m unittest discover -s tests -v` from the repository root. The tests use temporary SQLite stores, mocked models and research providers, disabled tracing, and blocked network access. They exercise prompt contents, all seven identities, quiet versus active rest, retained unread messages, optional reflection, source-context separation, neutral new metadata, legacy history, and idempotent initialization. No live model performance or trading performance is measured by these fixtures.

## Next implementation slice

Build the fixture-backed agent choice panel and make UI/API status contracts consistent. Then add configurable wake windows and concurrency protection, bounded local library retrieval, and timestamped market evidence. The proposed 15–30-minute/eight-hour and hourly/four-hour rhythm, overnight requests, evolving names/roles, creative tools, breathing-inspired intervals, and perspective lab remain design proposals rather than advertised capabilities.

Existing council execution/decision parsing, authentication, complete logging/privacy controls, and order lifecycle still need separate work. The shared council prompt is aligned here, but that legacy pipeline's activity-specific synthesis instructions and execution behavior are not redesigned or activated. API startup still starts the legacy scheduler if the application is independently launched; this patch does not make it a safe preview server. Tests do not launch it.

This branch does not merge the preceding pull request, change credentials or phases, start a server or scheduler, connect accounts, or submit orders. Keep using the offline fixtures until the next integration boundaries are implemented and reviewed.

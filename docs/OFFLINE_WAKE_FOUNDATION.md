# Offline wake foundation

This patch makes the existing seven-agent wake path testable without provider calls, credentials, broker access, a scheduler, or a running web server. It preserves the seven identities and the existing phase structure.

## Changes

- Restored the root and frontend ignore rules, frontend lint configuration, and archive placeholder omitted during the repository upload. Extended ignore protection to runtime configuration, environment-file variants, SQLite databases and sidecars, and generated dependencies.
- Removed the wake path's nonexistent `get_config` import and mismatched broker-constructor arguments. Position reads now use the existing credential loader and `AlpacaClient(agent_id)` interface.
- Distinguished confirmed position results from missing configuration, failed lookups, and malformed responses. Error snapshots expose a category rather than a raw exception that could contain sensitive information.
- Normalized the broker base URL once so versioned endpoint paths contain one `/v2`, not `/v2/v2`.
- Sampled action choices from the full eligible pool, deduplicated choices, retained rest in every menu, and displayed actual action costs or available rest recovery. No score-based access or authority was added.
- Limited solo-phase position context to the waking agent. Community phases can include peer holdings. Solo inbox selection includes user messages, with sender filtering applied before pagination; peer messages remain pending until the phase permits them.
- Passed message and position context to the model call performing the action, not only the separate action picker. Current market-data evidence is explicitly marked `not_supplied` until the next integration stage supplies it.
- Deferred unread-message acknowledgment until the action and HRV persistence succeed. Interval wakes rest before reading messages or fetching positions.
- Required an exact valid action number; malformed choices explicitly fall back to rest. Unsupported actions return an explicit status rather than silently becoming market monitoring.
- Implemented the previously offered consensus-review action as forum analysis only. It does not invoke council execution or submit an order.
- Stopped copying private journal text into ordinary episodes or returning it in the journal action summary. This is a narrow fix, not a complete audit of API-level journal visibility or operator permissions.

## Run the offline tests

From the repository root, with Python 3.10 or newer:

```sh
python3 -m unittest discover -s tests -v
```

The tests use Python's standard library, temporary directories, real SQLite stores, mocked model responses, and mocked position lookups. The wake suite disables tracing and blocks network access before importing the runtime. It checks all seven personas, state persistence, action reachability, phase boundaries, failed-wake message retention, private-journal handling, explicit position states, and read-endpoint URL construction. No model key, market-data subscription, or broker account is needed for this test command.

The tests demonstrate local runtime behavior with fixtures. They do not measure model judgment or trading performance. Neither the application server nor the scheduler needs to be started.

## Next integration stage

Add a shared local document catalog with bounded search and exact passage retrieval, then connect selected passages and timestamped market snapshots to this tested action-context boundary. Keep agent-private annotations separate from the shared corpus. The practical inquiry orientation and source-library ingestion remain future implementation work; this patch does not silently import the full design map into every prompt.

## Remaining operating boundaries

Provider connectivity, execution limits, order lifecycle, approval-worker behavior, application authentication, and complete privacy controls still require dedicated work before unattended paper operation. Existing action-assigned coherence values and the legacy philosophical system prompt remain unchanged here; a support-oriented prompt and resource policy need an explicit follow-up patch.

Message acknowledgment and HRV/episode writes are not a single transaction. A crash after one write can leave partial state, and retrying can duplicate an action. Exactly-once action processing is not claimed. Positions also remain synchronously read during active wakes; caching and network latency budgets are separate follow-up work.

Development should continue in small reviewed branches. The offline foundation does not enable autonomous trading, change credentials, alter phase settings, or start a service.

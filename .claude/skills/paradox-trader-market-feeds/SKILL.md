---
name: paradox-trader-market-feeds
description: Use when changing ParadoxTrader market feeds or filters.
category: market-data
---

# ParadoxTrader market feeds: read-only, cached, capped, filtered at ingest

- A feed only reads: one GET per source. Never send an order, webhook or broker call. Test with scripted HTTP that refuses any URL outside the listed addresses.
- Cache each source on its own clock (Reddit every two hours) and cap daily reads per source. Show the cost in the text, for example "about $0.0015 per subreddit read".
- Drop noise where the feed is fetched, not in the prompt: law-firm and claims ads in headlines, self-promotion and near-zero-likes posts on X, pinned and NSFW posts on Reddit. Fetch a few extra items so the kept list still fills.
- Owner-supplied lists (subreddits) are validated on save: strip "r/", dedupe case-insensitively, cap the count, and reject anything else with a named error.
- Use the provider host the owner named, with its own key slot. See provider-key-model-check.
- Each new source changes the cache test's call counts. See paradox-trader-python-tests.

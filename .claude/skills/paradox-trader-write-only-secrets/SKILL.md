---
name: paradox-trader-write-only-secrets
description: Use when editing a Settings API key or secret field.
category: security
---

# Write-only secrets on ParadoxTrader Settings

- A stored key is write-only. No read path, API response, log, or history row returns its value.
- Reads show only set or not set. The OpenRouter key may show its last four characters; data and broker keys show only "set" or "cleared" in history.
- Clearing needs an explicit empty value. Whitespace-only input never clears a key.
- A damaged or unreadable key file reads as not set (catch `OSError` and `UnicodeError`), so the page still renders.
- A failed write removes its temporary copy. History records only what actually took effect.
- Save on Enter through a form submit. A save must not overwrite a draft the user typed while it was in flight.
- Broker keys are paper-only: reject live Alpaca key IDs (AK...), accept paper key IDs (PK...).
- Keep POSIX-only imports such as `fcntl` guarded so the Windows preview still imports (see paradox-trader-dashboard-preview).
- Cover each rule in `tests/test_owner_settings.py` and run that module on Linux before pushing.

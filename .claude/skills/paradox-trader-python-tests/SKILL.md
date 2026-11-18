---
name: paradox-trader-python-tests
description: Use when running ParadoxTrader tests on Linux or in CI.
category: testing
---

# ParadoxTrader tests: run from a git archive on Linux, confirm in CI

- Run the suite from `git archive` of HEAD inside WSL, not from the Windows working tree (it has CRLF checkouts). Build the archive with `git archive --format=tar HEAD`. Do not use `git stash create` for it: it prints nothing on a clean tree and skips untracked files.
- Filter WSL output with `grep -E "^(Ran|OK|FAILED|FAIL:|ERROR:)"`; the wrapper script tails only 400 lines, so a long failure can be cut off.
- From Git Bash, call WSL with `MSYS_NO_PATHCONV=1 wsl -e bash SCRIPT`. Without it Git Bash rewrites `/mnt/c/...` paths and the call fails.
- Run one module with `python -m unittest tests.MODULE`, or one test by its dotted name, before the full suite.
- After changing any limit or constant, grep the tests for the old value (for example `grep -rn "wake 3" tests/`). Stale assertions surface only as CI failures when their module was not rerun.
- Confirm on GitHub: `gh workflow run tests.yml --ref BRANCH`, then `gh run watch RUN_ID`, then `gh run view RUN_ID --log | grep -E "FAILED|passed"`.
- A single failure that does not reproduce on rerun is a timing flake: rerun that test alone, then confirm in CI.
- Pass the WSL wrapper's module list as separate unquoted words (`tests.test_a tests.test_b`). A quoted list is read as one module name and every module fails to import.
- A local Linux kit can lack `fastapi`; modules that import it fail with ImportError before any test runs. Say in the report that those modules are covered only by the GitHub run.
- Python runs on Windows show dozens of false failures in the decision and rehearsal tests. Trust only the Linux run.
- Report Python and frontend counts together (for example 716 Python and 558 frontend passed) so a missing suite is visible.

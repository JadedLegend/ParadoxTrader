---
name: paradox-trader-python-tests
description: Use when running ParadoxTrader tests on Linux or in CI.
category: testing
---

# ParadoxTrader tests: run from a git archive on Linux, confirm in CI

- Run the suite from `git archive` of the staged tree inside WSL, not from the Windows working tree (it has CRLF checkouts). Build the archive from the tree you will PR: `git add` every intended change (new files too), then `git archive -o out.tar $(git write-tree)`. `write-tree` records only staged content, so an unrelated unstaged edit stays out. Do not use `git stash create`: it picks up unstaged edits, skips untracked files, and prints nothing on a clean tree.
- Filter WSL output with `grep -E "^(Ran|OK|FAILED|FAIL:|ERROR:)"`; the wrapper script tails only 400 lines, so a long failure can be cut off.
- From Git Bash, call WSL with `MSYS_NO_PATHCONV=1 wsl -e bash SCRIPT`. Without it Git Bash rewrites `/mnt/c/...` paths and the call fails.
- Run one module with `python -m unittest tests.MODULE`, or one test by its dotted name, before the full suite.
- A cost or budget test whose fixture prices models at zero sets nothing aside, so it passes without touching the guard. Give the test catalog real prices (for example $1 and $2 per million tokens) before asserting on reserved or counted spend.
- One heartbeat `tick()` does not wake every agent. Loop the minutes across the offsets (9:00 to 9:12 in the heartbeat test config) and collect the completed wakes before asserting on all seven.
- Before shipping a test that demonstrates a newly fixed bug, run it against `git archive origin/main` with only that test file added. It must fail there with the behavior it targets; if it passes on main, it proves nothing. A main run that errors on a config check (for example `invalid_heartbeat_config`) also proves nothing: adjust the test's config until main fails on the target assertion. Tests that guard existing, unchanged behavior (for example before a refactor) may pass on main; that is their job.
- After changing any limit or constant, grep the tests for the old value (for example `grep -rn "wake 3" tests/`). Stale assertions surface only as CI failures when their module was not rerun.
- Confirm on GitHub: `gh workflow run tests.yml --ref BRANCH`, then `gh run watch RUN_ID`, then `gh run view RUN_ID --log | grep -E "FAILED|passed"`.
- A single failure that does not reproduce on rerun is a timing flake: rerun that test alone, then confirm in CI.
- Pass the WSL wrapper's module list as separate unquoted words (`tests.test_a tests.test_b`). A quoted list is read as one module name and every module fails to import.
- Before naming modules, check them with `ls tests | grep -i KEYWORD`. A guessed name (`tests.test_inquiry` for `test_inquiry_receipts.py`) fails at import while the other modules still run, so read the `ERROR:` line rather than the `Ran` count.
- A local Linux kit can lack `fastapi`; modules that import it fail with ImportError before any test runs. Say in the report that those modules are covered only by the GitHub run.
- Python runs on Windows show dozens of false failures in the decision and rehearsal tests. Trust only the Linux run.
- Heartbeat and store tests fail on Windows for platform reasons, not logic: `os.O_NOFOLLOW` and `fcntl` do not exist there (`module 'os' has no attribute 'O_NOFOLLOW'`). Run them only in the WSL archive run.
- When a fix changes behavior a test pinned, rewrite that test to the new behavior and add a test for the failure the fix addresses. Do not keep the old test green by reverting the fix.
- To prove a failure predates your change, run the same test from `git archive origin/main` in WSL. One pass and one failure on main show the test is flaky, not that the branch left it unchanged. Run it several times on both main and the branch and compare the failure and how often it happens; a branch that fails more often is a regression.
- The full WSL suite takes about 10 minutes. Run it in the background with `PYTHONPATH` set to the Linux kit and the archive directory, then read its `Ran`/`OK`/`FAILED` lines before opening a PR. On a busy machine one full run took about 20 minutes and hit the Bash timeout: split it into module groups of about five, one background job per group against the same archive, and read each group's `Ran`/`OK`/`FAILED` lines.
- A test that compares live output to a checked-in fixture (for example `test_checked_in_fixture_matches_isolated_actual_controller`) fails whenever the controller output changes. First check the changed output against the behavior the PR intends; an unintended change is a regression, not a fixture to refresh. Only then regenerate the fixture with its build script in the same PR. Run the test on both `git archive origin/main` and the branch: failing on both means the fixture was already stale; passing on main and failing on the branch points to the branch's change.
- A cache test that counts HTTP calls must change when a source is added: count calls per source per window, not a bare total. Adding Reddit moved an expected 2 to 7 and failed the test.
- A `patch.object` wrapper around a function must forward `*args` and `**kwargs`. When the wrapped function gains a keyword parameter (for example `current_skill=`), a one-argument wrapper raises TypeError before the assertion runs. Give the wrapper `**kwargs` and pass them to the original.
- A `claude-review` check that fails in about 8 seconds with no review output means the repo has no `ANTHROPIC_API_KEY` secret. Check it with `gh secret list --repo OWNER/REPO` and ask the owner to add it; the code is not at fault.
- Report Python and frontend counts together (for example 716 Python and 558 frontend passed) so a missing suite is visible. Copy each count from the run output you just read; a count typed from memory is wrong (a PR body said "27 tests pass" where the run said 22).

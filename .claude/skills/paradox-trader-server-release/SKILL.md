---
name: paradox-trader-server-release
description: Use when building or installing a ParadoxTrader release.
category: deployment
---

# ParadoxTrader: build and install a release from Windows

- Build with Git for Windows' bash (usually `C:\Program Files\Git\bin\bash.exe`) running `deploy/build_release.sh`. A bare `bash` on PATH can resolve to WSL, which fails with `set: pipefail: invalid option name` and chokes on CRLF line endings.
- Build from main after the PR is merged, so the release id matches the merged commit. The tarball is written to `dist-release/` and named by that short commit id.
- A build takes about 10 minutes. Start it in the background and wait for its completion notice instead of polling. The Vite "chunks larger than 500 kB" warning is expected; the exit code decides pass or fail.
- Install on the droplet only when the owner asks. Afterwards, confirm the next wake starts before saying the agents have the new code (see paradox-trader-agent-heartbeat).
- The owner merges PRs. Do not merge or force-push to get a build out.

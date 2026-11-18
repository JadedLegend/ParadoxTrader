---
name: verify
description: Verify a ParadoxTrader deploy on the EdgeTrader droplet (159.65.171.105) - status checks plus a throwaway sandboxed dashboard probe that never touches /etc.
---

# Verify the droplet deploy

Access: `ssh -o BatchMode=yes root@159.65.171.105` (owner key `~/.ssh/id_ed25519` on this PC works).
Run the Bash tool, not PowerShell. Read-only unless the owner asks.

## 1. Status (read-only)

```bash
ssh root@159.65.171.105 'systemctl list-unit-files "paradoxtrader*"; systemctl list-timers "paradoxtrader*";
  ss -ltnp; ufw status; readlink -f /opt/paradoxtrader/current;
  awk -F= "{print \$1, (length(\$2)>0?\"set\":\"EMPTY\")}" /etc/paradoxtrader/dashboard.env;
  journalctl -u paradoxtrader-dashboard -u paradoxtrader-backup -n 30 --no-pager'
```

Never print `dashboard.env` values. The installer enables the dashboard only when
`PARADOX_DASHBOARD_PASSWORD_HASH=pbkdf2_sha256...` is present.

## 2. Throwaway dashboard probe (works even before the owner sets a password)

Start a transient unit on port 8099 with the real unit's sandbox flags, using a random
throwaway password whose hash lives in `/run/pt-probe.env` (tmpfs). Do not edit `/etc`.

- Build the hash: `cd /opt/paradoxtrader/current && venv python -c 'sys.path.insert(0,"deploy"); from private_dashboard import hash_password'`.
- Run `systemd-run --unit=pt-dash-probe --uid=paradoxtrader -p EnvironmentFile=/etc/paradoxtrader/dashboard.env -p EnvironmentFile=/run/pt-probe.env` with the sandbox `-p` flags copied from `/etc/systemd/system/paradoxtrader-dashboard.service`. Add `-p RuntimeMaxSec=900` as a safety stop.
- Pass the password to the remote as `ssh "PW=... bash -s" < script`. Do **not** use `read` inside `bash -s`, because the script and the password share stdin.
- Use curl to check: no auth, wrong password and wrong user each return 401; GET with auth returns 200; POST and DELETE return 405; a missing asset returns 404; `/api/<unknown>` returns 404; `%2e%2e` path traversal returns 404. Also check that the operator token is absent from responses.
- For the GUI, open a tunnel with `ssh -N -L 18099:127.0.0.1:8099`, then use Playwright `setExtraHTTPHeaders({Authorization: 'Basic ...'})`. Save screenshots under `TridentIGuess/.playwright-mcp/`, because the Playwright MCP refuses the scratchpad.
- Tear down: `systemctl stop pt-dash-probe; rm -f /run/pt-probe.env`. Confirm nothing listens on 8099.

## Gotchas

- Pasting into the DO web console can leave bracketed-paste junk (`[200~ ... ~`) in commands. Type `/root/set-dashboard-password.sh` by hand.
- The Sessions page can show "Loading runs..." for a few seconds over the tunnel before it settles.
- Every screen except Sessions calls `api/app.py` routes. The gateway deliberately doesn't serve those, so they 404 (expected, but noisy).

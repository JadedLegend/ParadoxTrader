# VPS deployment (read-only dashboard and backups)

These files replace the untracked drafts staged in `/root/paradoxtrader-upload/` on the Droplet, as described in the root README's "VPS handoff". They include both fixes the review asked for:

- **Missing static files** return 404 instead of an unhandled 500.
- **Interrupted backup staging folders** (`.backup-*`) are removed on the next run, and every SQLite handle is closed explicitly.

## What gets installed

| Piece | Behaviour |
|---|---|
| `private_dashboard.py` | Serves `frontend/dist` and the read-only rehearsal API (`api/rehearsal.py`).<br>Requires the owner's login and listens only on `127.0.0.1:8080`.<br>Accepts reads only (GET/HEAD).<br>Adds `LINEAGE_OPERATOR_TOKEN` itself on the server, so the browser never sees it.<br>Never imports `api/app.py`. |
| `backup_data.py` + timer | Daily consistent SQLite copies from `/var/lib/paradoxtrader` into `/var/backups/paradoxtrader`. Keeps 14 copies. |
| `install_host.sh` | Idempotent installer. Starts **only** the dashboard and the backup timer. |

The installer does not start any agent, scheduler, model session or broker connection. The first common arrival remains a separate, explicit `scripts/rehearsal.py prepare` / `start`, run after the models and budget are agreed.

## Steps

1. **Build a release** on a machine that has git and Node:

   ```bash
   deploy/build_release.sh
   ```

2. **Copy it to the Droplet.** Access needs a key you control; add one through the DigitalOcean console if the Manus key is unavailable.

   ```bash
   scp dist-release/paradoxtrader-<sha>.tar.gz root@<droplet>:/root/
   ```

3. **On the Droplet**, from an extracted copy of the release:

   ```bash
   tar -xzf /root/paradoxtrader-<sha>.tar.gz -C /root && sudo /root/paradoxtrader-<sha>/deploy/install_host.sh /root/paradoxtrader-<sha>.tar.gz
   ```

4. **Set the dashboard password.** Run:

   ```bash
   /opt/paradoxtrader/venv/bin/python /opt/paradoxtrader/current/deploy/private_dashboard.py hash-password
   ```

   Then put the output into `PARADOX_DASHBOARD_PASSWORD_HASH` in `/etc/paradoxtrader/dashboard.env`, and rerun the installer from step 3.

5. **Open it** through an SSH tunnel (UFW keeps only port 22 open):

   ```bash
   ssh -L 8080:127.0.0.1:8080 root@<droplet>
   ```

   Then browse to http://127.0.0.1:8080.

6. **Check the backups:**

   ```bash
   systemctl start paradoxtrader-backup.service && ls /var/backups/paradoxtrader
   ```

7. **Where real runs must live.** The dashboard and the backups read `/var/lib/paradoxtrader/sessions`, which only the `paradoxtrader` user can write. Start every real run as that user with that root, or it will be invisible to the dashboard and never backed up:

   ```bash
   cd /opt/paradoxtrader/current
   sudo -u paradoxtrader /opt/paradoxtrader/venv/bin/python scripts/rehearsal.py      --root /var/lib/paradoxtrader/sessions prepare --mode offline
   ```

   `scripts/rehearsal.py` also takes its default root from `PARADOX_SESSIONS_ROOT` when that is set.

## The heartbeat (installed, off until you switch it on)

The heartbeat wakes each agent on its own staggered clock through the day. One day is one "day run" that continues the agents' home from the day before. The installer copies its timer but does not enable it.

Every limit is enforced in code (`core/runtime/rehearsal/heartbeat.py` and the session store):
- **Scheduled wake times only.** Nights are quiet.
- **No catch-up.** A wake that's more than its grace window late is recorded as missed and never run.
- **Spending.** A daily budget that the store enforces on every request.
- **Pause.** A pause switch stops new wakes; `stop` also halts the day.
- **One wake at a time per agent.** An agent whose last wake is unfinished or uncertain is skipped until you recover it; the others carry on.
- **Clock-only mode.** It records wake times and dispatches nothing.

To switch it on:

1. Write `/etc/paradoxtrader/heartbeat.json` (owned `root:paradoxtrader`, mode `0640`). Start with `"dispatch": "clock-only"` to watch it keep time without spending anything:

   ```json
   {"timezone": "America/New_York",
    "active_window": ["09:00", "17:00"], "active_interval_minutes": 30,
    "quiet_window": ["17:00", "21:00"], "quiet_interval_minutes": 60,
    "grace_minutes": 10, "daily_budget_usd": "1.00",
    "mode": "real", "models_file": "/etc/paradoxtrader/models.json",
    "dispatch": "clock-only"}
   ```

   For real wakes, change `dispatch` to `"live"` and put `REHEARSAL_OPENROUTER_API_KEY=...` in `/etc/paradoxtrader/heartbeat.env` (mode `0640`). The Settings page (coming next) will replace the models file and the key file.

2. Enable it:

   ```bash
   systemctl enable --now paradoxtrader-heartbeat.timer
   ```

3. Check, pause or stop. `status` always says why nothing is happening:

   ```bash
   cd /opt/paradoxtrader/current
   sudo -u paradoxtrader /opt/paradoxtrader/venv/bin/python scripts/heartbeat.py --root /var/lib/paradoxtrader/sessions --config /etc/paradoxtrader/heartbeat.json status
   ```

   Swap `status` for `pause`, `resume` or `stop`.

## Verified here vs. on the host

**Verified in the repo:**
- `tests/test_deploy_scripts.py`, covering authentication, read-only access, the 404 fix, staging cleanup, failed-copy cleanup and pruning.
- A local smoke run of the built release.

**Not yet verified on a clean Ubuntu 24.04 host:**
- Package installation.
- The systemd sandboxing directives.
- The timer.

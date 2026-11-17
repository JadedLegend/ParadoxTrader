# Spec: first VPS setup (dashboard and backups only)

Status: draft for the owner's review, 2026-11-15.

## Objective

Put the current release on the DigitalOcean droplet so the owner can open the private dashboard and the daily backups run. This is groundwork for the first common arrival of the seven agents. It is not that arrival.

Success means the owner can open the dashboard through an SSH tunnel and a backup snapshot exists. No agent, scheduler, model call or broker connection is running.

## Assumptions (correct any that are wrong)

1. The droplet at `159.65.171.105` runs Ubuntu 24.04 and can be wiped of anything an earlier build left behind. **Unverified:** nobody here has logged in yet.
2. Access is as `root` with an SSH key that the owner creates on this PC. Password login stays off.
3. The droplet has no ParadoxTrader data worth keeping from an earlier build. If it does, it is copied off before the install.
4. The release is built on this PC from `main` with `deploy/build_release.sh`. Nothing is built on the droplet except the Python virtualenv.
5. Only port 22 is open to the internet. The dashboard listens on `127.0.0.1:8080` and is reached only through an SSH tunnel.
6. No model key, Alpaca key or agent profile goes on the droplet in this step.

## Commands

```bash
# This PC: build the release from main (about 3 minutes)
deploy/build_release.sh main

# This PC: copy it over
scp dist-release/paradoxtrader-<sha>.tar.gz root@159.65.171.105:/root/

# Droplet: install (idempotent; starts only the dashboard and the backup timer)
tar -xzf /root/paradoxtrader-<sha>.tar.gz -C /root
sudo /root/paradoxtrader-<sha>/deploy/install_host.sh /root/paradoxtrader-<sha>.tar.gz

# Droplet: set the dashboard password (owner types it), then rerun the installer
/opt/paradoxtrader/venv/bin/python /opt/paradoxtrader/current/deploy/private_dashboard.py hash-password

# This PC: open the dashboard at http://127.0.0.1:8080
ssh -L 8080:127.0.0.1:8080 root@159.65.171.105

# Droplet: first backup
systemctl start paradoxtrader-backup.service && ls /var/backups/paradoxtrader
```

## Where things live on the droplet

| Path | Holds |
|---|---|
| `/opt/paradoxtrader/releases/<name>` | Each installed release, owned by root |
| `/opt/paradoxtrader/current` | Link to the active release |
| `/opt/paradoxtrader/venv` | Python environment |
| `/etc/paradoxtrader/dashboard.env` | Dashboard user, password hash, operator token |
| `/var/lib/paradoxtrader/sessions` | Future agent runs (user `paradoxtrader`) |
| `/var/backups/paradoxtrader` | Daily snapshots, 14 kept |

## Testing

- Before: the full suite passes on Ubuntu 24.04 in CI (686 Python, 495 frontend at `b18a1ad`).
- On the droplet:
  - `systemctl is-active paradoxtrader-dashboard` prints `active`.
  - `ss -ltn` shows 8080 only on `127.0.0.1`.
  - The dashboard returns 401 without the password and 200 with it.
  - A backup snapshot appears.
  - `systemctl list-units 'paradoxtrader*'` shows nothing beyond the dashboard and backup.

## Boundaries

- **Always:**
  - Look at what is already on the droplet before installing.
  - Check each step before the next.
  - Keep secrets in `/etc/paradoxtrader/`.
- **Ask first:**
  - Deleting anything already on the droplet.
  - Changing the firewall.
  - Rebooting.
  - Installing packages beyond what the installer needs.
- **Never:**
  - Put a key or password in git or in chat.
  - Start agents, the scheduler or `api/app.py`.
  - Open port 8080 to the internet.
  - Connect a broker.

## Success criteria

1. The owner logs in to the dashboard through the tunnel and sees the Sessions view.
2. One backup snapshot exists, and the timer is scheduled.
3. Nothing ParadoxTrader-related runs on the droplet except the dashboard.

## Open questions

- Does the droplet hold anything from an earlier build (the Render-era app, data, a Manus setup) that should be kept?
- Where did the recovered profile work end up? It is not on GitHub or on this PC yet.

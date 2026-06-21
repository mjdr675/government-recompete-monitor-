# Phase 6 — Workstation setup (gov-recompete-worker VPS)

Operator runbook for the Hetzner engineering workstation. **Run on the VPS as
user `michael`**, not from CI or a cloud session. These scripts make only small,
reversible, user-local changes — nothing touches Railway, Cloudflare, DNS,
production, databases, or any application source.

## What Phase 6 does

1. **Install uv** (Astral's Python package manager), user-local, idempotent.
2. **Discord reboot notification** — adds a systemd *drop-in* to the existing
   `workstation-start.service` so `ae notify session-started` fires after a
   reboot restores your tmux sessions. The original unit file is never edited;
   rollback is a single `rm`.

## Apply

```bash
cd ~/government-recompete-monitor-
git pull origin claude/hetzner-phase-6-setup-d8k8su

scripts/phase6-setup.sh --dry-run    # preview — changes nothing
scripts/phase6-setup.sh              # apply + verify
scripts/phase6-setup.sh --test-notify  # apply + send one real Discord ping
```

Re-running is safe: correct state is detected and skipped.

## Verify

```bash
uv --version
systemctl --user cat workstation-start.service   # should show the ExecStartPost
~/bin/workstation-check                           # expect all checks passing
```

Force a real end-to-end test of the reboot notification:

```bash
systemctl --user restart workstation-start.service   # ExecStartPost fires now
# (or actually reboot) — watch Discord for "Workstation recovered — <host>"
```

## Roll back

```bash
scripts/phase6-rollback.sh --dry-run   # preview
scripts/phase6-rollback.sh             # remove the drop-in + daemon-reload
```

Rollback removes only the notification drop-in. `uv` is intentionally left
installed (harmless, generally useful); remove it manually if you really want it
gone: `rm ~/.local/bin/uv ~/.local/bin/uvx`.

## Path overrides

If your layout differs from the documented defaults, export before running:

```bash
AE_VENV=/path/to/autonomous-engineering/.venv \
SECRETS_ENV=/path/to/secrets/env \
scripts/phase6-setup.sh
```

## The exact systemd drop-in written

`~/.config/systemd/user/workstation-start.service.d/discord-notify.conf`:

```ini
[Service]
ExecStartPost=/bin/bash -lc 'source ~/.config/secrets/env && ~/autonomous-engineering/.venv/bin/ae notify session-started --task "REBOOT" --title "Workstation recovered — $(hostname)"'
```

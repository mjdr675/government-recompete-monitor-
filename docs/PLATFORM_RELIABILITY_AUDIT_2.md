# Platform & Infrastructure — Deployment Database Backup Layer

**Lane:** Platform & Infrastructure
**Date:** 2026-06-23
**Branch:** `platform-infra-backup`
**Base:** `origin/main` @ `2e5e489`
**Scope:** Hard safety layer — pre-deploy DB backup + restore. No product/UI/business-logic/migration-logic changes.

---

## Inspection — Deployment Lifecycle Map

**Deploy entrypoint:** GitHub Actions `.github/workflows/deploy.yml`, triggered on `push` to `main`.
- `test` job (gate): installs deps, runs `pytest -q`. `deploy` job `needs: test`.
- `deploy` job: `appleboy/ssh-action` → SSH into the VPS and run a shell script.

**Deploy host & code location:** VPS, repo at `/home/michael/government-recompete-monitor-`.

**Database type(s):**
- **PostgreSQL** when `DATABASE_URL` is set (production intent per `docs/DEPLOYMENT.md`).
- **SQLite** otherwise — file at `${DB_PATH:-contracts.db}` in the repo dir (dev, and prod if no `DATABASE_URL`).
- The Railway-vs-VPS ambiguity (Phase-1 finding D1) is still unresolved, so the backup layer **handles both** engines.

**Migration trigger point:** Migrations are **not** a discrete deploy step. They run at **service start**:
`systemctl restart recompete` → app boot → `init_db()` → `_apply_migrations()` (PG) / inline schema (SQLite).
So the only safe window for a pre-migration snapshot is **after code update, before restart.**

**Rollback capability (before this change):**
- Code: `git revert` / redeploy a prior commit (documented).
- **Database: NONE.** No snapshot, no dump, no restore path. A logically-bad-but-SQL-valid migration = permanent data loss. This is finding **B1**, the highest-severity remaining gap.

### Lifecycle — before
```
push main → [test gate] → SSH:
    git fetch
    git reset --hard origin/main      # code updated
    git clean -fd
    systemctl restart recompete       # ← migrations run here, NO snapshot exists
```

### Lifecycle — after (this change)
```
push main → [test gate] → SSH (set -e):
    git fetch
    git reset --hard origin/main      # code updated (gives us current backup_db.sh)
    git clean -fd
    bash scripts/backup_db.sh predeploy   # ← MANDATORY snapshot; non-zero aborts deploy
    systemctl restart recompete       # migrations run only AFTER a snapshot exists
```

---

## Implementation

### Phase 1 — Backup script: `scripts/backup_db.sh`
- Auto-detects engine: **PostgreSQL** (`pg_dump | gzip`) or **SQLite** (`sqlite3 .backup`, `cp` fallback) `| gzip`.
- Timestamped, commit-stamped, optionally labeled filenames:
  `backup_<YYYY-MM-DD>_<HHMMSS>_<gitshorthash>[_<label>].(db|sql).gz`
  e.g. `backup_2026-06-23_164540_c54928d_predeploy.db.gz`.
- Writes to a **persistent dir outside the repo** (`${RECOMPETE_BACKUP_DIR:-/var/backups/recompete}`) — immune to `git reset --hard` / `git clean -fd`.
- **Fails loudly** (exit 1) if the backup dir is missing/unwritable or a dump fails. Exit 0 only on success or a genuine fresh-install (no DB file yet). No optional skipping.

### Phase 2 — Deploy pipeline integration: `.github/workflows/deploy.yml`
- `set -e` added to the SSH script so any failure aborts the whole sequence (the `appleboy` action otherwise only checks the last command — a backup failure could be masked by a later success).
- Backup invoked **after** `git reset` (script is current) and **before** `systemctl restart` (migrations). Label `predeploy`.

### Phase 3 — Safety guards
- Backup dir is persistent and outside the tree; the script enforces writability before proceeding.
- Rotation: keeps newest `${RECOMPETE_BACKUP_RETAIN:-15}` (within the 10–20 target), prunes older.
- `.gitignore` adds `backups/` and `recompete-db-backups/` so any in-tree override can never be committed or cleaned mid-deploy.

### Phase 4 — Restore path: `scripts/restore_db.sh`
- `--list` shows backups newest-first.
- No file → restores the **latest**; `<file>` → restores a specific snapshot (bare name in backup dir or absolute path).
- SQLite: writes a `*.pre-restore.<ts>` safety copy of the live DB before overwriting. PostgreSQL: `gunzip | psql`.
- Refuses to run non-interactively without `--yes` (prevents accidental clobber). Logs every step.

---

## Validation (all locally exercised)

| Check | Result |
|-------|--------|
| `bash -n` both scripts | clean |
| Backup filename format | ✅ `backup_2026-06-23_164540_c54928d_predeploy.db.gz` |
| SQLite backup | ✅ gzipped snapshot, exit 0 |
| Fresh-install (no DB) | ✅ logged, exit 0 |
| **Wipe → restore latest → data recovered** | ✅ `[(1, 'Acme Gov')]` |
| Pre-restore safety copy | ✅ created |
| Non-interactive restore w/o `--yes` | ✅ refused, exit 1 |
| Backup to unwritable dir | ✅ aborts, exit 1 (deploy would stop) |
| Rotation (retain 3 of 6) | ✅ newest 3 kept |
| `--list` | ✅ |
| `deploy.yml` YAML valid | ✅ |
| Full test suite | ✅ 1949 passed |
| `compileall` | ✅ clean |

**VPS-side note:** the SSH execution path cannot be run from this environment (no VPS access). Both scripts are fully validated locally, including a wipe→restore round-trip; the deploy wiring is a single guarded, `set -e`-protected invocation.

---

## Outcome
No database change can be deployed without a recoverable snapshot existing first:
the deploy aborts (`set -e` + non-zero exit) before restart/migrations if the backup fails,
and any snapshot is restorable via `scripts/restore_db.sh`.

## Follow-ups (not in this lane)
- **D1:** Reconcile `docs/DEPLOYMENT.md` (Railway claims vs. actual VPS deploy).
- Off-host backup retention (copy snapshots to object storage) for full disaster recovery.
- **A2/T2:** Add `compileall` + codified `pytest.ini` to CI.
- **M1:** Harden the migration SQL splitter before any dollar-quoted PG migration.

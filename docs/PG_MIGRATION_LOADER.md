# SQLite → Postgres migration loader

`scripts/migrate_sqlite_to_pg.py` performs the **one-time data copy** from a
read-only SQLite snapshot into an already-migrated Postgres database during the
Recompete Postgres cutover.

It is a data loader only — it does **not** create schema, touch Railway, or read
the live SQLite volume. Always run it against a *snapshot copy* (a
`scripts/backup_db.sh` file pulled from R2 or the volume), never the live DB.

## Guarantees

- **Source is read-only.** The snapshot is opened with `file:<path>?mode=ro` via a
  sqlite3 creator, so the loader can never mutate it.
- **Atomic.** Truncate (fresh mode) → load → sequence reset → row-count verify all
  run in a single transaction. Any error — including a count mismatch — rolls the
  whole thing back, leaving Postgres unchanged.
- **FK-safe without superuser.** Tables load in topological order (parents before
  children) from the target's foreign-key graph, so constraints are satisfied
  during load with no need to disable triggers.
- **Column-drift tolerant.** Only columns present on **both** sides are copied;
  source-only columns are logged and skipped (handles SQLite-vs-Postgres schema
  drift). `schema_migrations`, `sqlite_*`, and FTS shadow tables are excluded.
- **Idempotent.** `--fresh` truncates first (`RESTART IDENTITY CASCADE` on
  Postgres), so a re-run is a clean reload. Sequence values are reset past the
  copied ids so future inserts don't collide.

## Usage

```bash
# Preview only — no writes:
python scripts/migrate_sqlite_to_pg.py --source /backups/contracts_snapshot.db \
    --target "$DATABASE_URL" --dry-run

# Load into an empty, freshly-migrated Postgres:
python scripts/migrate_sqlite_to_pg.py --source /backups/contracts_snapshot.db \
    --target "$DATABASE_URL"

# Re-run / reload (destructive: truncates target first):
python scripts/migrate_sqlite_to_pg.py --source /backups/contracts_snapshot.db \
    --target "$DATABASE_URL" --fresh
```

Exit codes: `0` success, `1` loader/verification failure (rolled back), `2` bad args.

## Where this fits relative to PR #53

PR #53 is the **repo-side Railway config** (activates `worker`/`beat`, wires the
`DATABASE_URL`/`REDIS_URL` references, single ingest owner). It must **not** be
merged/deployed until the Postgres data cutover is done. This loader is the tool
that performs the data step of that cutover. Ordering:

1. Provision Postgres (done) and take a fresh, verified SQLite snapshot
   (`scripts/backup_db.sh`, integrity-checked + uploaded to R2).
2. Set `DATABASE_URL` on the live `web` service and redeploy so
   `init_db()` → `_apply_migrations()` **builds the schema** on the empty Postgres.
3. **Run this loader** against the snapshot copy → `DATABASE_URL` (this step).
4. Run the integrity gate (per-table counts, spot checks, `/api/health/detailed`).
5. Soak `web` on Postgres.
6. **Only then merge PR #53** so `worker`/`beat` come up against the populated
   shared Postgres.

This loader therefore lands as its **own PR, merged before PR #53** — it is a
prerequisite for the cutover, and keeping it separate keeps PR #53 to config/docs.

Steps 2–6 are human-only, authorization-gated production actions
(see `recompete-worktrees/ops-celery-postgres` → `docs/O5_POSTGRES_MIGRATION_PLAN.md`).

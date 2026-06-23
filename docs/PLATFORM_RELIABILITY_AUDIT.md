# Platform & Infrastructure Reliability Audit

**Lane:** Platform & Infrastructure
**Date:** 2026-06-23
**Branch:** `platform-infra-reliability`
**Base:** `origin/main` @ `67218ac`
**Scope:** Inspection of CI, deployment, migrations, test execution, backups. No product/UI/billing changes.

---

## 1. GitHub Actions Audit (`.github/workflows/deploy.yml`)

**What exists:**
- Single workflow `Deploy Recompete`, triggered on `push` to `main`.
- `test` job: checkout → setup Python 3.14 → `pip install -r requirements.txt` + `pytest` → stub `ae` CLI → `pytest -q`.
- `deploy` job: `needs: test` → SSH to VPS (`appleboy/ssh-action`) → `git fetch` + `git reset --hard origin/main` + `git clean -fd` → `systemctl restart recompete`.

**Findings:**
| # | Severity | Finding |
|---|----------|---------|
| A1 | **High** | **No `concurrency` control.** Two pushes to `main` in quick succession launch two overlapping `deploy` jobs. Both SSH into the same VPS path and run `git reset --hard` + `systemctl restart recompete` simultaneously — a race that can leave the working tree or service in an indeterminate state (partial reset, double restart, restart against half-updated files). |
| A2 | Medium | `test` job runs `pytest -q` but **not** the project's documented compile check (`python3 -m compileall . -q`). Marginal, since pytest collection imports modules. |
| A3 | Low | No pip cache; every run reinstalls all deps. Slower, not a correctness risk. |
| A4 | Low | `pytest` installed twice (in `requirements.txt`? + explicit `pip install pytest`). Cosmetic. |

## 2. Deployment Flow Audit

**Findings:**
| # | Severity | Finding |
|---|----------|---------|
| D1 | **High** | **Documentation contradicts reality.** `docs/DEPLOYMENT.md` (dated 2026-06-23) states: *"There is no VPS, no systemd, no nginx, no GitHub Actions CI/CD defined in this repo. Deploys happen automatically via Railway."* But `deploy.yml` **does** deploy to a VPS via SSH + `systemctl`. The rollback procedure in the doc ("Railway one-click redeploy") does not apply to the actual VPS deploy path. An operator following the doc during an incident would take the wrong recovery action. |
| D2 | Medium | `git reset --hard origin/main` + `git clean -fd` runs with **no pre-deploy database backup**. `.gitignore` does spare `.env` and `contracts.db` (clean lacks `-x`), so secrets/DB survive — but a bad schema migration during `release`/startup has no snapshot to roll back to. |
| D3 | Low | `deploy.yml` restart (`systemctl restart recompete`) does not run migrations explicitly; relies on app startup `init_db()`. Fine for current design, undocumented. |

## 3. Migrations Audit (`db.py` `_apply_migrations`)

**Strengths (well-built):**
- Version-tracked via `schema_migrations` table.
- Each migration runs **atomically** (statements + tracking INSERT in one transaction).
- Applied in deterministic filename order.
- **Stops immediately on first failure** — never leaves partial state, never advances.
- First-use bootstrap (`_stamp_pre_existing`) probes the live schema so pre-tracking installs (001–010) aren't re-executed.

**Findings:**
| # | Severity | Finding |
|---|----------|---------|
| M1 | Medium (latent) | Migrations are split on `;` naively. A future migration using dollar-quoted PG function bodies, triggers, or semicolons inside string literals would split incorrectly. Current files (001–012) are safe; this is a latent trap for future authors. |
| M2 | Low | SQLite path (no `DATABASE_URL`) skips the SQL migration files entirely and relies on inline `CREATE TABLE IF NOT EXISTS` + additive `ALTER TABLE` helpers. Dev/prod schema-application paths diverge; acceptable but worth documenting. |

## 4. Test Execution Audit

**Strengths:**
- `tests/conftest.py` has two well-reasoned autouse fixtures: mocks `send_email_task.delay` (avoids 20s Celery retry hangs when Redis absent) and resets the rate limiter between tests (prevents 429 cross-test contamination).
- Full suite gates deploy via `needs: test`.

**Findings:**
| # | Severity | Finding |
|---|----------|---------|
| T1 | Low | No `pytest.ini`/`pyproject.toml` pytest config — no enforced markers, `-x`, or warning filters. The documented standard (`pytest -x -q`) is not codified. |
| T2 | Low | Compile check (`compileall`) is documented as part of validation but absent from CI (see A2). |

## 5. Backup Strategy Audit

**Findings:**
| # | Severity | Finding |
|---|----------|---------|
| B1 | Medium | **No automated backup of the production database** anywhere in the repo (no `pg_dump`, no scheduled snapshot, no pre-deploy dump). If prod is PostgreSQL (Railway-managed), the platform provides backups; if prod is the VPS SQLite at the repo path, there is no backup and a corrupt migration is unrecoverable. The ambiguity (D1) makes this worse — we cannot be certain which DB is live. |

---

## Prioritization — Highest Value vs. Smallest Merge Risk

| Candidate | Value | Merge risk | Touches prod-deploy path? |
|-----------|-------|-----------|---------------------------|
| **A1: add `concurrency` to deploy workflow** | **High** — eliminates overlapping-deploy race | **Minimal** — pure GitHub Actions guard, no code, no script change | No (guards the job, doesn't change its steps) |
| D1: rewrite DEPLOYMENT.md | High (operational) | Minimal | No |
| A2/T2: add compileall to CI | Low-med | Minimal | No |
| D2/B1: pre-deploy DB backup | High | **High** — must edit the live SSH deploy script | **Yes** |
| M1: robust SQL splitter | Med (latent) | Medium — changes migration engine | Indirectly |

**Selected fix: A1 — add a `concurrency` group to the deploy workflow.**

Rationale: it is the single change with the highest reliability value per unit of merge risk. Overlapping production deploys that both run `git reset --hard` + `systemctl restart` are a genuine corruption/downtime hazard with no current safeguard. Adding `concurrency` is a purely additive GitHub Actions guard — it changes none of the existing job steps, no application code, no migration logic, and cannot affect the test suite or runtime behavior. Deploys serialize instead of racing; `cancel-in-progress: false` ensures an in-flight deploy is never killed mid-`reset`/`restart` (we queue the next one instead).

The other high-value items (D1 doc fix, D2/B1 backups) are recorded above for follow-up lanes. D2/B1 in particular must wait until the Railway-vs-VPS ambiguity (D1) is resolved, since the correct backup mechanism depends on which database is actually live.

---

## Implemented Change

Added to `.github/workflows/deploy.yml`:

```yaml
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false
```

- `group: deploy-${{ github.ref }}` — one deploy pipeline per branch (i.e. per `main`).
- `cancel-in-progress: false` — never cancel a running deploy; the next push waits until the current deploy finishes before starting. This prevents two `git reset --hard` + `systemctl restart` sequences from interleaving on the VPS.

## Validation
- Full test suite: see commit/report output.
- Compile check: `python3 -m compileall . -q`.

## Follow-up (not in this lane)
- **D1:** Reconcile `docs/DEPLOYMENT.md` with the real VPS deploy path (or remove the stale Railway claims).
- **D2 / B1:** Add a pre-deploy database snapshot once the live DB engine is confirmed.
- **M1:** Harden the migration SQL splitter before any dollar-quoted PG migration is written.
- **A2 / T2:** Add `compileall` and a codified `pytest.ini` to CI.

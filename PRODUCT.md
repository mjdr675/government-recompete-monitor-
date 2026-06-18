# PRODUCT.md — Architecture Reference

This document describes how the product is built. For what it does and why,
see `VISION.md`. For where it is going, see `ROADMAP.md`.

---

## Overview

The application is a Python/Flask web app backed by SQLite, deployed on Railway,
maintained by an AI agent system that runs locally. The stack is intentionally
minimal: no JavaScript framework, no ORM, no message queue. Complexity is added
only when a real constraint demands it.

```
Browser → Railway (gunicorn) → Flask app → SQLite
                                        ↘ Jinja2 templates
AI agent (local) → patches/ → patcher → git commit
```

---

## Flask Application (`app.py`)

Entry point for all HTTP traffic. Responsibilities:

- Route definitions and URL dispatch
- HTTP basic authentication (bypassed for `/health`)
- Request parameter extraction and validation
- Passing data from the database layer to Jinja2 templates
- No business logic — that lives in `db.py`, `analytics.py`, and `report_builder.py`

**Key routes:**

| Route | Purpose |
|---|---|
| `GET /` | Dashboard with summary report |
| `GET /contracts` | Searchable, filterable, paginated contract list |
| `GET /contract/<id>` | Single contract detail |
| `GET /compare?a=<id>&b=<id>` | Side-by-side contract comparison |
| `GET /vendor/<name>` | Vendor intelligence profile |
| `GET /agency/<name>` | Agency intelligence profile |
| `GET /views` / `GET /views/<id>` | Saved views (redirects to filtered /contracts) |
| `GET,POST /ingest` | Manual CSV upload or API pull trigger |
| `GET /health` | Railway uptime probe — always returns `{"status":"ok"}` |

**Authentication:**
HTTP Basic Auth controlled by `AUTH_USER` and `AUTH_PASS` environment variables.
If either is unset, auth is bypassed entirely (useful for local development).
The `/health` route is always unauthenticated.

---

## Database (`db.py`)

SQLite via the Python standard library `sqlite3`. No ORM.

**Schema — `contracts` table:**

| Column | Type | Notes |
|---|---|---|
| `internal_id` | TEXT PK | Stable identifier for joins |
| `award_id` | TEXT | Official contract award identifier |
| `vendor` | TEXT | Contractor name |
| `agency` | TEXT | Top-level federal agency |
| `sub_agency` | TEXT | Component or office |
| `value` | REAL | Total contract value in dollars |
| `start_date` | TEXT | ISO 8601 |
| `end_date` | TEXT | ISO 8601 — primary recompete signal |
| `days_remaining` | INTEGER | Computed at ingest time |
| `competition_type` | TEXT | Full, set-aside, sole source, etc. |
| `solicitation_id` | TEXT | |
| `recompete_score` | INTEGER | 0–100, higher = more likely to recompete |
| `priority` | TEXT | CRITICAL / HIGH / MEDIUM / LOW |
| `raw_json` | TEXT | Original API response, preserved for reprocessing |
| `updated_at` | TEXT | ISO 8601 |

**Full-text search:**
FTS5 virtual table `contracts_fts` indexes `vendor`, `agency`, and `award_id`.
Kept in sync via SQLite triggers on INSERT, UPDATE, and DELETE.

**Key functions:**
- `init_db()` — creates tables, indexes, FTS table, and triggers
- `upsert_contract(row)` — idempotent insert/update by `internal_id`
- `get_contracts(q, agency, priority, days, sort, direction, page, limit)` — paginated search
- `save_snapshot(run_date, rows)` — records a point-in-time snapshot for change detection
- `connect()` — returns a `sqlite3.Connection`; callers are responsible for closing it

**Known limitation:**
SQLite is single-writer. Phase 2 migration to PostgreSQL is required for multi-
user concurrent access. See `ROADMAP.md — Phase 2`.

---

## Analytics (`analytics.py`)

Query layer for aggregated intelligence. Reads from the `contracts` table via
raw SQL and returns typed dictionaries.

- `vendor_profile_analytics(con, name)` — total value, contract count, agencies
  served, win history for a specific vendor
- `agency_profile(con, name)` — spend profile, active vendors, NAICS breakdown
  for a specific agency

No write operations. Returns data ready for template rendering.

---

## Report Builder (`report_builder.py`)

Generates the dashboard summary report for a given date. Aggregates totals,
priority breakdowns, and top opportunities into a single dict passed to
`dashboard.html`.

---

## Change Detector (`change_detector.py`)

Compares the latest snapshot against the previous one to identify contracts that
changed status, value, or vendor since the last ingest run. Results surface as
alerts in future versions.

---

## Views (`views.py`)

Defines `SAVED_VIEWS` — a list of named filter presets (High Value, Expiring Soon,
etc.) that map to pre-built query strings for `/contracts`. The views list page
displays these as quick-access links.

---

## AI Agent System (`ai_agent/`)

A local, multi-agent engineering organization that reads the backlog, writes code,
reviews it, applies it, tests it, and commits it — all without human intervention
at the code level. Humans control what goes to the remote.

**Components:**

| File | Role |
|---|---|
| `agent.py` | Entry point. Safety checks, git status, delegates to manager |
| `manager.py` | Orchestrator. Loads tasks, assigns specialists, runs pipeline |
| `llm.py` | Anthropic API wrapper. Reads key from env, never prints it |
| `reviewer.py` | Safety scanner. Blocks patches containing dangerous patterns |
| `memory.py` | Repository knowledge base. SQLite index of functions, routes, classes |
| `patcher.py` | Patch execution pipeline. Validate → apply → test → commit or rollback |
| `backend_engineer.py` | Specialist for Python/Flask/DB tasks |
| `frontend_engineer.py` | Specialist for templates and UI |
| `qa_engineer.py` | Specialist for tests and quality |
| `devops_engineer.py` | Specialist for deployment, Railway, environment |
| `docs_writer.py` | Specialist for documentation |

**Pipeline (one run):**
```
agent.py
  → safety checks (branch = ai-agent, DRY_RUN flag)
  → git status log
  → manager.py
      → memory.update() — re-index changed files
      → load_all_tasks() — read backlog/ in priority order
      → assign_specialist(task) — keyword match
      → specialist.plan(task, memory) — LLM call
      → reviewer.review(patch) — safety scan
      → save_patch() — write to patches/
      → write_handoff() → HANDOFF.md
      → write_task_log() → TASK_LOG.md
      → if DRY_RUN=false and APPLY_PATCH=true and safe:
          → patcher.execute()
              → parse_patch()
              → validate() — path traversal, exact-match, UTF-8
              → _apply_changes() — writes files, keeps in-memory backups
              → _run_tests() — pytest
              → if tests pass: _commit()
              → if tests fail: _rollback(), _save_failure_report()
```

**Safety gates:**
- `DRY_RUN=true` by default — never edits files without explicit opt-in
- `APPLY_PATCH=true` required as a second gate for file modifications
- Branch must be `ai-agent` when `DRY_RUN=false`
- Reviewer blocks: `git push`, `rm -rf`, `DROP TABLE`, `DELETE FROM`,
  `subprocess` exec, `.env` reads, hardcoded API keys
- Patcher validates: no `..` path traversal, file must exist, before-text
  must match exactly once, file must be UTF-8

---

## Repository Memory (`ai_agent/memory.py`)

SQLite index (`.ai_agent_memory.db`, gitignored) that the AI uses for context.

**Indexed per Python file:**
- Functions (name, line number, docstring, source snippet)
- Classes (name, line number, methods)
- Flask routes (path, function name, HTTP methods)
- Imports (module name, alias)
- Template references (`render_template()` calls)

**Update strategy:** mtime-based. Only files changed since the last index run
are re-parsed. Full re-index available via `force=True`.

**Search API:**
- `find_function(name)` — fuzzy name match
- `find_route(path)` — route path match
- `find_import(module)` — module name match
- `find_class(name)` — class name match
- `find_template(name)` — template reference match
- `get_function_source(name)` — returns full source of a function

---

## Deployment (Railway)

**Process:** `gunicorn app:app --bind 0.0.0.0:$PORT` (defined in `Procfile`)

**Environment variables required:**
| Variable | Purpose |
|---|---|
| `PORT` | Assigned by Railway; gunicorn binds to it |
| `AUTH_USER` | HTTP Basic Auth username (optional) |
| `AUTH_PASS` | HTTP Basic Auth password (optional) |
| `ANTHROPIC_API_KEY` | Required for AI agent runs (not needed for the web app) |

**Health check:** Railway polls `GET /health` every 30 seconds. Returns
`{"status": "ok"}` with HTTP 200. Auth is bypassed on this route.

**Database:** SQLite file on Railway's ephemeral filesystem. Data is lost on
redeploy. Phase 2 migration to Railway PostgreSQL plugin resolves this.
See `ROADMAP.md — Phase 2, Technical Goals`.

---

## Patch Pipeline (`patches/`)

- Pending patches: `patches/*.md` with status `proposed — not applied`
- Failure reports: `patches/failures/*.md` (gitignored)
- Patch format: markdown with `## Patch: path/to/file` blocks containing
  `### Before` / `### After` fenced code sections
- The patcher does exact-string replacement — the `Before` block must match
  the file content character-for-character

---

## Testing Strategy

**Test runner:** pytest

**Test locations:**
- `tests/test_memory.py` — 32 tests for the repository memory subsystem
- `tests/test_patcher.py` — 25 tests using real temporary git repos
- `tests/test_app.py` — Flask route tests using a temporary SQLite database

**Principles:**
- No mocking of the database in integration tests — use a real SQLite file in a `tmp_path` fixture
- The patcher tests use `git init` in a temp directory so the real repo is never touched
- The agent system writes failure reports to `patches/failures/` (gitignored)
  rather than leaving state in the main test tree
- `pytest` exit code 5 (no tests collected) is treated as a pass by the patcher
  to avoid blocking on repositories where test files haven't been written yet

**Running tests:**
```bash
python -m pytest --tb=short -q
```

All tests must pass before any commit. The patcher enforces this gate automatically.
See `STYLE.md — Testing` for standards on writing new tests.

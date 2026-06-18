# ARCHITECTURE.md — System Architecture

A complete technical reference for the government recompete intelligence platform.
For the product vision and roadmap see `company/VISION.md` and `company/ROADMAP.md`.
For coding standards see `docs/STYLE.md`. For feature-level architecture see `docs/PRODUCT.md`.

---

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser                             │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│                  Railway (cloud)                        │
│  Procfile: python -c "init_db()" && gunicorn app:app    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │               Flask (app.py)                     │   │
│  │  auth.py blueprint  ·  require_login hook        │   │
│  │  Jinja2 templates   ·  session cookie (SECRET_KEY│   │
│  └──────────────┬──────────────────┬────────────────┘   │
│                 │                  │                     │
│  ┌──────────────▼────┐  ┌──────────▼─────────────────┐  │
│  │   db.py / users.py│  │   analytics.py             │  │
│  │   SQLite          │  │   report_builder.py        │  │
│  │   contracts.db    │  │   change_detector.py       │  │
│  └───────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

Local machine:
┌─────────────────────────────────────────────────────────┐
│  ai_agent/  (runs locally, commits locally, never pushes│
│  agent.py → manager.py → specialist → llm.py           │
│                        → reviewer.py → patcher.py       │
│                                      → pytest → git commit│
│  memory.py  (.ai_agent_memory.db — repo knowledge index)│
└─────────────────────────────────────────────────────────┘
```

---

## Flask Application

**Entry point:** `app.py`  
**Pattern:** route handler only — no business logic  
**Auth:** `auth.py` Blueprint, session cookie, `require_login` before_request  

### Request lifecycle

```
Request arrives
  → require_login (before_request)
      → public path (/health /login /register)? → pass through
      → session has user_id? → pass through
      → else → redirect /login?next=<path>
  → load_logged_in_user (auth blueprint before_app_request)
      → sets g.user from DB for use in templates
  → route handler
      → queries db.py / analytics.py
      → renders Jinja2 template
  → response
```

### Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | None | Railway uptime probe |
| GET/POST | `/login` | None | Sign-in form |
| GET/POST | `/register` | None | Account creation |
| GET | `/logout` | None | Clear session |
| GET | `/` | Required | Dashboard summary |
| GET | `/contracts` | Required | Searchable contract list |
| GET | `/contract/<id>` | Required | Contract detail |
| GET | `/compare` | Required | Side-by-side comparison |
| GET | `/vendor/<name>` | Required | Vendor intelligence |
| GET | `/agency/<name>` | Required | Agency intelligence |
| GET | `/views` | Required | Saved view list |
| GET | `/views/<id>` | Required | Saved view (redirect) |
| GET/POST | `/ingest` | Required | CSV upload / API pull |

---

## Database

**Engine:** SQLite 3 via Python standard library `sqlite3`. No ORM.  
**File:** `contracts.db` (ephemeral on Railway — Phase 2 migrates to PostgreSQL)  
**Initialization:** `db.init_db()` — idempotent, called from Procfile at startup  

### Schema

**`contracts`** — core contract records  
Primary key: `internal_id TEXT`  
Key columns: `vendor`, `agency`, `value`, `end_date`, `days_remaining`, `recompete_score`, `priority`  
FTS5 virtual table `contracts_fts` mirrors `vendor`, `agency`, `award_id` for full-text search.  
SQLite triggers keep FTS in sync on INSERT/UPDATE/DELETE.

**`users`** — registered accounts  
Primary key: `id INTEGER AUTOINCREMENT`  
Columns: `email UNIQUE`, `password_hash` (Werkzeug scrypt), `created_at`, `is_active`  
Index on `email` for fast login lookup.

**`contract_snapshots`** — point-in-time copies for change detection  
Unique on `(run_date, internal_id)`.

**`changes`** — detected changes between snapshots  
Drives the change detection system and future alerting.

### Write safety

SQLite is single-writer. Concurrent writes from multiple gunicorn workers are
serialized by SQLite's WAL mode (enabled automatically). This works at low
traffic. Phase 2 migrates to PostgreSQL when concurrent write contention appears.

---

## Authentication

**Module:** `auth.py` (Flask Blueprint) + `users.py` (model)  
**Session store:** Flask signed cookie (`itsdangerous`) — requires `SECRET_KEY` env var  
**Password hashing:** Werkzeug `generate_password_hash` with scrypt  

### Security properties

- Passwords are never stored, logged, or transmitted in plaintext
- Sessions are signed with `SECRET_KEY` — tampering invalidates the cookie
- All routes except `/health`, `/login`, `/register` require an active session
- `g.user` is populated from DB on every request (not from session data directly)
- Email addresses are normalized to lowercase on creation and lookup

### Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | Production | `"dev-secret-change-in-production"` | Must be set in Railway |
| `AUTH_USER` | No | (removed) | Legacy Basic Auth — no longer used |
| `AUTH_PASS` | No | (removed) | Legacy Basic Auth — no longer used |

---

## Repository Memory

**Module:** `ai_agent/memory.py`  
**Database:** `.ai_agent_memory.db` (SQLite, gitignored, auto-rebuilt)  
**Purpose:** Gives the AI agent structured knowledge of the codebase so it can write
targeted patches without reading every file on every run.

### What is indexed

For every `.py` file in the repo:
- **Functions** — name, line number, docstring excerpt, source snippet
- **Classes** — name, line number, method list
- **Flask routes** — HTTP path, handler function name, methods
- **Imports** — module name and alias
- **Template references** — `render_template()` call sites

### Update strategy

Mtime-based incremental indexing. Only files modified since the last index run
are re-parsed. Full rebuild: `RepoMemory.index(force=True)`.

### Search API

```python
mem = get_memory(repo_root)
mem.find_function("get_contracts")   # → list of {name, file, line, source}
mem.find_route("/contracts")         # → list of {path, handler, file}
mem.find_class("RepoMemory")         # → list of {name, file, methods}
mem.get_function_source("compare")   # → str source of function
```

---

## AI Agent Workflow

The agent system runs locally and never pushes to the remote. One run = one task.

```
python ai_agent/agent.py
  │
  ├── Safety checks
  │   ├── Branch must be 'ai-agent' when DRY_RUN=false
  │   └── Git status logged
  │
  ├── memory.update()          — re-index changed files
  │
  ├── load_all_tasks()         — read backlog/ in priority order
  │   critical → bugs → high → medium → TASK.md
  │
  ├── assign_specialist(task)  — keyword match
  │   devops / qa / frontend / docs / backend (default)
  │
  ├── specialist.plan(task, memory)  — LLM call via llm.py
  │
  ├── reviewer.review(patch)   — safety scan (blocks dangerous patterns)
  │
  ├── save_patch()             — write to patches/
  │
  ├── write_handoff()          — append to HANDOFF.md
  ├── write_task_log()         — append row to TASK_LOG.md
  │
  └── if DRY_RUN=false and APPLY_PATCH=true and safe:
        patcher.execute()
```

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `DRY_RUN` | `true` | Never modify files |
| `APPLY_PATCH` | `false` | Apply reviewed patches |
| `ANTHROPIC_API_KEY` | (unset) | Required for LLM calls |

---

## Patch Pipeline

**Module:** `ai_agent/patcher.py`

### Patch file format

```markdown
# Proposed Patch
**Task:** Short description
**Role:** backend
**Status:** proposed — not applied

## Patch: path/to/file.py
### Before
```python
<exact text to replace>
```
### After
```python
<replacement text>
```
```

### Execution pipeline

```
parse_patch(path)
  → validate()
      ✓ No path traversal (..)
      ✓ File exists within repo root
      ✓ File is UTF-8 text
      ✓ Before text appears exactly once
  → _apply_changes()
      → backup all files to memory
      → write After text
  → _run_tests()  (pytest --tb=short -q)
      → PASS: _commit() → git add + git commit
      → FAIL: _rollback() → restore from backup
               _save_failure_report() → patches/failures/
```

### Safety scanner (`reviewer.py`)

Blocks patches containing: `git push`, `rm -rf`, `DROP TABLE`, `DELETE FROM`,
`subprocess` exec, `.env` file reads, hardcoded API keys.

---

## Testing Pipeline

**Runner:** pytest  
**Location:** `tests/`  

### Test files

| File | What it tests | Count |
|---|---|---|
| `test_memory.py` | Repository memory index — parse, search, update | 32 |
| `test_patcher.py` | Patch pipeline — parse, validate, apply, rollback | 25 |
| `test_app.py` | Flask routes — compare, contract data | 5 |
| `test_auth.py` | Auth — registration, login, logout, protection | 22 |

**Total: 84 tests**

### Test isolation

- All tests use `tmp_path` fixtures — never the live `contracts.db`
- `db.DB_PATH` is monkey-patched per-test via `yield` fixtures
- Patcher tests create real `git init` repos in `tmp_path`
- Auth tests register a fixture user before exercising routes

### Running tests

```bash
python -m pytest --tb=short -q
```

The patcher treats pytest exit code 5 (no tests collected) as a pass, so new
files don't block agent runs before their tests are written.

---

## Deployment Flow

### Railway (production)

```
git push origin main (human action)
  → Railway detects push
  → Procfile: python -c "from db import init_db; init_db()"
  → Procfile: gunicorn app:app --bind 0.0.0.0:$PORT
  → Railway polls GET /health every 30s
```

### Environment variables (Railway)

| Variable | Required | Purpose |
|---|---|---|
| `PORT` | Auto-set | gunicorn bind port |
| `SECRET_KEY` | Yes | Flask session signing |

### Known limitation

SQLite `contracts.db` is stored on Railway's ephemeral filesystem. A redeploy
wipes the database. Phase 2 migrates to the Railway PostgreSQL plugin with a
persistent volume.

---

## Directory Structure

```
/
├── app.py                   # Flask app — routes only
├── auth.py                  # Auth Blueprint (/login /register /logout)
├── users.py                 # User model, password hashing
├── db.py                    # Database — schema, queries, init
├── analytics.py             # Aggregation queries (vendor, agency profiles)
├── report_builder.py        # Dashboard summary builder
├── change_detector.py       # Contract change detection across snapshots
├── views.py                 # Saved view presets
├── Procfile                 # Railway startup command
├── requirements.txt         # Python dependencies
│
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Layout, nav, CSS
│   ├── dashboard.html
│   ├── contracts.html       # List with checkboxes + compare button
│   ├── contract_detail.html
│   ├── compare.html         # Side-by-side comparison
│   ├── vendor.html
│   ├── agency.html
│   ├── views.html
│   ├── ingest.html
│   ├── login.html
│   └── register.html
│
├── tests/                   # pytest test suite (84 tests)
│   ├── test_memory.py
│   ├── test_patcher.py
│   ├── test_app.py
│   └── test_auth.py
│
├── ai_agent/                # AI engineering system
│   ├── agent.py             # Entry point + safety checks
│   ├── manager.py           # Orchestrator
│   ├── llm.py               # Anthropic API wrapper
│   ├── reviewer.py          # Safety scanner
│   ├── memory.py            # Repository knowledge index
│   ├── patcher.py           # Patch apply + rollback pipeline
│   ├── backend_engineer.py
│   ├── frontend_engineer.py
│   ├── qa_engineer.py
│   ├── devops_engineer.py
│   └── docs_writer.py
│
├── patches/                 # Patch records (proposed and applied)
│   └── failures/            # Failure reports (gitignored)
│
├── backlog/                 # Agent task queue (priority-ordered)
│   ├── critical.md
│   ├── bugs.md
│   ├── high.md
│   ├── medium.md
│   └── ideas.md
│
├── company/                 # Business and product documents
│   ├── CEO.md               # Engineering operating manual
│   ├── VISION.md            # Product vision
│   ├── ROADMAP.md           # Phased roadmap
│   ├── COMPETITORS.md       # Market landscape
│   ├── SPRINT.md            # Active sprint
│   ├── CUSTOMERS.md         # Customer registry
│   ├── FEATURE_SCORECARD.md # Feature prioritization scoring
│   ├── PRODUCT_BACKLOG.md   # Long-term feature backlog
│   └── RELEASE_PLAN.md      # Release milestones
│
├── docs/                    # Technical documentation
│   ├── ARCHITECTURE.md      # This file
│   ├── PRODUCT.md           # Component-level architecture
│   └── STYLE.md             # Coding standards
│
├── HANDOFF.md               # Agent run log (append-only)
├── TASK.md                  # Agent sprint work queue
└── TASK_LOG.md              # One-line-per-run history table
```

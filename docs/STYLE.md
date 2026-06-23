# STYLE.md — Coding Standards

These standards apply to all code in this repository, whether written by a human
or the AI agent. Consistency matters more than any individual rule. When in doubt,
match the surrounding code.

---

## Python

**Version:** Python 3.11+. Use modern syntax: `match`, `|` union types, `f`-strings.

**Formatter:** No auto-formatter is enforced, but code must be readable at a glance.
Line length: 100 characters soft limit, 120 hard limit.

**Imports:**
```python
# Standard library first
import os
import re
from pathlib import Path

# Third-party second
from flask import Flask, request

# Local last
from db import connect, get_contracts
```

**Naming:**
- `snake_case` for variables, functions, and modules
- `PascalCase` for classes
- `UPPER_SNAKE` for module-level constants
- Private helpers: `_leading_underscore`
- Never abbreviate unless the abbreviation is universally understood (`con`, `db`, `id`)

**Functions:**
- One responsibility per function
- Short functions (under 30 lines) are the norm; split longer ones
- Return early to avoid deep nesting
- Prefer named return values (dicts, dataclasses) over positional tuples for
  anything with more than two elements

**Error handling:**
- Only catch exceptions you can recover from
- Let unexpected exceptions propagate — do not swallow with bare `except:`
- Validate at system boundaries (user input, external API responses); trust
  internal functions and framework guarantees

**Type hints:**
- Use for all function signatures in `ai_agent/`
- Optional in app-level code, but encouraged for non-obvious parameters
- Use `Optional[X]` or `X | None`, not `Union[X, None]`

**Comments:**
- Default: no comments
- Add a comment only when the WHY is non-obvious: a hidden constraint, a
  workaround for a specific bug, a subtle invariant that would surprise a reader
- Never explain WHAT the code does — well-named identifiers do that
- Never reference the task, issue, or PR that caused the change — that belongs
  in the commit message

**Docstrings:**
- One line only, if at all
- Never multi-paragraph docstrings in application code
- `ai_agent/` modules may have a brief module docstring explaining the role

---

## HTML / Jinja2 Templates

- All templates extend `base.html`
- Block names: `title`, `content`
- Indentation: 2 spaces
- Attribute order: `id`, `class`, `name`, `type`, `value`, `href`, `style`
- Inline styles are acceptable for layout tweaks; do not introduce a CSS file
  without a good reason
- Template variables use `{{ double_braces }}`, control flow uses `{% braces %}`
- Filter values before rendering: `{{ value or '—' }}` not `{{ value }}`
- Currency: `${{ "{:,.0f}".format(value or 0) }}`
- Priority badges: `class="priority-badge priority-{{ priority.lower() }}"`
- Links to internal pages: absolute paths (`/contracts`, `/vendor/...`),
  never relative paths
- URL-encode dynamic path segments: `{{ name|urlencode }}`

---

## CSS

CSS lives entirely in `base.html` `<style>` block. No external stylesheets,
no CSS frameworks, no build step.

**Rules:**
- Mobile-readable but not mobile-first (desktop users are the primary target)
- Color palette is defined as classes, not inline:
  - `.priority-critical` — `#b00020`
  - `.priority-high` — `#d97706`
  - `.priority-medium` — `#2563eb`
  - `.priority-low` — `#4b5563`
- Add new utility classes to `base.html`; never repeat the same style in
  multiple templates
- No animations or transitions except the `.card:hover` shadow lift already defined
- Font: `Arial, sans-serif` — system font, no web font loading

---

## SQL

**Style:**
```sql
SELECT c.vendor, c.agency, c.value
FROM contracts c
WHERE c.priority = ?
  AND c.days_remaining <= ?
ORDER BY c.recompete_score DESC
LIMIT ?
```

- Keywords in `UPPER CASE`
- Table aliases one letter: `c` for contracts, `s` for snapshots
- One condition per line in `WHERE` clauses
- Parameterized queries only — never f-string or %-format SQL with user input
- Joins written explicitly (`INNER JOIN`, `LEFT JOIN`), never implicit comma joins
- Column lists are explicit — never `SELECT *` in production query functions
  (the `contract_detail` route is the only exception, and it is documented)

**Schema changes:**
- `init_db()` uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`
- No destructive migrations without an explicit data migration plan
- SQLite does not support `ALTER TABLE DROP COLUMN` in older versions — add
  columns with defaults, never remove columns from existing deployments

---

## Documentation

**What belongs in docs:**
- Operating decisions that cannot be inferred from code (`company/CEO.md`)
- Product direction and customer reasoning (`company/VISION.md`, `company/ROADMAP.md`)
- Architecture that spans multiple files (`docs/PRODUCT.md`, `docs/ARCHITECTURE.md`)
- Standards that must be explicitly agreed upon (`docs/STYLE.md`, `company/COMPETITORS.md`)
- Agent run logs (`HANDOFF.md`, `TASK_LOG.md`)

**What does not belong in docs:**
- Explanations of what a function does (that is what code is for)
- Completed task logs in backlog files (mark as `[DONE]`, do not delete)
- PR descriptions (those live in git/GitHub)

**Backlog format:**
```markdown
### [OPEN] Short descriptive title
One or two sentences describing the problem and the expected change.
Role: backend
```

Status values: `OPEN`, `IN_PROGRESS`, `DONE`, `BLOCKED`.

---

## Testing

**Framework:** pytest

**File naming:** `tests/test_<module>.py`

**Structure:** group with classes (`TestFeatureName`) when a module has more
than ~10 tests for the same component; use plain functions otherwise.

**Fixtures:**
- Use `tmp_path` for temp files and directories
- Patch module-level singletons (like `db.DB_PATH`) in the fixture, restore
  in teardown via `yield` + reassignment
- Never use `monkeypatch` on external services in integration tests — spin up
  a real instance instead

**Coverage:**
- Every new route gets at least: happy path, missing resource (404-equivalent),
  and one edge case
- Every new function in `ai_agent/` gets at least one unit test
- The patcher tests use real git repos in `tmp_path` — never the live repo

**Test data:**
- Minimal: only the fields needed for the assertion under test
- Insert directly via SQL in fixtures, not through application functions,
  unless you are specifically testing the application function

**Assertions:**
- Assert specific values, not just truthiness: `assert status == 200` not
  `assert status`
- String checks: `assert "Acme Corp" in body` not `assert body`
- One logical assertion per test function — split if you have `and`

All tests must pass before any commit. See `docs/PRODUCT.md — Testing Strategy` for
test file locations and how the patcher gate works.

---

## Git Commits

**Format:**
```
<type>: <short summary under 72 chars>

<optional body — why this change, not what it is>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

**Types:**
| Type | When to use |
|---|---|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `test` | Tests only |
| `docs` | Documentation only |
| `refactor` | Code restructuring with no behavior change |
| `agent` | AI-generated patch applied by the patcher |
| `chore` | Build, config, dependency changes |

**Rules:**
- Present tense imperative: "Add compare route" not "Added compare route"
- The body explains WHY, not WHAT — the diff shows what
- Never `git push` from the agent; never `--no-verify` without explaining why
- The AI agent always appends `Co-Authored-By: Claude Sonnet 4.6`

---

## File Organization

```
/                        # Repo root
├── app.py               # Flask entry point — routes only
├── auth.py              # Authentication blueprint
├── users.py             # User model and password hashing
├── db.py                # Database layer — schema, queries
├── analytics.py         # Aggregation queries
├── report_builder.py    # Dashboard report assembly
├── change_detector.py   # Snapshot diffing
├── views.py             # Saved view presets
├── requirements.txt     # Python dependencies
├── Procfile             # Railway process definition
├── templates/           # Jinja2 HTML templates
├── tests/               # pytest test files
├── ai_agent/            # AI engineering system
│   ├── agent.py         # Entry point
│   ├── manager.py       # Orchestrator
│   ├── llm.py           # LLM API wrapper
│   ├── reviewer.py      # Safety scanner
│   ├── memory.py        # Repository index
│   ├── patcher.py       # Patch execution pipeline
│   └── *_engineer.py    # Specialist agents
├── patches/             # Proposed and applied patch records
├── backlog/             # Prioritized task lists
├── company/             # Business and product documents
│   ├── CEO.md           # Engineering operating manual
│   ├── VISION.md        # Product vision
│   ├── ROADMAP.md       # Phased product roadmap
│   ├── COMPETITORS.md   # Market landscape
│   ├── SPRINT.md        # Current sprint
│   ├── CUSTOMERS.md     # Customer registry
│   ├── FEATURE_SCORECARD.md  # Feature prioritization
│   ├── PRODUCT_BACKLOG.md    # Long-term backlog
│   └── RELEASE_PLAN.md  # Release schedule
├── docs/                # Technical documentation
│   ├── PRODUCT.md       # Architecture reference
│   ├── STYLE.md         # This file
│   └── ARCHITECTURE.md  # System architecture deep-dive
├── HANDOFF.md           # Agent run log
└── TASK_LOG.md          # One-line-per-run table
```

**Rules:**
- Business logic does not live in `app.py` — it belongs in `db.py`, `analytics.py`,
  or a dedicated module
- New templates go in `templates/` — no inline HTML in Python
- New agent specialists go in `ai_agent/` with a `ROLE` constant and `can_handle()`
  and `plan()` functions
- New tests go in `tests/` — never in the module directory
- Configuration comes from environment variables, never from files committed to git

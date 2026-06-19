# Task Log

## 2026-06-19 — Engineering Memory

**Task:** Build engineering memory — 5 auto-maintained documents in `ai_agent/`.

**Changes:**
- `ai_agent/eng_memory.py` (new): `EngineeringMemory` class wrapping 5 markdown docs (`ARCHITECTURE`, `CURRENT_STATE`, `DECISIONS`, `ROADMAP`, `KNOWN_BUGS`). `initialize_if_missing()` seeds docs with substantive starter content. `build_context()` builds a context block for LLM injection (empty string when all docs are blank). `apply_updates()` writes only changed docs. `append_task_completion()` structured fallback append to CURRENT_STATE. `update_from_llm()` calls an injectable `llm_fn` with a structured prompt, parses fenced-block responses, writes changed docs.
- `ai_agent/loop.py`: Import `EngineeringMemory`; add `eng_memory` param to `AutonomousLoop.__init__` (injectable for tests, otherwise created from `_AGENT_DIR`). `_call_plan()` now prepends `build_context()` to the task body before the LLM call. `_update_eng_memory()` called after both DRY_RUN and DONE — uses LLM to update docs, falls back to `append_task_completion()` on LLM error. Memory errors are caught and logged; they never fail the task.
- `tests/test_eng_memory.py` (new): 51 unit tests covering read/write, context building, initialization, apply_updates, append_task_completion, update_from_llm, prompt construction, and response parsing.
- `tests/test_loop.py`: Added `autouse=True` fixture `_eng_memory_mock` that prevents real filesystem writes in all existing tests. 7 new integration tests covering context injection, update after dry-run, update after apply, exception isolation, LLM-error fallback, and no-update-on-failure.
- `ai_agent/ARCHITECTURE.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md`, `KNOWN_BUGS.md`: Created with substantive starter content.

**Result:** 336 passed (was 285). Not pushed.

---

## 2026-06-19 — Automatic Recovery

**Task:** Build automatic recovery into the autonomous loop.

**Changes:**
- `ai_agent/recovery.py` (new): `FailureCategory` enum (llm_error, reviewer_blocked, validation_failed, test_failed, commit_missing, unknown), `AttemptRecord` dataclass, `RecoveryTracker` class. `record()` captures attempt #, timestamp, classified category, error text, and MD5 hash of patch content. `has_repeated_category()` / `has_identical_patch()` detect stuck patterns. `should_cut_short()` triggers early exit when identical patches are generated. `build_feedback()` produces cumulative failure history for the LLM retry prompt. `write_failure_report()` writes structured markdown to `ai_agent/logs/<task>-failure-report.md`.
- `ai_agent/loop.py`: Integrated `RecoveryTracker` into `run_one()`. Default `max_plan_attempts=3`. Config errors (missing key, package not installed) break the retry loop immediately. All other failures are recorded by the tracker and retried with cumulative feedback. `_record_failure()` now accepts optional tracker and writes the failure report. `_escalate()` lists failure report paths. `TaskOutcome` gains `failure_report` field.
- `tests/test_recovery.py` (new): 34 unit tests for `recovery.py` — classification, pattern detection, feedback generation, cut-short logic, failure report output.
- `tests/test_loop.py`: 9 new recovery integration tests — exactly 3 attempts, failure reports written, early cut-short on identical patch, report paths in TaskOutcome, never-exceed-max-attempts.

**Result:** 285 passed (was 233). Not pushed.

---

## 2026-06-19 — Autonomous Execution Loop

**Task:** Build complete autonomous execution loop (`ai_agent/loop.py`).

**Changes:**
- `ai_agent/loop.py` (new): `AutonomousLoop` class that selects the next queued task, assigns a specialist, calls the LLM with retry + feedback on failure, reviews the patch, applies via patcher (tests + commit), independently validates pytest passes and a new commit exists, then advances the queue. Escalates to `ai_agent/ESCALATE.md` after N consecutive failures. CLI: `python -m ai_agent.loop [--apply] [--all] [--daemon]`.
- `tests/test_loop.py` (new): 34 unit tests covering all state transitions, retry logic, feedback injection, reviewer blocking, post-apply validation, escalation, logging, and run_loop().

**Result:** 233 passed (was 199). Not pushed.

---

## 2026-06-19 — Task 044: AI Engineering Manager

**Task:** Build queue-based task manager at `ai_agent/manager.py`.

**Changes:**
- `ai_agent/manager.py`: Added `QueueManager` class, `TaskInfo` dataclass, `TaskState` enum, and `_queue_cli()` CLI entry point. Existing LLM orchestration code unchanged. New imports: `json`, `dataclasses.dataclass`, `enum.Enum`.
- `tests/test_queue_manager.py`: 33 unit tests covering all_tasks, queued/running/completed/failed detection, next_task, mark_running, mark_done, mark_failed, status, generate_morning_report, resume-after-interruption, corrupted-state recovery, and on-demand directory creation.
- `ai_agent/logs/.gitkeep`: Created logs directory.

**CLI:** `python -m ai_agent.manager [status|next|report|start <f>|done <f>|fail <f> [note]]`

**Result:** 199 passed (was 166). Not pushed.

---

## 2026-06-19 — Task 043: Opportunity Recommendations

**Task:** Add recommendation logic that surfaces best opportunities with explanations.

**Changes:**
- `analytics.py`: Added `opportunity_recommendations(con)` with 5 categories (top score, highest value, soonest expiration, critical priority, recently changed). Deduplicates across categories so each contract appears once. Each entry carries a `reason` string explaining why it appears.
- `app.py`: Passes `recommendations` to dashboard template.
- `templates/dashboard.html`: Replaced plain top-contracts table with categorized table including a "Why" column.
- `tests/test_analytics.py`: New file — 14 unit tests for `opportunity_recommendations` and `dashboard_analytics`.
- `tests/test_app.py`: 5 route/template tests for recommendation rendering.

**Result:** 166 passed (was 146). Not pushed.

---

## 2026-06-19 — Task 042: Customer Dashboard

**Task:** Build a useful customer-facing dashboard landing page.

**Changes:**
- `analytics.py`: Added `dashboard_analytics(con)` — platform summary (total_pipeline, total_contracts, active_contracts, critical_contracts, avg_score), upcoming expirations (next 90 days), critical active contracts, top 5 agencies and vendors by pipeline.
- `app.py`: Updated `dashboard()` route to call `dashboard_analytics(con)` and pass `analytics` to template alongside existing `report`.
- `templates/dashboard.html`: Full rewrite — 5 platform summary cards, quick-nav action buttons, Critical Opportunities section, Upcoming Expirations, Recommended Opportunities (top score), Recent Changes, side-by-side Top Agencies + Top Vendors.

**Tests added:** 13 tests in `tests/test_app.py` covering all sections and key data checks.

**Result:** 146 passed (was 133). Not pushed.

---

## 2026-06-19 — Task 041: Agency Intelligence

**Task:** Bring agency profile page to full Vendor Intelligence quality parity.

**Changes:**
- `analytics.py`: Expanded `agency_profile()` to return `active`, `timeline`, `win_loss_summary`, `change_events`, `score_distribution`, `pipeline_by_priority` alongside enriched `summary` (active_contracts, expired_contracts, max_score, platform_avg_score) and `vendors` (active_contracts, top_score).
- `templates/agency.html`: Full rewrite matching `vendor.html` — 7 summary cards, active contracts table, timeline bar chart, win/loss indicators, score analysis, priority doughnut + table, vendor leaderboard with share %, enhanced upcoming expirations with urgency coloring, overflow-x:auto wrappers.

**Tests added:** 18 tests in `tests/test_app.py` covering all new sections.

**Result:** 133 passed (was 115). Not pushed.

---

## 2026-06-19 — Fix FTS rebuild not called after save_snapshot()

**Bug:** `save_snapshot()` uses `INSERT ... ON CONFLICT DO UPDATE` which fires `AFTER INSERT` triggers (not `AFTER UPDATE`), so `contracts_au` never runs during ingest. Stale FTS entries accumulate, causing full-text search to return wrong or missing results.

**Fix:** Added `INSERT INTO contracts_fts(contracts_fts) VALUES ('rebuild')` at the end of the ingest loop in `save_snapshot()` (`db.py`), before the final commit.

**Tests added:** 5 tests in `tests/test_db.py` — vendor/agency FTS search, upsert update reflected in FTS, empty id skipped, multi-row all searchable.

**Result:** 115 passed (was 110). Committed as `12d722c`. Backlog item marked [DONE].

---

## 2026-06-19 — Build production Vendor Intelligence page

**Task:** Full vendor intelligence page with all required sections.

**Commits (12):** a8531b5 → d7c95eb

| Commit | Description |
|---|---|
| a8531b5 | Baseline vendor profile route tests |
| f3d5620 | Add `{% block scripts %}` to base.html |
| 8ba578f | Responsive CSS + table scroll wrappers |
| 048ddab | Expand summary cards (active/expired/max_score) |
| 12cb83a | Enhance agency breakdown (value, share, top score) |
| b011b27 | Enhance upcoming recompetes (competition type, urgency) |
| 0a3b569 | Add active contracts section |
| 80290fc | Add pipeline by priority breakdown |
| 865e228 | Add score distribution + platform avg |
| 6bcb9b1 | Add win/loss indicators |
| 6b3c40c | Add contract timeline bar chart |
| d7c95eb | Add priority doughnut chart |

**Result:** 110 passed (was 90). Not pushed.

---

## 2026-06-19 — Warn at startup when Railway volume is missing

**Task:** SQLite DB lost on Railway redeploy (`backlog/critical.md`)

**Fix:** Added `_warn_if_ephemeral_db()` to `app.py`. Checks `RAILWAY_ENVIRONMENT` (set on all Railway deployments) and `RAILWAY_VOLUME_NAME` (only set when a persistent volume is attached). Logs a `DATA LOSS RISK` warning if on Railway with no volume.

**Tests added:** 3 tests in `tests/test_app.py` covering warning emitted, suppressed with volume, suppressed off-Railway.

**Result:** 90 passed (was 87). Committed as `1810440`.

---

## 2026-06-19 — Fix negative days filter on /contracts

**Bug:** `GET /contracts?days=-1` silently returned expired contracts instead of rejecting the input.

**Fix:** Added a guard in `app.py` after parsing the `days` query param — returns HTTP 400 if the value is negative.

**Tests added:** `test_contracts_negative_days_returns_400`, `test_contracts_zero_days_returns_200`, `test_contracts_positive_days_returns_200` in `tests/test_app.py`.

**Result:** 87 passed (was 84). Committed as `f4b8959`.

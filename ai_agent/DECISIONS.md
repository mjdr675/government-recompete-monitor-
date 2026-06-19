# Decisions

## 2026-06-19 — SQLite over Postgres
Single-file DB sufficient for current scale; no infra overhead.

## 2026-06-19 — Queue-based task system (ai_agent/queue/)
Separate from backlog/ LLM orchestration to allow autonomous loop
without modifying the existing manager pipeline.

## 2026-06-19 — RecoveryTracker per task (not per attempt)
Accumulates failure history across all attempts so each retry prompt
includes the full context of what was tried before.

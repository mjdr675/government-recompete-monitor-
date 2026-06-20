# TASK STANDARDS
# Format and lifecycle rules for all roadmap tasks

---

## 1. Task File Format

Every task file in `ai_agent/queue/` must follow this format exactly:

```markdown
# Task <number> — <Title>

**Epic:** <E01–E24>
**Milestone:** <M1–M6>
**Complexity:** <XS|S|M|L|XL>
**Status:** QUEUED

## Objective
One paragraph. What this task accomplishes and why it matters.

## Requirements
- Bullet list of concrete, implementable requirements
- Each bullet is independently verifiable
- No vague language ("improve", "enhance", "make better")

## Acceptance Criteria
- [ ] Specific, testable outcome 1
- [ ] Specific, testable outcome 2
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- Task <number>: <title> — must be DONE before this task starts
- (or "None")

## DB Changes
- Table: <name> — columns added/created
- (or "None")

## API Changes
- Route: <METHOD> <path> — purpose
- (or "None")

## Frontend Changes
- Template: <name> — what changes
- (or "None")

## New Dependencies (requirements.txt)
- <package> — reason
- (or "None")

## Suggested Commit Message
`feat: <description> (Task <number>)`
```

---

## 2. Task Status Lifecycle

```
QUEUED (in ai_agent/queue/)
  → IN_PROGRESS (being implemented — rename file header only, not the file location)
  → DONE (move to ai_agent/done/)
  → FAILED (move to ai_agent/failed/ — with failure notes appended to file)
```

**Rules:**
- Only one task may be IN_PROGRESS at a time
- A task is DONE only when: code written + tests pass + commit made + TASK_LOG updated
- Failed tasks stay in `failed/` for analysis. Do not re-queue without reading the failure notes.

---

## 3. Scope Rules

A task may only touch files listed in its DB Changes, API Changes, and Frontend Changes sections,
plus their corresponding test files.

**Allowed side effects (without listing):**
- Updating `requirements.txt` for a listed new dependency
- Updating `HANDOFF.md` and `TASK_LOG.md` at end of task
- Fixing a breaking import caused by the task's own changes
- Adding a missing `CREATE INDEX IF NOT EXISTS` for a table the task creates

**Not allowed:**
- Changing any file not mentioned in the task
- Adding features not in the Requirements list
- Deleting or renaming existing functions
- Changing existing function signatures (unless the task explicitly requires it)
- Touching `ai_agent/plans/` files during implementation

---

## 4. Complexity Definitions

| Level | Max files changed | Max new test count | Session estimate |
|---|---|---|---|
| XS | 2 | 2 | 0.5 |
| S | 4 | 5 | 1 |
| M | 8 | 10 | 1–2 |
| L | 12 | 20 | 2–3 |
| XL | 20 | 30 | 3–5 |

If an implementation requires more files or tests than the complexity level allows,
the task is too large. Split it and create subtasks in `ai_agent/queue/`.

---

## 5. Adding New Tasks (not in the roadmap)

If a bug or gap is discovered during implementation:

**Bugs** → Add to `backlog/bugs.md` as `[OPEN]`. Do not fix in the current session.

**Missing tasks** → Add to `ai_agent/queue/` with a number higher than 278.
Use the task file format above. Add an entry to `TASK_LOG.md` noting the addition.

**Roadmap corrections** → Add a comment to the relevant `MASTER_ROADMAP_0x_*.md` file
but do not restructure the roadmap during implementation.

---

## 6. TASK_LOG.md Entry Format

Append one row after every completed session:

```
| <ISO timestamp UTC> | <role> | Task <number>: <title> | <queue file> | completed |
```

Example:
```
| 2026-06-21 14:30 UTC | backend | Task 056: min_value filter | 056-min-value-filter.md | completed |
```

If the task failed:
```
| 2026-06-21 14:30 UTC | backend | Task 062: PostgreSQL migration | 062-postgresql.md | failed — FTS trigger incompatibility |
```

---

## 7. HANDOFF.md Entry Format

Append one entry after every session (completed or not):

```markdown
## <ISO date> UTC — [<ROLE>] Task <number>: <title>
**Status:** completed | failed | partial
**Files changed:** list of files
**Tests:** <count before> → <count after>
**Notes:** What was done, any surprises, anything the next session needs to know.
```

---

## 8. Moving Tasks Between Folders

```bash
# When starting a task (update Status header in file, leave in queue/)
# When completing:
mv ai_agent/queue/<file>.md ai_agent/done/<file>.md

# When failing:
# Append failure notes to bottom of file, then:
mv ai_agent/queue/<file>.md ai_agent/failed/<file>.md
```

The `done/` and `failed/` directories are permanent records. Never delete files from them.

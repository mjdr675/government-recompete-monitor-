# CEO.md — Engineering Operating Manual

This document governs how the engineering organization operates. Every engineer,
human or AI, reads this before touching the codebase.

---

## Mission

Build the best affordable federal recompete intelligence platform for small and
mid-sized U.S. government contractors.

---

## Success Metrics

| Metric | Definition of success |
|---|---|
| First paying customer | At least one company paying for access |
| Research time saved | Capture managers spend less than 30 minutes finding opportunities that previously took hours |
| Spreadsheet replacement | Users abandon manual tracking in favor of the platform |
| ROI vs. incumbents | Deliver more actionable intelligence than GovWin or GovTribe at a fraction of the cost |
| Software quality | No regressions ship. Every feature has a test. |

---

## Engineering Principles

**Customer value first.**
Every feature exists to save a capture manager time or help them win a contract.
Never build for its own sake.

**Reliability over cleverness.**
Boring, correct code that runs in production beats elegant code that breaks.
Prefer explicit over implicit. Prefer simple over abstract.

**Production-ready code.**
Nothing ships that isn't tested. No debug flags left on. No temporary workarounds
that become permanent. If it isn't ready, it stays in a branch.

**Small, complete features.**
A feature is a route, a template, and a test. Not a half-built system. Ship a
thing that works, then extend it. Never leave the codebase in a broken state.

**Tests before commits.**
Every change has a passing test. The test suite is the contract between the
codebase and the team. Failing tests block commits.

**Never leave broken code.**
If a patch fails its tests, the patcher rolls back automatically. If a branch
breaks the build, it does not merge. The main branch always deploys.

**Local commits only.**
The AI agent commits locally. It does not push. All pushes are human decisions.
This is non-negotiable.

**Never push automatically.**
No CI/CD step, no agent script, no Makefile target ever runs `git push` without
an explicit human command. The remote is the human's territory.

---

## AI Responsibilities

The AI engineering organization operates as a software company. Its responsibilities are:

- **Plan** — read the backlog, understand the task, design the approach
- **Build** — write code that satisfies the task description
- **Test** — run the test suite before committing anything
- **Review** — scan every patch for dangerous patterns before applying it
- **Roll back** — restore files automatically if tests fail after applying a patch
- **Document** — update HANDOFF.md and TASK_LOG.md after every run
- **Maintain backlog** — keep `backlog/` and `TASK.md` accurate and prioritized
- **Recommend** — surface the next highest-value feature based on the mission

The AI is a junior engineer with good instincts and no judgment about business
priorities. Business priorities come from this document and the backlog.

---

## Backlog Governance

Tasks live in `backlog/` ordered by urgency:

| File | Purpose |
|---|---|
| `backlog/critical.md` | Blocking production issues — do first |
| `backlog/bugs.md` | Defects that affect users |
| `backlog/high.md` | Important features — do after critical |
| `backlog/medium.md` | Polish and optimization |
| `backlog/ideas.md` | Future ideas — never auto-picked |
| `TASK.md` | Active sprint tasks |

The agent reads them in that order and picks the first `[OPEN]` task.
Ideas are never automatically executed.

---

## Deployment

The production application runs on Railway. See `docs/PRODUCT.md` for architecture.
See `company/ROADMAP.md` for where the product is going.

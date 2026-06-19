#!/usr/bin/env bash

cat <<'PROMPT'
Read ai_agent/RULES.md, ai_agent/TASK.md, ai_agent/HANDOFF.md, and ai_agent/TASK_LOG.md.

Complete exactly ONE task.

Rules:
- Keep changes small.
- Run the full test suite.
- Commit locally only if tests pass.
- Update HANDOFF.md.
- Update TASK_LOG.md.
- Do not push.
- Stop after the task is complete.
PROMPT

# Queue Rules

Work through ai_agent/queue in filename order.

One task at a time.

For each task:
1. Read the task.
2. Inspect relevant code.
3. Implement only that task.
4. Run pytest -q.
5. Fix failures.
6. Update ai_agent/HANDOFF.md.
7. Update ai_agent/TASK_LOG.md.
8. Commit locally.
9. Move completed task to ai_agent/done/.
10. Continue.

Stop if:
- tests cannot be fixed safely
- task is unclear
- repo state is unsafe

Never push.
Never deploy.
Never remove tests to pass.

# Task 052 — Autonomous Daemon

Implement continuous execution mode.

Requirements:
- Optional daemon mode.
- Sleep between tasks.
- Wake when work exists.
- Safe shutdown.
- Resume after reboot.
- Tests.
- Commit locally.
- Do not push.

Additional requirements:
- Detect Claude/session usage-limit failures from command output.
- When usage limit is hit:
  - stop current execution safely
  - preserve task state
  - write a clear log entry
  - sleep until the next configured window
  - resume from the queue afterward
- Support config:
  - max_tasks_per_window
  - sleep_minutes_after_usage_limit
  - max_runtime_minutes
- Default to conservative behavior to avoid runaway usage.

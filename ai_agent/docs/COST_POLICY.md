# Cost Policy

Goals

- Maximize engineering output per usage window.
- Never waste usage on infinite retries.
- Stop after repeated failures.
- Resume automatically when usage becomes available.

Rules

- Maximum retries: 3
- Escalate repeated failures.
- Never continue after an unsafe state.
- Prefer batching work over frequent startup/shutdown.

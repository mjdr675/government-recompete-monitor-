# Critical Backlog

Tasks here block production use or represent security issues.
Agent picks these first.

## Format
### [STATUS] Title
Description. Role hint: backend | frontend | qa | devops | docs

---

### [DONE] Auth bypass on /health exposes info to unauthenticated users
`/health` correctly skips auth, but the response should not reveal internal
state if the app is ever extended. Keep it minimal: `{"status":"ok"}` only.
Role: backend

### [OPEN] SQLite DB lost on Railway redeploy
`contracts.db` is ephemeral on Railway. Document the data-loss risk clearly
and add a startup warning log line when running under gunicorn with no
persistent volume detected.
Role: devops

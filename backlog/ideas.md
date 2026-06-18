# Ideas Backlog

Unvalidated ideas — discuss before promoting to medium/high.

---

### [IDEA] Email digest of daily changes
Send a daily email summary of new/changed contracts using SendGrid or
SMTP. Would need an `EMAIL_TO` env var and a cron trigger.

### [IDEA] Slack webhook for critical new contracts
POST to a Slack webhook when a new CRITICAL-priority contract is ingested.
Configurable via `SLACK_WEBHOOK_URL` env var.

### [IDEA] Export filtered contracts as CSV
Add a `/contracts.csv` route that respects the same filters as `/contracts`
and streams a CSV download.

### [IDEA] Agency comparison view
Side-by-side comparison of two agencies: total contract value, avg score,
upcoming recompetes. New route `/compare?a=AgencyA&b=AgencyB`.

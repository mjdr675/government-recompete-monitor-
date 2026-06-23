# Task 111 — Write docs/OPERATIONS.md credential rotation runbook

**Epic:** E05
**Milestone:** M3
**Sprint:** G-6
**Complexity:** S
**Status:** QUEUED

## Objective

Document the credential rotation procedure so any team member can rotate secrets without
institutional knowledge. This satisfies Sprint G-6 and the M3 exit criterion for operational
documentation.

## Requirements

Create `docs/OPERATIONS.md` with the following sections:

### 1. Credential Inventory
Table of all production secrets: `STRIPE_SECRET_KEY`, `HUBSPOT_ACCESS_TOKEN`,
`SECRET_KEY`, `EMAIL_API_KEY`, `SENTRY_DSN`, `DATABASE_URL`, `REDIS_URL`.
For each: where it is set, how to rotate it, and who owns it.

### 2. Stripe Key Rotation
Step-by-step: log in to Stripe dashboard → Developers → API Keys → Roll secret key →
update Railway env var `STRIPE_SECRET_KEY` → trigger redeploy → verify `/health`.

### 3. HubSpot Token Rotation
Step-by-step: log in to HubSpot → Settings → Integrations → Private Apps → rotate
access token → update Railway env var `HUBSPOT_ACCESS_TOKEN` → redeploy → verify demo
form submission reaches CRM.

### 4. Flask SECRET_KEY Rotation
Generate with `python -c "import secrets; print(secrets.token_hex(32))"` → update
Railway `SECRET_KEY` → redeploy. Note: all active user sessions are invalidated on
rotation; users must log in again.

### 5. Database Backup and Restore
How to verify Railway PostgreSQL automated backups are enabled. How to trigger a
point-in-time restore via Railway dashboard. Expected recovery time: < 15 minutes.

### 6. Emergency Contacts
Leave a placeholder section: `[FILL IN: on-call contact, Railway support link, Stripe support link]`.

### 7. Post-Rotation Checklist
Ordered list: rotate → update env var → redeploy → run smoke test → check Sentry for errors.

## Acceptance Criteria

- [ ] `docs/OPERATIONS.md` exists and is non-empty
- [ ] All 5 credentials listed in the inventory with rotation steps
- [ ] Backup and restore section present
- [ ] Post-rotation checklist present
- [ ] No real credentials or tokens appear in the file

## Hard Dependencies

- Task 094: ARCHITECTURE.md updated (establishes docs/ pattern) — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 1 test to a new `tests/test_ops_docs.py`:
- `test_operations_md_exists_and_has_sections`: read `docs/OPERATIONS.md`; assert file
  exists; assert the strings "STRIPE_SECRET_KEY", "HubSpot", "SECRET_KEY", "Backup",
  "Checklist" all appear in the content.

## Suggested Commit Message

`docs: write credential rotation runbook in docs/OPERATIONS.md (Task 111)`

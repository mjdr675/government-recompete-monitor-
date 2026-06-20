# Task 114 — Add GET/POST /settings/alerts page

**Epic:** E03
**Milestone:** M3
**Sprint:** E-2
**Complexity:** S
**Status:** QUEUED

## Objective

Give users a page to configure their expiration alert preferences: which day thresholds
trigger alerts, minimum contract value, and whether alerts are enabled at all.

## Requirements

- In `auth.py` (or a new `settings.py` blueprint), add:
  ```python
  @bp.route("/settings/alerts", methods=["GET", "POST"])
  @login_required
  def alert_settings():
  ```
  - GET: query `alert_preferences` for `user_id = session['user_id']`; if no row exists,
    use defaults (`alert_days=[30,60,90]`, `min_value=0`, `enabled=True`); render
    `templates/settings_alerts.html` with current prefs.
  - POST: read form fields `alert_days` (checkboxes: 30, 60, 90), `min_value` (integer),
    `enabled` (checkbox); upsert into `alert_preferences` using
    `INSERT OR REPLACE` (SQLite) / `INSERT … ON CONFLICT DO UPDATE` (PostgreSQL);
    flash "Preferences saved." and redirect to GET.
- Register the blueprint in `app.py` if not already registered.
- Add `templates/settings_alerts.html` extending `base.html` with:
  - Three checkboxes for day thresholds (30, 60, 90 days)
  - Number input for minimum contract value (dollars)
  - Toggle checkbox for "Send me alerts"
  - Submit button

## Acceptance Criteria

- [ ] GET `/settings/alerts` requires auth; returns 302 for anonymous users
- [ ] GET renders current preferences (defaults on first visit)
- [ ] POST updates the `alert_preferences` row and redirects back to the page
- [ ] POST with all thresholds unchecked stores `alert_days=[]`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 112: alert_preferences table — must be DONE

## DB Changes

Reads and upserts `alert_preferences`.

## API Changes

New routes: `GET /settings/alerts`, `POST /settings/alerts`.

## Frontend Changes

New template: `templates/settings_alerts.html`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_settings.py` (new file if absent):
- `test_alert_settings_requires_auth`: anonymous GET → 302 to login.
- `test_alert_settings_get_defaults`: authenticated GET → 200, response contains "30".
- `test_alert_settings_post_saves_preferences`: POST with `alert_days=[60]`, `min_value=50000`,
  `enabled=on` → DB row updated; verify via direct DB query.
- `test_alert_settings_post_redirects`: POST → 302 back to `/settings/alerts`.

## Suggested Commit Message

`feat: add GET/POST /settings/alerts page for alert preferences (Task 114)`

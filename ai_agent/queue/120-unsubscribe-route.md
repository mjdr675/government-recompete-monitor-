# Task 120 — Add GET /unsubscribe route

**Epic:** E03
**Milestone:** M3
**Sprint:** E-8
**Complexity:** S
**Status:** QUEUED

## Objective

Let users opt out of expiration alerts with a single click from any alert email.
The unsubscribe link uses the token stored in `alert_preferences.unsubscribe_token`
(set by Task 118) so no login is required.

## Requirements

- In `auth.py` (or a new `settings.py` blueprint), add:
  ```python
  @bp.route("/unsubscribe", methods=["GET"])
  def unsubscribe():
  ```
  - Read `token` from `request.args.get("token")`.
  - If `token` is missing or blank: return 400 with a brief HTML page ("Invalid link").
  - Query `alert_preferences WHERE unsubscribe_token = :token`.
  - If no row found: return 400 ("Invalid or expired unsubscribe link").
  - If found: `UPDATE alert_preferences SET enabled = 0 WHERE unsubscribe_token = :token`.
  - Render `templates/unsubscribe_confirm.html` with message: "You have been unsubscribed
    from contract expiration alerts. You can re-enable alerts at any time in your
    account settings."
- Add `/unsubscribe` to `_PUBLIC_PATHS` in `app.py` (no auth required).
- Create `templates/unsubscribe_confirm.html` extending `base.html` with the confirmation
  message and a link to `/settings/alerts`.

## Acceptance Criteria

- [ ] GET `/unsubscribe?token=<valid>` sets `enabled=0` and returns 200
- [ ] GET `/unsubscribe?token=<invalid>` returns 400
- [ ] GET `/unsubscribe` (no token) returns 400
- [ ] Route is accessible without auth
- [ ] Calling the route twice with the same token is idempotent (sets enabled=0, returns 200)
- [ ] All existing tests still pass

## Hard Dependencies

- Task 112: alert_preferences table (has `unsubscribe_token` column) — must be DONE
- Task 118: enqueue alert emails (populates `unsubscribe_token`) — must be DONE

## DB Changes

Updates `alert_preferences.enabled`.

## API Changes

New route: `GET /unsubscribe`.

## Frontend Changes

New template: `templates/unsubscribe_confirm.html`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_settings.py`:
- `test_unsubscribe_valid_token_disables_alerts`: insert alert_prefs row with known token;
  GET `/unsubscribe?token=<tok>`; assert `enabled=0` in DB; assert 200.
- `test_unsubscribe_invalid_token_returns_400`: GET `/unsubscribe?token=bogus`; assert 400.
- `test_unsubscribe_no_token_returns_400`: GET `/unsubscribe`; assert 400.
- `test_unsubscribe_idempotent`: call route twice with same token; assert `enabled=0`
  after both calls, no exception on second call.

## Suggested Commit Message

`feat: add GET /unsubscribe route with token-based alert opt-out (Task 120)`

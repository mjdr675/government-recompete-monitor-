# Task 071 — Add Flask-WTF CSRF protection to app and auth forms

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

The application has no CSRF protection. All POST forms are vulnerable to cross-site
request forgery. Add Flask-WTF, configure `CSRFProtect` globally, exempt the Stripe
webhook, and immediately add CSRF tokens to `login.html` and `register.html` in the
same commit. Auth forms must continue to work after this commit — repo must be in a
working state at all times.

## Requirements

- Add `Flask-WTF` to `requirements.txt` (pinned version)
- In `app.py`:
  - Import `from flask_wtf.csrf import CSRFProtect`
  - Initialize: `csrf = CSRFProtect(app)` (immediately after `app.secret_key` is set)
  - Decorate `stripe_webhook()` with `@csrf.exempt` (must accept unsigned POST from Stripe)
- `CSRFProtect` uses `SECRET_KEY` for token signing — no additional config needed
- In `templates/login.html`: add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` immediately after the opening `<form>` tag
- In `templates/register.html`: same hidden field immediately after the opening `<form>` tag
- Do NOT add `WTF_CSRF_CHECK_DEFAULT = False` or any global disable

## Acceptance Criteria

- [ ] `Flask-WTF` appears in `requirements.txt` at a pinned version
- [ ] `CSRFProtect(app)` initialised in `app.py` after `app.secret_key` assignment
- [ ] `stripe_webhook()` is decorated with `@csrf.exempt`
- [ ] `login.html` and `register.html` each contain the CSRF hidden field
- [ ] A user can log in via the browser after this commit (form submits successfully)
- [ ] A user can register via the browser after this commit (form submits successfully)
- [ ] `/health` GET continues to return 200 unauthenticated
- [ ] All existing tests still pass (CSRF disabled in test fixture — see Testing)
- [ ] New test: POST to `/login` with `WTF_CSRF_ENABLED = True` and no token — assert 400

## Hard Dependencies

- Task 066: `users.py` fix — must be DONE

## DB Changes

None.

## API Changes

- All POST routes now require a valid `csrf_token` hidden field. External POST without token returns 400.
- Exception: `POST /stripe/webhook` — remains exempt.

## Frontend Changes

- `templates/login.html` — add one CSRF hidden input inside `<form>`
- `templates/register.html` — add one CSRF hidden input inside `<form>`

## New Dependencies (requirements.txt)

- `Flask-WTF==1.2.2` (or latest stable — pin the installed version)

## Testing

Set `WTF_CSRF_ENABLED = False` in the test app fixture (in `tests/conftest.py` or wherever
the Flask app is created for tests). This disables CSRF checks in the test suite so all
existing tests continue to pass without modification.

Add one new test: `test_csrf_rejected` — temporarily enable CSRF (`WTF_CSRF_ENABLED = True`),
POST to `/login` with no `csrf_token` field, assert 400 returned.

## Documentation

Update `docs/ARCHITECTURE.md` — Authentication section: note CSRF protection via Flask-WTF,
Stripe webhook exemption.

## Suggested Commit Message

`feat: add Flask-WTF CSRF protection and update auth form templates (Task 071)`

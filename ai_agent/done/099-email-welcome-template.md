# Task 099 — Write welcome email template

**Epic:** E08
**Milestone:** M3
**Sprint:** D-7
**Complexity:** S
**Status:** QUEUED

## Objective

Create the welcome email sent to new users on registration.

## Requirements

- New file `templates/email/welcome.html`:
  - Extends `templates/email/base.html` via Jinja (`{% extends "email/base.html" %}`)
  - `{% block preheader %}Welcome to Gov Recompete Monitor — start finding contract opportunities.{% endblock %}`
  - `{% block content %}` contains:
    - `<h2>Welcome, {{ user_email }}!</h2>`
    - 2–3 sentences explaining the product: track expiring federal contracts, bookmark opportunities, receive alerts
    - CTA button (inline-styled `<a>` tag, `#1f4f8f` background, white text): "Browse Contracts" → `{{ app_url }}/contracts`
    - Secondary link: "View Dashboard" → `{{ app_url }}`
  - Variable: `{{ app_url }}` (e.g. `https://govrecompete.com`), `{{ user_email }}`
- New file `templates/email/welcome.txt`:
  - Extends `templates/email/base.txt`
  - Plain-text equivalent of the above (no HTML)

## Acceptance Criteria

- [ ] `templates/email/welcome.html` exists and extends `email/base.html`
- [ ] `templates/email/welcome.txt` exists
- [ ] Template renders without error when given `user_email` and `app_url` variables
- [ ] All existing tests still pass

## Hard Dependencies

- Task 098: email base template — must be DONE

## Testing

Add 1 test to a new file `tests/test_email_templates.py`: use Flask's `render_template` to render `email/welcome.html` with test vars; assert `user_email` appears in output and `app_url` link appears. Use the existing app fixture for template rendering context.

## Suggested Commit Message

`feat: add welcome email template (Task 099)`

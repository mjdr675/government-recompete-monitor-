# Task 104 — Add password reset email templates

**Epic:** E05
**Milestone:** M3
**Sprint:** D-11
**Complexity:** S
**Status:** QUEUED

## Objective

Write the branded HTML and plain-text email templates for the password reset link.
These extend the existing `email/base.html` and `email/base.txt` skeletons.

## Requirements

- `templates/email/reset_password.html` extending `email/base.html`:
  - `{% block title %}Reset your password{% endblock %}`
  - `{% block preheader %}Click the link below to reset your Gov Recompete Monitor password.{% endblock %}`
  - `{% block content %}`: greeting using `{{ user_email }}`, one-sentence explanation,
    CTA button linking to `{{ reset_url }}` with label "Reset Password", note that the
    link expires in 1 hour, and "If you did not request a password reset, ignore this email."
  - No `<style>` blocks — inline CSS only (Gmail compatibility rule).
- `templates/email/reset_password.txt` extending `email/base.txt`:
  - `{% block text_content %}`: same message in plain text; print `{{ reset_url }}` on its
    own line so it is clickable in plain-text clients.
- Template variables: `user_email` (str), `reset_url` (str).

## Acceptance Criteria

- [ ] `reset_password.html` renders with `user_email` and `reset_url` injected
- [ ] `reset_password.txt` renders with `reset_url` on its own line
- [ ] No `<style>` block appears in rendered HTML
- [ ] CTA button `href` matches `{{ reset_url }}`
- [ ] "1 hour" expiry language present in both templates

## Hard Dependencies

- Task 098: email base templates — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

New files: `templates/email/reset_password.html`, `templates/email/reset_password.txt`.

## New Dependencies

None.

## Testing

Add 3 tests to `tests/test_email_templates.py`:
- `test_reset_html_renders`: renders template with `user_email` and `reset_url`; asserts
  both values appear in output; asserts "Reset Password" in output.
- `test_reset_txt_renders`: renders txt template; asserts `reset_url` on its own line.
- `test_reset_html_has_no_style_blocks`: asserts `<style` not in rendered HTML.

## Suggested Commit Message

`feat: add password reset email templates HTML and TXT (Task 104)`

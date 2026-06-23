# Task 134 — Write trial expiry email template

**Epic:** E10
**Milestone:** M3
**Sprint:** F-12
**Complexity:** S
**Status:** QUEUED

## Objective

Create the trial expiry email sent on day 14 when the trial ends. This is the last
automated nudge before the user hits the trial gate on next login.

## Requirements

- Create `templates/email/trial_expired.html` extending `templates/email/base.html`:
  - Subject line: "Your Gov Recompete Monitor trial has ended"
  - Heading: "Your free trial has ended"
  - Body:
    - Paragraph: "Your 14-day trial expired on {{ trial_ends_at }}. Your watchlist,
      saved searches, and alert preferences are saved — subscribe to continue where
      you left off."
    - Primary CTA button: "Subscribe and restore access" → `{{ subscribe_url }}`
    - Secondary text: "Not ready? Your data stays with us for 30 days."
  - Footer: standard links
- Create `templates/email/trial_expired.txt` (plain-text equivalent).
- Context variables: `user_first_name`, `trial_ends_at`, `subscribe_url`.

## Acceptance Criteria

- [ ] `templates/email/trial_expired.html` exists and extends `email/base.html`
- [ ] `templates/email/trial_expired.txt` exists
- [ ] Both templates render without error with sample context
- [ ] CTA links to `{{ subscribe_url }}`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 098: branded email base template — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

New templates: `templates/email/trial_expired.html`, `templates/email/trial_expired.txt`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_email_templates.py`:
- `test_trial_expired_html_renders`: render with sample context; assert "trial has ended"
  and subscribe URL in output.
- `test_trial_expired_txt_renders`: plain-text template renders without error.

## Suggested Commit Message

`feat: add trial expiry email template (Task 134)`

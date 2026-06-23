# Task 133 — Write trial day-10 email template

**Epic:** E10
**Milestone:** M3
**Sprint:** F-11
**Complexity:** S
**Status:** QUEUED

## Objective

Create the day-10 trial reminder with urgency messaging — 4 days remain, subscribe now
to keep access.

## Requirements

- Create `templates/email/trial_day10.html` extending `templates/email/base.html`:
  - Subject line: "4 days left in your trial — don't lose access"
  - Heading: "Your trial ends in 4 days"
  - Body:
    - Paragraph: "Your 14-day free trial expires on {{ trial_ends_at }}. Subscribe now
      to keep your watchlist, saved searches, and expiration alerts."
    - Contract count teaser (optional, if context provided): "You've tracked {{ contract_count }}
      contracts this week." (skip gracefully if `contract_count` is None)
    - Primary CTA button: "Subscribe now" → `{{ subscribe_url }}`
    - Secondary text: "Questions? Reply to this email."
  - Footer: standard links
- Create `templates/email/trial_day10.txt` (plain-text equivalent).
- Context variables: `user_first_name`, `trial_ends_at`, `subscribe_url`, `contract_count` (optional).

## Acceptance Criteria

- [ ] `templates/email/trial_day10.html` exists and extends `email/base.html`
- [ ] `templates/email/trial_day10.txt` exists
- [ ] Both templates render with and without `contract_count` (graceful None handling)
- [ ] Subscribe CTA links to `{{ subscribe_url }}`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 098: branded email base template — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

New templates: `templates/email/trial_day10.html`, `templates/email/trial_day10.txt`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_email_templates.py`:
- `test_trial_day10_html_renders_with_contract_count`: render with `contract_count=5`;
  assert "4 days" and subscribe URL in output.
- `test_trial_day10_html_renders_without_contract_count`: render with `contract_count=None`;
  assert no exception, "4 days" in output.
- `test_trial_day10_txt_renders`: plain-text template renders correctly.

## Suggested Commit Message

`feat: add trial day-10 reminder email template (Task 133)`

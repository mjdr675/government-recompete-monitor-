# Task 132 — Write trial day-3 email template

**Epic:** E10
**Milestone:** M3
**Sprint:** F-10
**Complexity:** S
**Status:** QUEUED

## Objective

Create the day-3 trial reminder email that shows users what they can do with 11 days left,
keeping them engaged and pointing them toward features they may not have explored.

## Requirements

- Create `templates/email/trial_day3.html` extending `templates/email/base.html`:
  - Subject line (passed as context): "You have 11 days left in your Gov Recompete Monitor trial"
  - Heading: "Make the most of your trial"
  - Body:
    - Paragraph: "You're 3 days in — here's what to try before your trial ends:"
    - Bulleted list: "Bookmark contracts with the watchlist", "Save a custom search",
      "Set up expiration alerts so you never miss a recompete"
    - CTA button: "Explore the platform" → `{{ dashboard_url }}`
    - Secondary link: "Ready to subscribe? View plans →" → `{{ subscribe_url }}`
  - Footer: standard unsubscribe / manage subscription links
- Create `templates/email/trial_day3.txt` (plain-text equivalent).
- Context variables: `user_first_name`, `trial_ends_at`, `dashboard_url`, `subscribe_url`.

## Acceptance Criteria

- [ ] `templates/email/trial_day3.html` exists and extends `email/base.html`
- [ ] `templates/email/trial_day3.txt` exists
- [ ] Both templates render without error with sample context
- [ ] CTA links to `{{ dashboard_url }}`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 098: branded email base template — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

New templates: `templates/email/trial_day3.html`, `templates/email/trial_day3.txt`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_email_templates.py`:
- `test_trial_day3_html_renders`: render with sample context; assert "11 days" and
  dashboard URL in output.
- `test_trial_day3_txt_renders`: same for plain-text template.

## Suggested Commit Message

`feat: add trial day-3 reminder email template (Task 132)`

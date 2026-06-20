# Task 115 — Write expiration alert email template

**Epic:** E03
**Milestone:** M3
**Sprint:** E-4
**Complexity:** S
**Status:** QUEUED

## Objective

Create the HTML and plain-text email templates that notify a user when a watched contract
is approaching its expiration threshold. These templates are consumed by the alert dispatch
task (Task 118).

## Requirements

- Create `templates/email/expiration_alert.html` extending `templates/email/base.html`:
  - Subject context variable: `{{ subject }}`
  - Heading: "Contract expiring in {{ days_remaining }} days"
  - Body:
    - Contract name: `{{ contract_title }}`
    - Agency: `{{ agency }}`
    - Current expiration date: `{{ expiry_date }}`
    - Estimated value: `{{ value | format_currency }}`
    - Call to action: "View on Gov Recompete Monitor" button linking to `{{ contract_url }}`
  - Footer: unsubscribe link `{{ unsubscribe_url }}`
- Create `templates/email/expiration_alert.txt` (plain-text equivalent):
  ```
  Contract expiring in {{ days_remaining }} days: {{ contract_title }}
  Agency: {{ agency }}
  Expiration: {{ expiry_date }}
  Value: {{ value }}
  View contract: {{ contract_url }}
  Unsubscribe: {{ unsubscribe_url }}
  ```
- Both templates receive these context variables:
  `days_remaining`, `contract_title`, `agency`, `expiry_date`, `value`, `contract_url`, `unsubscribe_url`.

## Acceptance Criteria

- [ ] `templates/email/expiration_alert.html` exists and extends `email/base.html`
- [ ] `templates/email/expiration_alert.txt` exists
- [ ] Both templates render without error when all context variables are provided
- [ ] Unsubscribe link is present in both templates
- [ ] All existing tests still pass

## Hard Dependencies

- Task 098: branded email base template — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

New templates: `templates/email/expiration_alert.html`, `templates/email/expiration_alert.txt`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_email_templates.py` (new file if absent):
- `test_expiration_alert_html_renders`: use Flask's `render_template` in app context with
  sample context; assert "expiring in" in output and unsubscribe URL present.
- `test_expiration_alert_txt_renders`: same for plain-text template.

## Suggested Commit Message

`feat: add expiration alert email templates (Task 115)`

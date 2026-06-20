# Task 116 — Write status change alert email template

**Epic:** E03
**Milestone:** M3
**Sprint:** E-9
**Complexity:** S
**Status:** QUEUED

## Objective

Create the HTML and plain-text email templates that notify a user when a watched contract
changes its recompete or priority status. These templates are consumed by the status change
trigger in Task 121.

## Requirements

- Create `templates/email/status_change.html` extending `templates/email/base.html`:
  - Heading: "A contract you're watching has been updated"
  - Body:
    - Contract name: `{{ contract_title }}`
    - Agency: `{{ agency }}`
    - Change description: "Status changed from **{{ old_status }}** to **{{ new_status }}**"
    - Expiration date: `{{ expiry_date }}`
    - Call to action: "View updated contract" button linking to `{{ contract_url }}`
  - Footer: unsubscribe link `{{ unsubscribe_url }}`
- Create `templates/email/status_change.txt` (plain-text equivalent):
  ```
  Contract updated: {{ contract_title }}
  Agency: {{ agency }}
  Status changed: {{ old_status }} → {{ new_status }}
  Expiration: {{ expiry_date }}
  View contract: {{ contract_url }}
  Unsubscribe: {{ unsubscribe_url }}
  ```
- Both templates receive: `contract_title`, `agency`, `old_status`, `new_status`,
  `expiry_date`, `contract_url`, `unsubscribe_url`.

## Acceptance Criteria

- [ ] `templates/email/status_change.html` exists and extends `email/base.html`
- [ ] `templates/email/status_change.txt` exists
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

New templates: `templates/email/status_change.html`, `templates/email/status_change.txt`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_email_templates.py`:
- `test_status_change_html_renders`: render with sample context; assert "Status changed"
  and unsubscribe URL in output.
- `test_status_change_txt_renders`: same for plain-text template.

## Suggested Commit Message

`feat: add status change alert email templates (Task 116)`

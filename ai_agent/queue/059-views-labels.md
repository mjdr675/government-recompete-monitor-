# Task 059 — Fix human-readable labels in views.html

**Epic:** E01
**Milestone:** M1
**Complexity:** XS
**Status:** QUEUED

## Objective
The saved views page (`templates/views.html`) currently renders raw filter dictionary keys
such as `days: 90` and `priority: CRITICAL`. Replace these with human-readable labels so
users can understand what each saved view is filtering on. Carry-forward backlog item.

## Requirements
- In `templates/views.html`, replace raw filter key/value rendering with a label map
- Map at minimum: `days` → `Expiring within`, `priority` → `Priority`, `min_value` → `Min value`,
  `naics_code` → `NAICS`, `agency` → `Agency`, `keywords` → `Keywords`
- Format values: `days: 90` → `Expiring within: 90 days`; `priority: CRITICAL` → `Priority: Critical`
  (title-case the value); `min_value: 1000000` → `Min value: $1,000,000`
- If a filter key has no label in the map, display the key as-is (do not raise an error)

## Acceptance Criteria
- [ ] All current saved views display human-readable filter summaries (no raw dict keys)
- [ ] `days` values rendered as "Expiring within: N days"
- [ ] `priority` values title-cased
- [ ] `min_value` values formatted as currency
- [ ] Unknown filter keys fall through gracefully
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None

## API Changes
- None

## Frontend Changes
- Template: `templates/views.html` — replace raw filter key display with label map rendering

## New Dependencies (requirements.txt)
- None

## Suggested Commit Message
`fix: display human-readable filter labels in saved views (Task 059)`

# Task 072 — Add CSRF tokens to ingest, demo, and early-access forms

**Epic:** E05  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

Complete CSRF coverage for all remaining POST forms. After Task 071 covered auth
forms, this task adds the CSRF hidden field to the three remaining templates that
have POST forms: `ingest.html`, `demo.html`, and `early_access.html`.

## Requirements

- In `templates/ingest.html`: add CSRF hidden field to the CSV upload form AND the
  "Pull from API" form (there are two POST forms on this page — both need the token)
- In `templates/demo.html`: add CSRF hidden field inside the demo request `<form>`
- In `templates/early_access.html`: add CSRF hidden field inside the early access `<form>`
- Use the same pattern as Task 071: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- Do not modify any other form fields or layout

## Acceptance Criteria

- [ ] Both forms on `ingest.html` contain the CSRF hidden field
- [ ] `demo.html` form contains the CSRF hidden field
- [ ] `early_access.html` form contains the CSRF hidden field
- [ ] CSV ingest via UI still works (form submits successfully)
- [ ] Demo request form submission still works
- [ ] Early access form submission still works
- [ ] All existing tests pass (CSRF disabled in test fixture)

## Hard Dependencies

- Task 071: CSRF infrastructure and auth forms — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

- `templates/ingest.html` — add hidden input to both POST forms
- `templates/demo.html` — add hidden input inside `<form>`
- `templates/early_access.html` — add hidden input inside `<form>`

## New Dependencies (requirements.txt)

None.

## Testing

No new tests required. Verify with existing test suite (CSRF disabled in test fixture).

## Documentation

None required.

## Suggested Commit Message

`feat: add CSRF tokens to ingest, demo, and early-access forms (Task 072)`

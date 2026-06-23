# Task 060 — Add first/last page buttons and page count to contracts list

**Epic:** E01
**Milestone:** M1
**Complexity:** XS
**Status:** QUEUED

## Objective
The contract list pagination controls are missing "First" and "Last" page links and do not
show the total page count. Users on page 3 of 20 have no fast way to jump to the beginning
or end and no indication of how many pages exist. Carry-forward backlog item.

## Requirements
- Add "First" and "Last" page links to the pagination block in `templates/contracts.html`
- Display "Page X of Y" text, computed from total record count and page size
- Disable (visually and functionally) the "First" and "Prev" links when on page 1
- Disable (visually and functionally) the "Next" and "Last" links when on the final page
- The total page count (`Y`) must be derived from the total contract count already passed
  to the template (do not add a new DB query)

## Acceptance Criteria
- [ ] "First" and "Last" links present in pagination block
- [ ] "Page X of Y" text visible between navigation controls
- [ ] "First" and "Prev" links are disabled/non-clickable on page 1
- [ ] "Next" and "Last" links are disabled/non-clickable on the last page
- [ ] Pagination renders correctly on single-page result sets (no "Last" confusion)
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None

## API Changes
- None

## Frontend Changes
- Template: `templates/contracts.html` — pagination block: add First/Last links and Page X of Y label

## New Dependencies (requirements.txt)
- None

## Suggested Commit Message
`fix: add first/last page buttons and page count to contracts list (Task 060)`

# Task 098 — Write templates/email/base.html branded email layout

**Epic:** E08
**Milestone:** M3
**Sprint:** D-6
**Complexity:** S
**Status:** QUEUED

## Objective

Create a reusable HTML email base template with inline styles that renders correctly in major email clients.

## Requirements

- New directory `templates/email/` (create if absent)
- New file `templates/email/base.html`:
  - Standalone HTML (not a Jinja `extends` — email templates are rendered with `render_template` directly, not extending base.html)
  - Jinja `{% block content %}{% endblock %}` and `{% block preheader %}{% endblock %}` for child templates
  - Inline CSS only (no `<style>` blocks — Gmail strips them)
  - Structure: centered 600px container, white background, top header bar with product name "Gov Recompete Monitor", content area, footer with "You received this because you registered at govrecompete.com" and an `{{ unsubscribe_url | default('#') }}` link
  - Font: Arial/sans-serif, 14px body, 22px heading
  - Color: header `#1f4f8f` (matches app nav), body text `#222`
  - Variables available to all child templates: `{{ user_email }}`, `{{ unsubscribe_url }}`
- New file `templates/email/base.txt` — plain-text fallback skeleton with `{% block text_content %}{% endblock %}`

## Acceptance Criteria

- [ ] `templates/email/base.html` exists and contains `{% block content %}`
- [ ] `templates/email/base.txt` exists and contains `{% block text_content %}`
- [ ] No `<style>` blocks (all CSS is inline)
- [ ] Footer contains unsubscribe link placeholder
- [ ] All existing tests still pass (no app code changed)

## Hard Dependencies

None (template files only).

## Testing

No automated tests required — template files only. Existing suite must pass.

## Suggested Commit Message

`feat: add branded email base templates (Task 098)`

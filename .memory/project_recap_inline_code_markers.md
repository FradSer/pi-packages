---
name: recap-inline-code-markers
description: Recap cleanup must preserve paired inline-code backticks at the start of summaries
type: project
---

## Why

`@fradser/pi-recap` renders summaries through `pi-tui` Markdown. The previous cleanup removed every leading and trailing backtick independently, so a recap beginning with `` `list_directory_sessions` `` lost only its opening marker and displayed as `list_directory_sessions``, with the code span malformed.

## How to apply

- In `packages/recap/extensions/recap.ts`, remove quote characters only when a recognized opening/closing pair wraps the complete summary.
- Preserve balanced inline backticks when code appears at the start of a longer recap.
- Keep regression coverage in `packages/recap/features/recap.feature` and `packages/recap/tests/test_recap_package.py`.

## Related

[[project_recap_persistence_design]]

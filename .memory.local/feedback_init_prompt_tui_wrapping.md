---
name: init-prompt-tui-wrapping
description: /init preserves semantic line breaks while leaving width wrapping to the Pi TUI
type: feedback
---

## Why

The `/init` prompt is delivered as one user message. Source-code wrapping and indentation create unnecessary visual breaks, but removing every newline makes the instructions harder to scan. Preserve paragraph and bullet boundaries while letting Pi's TUI wrap long lines to the available terminal width.

## How to apply

Keep `buildInitPrompt` in `packages/utils/extensions/init.ts` trimming source indentation, collapsing wrapped prose, and retaining meaningful paragraph and bullet line breaks. Normalize optional focus text to one inline sentence. Update `packages/utils/features/init.feature` and `packages/utils/tests/test_init_extension.py` when this behavior changes.

## Related

[[project_pi_package_conventions]]

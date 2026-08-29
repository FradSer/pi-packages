---
name: retest-reloaded-pi-package
description: Retest the current real-world case for the Pi package being developed after the user says they reloaded Pi. Use whenever the user says they reloaded/restarted Pi and asks to test again, verify again, retry the current package case, or confirms an extension reload while developing a Pi package.
---

# Retest Reloaded Pi Package

Use this skill after the user reloads Pi and asks to test again. The objective is to validate the **current real-world case** for the Pi package under development, not merely rerun its unit tests.

## Recover the active case

1. Read recent conversation context to identify:
   - The package being developed.
   - The bug, behavior, or UX case the user was validating before reload.
   - The exact user-visible failure or expected result.
2. Do not infer a new engineering workflow merely because Pi has been reloaded. Continue an active workflow only if the current case is still within its deliberate scope.
3. If the user has switched to unrelated work, do not reuse the previous package case or workflow.

## Retest the real case

1. Invoke the package's actual extension tool, command, or user-facing path that previously failed.
2. Use the same meaningful parameters described in the conversation. For interactive flows, exercise the real UI path where available.
3. Verify the user-visible result first. Then run targeted automated checks when they support the case.
4. Report whether the retry passed or failed, with concise evidence. If it fails, quote the observed result and identify the next diagnosis step.

## Completion report

State:

- Package and exact case retested.
- Observed user-visible outcome.
- Supporting validation commands and results.
- Any remaining limitation or required user action.

Do not claim success merely because Pi reloaded or a test suite passes; the requested real case must succeed.

---
name: retest-reloaded-pi-package
description: Re-run one concrete reproduction of the current Pi-package problem after the user reloads Pi. Use whenever the user says they reloaded/restarted Pi and asks to test, verify, or retry the current case. This is a user-visible reproduction retry, not a request to run unit tests, typechecks, or a test suite.
---

# Retest Reloaded Pi Package

Use this skill after the user reloads Pi and asks to try the current case again.

The purpose is to **simulate the problem the user encountered, then execute that same scenario once against the reloaded package**. It is not a generic test run. A passing `pytest`, `pnpm test`, or typecheck result does not answer whether the reloaded Pi extension works for the user's actual workflow.

## Recover the exact reproduction

1. Read the recent conversation and identify:
   - The package under development.
   - The specific command, tool, UI interaction, input, and any required prior state that exposed the problem.
   - The original user-visible symptom and the expected post-fix outcome.
2. Preserve meaningful inputs exactly. If the prior failure was `/context react --method=context7`, retry that command — do not substitute a generic Context7 request or an unrelated smoke test.
3. Identify the smallest **real** setup needed to recreate the failure conditions. For example, preserve a required active turn, package configuration, attachment, working directory, or queued follow-up when those were material to the bug.
4. Do not invent a new workflow merely because Pi was reloaded. If the user moved to unrelated work, do not reuse the earlier case.

## Simulate and retry once

1. Recreate the problem scenario through Pi's real user-facing surface:
   - Extension command: invoke that command with the original arguments.
   - Extension tool: issue the same meaningful tool request.
   - Interactive UI: drive the same menu, popup, or key path when available.
   - Print/RPC repro: use the same Pi CLI mode and package configuration that made the issue observable.
2. Use the minimum setup needed to simulate the original conditions, then run the scenario **once** after reload.
3. Observe the user-visible outcome first: transcript row, command result, tool invocation, UI state, error, or follow-up behavior. Capture only the signal needed to compare it with the original symptom.
4. Do **not** run `pytest`, `pnpm test`, `tsc`, a package build, or a broad smoke suite as this retest. Those commands may be useful for later development, but they neither replace nor belong in the reload retry by default.
5. If the scenario fails, report the observed failure verbatim enough to diagnose it and stop there. Do not mask it with unrelated automated checks.

## Completion report

State concisely:

- **Package and simulated case:** the exact original command/tool/UI path and relevant setup.
- **Single retry outcome:** what the user would see after reload, compared with the prior symptom.
- **Evidence:** the one real invocation and its decisive output or UI observation.
- **Remaining limitation:** only if the original scenario could not be reproduced or still fails.

Do not claim success because Pi reloaded, because the command exited zero, or because any test suite passes. Success means the one recreated user scenario no longer exhibits the reported problem.

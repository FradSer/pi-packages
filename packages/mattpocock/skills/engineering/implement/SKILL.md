---
name: implement
description: "Implements a piece of work from a spec or ticket set. Use when the user says \"implement this spec\", \"work the tickets\", or wants code written from an existing plan."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use /skill:bdd where possible, at pre-agreed seams. During the Automation phase, load `/skill:tdd` (BDD-driven) for test quality, seams, and mocking guidance.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /skill:code-review to review the work.

## CRITICAL: BDD at pre-agreed seams, review before commit

Use `/skill:bdd` where possible, one red-green slice at a time at pre-agreed seams. Load `/skill:tdd` (BDD-driven) during the Automation phase for test quality, seams, and mocking guidance. When the work is done, run `/skill:code-review` over it — a change without the two-axis review is not finished work.

When the user asks to commit, follow the repository's git-agent workflow rather than staging or committing directly.

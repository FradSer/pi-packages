# e2e Package Guidelines

## Scope and structure

`@fradser/pi-e2e` judges whether an end-to-end Gherkin `.feature` scenario was fulfilled by one test run.

- `src/gherkin.ts` parses Feature, Background, Scenario, tags, and steps.
- `src/checks.ts` executes L0 deterministic checks in code with veto authority.
- `src/questions.ts` builds atomic L1 System One questions for TypeSafe Jev.
- `src/typesafe.ts` handles communication with the TypeSafe API.
- `src/compose.ts` evaluates probability gates and derives the composed verdict.
- `src/verify.ts` orchestrates the three verification layers.
- `src/report.ts` renders markdown and HTML reports.
- `src/cli.ts` provides the standalone command-line entry point.
- `src/run.ts` runs the project adapter and tracks fresh per-attempt evidence.
- `src/harness.ts` manages feature checkpoints and same-turn verification retries.
- `src/tool.ts` exposes `e2e_verify`; `extensions/index.ts` also exposes `/e2e` in Pi.
- `features/e2e.feature` defines package contracts.
- `tests/test_e2e_package.py` runs Python and TypeScript harnesses.
- `tests/e2e/` runs containerized end-to-end browser tests via `e2e`.

Read @README.md for usage and @../../AGENTS.md for repository rules.

## Contracts

- Never send clauses to Jev that can be decided deterministically in code.
- Deterministic checks have hard veto authority: if a check fails, the verdict is `not_fulfilled`.
- Model questions must be atomic: each unjudged clause receives an independent Noul.
- Candidate triage causes must be independent Nouls; do not use a single multi-choice question for multiple potential causes.
- Policy gates (`clauseGate`, `verdictGate`) belong in code, not prompts.
- When probability or confidence is below gate thresholds, return `needs_review`, never `fulfilled`.
- Jev receives plain text and structured JSON only; image-based UI observations must be transcribed before submission.
- The CLI must return stable exit codes: 0 for fulfilled, 1 for unfulfilled, 2 for needs_review.

## Verification

Run these commands from the repository root:

```bash
python3 -m pytest packages/e2e/tests/ -q
pnpm typecheck
pnpm exec tsc --noEmit -p packages/e2e/tsconfig.json
pnpm --dir packages/e2e pack --dry-run
```

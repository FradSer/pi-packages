# Tasks working context

Read @README.md for the task interface and persistence contract.

## Current work

The user requests all lifecycle-review fixes and collapsed automatic waiting messages.
The source review is @../../docs/research/tasks-lifecycle-review-2026-10-13.md.
The current candidate hashes are @../../docs/research/tasks-fix-candidate.json.

## Changes

- Explicit reads identify the current blocker before historical recovery notes.
- Mixed completion errors identify content edits that were already saved.
- Recovery notes and retained evidence history count against normal write budgets.
- Earlier failure and operational blocker bodies remain in evidence history.
- Explicit outstanding lists replace current work; empty lists clear it.
- Present malformed task files do not become empty writable stores.
- Public tool success requires recovery from blocked state first.
- Existing library fallback acceptance remains available for verified external outcomes.
- Agent Teams checks `.ok` before reporting accepted outcomes or releasing holdings.
- Waiting messages collapse by default and use native expansion.
- Expanded recovery details distinguish current blocker, handoff, original plan and history.
- Tool activity wording no longer claims verified task progress.

## Verification

- Final combined Tasks and Agent Teams suites: 475 passed.
- Typecheck passed with `pnpm --config.verify-deps-before-run=false typecheck`.
- Tasks and Agent Teams packed manifests passed dry-run inspection.
- Isolated native Pi acceptance passed at 120x40, 48x24 and 48x12.
  Evidence: `/tmp/tasks-complete-handoff-final`.
- Native captures show collapsed headlines and expanded current recovery details.
- Independent final review: Standards PASS and Spec PASS. All 24 reviewed file hashes match.
- This final context update changes documentation only, after reviewed candidate validation.

## Limitations and next checks

- Native expansion shows the host shortcut label. Complete handoff fields are verified.
- Review and acceptance match the frozen runtime candidate. This context records final results.
- Installation audit reports eleven missing packages, including Agent Teams; Tasks is configured.
- Standard pnpm commands request dependency installation without a TTY.
  `--config.verify-deps-before-run=false` uses existing dependencies without changing them.
- No user settings, credentials, remote machines, or chezmoi files changed.
- Deterministic CLI checks do not prove real-model judgment or physical-terminal accessibility.
- A reload is needed before this running session can prove it loaded the updated renderer.

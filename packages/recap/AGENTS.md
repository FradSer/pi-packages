# Repository Guidelines

## Project Structure

`packages/recap/` publishes `@fradser/pi-recap`. The package-root `index.ts`
re-exports `extensions/index.ts`. `extensions/index.ts` registers `/recap`,
lifecycle hooks, model/language menus, and the above-editor widget;
`extensions/config.ts` handles `recap.json` and environment overrides;
`extensions/recap.ts` extracts exchanges, builds prompts, applies the
automatic-recap cost policy, cleans one-line summaries, and calls the model
registry. BDD contracts are in `features/recap.feature`, with executable checks
in `tests/test_recap_package.py`. Tests isolate `PI_CODING_AGENT_DIR` per
process: `config.ts` resolves its path when it loads, so a harness that reads
`recap.json` without isolation is asserting against the developer's own
configuration.

## Commands

Run focused tests and type checks from the repository root:

```bash
python3 -m pytest packages/recap/tests/ -q
pnpm exec tsc --noEmit --allowImportingTsExtensions -p packages/recap/tsconfig.json
pnpm --dir packages/recap pack --dry-run
```

## Style and Architecture

Recap generation is asynchronous and in-process through
Pi's model registry: preserve deduplication, cancellation, stale-session error
handling, and the automatic-recap cost policy. Three rules hold the boundaries:

- One request is bounded end to end. The 30-second budget is armed before
  credentials are requested and settles the caller's promise instead of only
  signalling the provider, so neither a hung credential lookup nor an
  uncooperative provider can leave a caller awaiting a recap forever.
- A failure after a result exists never becomes a rejection. Widget refreshes
  run from `performRecap`'s `finally`, so `updateRecapWidget` reports and
  returns instead of throwing; `/recap now` reports failure only when no recap
  was produced.
- Automatic recapping spends the session's own model once per turn. With no
  stored `autoRecap` preference it stays off for a reasoning model the user
  never chose for recaps, the menu and summary state the reason, and the
  one-shot startup recap is not withheld.

Keep summaries single-line and capped at 120 characters, truncated on grapheme
boundaries so a cut cannot leave a lone surrogate or an unbalanced code span.
The output-quality gate must hold in every configured language. Persist changed
recaps with `pi.appendEntry` and best-effort directory-session synchronization
through `withDirectorySessionRecord`, which resolves the registry path with
pi-kit's shared helper, verifies canonical ownership, and writes only the
`recap` field. Build the widget's Markdown once and swap its text; the recap row
re-renders on every frame while the agent streams. Widgets and menus are TUI
only; headless sessions and commands must not start generation. Keep the
recap widget above the editor and preserve its native-spinner alignment. While
generation runs, the recap line is replaced by the identity-only `Recapping...`
activity row; never render the marker above a stale recap line.

## Testing Guidelines

`features/recap.feature` and `tests/test_recap_package.py` cover persistence,
startup restoration, prompt cleanup, configuration, cancellation, the cost
policy, and headless behavior. Verify first-prompt summaries describe requested
work as planned, not completed; unchanged recaps must not create new entries.
The prompt keeps one rule per distinct failure mode: re-merge them only with a
named failure the merge provably still rejects. The manifest
ships `index.ts`, `extensions`, `features`, and `README.md`, excluding tests.

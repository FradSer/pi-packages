# CONTEXT

## Current state

`packages/loop` (npm `@fradser/pi-loop`, 0.1.0) is implemented and verified on branch
`pi/worktree/loop`, worktree `.pi/worktrees/loop`. Nothing is committed; `main` is untouched.

Source: `index.ts` re-exports `src/index.ts`; `src/index.ts` (command, native delivery,
lifecycle, transcript row), `params.ts` (flags), `duration.ts`, `template.ts`,
`segments.ts`, `candidates.ts`, `decide.ts` (all Jev questions), `scheduler.ts`,
`config.ts`, `types.ts`.
Docs: `README.md`, `AGENTS.md`, `features/loop.feature`.
Tests: `tests/loop-core-fixture.ts`, `tests/loop-decision-fixture.ts`,
`tests/loop-live-fixture.ts`, `tests/test_loop.py`, `tests/test_loop_decisions.py`,
`tests/test_loop_native.py`.

Root files changed: `scripts/publish-release.mjs` (publish scope, right after pi-kit),
`README.md` (package section), `.git-agent/config.yml` (`loop` commit scope),
`pnpm-lock.yaml` (new workspace member), `.changeset/loop-scheduled-self-prompting.md`.

## Last verified

- `python3 -m pytest packages/loop/tests/ -q` -> 15 passed (includes a real PTY run).
- `pnpm typecheck` -> pass. `pnpm pack:check` -> 19 packed manifests validated.
- `pnpm --dir packages/loop pack --dry-run` -> pass; no `workspace:` protocol in the tarball.
- `tests/` release, install-wiring and root-entry tests -> 60 passed.
- Whole repository suite -> 3620 passed, 3 failed, 1 skipped in 31m33s. All three failures
  are outside this change: `test_prompt_budget` measures the agent-teams `tmIdleLeader`
  section (3604 > 3600), `test_runtime_workspace_contracts` names
  `packages/continual-learning/package.json` (`typebox` not a `*` peer), and
  `test_memory_security` compares a home path with `FradSer` against the local `fradser`.
- Native PTY, parameterized: `LOOP_PROBE 1/2` and `LOOP_PROBE 2/2` delivered as
  `messageType: "user"`; no `/loop` text reached the model.
- Native PTY, semantic: a free request produced two real HTTP decision requests
  (`interval`/`runs`/`stop`, then `message`) and injected the selected candidate text.
- Native PTY, stopping: one `met` judgment answered 0.95 ended the loop after exactly one
  turn with no repeat judgment; the same request answered 0.3 kept injecting. The pair is
  the differential that shows the 0.8 threshold is what stops the loop.
- Terminal probe (`tests/live_loop_rows.py`, pyte): the row
  `[loop] started · every 1s · 2 times · UI_PROBE` and the status row
  `Looping · every 1s · 1/2` render at 120x40, survive a live resize of the same component to
  48x24, and are reachable by PageUp at 48x12. The status row clears when the loop finishes.
- `pi install <local tarball>` records the `.tgz` path and Pi's loader then rejects `.tgz`,
  so a tarball is not a usable install form. The directory form is, and it was verified.
- Installed path: `pi install` into an isolated `PI_CODING_AGENT_DIR`, then a native run that
  loaded `/loop` from settings with no `-e` delivered both injections.
- Install audit: `node scripts/check-installation.mjs <settings with workspace paths>` ->
  `OK: 18 workspace pi packages installed`.

## Commits on pi/worktree/loop

- `7cb3ed7 feat(loop): add scheduled self-prompting package`
- `2675ac8 test(loop): verify surface and unify reports`

## Open items

- `packages/loop` is live-installed in the real `~/.pi/agent/settings.json` as
  `../../Developer/FradSer/pi-packages/.pi/worktrees/loop/packages/loop`. It resolves to
  `@fradser/pi-loop` with `pi.extensions: ["./index.ts"]`, and `check:install` no longer
  reports it missing. AFTER MERGE, repoint that entry to the `packages/loop` path on `main`,
  because the worktree path becomes dead when the worktree is removed.
  Settings backup before the write: /tmp/pi-settings-backup-1792026113.json.
- `pnpm check:install` still exits 1 from this worktree, with 17 MISSING entries that are all
  pre-existing and unrelated: every other package is registered against the main checkout, so
  each path compares unequal against this worktree. The same audit passes with the worktree's
  own package paths (`OK: 18 workspace pi packages installed`).
- A full session with the real settings was not run: it would load the `pi-odk` extension,
  which reports sessions to Open DeskOS. Extension loading was verified in isolation instead.
- `test_readable_private_root_preserves_whitespace` is environment-specific; it asserts the
  local home path spelling. It cannot pass on this machine.
- The command surface is covered by `tests/loop-command-fixture.ts` + `test_loop_command.py`:
  no injection before the interval, one lifecycle row with `triggerTurn: false`, the status
  report, the stop path clearing the row, every refusal with its level, and the headless
  notice. The idle condition has one wording in both the status and the stop path.
- Not measured: physical-terminal and theme rendering, screen-reader output, and real-model
  Jev accuracy or service cost.
- Nothing is committed, pushed or published.

## Current decisions

- Every judgment goes through pi-kit `askSystemOne` (closed `noul`/`choice`/`score`). A model
  never writes the repeated message; code builds candidates and the model selects one.
- Fail closed: missing credential, unspecified cadence, low confidence and unknown answer
  keys are reports. `--until` needs a credential because Pi judges the condition.
- A tick whose previous injection has not settled is skipped and counted. `stop()` is terminal.
- Interval bounds are 1s to 1d, which is why a native test costs at least one second per tick.

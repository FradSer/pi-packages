# CONTEXT

## Current state

`packages/loop` (npm `@fradser/pi-loop`) is complete. Branch `pi/worktree/loop` is **rebased onto
`origin/main` (`05ab406`)** so the pull request carries only loop work, and it is pushed with PR
**https://github.com/FradSer/pi-packages/pull/43** (5 commits, mergeable, Code Terrier review passed).
`main` is untouched; its 5 unpushed local commits were left alone and a PR never carries them.

Source: `index.ts` re-exports `src/index.ts`; `src/index.ts` (command, native delivery, lifecycle,
transcript row), `params.ts`, `duration.ts`, `template.ts`, `segments.ts`, `candidates.ts`,
`decide.ts` (every Jev question), `scheduler.ts`, `config.ts`, `types.ts`. Docs: `README.md`,
`AGENTS.md`, `features/loop.feature`. Tests: `loop-core-fixture.ts`, `loop-decision-fixture.ts`,
`loop-command-fixture.ts`, `loop-live-fixture.ts`, `live_loop_rows.py`, `bun.d.ts`, and the four
`test_*.py` modules.

Root files changed by the branch: `scripts/publish-release.mjs` (publish scope, after pi-kit),
`README.md` (package section), `.git-agent/config.yml` (`loop` commit scope), `pnpm-lock.yaml`,
`.changeset/loop-scheduled-self-prompting.md`.

## Last verified

- `python3 -m pytest packages/loop/tests/ -q` -> 15 passed.
- The three native tests also pass against the workspace Pi 1.0.0 binary, which is the version CI
  installs: `PATH=$PWD/node_modules/.bin:$PATH pytest packages/loop/tests/test_loop_native.py` -> 3 passed.
- `pnpm exec tsc -NoEmit -p packages/loop/tsconfig.tests.json` -> 0 errors.
- `pnpm typecheck` -> pass. `pnpm pack:check` -> 19 packed manifests validated.
- `pnpm --dir packages/loop pack --dry-run` -> pass; the packed manifest pins `@fradser/pi-kit@0.5.1`
  with no `workspace:` protocol.
- Native PTY evidence: real `messageType: "user"` injection; two real HTTP decision requests for a
  free request; a `met` 0.95 judgment stopping after one turn against 0.3 continuing; and the row
  `[loop] started · every 1s · 2 times · UI_PROBE` composed at 120x40, across a live resize to 48x24,
  and reached by PageUp at 48x12.
- Install audit against this checkout's package paths: `OK: 18 workspace pi packages installed`.

## Open items

- CI (`quality.yml`) is **red at baseline**: the last five quality runs on `main` all failed, for
  reasons unrelated to this branch (`continual-learning` `typebox` peer, `matt-pocock` journeys,
  `subagents` TUI, `btw` TUI, `install_wiring`, and a `pnpm` modules-purge abort with no TTY). The
  three native loop tests that failed on the first CI run were a Pi-version artifact and are fixed.
- `packages/loop` is installed in the real `~/.pi/agent/settings.json` against the worktree path.
  AFTER MERGE, repoint it to `packages/loop` on `main`. Backup: `/tmp/pi-settings-backup-1792026113.json`.
- `pnpm check:install` also fails from `main` for seven packages the machine never installed
  (agent-teams, btw, context, monitor, plan-mode, skill-router, vision). This branch changes neither.
- A full session with the real settings was not run: it would load `pi-odk`, which reports sessions to
  Open DeskOS.

## Current decisions

- All judgments go through pi-kit `askSystemOne` (closed `noul`/`choice`/`score`). A model never writes
  the repeated message; code builds candidates and the model selects one.
- Fail closed: no credential, unspecified cadence, low confidence and unknown answer keys are reports.
  `--until` needs a credential because Pi judges the condition.
- A tick whose previous injection has not settled is skipped and counted. `stop()` is terminal.
- Native assertions must not depend on a Pi-version-specific field. `messageType` is Pi 1.2 and later,
  so the portability proof is the starting prompt, which only a user-input run carries; the
  `messageType` assertion stays where the host reports it.

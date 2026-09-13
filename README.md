# Frad's Pi Packages ![](https://img.shields.io/badge/packages-14-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable skills, extensions, and workflow commands.

## Packages

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

Compact `agent` delegation and shared `agent_event` communication for Pi. New work starts an independent session, fresh by default or forked from the Leader's context with `fork: true`; final answers return automatically. Work IDs target existing execution. Resident teams, board work, and peer messaging remain available.

**Tools:** `agent`, `agent_event`, `teammate_spawn`, `teammate_shutdown`, `task_create`, `send_message`, `task_list`

**Command:** `/agent-teams`

**Install:**

```bash
pi install npm:@fradser/pi-agent-teams
```

### [`@fradser/pi-btw`](packages/btw/)

Answers side questions in a read-only overlay without adding them to the current session history.

**Command:** `/btw <question>`

**Install:**

```bash
pi install npm:@fradser/pi-btw
```

### [`@fradser/pi-context`](packages/context/)

Researches repositories, libraries, and technical questions through an isolated prompt-constrained Pi child process with read and bash tools; its no-modification boundary comes from the research prompt rather than an OS sandbox. Natural-language research requests invoke the tool automatically; the started display wraps the complete query without an ellipsis, while results remain compact and expandable.

**Tool:** `context_get`

**Install:**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

Continual learning for Pi at the harness and prompt surfaces: declarative tool-call guardrails with corrective guidance, plus memory retrieval, injection, and manual consolidation.

**Commands:** `/memory`, `/consolidate`, `/harness`

**Install:**

```bash
pi install npm:pi-continual-learning
```

### [`@fradser/pi-impeccable`](packages/impeccable/)

Loads design guidance for interface polish, animation, typography, color, layout, copy, and browser-based iteration. Loading guidance does not execute scripts or authorize edits.

**Tool:** `impeccable_load`

**Command:** `/impeccable`

Install from this checkout (Node.js 22.18+):

```bash
pi install ./packages/impeccable
```

### [`pi-keyboard`](packages/keyboard/)

Controls VIA and QMK keyboard lighting to reflect Pi states, including idle, thinking, unread messages, approval prompts, and fatal errors. Requires a compatible keyboard.

**Command:** `/keyboard`

**Install:**

```bash
pi install npm:pi-keyboard
```

### [`pi-matt-pocock`](packages/matt-pocock/)

Provides `/matt-pocock`, a persisted Pi workflow harness for BDD, TDD, implementation, review, debugging, architecture, research, planning, teaching, and skill-writing procedures.

**Tool:** `matt_pocock_workflow`

**Command:** `/matt-pocock`

**Install:**

```bash
pi install npm:pi-matt-pocock
```

### [`@fradser/pi-monitor`](packages/monitor/)

Runs background commands against an explicit result contract and reports one structured terminal result.

**Tools:** `monitor_start`, `monitor_stop`

**Command:** `/monitor`

**Install:**

```bash
pi install npm:@fradser/pi-monitor
```

### [`@fradser/pi-plan-mode`](packages/plan-mode/)

Read-only exploration and planning in the main session before code modifications, with dedicated planning model support.

**Command:** `/plan`, `/plan start`, `/plan exit`, `/plan model`, `/plan status`

**Install:**

```bash
pi install npm:@fradser/pi-plan-mode
```

### [`@fradser/pi-recap`](packages/recap/)

Displays a concise summary of session progress above the TUI editor and restores it across restarts.

**Command:** `/recap`, `/recap now`, `/recap on`, `/recap off`, `/recap auto`, `/recap model [provider/model]`

**Install:**

```bash
pi install npm:@fradser/pi-recap
```

### [`pi-skill-router`](packages/skill-router/)

Routes to externally hosted skill collections: add GitHub skill repositories through the `/skill-router` menu, exposing selected skills behind a model-visible gateway. Ships no skill content directly.

**Command:** `/skill-router`

**Install:**

```bash
pi install npm:pi-skill-router
```

### [`@fradser/pi-utils`](packages/utils/)

Adds `/effort`, `/continue`, `/sessions`, `/init`, and redirects safe Git worktrees into `.pi/worktrees/`.

**Tools:** `enter_worktree`, `exit_worktree`, `list_directory_sessions`

**Commands:** `/effort`, `/continue`, `/sessions`, `/init`

**Install:**

```bash
pi install npm:@fradser/pi-utils
```

### [`@fradser/pi-vision`](packages/vision/)

Bridges images to a configured vision-capable model when the active Pi model only accepts text.

**Command:** `/vision`, `/vision model <model>`, `/vision on`, `/vision off`

**Install:**

```bash
pi install npm:@fradser/pi-vision
```

### [`@fradser/pi-session-control`](packages/session-control/)

Private Unix-socket discovery and prompt delivery to live sessions, with replay-safe stdin JSON-lines CLI `pi-session-control`. Accepted or queued receipts never imply completion.

For local installation and the versioned API, see the [package README](packages/session-control/README.md). First npm publication is pending.

## Development

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm pack:check
# or run all three checks together
pnpm check
```

Each package keeps behavior scenarios in `features/` and tests in `tests/`.

`pnpm check` runs the package and root pytest suites, the extension TypeScript project, and a registry-free packed-manifest check for every workspace package. Use `pnpm check:install` separately to audit the packages in the live Pi settings file.

The test suite requires Python 3 with `pytest` and Bun 1.4.1 for subprocess fixtures. The CI workflows install both runtimes before running `pnpm check`.

Use `pnpm --dir packages/<name> pack --dry-run` to inspect one package's contents before publishing.

Shared runtime helpers live in the internal [`@fradser/pi-kit`](packages/kit/) package. It is an internal workspace dependency and is not installable via `pi install`.

## Adding a package

1. Create `packages/<name>/`.
2. Add a `package.json` with the `pi-package` keyword and an explicit `pi` resource manifest.
3. Include runtime resources in `files` and declare imported Pi core packages as peer dependencies.
4. Write the BDD scenario under `features/` before implementation, then add executable tests.
5. Add a Changeset for a released package change.

## Publishing

Releases use Changesets and the GitHub Actions workflow in `.github/workflows/release.yml`. Pull requests and releases run `pnpm check` before release actions; the root `pnpm run publish` command runs the same gate before its local release script. Push changes to `main`, then merge the generated version PR. The workflow publishes the explicit package list through npm Trusted Publishing, in dependency order, and skips exact versions already present in the npm registry.

New packages require one manual first publication and npm Trusted Publishing configuration before later versions can be released by GitHub Actions.

## License

Each package is licensed under MIT.

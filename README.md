# Frad's Pi Packages ![](https://img.shields.io/badge/packages-12-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable skills, extensions, and workflow commands.

## Packages

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

Claude-Code-style collaborative agent teams for Pi with named resident teammates, a shared task board, and peer messaging.

**Tools:** `teammate_spawn`, `teammate_shutdown`, `task_create`, `send_message`, `task_list`

**Command:** `/agent-teams`, `/teammate`

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

Researches repositories, libraries, and technical questions through an isolated read-only Pi child process.

**Tool:** `context_get`

**Command:** `/context`

**Install:**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

Continual learning for Pi at the harness and prompt surfaces: declarative tool-call guardrails with corrective guidance, plus memory retrieval, injection, and manual consolidation.

**Commands:** `/memory`, `/consolidate`, `/guardrails`

**Install:**

```bash
pi install npm:pi-continual-learning
```

### [`pi-keyboard`](packages/keyboard/)

Controls VIA and QMK keyboard lighting to reflect Pi states, including idle, thinking, unread messages, approval prompts, and fatal errors.

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

**Command:** `/recap`, `/recap on`, `/recap off`, `/recap language <lang>`, `/recap model <model>`

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

## Development

```bash
pnpm install
python3 -m pytest packages
npx tsc --noEmit -p tsconfig.extensions.json
```

Each package keeps behavior scenarios in `features/` and tests in `tests/`.

Use `pnpm --dir packages/<name> pack --dry-run` to inspect package contents before publishing.

Shared runtime helpers live in the internal [`@fradser/pi-kit`](packages/kit/) package. It is an internal workspace dependency and is not installable via `pi install`.

## Adding a package

1. Create `packages/<name>/`.
2. Add a `package.json` with the `pi-package` keyword and an explicit `pi` resource manifest.
3. Include runtime resources in `files` and declare imported Pi core packages as peer dependencies.
4. Write the BDD scenario under `features/` before implementation, then add executable tests.
5. Add a Changeset for a released package change.

## Publishing

Releases use Changesets and the GitHub Actions workflow in `.github/workflows/release.yml`. Push changes to `main`, then merge the generated version PR. The workflow publishes the explicit package list through npm Trusted Publishing and skips versions already present in the npm registry.

New packages require one manual first publication and npm Trusted Publishing configuration before later versions can be released by GitHub Actions.

## License

Each package is licensed under MIT.

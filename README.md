# Frad's Pi Packages ![](https://img.shields.io/badge/packages-10-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable skills, extensions, and workflow commands.

## Packages

### [`keyboard`](packages/keyboard/)

Controls VIA and QMK keyboard lighting to reflect Pi states, including idle, thinking, unread messages, approval prompts, and fatal errors.

**Install:**

```bash
pi install npm:pi-keyboard
```

### [`recap`](packages/recap/)

Displays a concise summary of session progress above the TUI editor and restores it across restarts.

**Command:** `/recap`, `/recap on`, `/recap off`, `/recap language <lang>`, `/recap model <model>`

**Install:**

```bash
pi install npm:@fradser/pi-recap
```

### [`vision`](packages/vision/)

Bridges images to a configured vision-capable model when the active Pi model only accepts text.

**Command:** `/vision`, `/vision model provider/model`, `/vision on`, `/vision off`

**Install:**

```bash
pi install npm:@fradser/pi-vision
```

### [`btw`](packages/btw/)

Answers side questions in a read-only overlay without adding them to the current session history.

**Command:** `/btw <question>`

**Install:**

```bash
pi install npm:@fradser/pi-btw
```

### [`memory`](packages/memory/)

Manages durable project memory with a `/memory` menu, auto-memory guidance, and manual consolidation.

**Command:** `/memory`, `/consolidate`

**Install:**

```bash
pi install npm:@fradser/pi-memory
```

### [`monitor`](packages/monitor/)

Runs background commands against an explicit result contract and reports one structured terminal result.

**Tools:** `monitor_start`, `monitor_stop`

**Install:**

```bash
pi install npm:@fradser/pi-monitor
```

### [`utils`](packages/utils/)

Adds `/effort`, `/continue`, and `/sessions`, and redirects safe Git worktrees into `.pi/worktrees/`.

**Install:**

```bash
pi install npm:@fradser/pi-utils
```

### [`agent-teams`](packages/agent-teams/)

Coordinates child Pi workers through dependency-aware task graphs, bounded concurrency, cancellation, retries, and a full-screen console.

**Tools:** `teammate_run`, `teammate_cancel`, `teammate_retry`, `teammate_message`

**Command:** `/teammate`

**Install:**

```bash
pi install npm:@fradser/pi-agent-teams
```

### [`code-context`](packages/code-context/)

Provides DeepWiki, Context7, and Exa retrieval tools through native Pi extensions, with clone and HTTP fallbacks.

**Skills:** `/skill:get-context`, `/skill:code-context`

**Install:**

```bash
pi install npm:@fradser/pi-context
```

### [`mattpocock`](packages/mattpocock/)

Provides Pi-adapted BDD, TDD, implementation, review, debugging, architecture, research, planning, teaching, and skill-writing workflows.

**Install:**

```bash
pi install npm:pi-mattpocock
```

## Development

```bash
pnpm install
python3 -m pytest packages
```

Each package keeps behavior scenarios in `features/` and tests in `tests/`. For an extension, run the relevant strict TypeScript check:

```bash
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/<name>/{src,extensions}/*.ts
```

Use `pnpm pack --dry-run` from a package directory to inspect its published files.

## Adding a package

1. Create `packages/<name>/`.
2. Add a `package.json` with the `pi-package` keyword and an explicit `pi` resource manifest.
3. Include runtime resources in `files` and declare imported Pi core packages as peer dependencies.
4. Write the BDD scenario under `features/` before implementation, then add executable tests.
5. Add a Changeset for a released package change.

## Publishing

Releases use Changesets and the GitHub Actions workflow in `.github/workflows/release.yml`. Push changes to `main`, then merge the generated version PR. The workflow publishes the explicit package list through npm Trusted Publishing and skips versions already present in the npm registry, so partial runs can be retried safely.

New packages require one manual first publication and npm Trusted Publishing configuration before later versions can be released by GitHub Actions.

## License

Each package is licensed under MIT.

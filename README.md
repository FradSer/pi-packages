# Frad's Pi Packages ![](https://img.shields.io/badge/packages-8-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable skills, extensions, and workflow commands.

## Using packages

Skills use Pi's `/skill:<name>` command. Arguments after the command are appended to the skill text. Pi does not expand `$ARGUMENTS` or execute shell substitutions embedded in skill Markdown.

Packages that manage interactive workflows use native commands such as `/memory`, `/btw`, and `/teammate` instead of skills.

Released packages can be installed with a copyable npm source:

```bash
pi install npm:@fradser/pi-memory
```

Every package can be used from this checkout during development:

```bash
pi install /path/to/pi-packages/packages/<name>
```

## Packages

### [`vision`](packages/vision/)

Bridges images to text for a text-only active model through a configured vision-capable Pi model. It preserves the original session attachment and adds visual analysis only to the transient provider context.

**Command:** `/vision`, `/vision model provider/model`, `/vision on`, `/vision off`

**Availability:** install from this checkout. Its first npm release has not been published yet.

---

### [`btw`](packages/btw/)

Answers a side question in a read-only overlay without adding it to the current session history. The child Pi process may use `read`, `grep`, `find`, and `ls` to check the codebase, but cannot use `bash`, `edit`, or `write`.

**Command:** `/btw <question>`

**Install:**

```bash
pi install npm:@fradser/pi-btw
```

---

### [`code-context`](packages/code-context/)

Provides DeepWiki, Context7, and Exa retrieval tools, with clone and HTTP fetch workflows as fallbacks. The package uses direct REST calls rather than MCP sidecars.

**Skills:** `/skill:get-context`, `/skill:code-context`

**Tools:** `context_deepwiki`, `context_context7`, `context_exa`

**Availability:** install from this checkout. It is not currently released to npm.

---

### [`mattpocock`](packages/mattpocock/)

A collection of Pi-adapted BDD, TDD, implementation, review, debugging, architecture, research, planning, handoff, teaching, and skill-writing workflows.

**Skills:** 27 individual skills, including `/skill:bdd`, `/skill:tdd`, `/skill:implement`, and `/skill:code-review`

**Availability:** install from this checkout. It is not currently released to npm.

---

### [`memory`](packages/memory/)

Manages durable project memory with a `/memory` menu, auto-memory guidance, and background consolidation. The consolidation procedure runs in a separate child Pi process and keeps its raw work outside the active conversation.

**Commands:** `/memory`, `/consolidate`

**Install:**

```bash
pi install npm:@fradser/pi-memory
```

---

### [`monitor`](packages/monitor/)

Runs a command in the background against an explicit result contract. It stores ordinary output outside model context and sends exactly one structured terminal result for success, failure, timeout, or a missing result.

**Tools:** `monitor_start`, `monitor_stop`

The terminal notification includes a bounded diagnostic tail. `/monitor` is for human inspection; there is no model-facing output reader or polling tool.

**Skill:** `/skill:using-monitor`

**Command:** `/monitor`

**Install:**

```bash
pi install npm:@fradser/pi-monitor
```

---

### [`agent-teams`](packages/agent-teams/)

Coordinates autonomous child Pi workers through a leader-owned task board and mailbox protocol. The team leader can register teammates, create and start ready tasks, wait for results, send messages, cancel runs, and inspect the full-screen console.

**Tools:** `teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_message`, `teammate_inbox`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, `teammate_wait`, `teammate_cancel_task`, `teammate_cleanup`

**Command:** `/teammate`

**Availability:** install from this checkout. It is not currently released to npm.

---

### [`utils`](packages/utils/)

Adds commands for selecting a model thinking level and recovering interrupted work. It also directs safe `git worktree add` invocations into `.pi/worktrees/`.

**Commands:** `/effort`, `/continue`

**Install:**

```bash
pi install npm:@fradser/pi-utils
```

## Development

```bash
pnpm install
python3 -m pytest packages
```

Each package keeps its behavior scenarios in `features/` and tests in `tests/`. Run the relevant strict TypeScript check after editing an extension:

```bash
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/<name>/{src,extensions}/*.ts
```

Use `pnpm pack --dry-run` from an individual package to inspect the files that would ship.

## Adding a package

1. Create `packages/<name>/`.
2. Add a `package.json` with the `pi-package` keyword and an explicit `pi` resource manifest.
3. Include every runtime resource in `files` and declare every imported Pi core package as a peer dependency.
4. Write the BDD scenario under `features/` before implementation, then add executable tests.
5. Install the package locally with `pi install /path/to/pi-packages/packages/<name>` and validate its package contents.

## Publishing

This repository publishes through Changesets and the GitHub Actions release workflow. Do not run recursive `pnpm publish` from the repository root.

For a released package change, create a Changeset, push it to `main`, and merge the generated version PR. The release workflow publishes only its explicit package allowlist with npm trusted publishing. A new package needs its first npm publication and trusted-publishing setup before the workflow can publish later versions.

## License

Each package declares the MIT license in its own manifest. The repository does not have a separate root license file.

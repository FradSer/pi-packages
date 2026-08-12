# Frad's Pi Packages ![](https://img.shields.io/badge/packages-8-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable agent skills, extensions, and project workflows.

## Invocation

Invoke every skill with Pi's `/skill:<name>` command. Arguments are appended after the skill body. Pi does not expand `$ARGUMENTS` or run shell injections inside skill Markdown.

## Packages

### [`code-context`](packages/code-context/)

Retrieves code context through DeepWiki, Context7, Exa, direct git cloning, and web fetches. The three retrieval methods are native pi tools (`context_deepwiki`, `context_context7`, `context_exa`) calling the public REST APIs directly — no MCP servers; git clone and HTTP fetch always remain available.

**Skills:** `code-context`, `get-context`

**Installation:**
```bash
pi install npm:@fradser/code-context
# or from this repo: pi install /path/to/pi-packages/packages/code-context
```

---

### [`git`](packages/git/)

Automates GitFlow feature, hotfix, and release branch lifecycles, including tests, changelog updates, tags, releases, and cleanup.

**Skills:** `start-feature`, `finish-feature`, `start-hotfix`, `finish-hotfix`, `start-release`, `finish-release`, `commit`, `commit-and-push`

**Installation:**
```bash
pi install npm:@fradser/git
# or from this repo: pi install /path/to/pi-packages/packages/git
```

---

### [`git-agent`](packages/git-agent/)

Provides AI-first atomic commits, co-change analysis, workspace initialization, and a pre-tool guard for raw Git commit operations.

**Skills:** `commit`, `commit-and-push`, `related`, `init`

**Installation:**
```bash
pi install npm:@fradser/git-agent
# or from this repo: pi install /path/to/pi-packages/packages/git-agent
```

---

### [`github`](packages/github/)

Handles GitHub issues and pull requests with TDD-oriented quality gates, validation, and a persistent CI and review-comment workflow.

**Skills:** `github-create-issues`, `github-create-pr`, `resolve-issues`, `review-pr`

**Requirements:** GitHub CLI (`gh`) must be installed and authenticated, and the repository must have a GitHub remote.

**Installation:**
```bash
pi install npm:@fradser/github
# or from this repo: pi install /path/to/pi-packages/packages/github
```

---

### [`lark`](packages/lark/)

Provides Feishu/Lark CLI skills for documents, sheets, messaging, calendars, approvals, drives, wikis, contacts, mail, tasks, meetings, and related services.

**Skills:** `lark` router plus the mirrored Lark sub-skills

**Installation:**
```bash
pi install npm:@fradser/lark
# or from this repo: pi install /path/to/pi-packages/packages/lark
```

---

### [`mattpocock`](packages/mattpocock/)

BDD-first engineering and productivity skills adapted from Matt Pocock's skills. Covers TDD, implementation, debugging, architecture, research, code review, planning, handoff, teaching, and skill writing.

**Installation:**
```bash
pi install npm:@fradser/mattpocock
# or from this repo: pi install /path/to/pi-packages/packages/mattpocock
```

---

### [`memory`](packages/memory/)

Maintains project memory in `.memory/` and provides manual consolidation with clustering, staleness checks, ground-truth verification, and privacy validation.

**Skills:** `consolidate`

**Installation:**
```bash
pi install npm:@fradser/memory
# or from this repo: pi install /path/to/pi-packages/packages/memory
```

---

### [`utils`](packages/utils/)

Keeps project READMEs synchronized and creates or updates changelogs in Keep a Changelog 1.1.0 format.

**Skills:** `update-readme`, `update-changelog`

**Installation:**
```bash
pi install npm:@fradser/utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Notes

The `git` and `git-agent` packages both expose `commit` and `commit-and-push`. Install order determines which skill wins if both packages are enabled.

## SDK Harness

`examples/sdk-session.ts` shows a programmatic `createAgentSession()` consumer that wires package extensions and inspects discovered skills. Packages remain installable skill and extension bundles rather than embedded applications.

```bash
pnpm example:sdk
# or directly:
npx tsx examples/sdk-session.ts
# optional live model turn:
PI_SDK_LIVE=1 npx tsx examples/sdk-session.ts
```

## Adding a Package

1. Create a package directory under `packages/`.
2. Add `package.json` with the `pi-package` keyword and a `pi` resource manifest.
3. Add skills, extensions, prompts, or themes under the paths declared in `package.json`.
4. Install the local package with `pi install /path/to/pi-packages/packages/<name>` and run its tests.
5. Run `/skill:update-readme` manually to synchronize both README files.

## Publishing

Packages are published to npm under the `@fradser` scope and appear in the [pi.dev/packages](https://pi.dev/packages) gallery via the `pi-package` keyword.

```bash
pnpm install          # install workspace dev dependencies
pnpm publish          # publish all packages (pnpm -r publish --access public)
pnpm publish:dry-run  # build tarballs to inspect package contents
```

## Licensing

Each package currently declares the MIT license in its own manifest. The repository does not have a separate root license file.

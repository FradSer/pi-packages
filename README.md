# Frad's Pi Packages

A collection of Pi Agent packages, skills, extensions, and workflows.

## Invocation

All skills are loaded with Pi's **`/skill:<name>`** command (not Claude `/plugin:cmd` slash forms). Arguments are appended after the skill body; Pi does not expand `$ARGUMENTS` or run `` !`cmd` `` injections inside skill Markdown.

Extension packages (`memory`, `git`, `git-agent`) declare `peerDependencies` on `@earendil-works/pi-coding-agent`.


## Packages

### 1. `code-context`
Retrieve code context for any repository, library, or natural-language query via DeepWiki, Context7, Exa, git clone, and web search+fetch.

**Skills included:**
- `code-context`: Code context retrieval workflow and token isolation principles
- `get-context`: Multi-source context researcher invocation

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/code-context
```

---

### 2. `github`
GitHub project operations with quality gates, TDD workflows, and validation.

**Skills included:**
- `github-create-issues`: Creates GitHub issues following TDD and conventional commit standards
- `github-create-pr`: Creates Pull Requests with quality gates
- `resolve-issues`: Resolves GitHub issues using TDD workflow
- `review-pr`: Comprehensive PR review workflow and monitoring

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/github
```

---

### 3. `git`
Conventional Git automation, advanced repository management, and GitFlow workflow automation for feature, hotfix, and release branches with post-finish cleanup.

**Skills included:**
- `commit` / `commit-and-push`: GitFlow-oriented commit helpers (note: may collide with `git-agent` skill names — install order decides which wins)
- `start-feature`: Starts a `feature/*` branch from develop via git-flow-next
- `finish-feature`: Runs tests, updates changelog, finishes feature into develop, pushes, and cleans up
- `start-hotfix`: Resolves next patch version and starts `hotfix/*` branch from main
- `finish-hotfix`: Runs tests, updates changelog, finishes hotfix into main and develop with tag, and cleans up
- `start-release`: Resolves next semver version and starts `release/*` branch from develop
- `finish-release`: Runs tests, updates changelog, finishes release with tag, creates GitHub release, and cleans up

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/git
```

---

### 4. `git-agent`
AI-first Git CLI automation — atomic AI commits, co-change relations (`git-agent related`), pre-tool hook safety, and workspace initialization.

**Skills included:**
- `commit`: Creates atomic conventional commits via `git-agent`
- `commit-and-push`: Creates atomic conventional commits and pushes to remote
- `related`: Mines git history for historically coupled files and test suites
- `init`: Regenerates commit scopes and `.gitignore` rules from history

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/git-agent
```

---

### 5. `lark`
Feishu/Lark CLI skills mirrored from `larksuite/cli` — docs, sheets, IM, calendar, approval, drive, wiki, contacts, minutes, mail, tasks, events, video conferences, whiteboards, and more.

**Skills included:**
- `lark`: Router skill indexing all Lark/Feishu sub-skills (`lark-shared`, `lark-doc`, `lark-sheets`, `lark-im`, `lark-calendar`, etc.)

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/lark
```

---

### 5. `memory`
Active memory writing and consolidated project memory management (`.memory/` canonical git-tracked files + harness memory).

**Skills included:**
- `consolidate`: Consolidates project memory with theme clustering, practical-expiry prune, ground-truth verify, and validation.

**Installation:**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/memory
```

---

## SDK harness (optional)

`examples/sdk-session.ts` shows a programmatic `createAgentSession()` consumer that wires package extensions and inspects discovered skills. Packages themselves remain skill/extension packages, not embedded apps.

```bash
npx tsx examples/sdk-session.ts
# optional live model turn:
PI_SDK_LIVE=1 npx tsx examples/sdk-session.ts
```

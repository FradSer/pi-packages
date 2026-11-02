# @fradser/pi-utils

## 0.6.0

### Minor Changes

- e86a44f: `/autoname` names the current session with the current model.
  
  Pi's own `/name` answers `Usage: /name <name>` when it is submitted with no
  argument and no name set. `/autoname` is the model-generated counterpart: it
  reads what the session is about and applies a short, recognizable display name.
  
  **Why a new command**
  
  `/name` is compiled into the interactive mode. Its branch runs before
  extension commands are consulted, and Pi exposes no hook to intercept it, so an
  extension cannot give it a model-generated argumentless behavior. `/name
  <name>` still sets an explicit name; `/autoname` is for the case where you do
  not want to type one.
  
  **What it does**
  
  - Builds its digest from the user's own requests only, so the name describes the
    task instead of the assistant's wording, and bounds the digest to a fixed
    character budget.
  - Steers the name with an optional argument: `/autoname release notes rewrite`.
  - Reduces the model answer to a plain display name. Quoting, markdown, list
    markers, and any sentence after the first line are dropped; an over-long name
    is cut at a word boundary.
  - Sends a bounded one-shot request: no tools, at most 64 output tokens, no
    caching, and the current session id forwarded so conversation-routing gateways
    accept the nested call.
  
  **Failure behavior**
  
  Generation always settles. A 20-second deadline, an aborted session, a missing
  model, absent credentials, a provider rejection, and an unusable answer each
  report their own cause. The deadline races the request rather than only
  signalling it, so a provider that ignores its abort signal cannot hold the
  command open, and each failure is reported as a reported failure rather than an
  unhandled rejection. A provider rejection arrives as a message carrying
  `stopReason: "error"` rather than as a thrown error, and is no longer reported
  as a credential problem.
- e86a44f: Worktree paths now anchor to the repository root, the /effort menu mirrors pi's supported-level rule, and live-session control has a command to reach it.
  
  **@fradser/pi-utils**
  
  - **One worktree location.** `git worktree add` issued from a repository subdirectory was rewritten to a cwd-relative `.pi/worktrees/<name>`, so the worktree landed somewhere `/enter-worktree` and the isolation filters never looked. The redirect now resolves the repository root and emits the absolute managed path, and all three worktree layers share one porcelain parser, canonicalizer, and `.pi/worktrees` definition (`extensions/git/worktrees.ts`). A repository that does not git-ignore `.pi/` is told so; the extension never edits a `.gitignore`.
  - **`/effort` matches pi.** The menu hid `xhigh`/`max` only when a `thinkingLevelMap` was present and treated an absent `reasoning` flag as full support, diverging from pi's own rule. It now applies the same predicate, pinned by a parity test against `getSupportedThinkingLevels` from `@earendil-works/pi-ai`.
  - **`/live-sessions`.** Live-session discovery and delivery had no entry point in the shipped package. The new command lists instances (with id completions) and sends text, reporting `accepted` or `queued` without ever claiming completion, and bounds its arguments before touching a socket.
  - **Transition honesty.** An aborted run drops the queued worktree transition and now says so instead of leaving the model believing one was coming; a worktree command invoked while a transition is queued is refused rather than racing the session switch; the batch barrier names the pending transition.
  - **Registry and guard cleanups.** A session removes its record from every directory it registered under (session replacement changes cwd without reloading extensions), registry temp names no longer depend on a per-millisecond clock, and the publish guard's advice follows the repository's lockfile instead of asserting "this pnpm workspace" to every user.
  - **Cross-package tool inputs.** The worktree isolation filters write `exclude` only into search tools whose declared schema has that parameter; undeclared tools keep their input untouched and are still filtered on the way back.
  - **Verification.** Extension tests that asserted on source text are replaced by tests that drive registered command handlers, tool `execute`, and event handlers against a fake host: the same mutation that used to pass `/effort` tests silently now fails seven.
- 4d20b94: A managed worktree is created on the name itself, with no tool namespace.
  
  `/enter-worktree feature-auth` created `.pi/worktrees/feature-auth` on branch
  `pi/worktree/feature-auth`: a namespace plus a `worktree` segment that repeated
  what the managed path already says.
  
  - The branch is now the name: `.pi/worktrees/feature-auth` on branch
    `feature-auth`, the spelling a plain
    `git worktree add .pi/worktrees/<name> <branch>` reads. The location stays
    `.pi/worktrees/<name>`; only the branch lost the prefix.
  - Two names are refused before anything is created, so the user reads one reason
    instead of git's fatal and no empty `.pi/worktrees` directory is left behind:
    a name git rejects as a ref (a leading dot, a trailing `.lock`), and a name
    whose branch already exists — the common collision of a bare name, which
    `git worktree add -b` would refuse. That message names the way out: another
    name, or `path` for an existing worktree.
  - `/exit-worktree` is unaffected: it removes the branch recorded in the session
    state, so a worktree created under the old name still cleans up.
  
  A worktree created by a redirected `git worktree add` keeps the branch named in
  that command; this changes only the branch this package creates.
- faa2664: A redirected `git worktree add` moves the Pi session into the worktree it
  created.
  
  The redirect already kept linked worktrees inside `.pi/worktrees/<name>`. It now
  also switches the session there, so the next relative path, edit, or shell
  command belongs to the new checkout instead of the parent.
  
  - The move is reserved before the command runs, so the rest of that tool batch
    is blocked rather than editing the checkout the session is leaving.
  - The replacement session is forked from the current one and records the parent,
    exactly like `/enter-worktree`, so `/exit-worktree` keeps its behavior. The
    worktree is entered as an existing one: no second worktree or branch appears.
  - The replacement session records one `[worktree] entered` row with the managed path,
    so the move is confirmed in the session it happened in. An extension notice sent
    during the switch does not reliably paint; the row does, and Ctrl+O expands it to
    `Path: <absolute directory>`. This replaces the transient
    `Entered worktree:` notice of the explicit command path too.
  - A failed creation releases the batch and tells the user the session stays in
    its current directory. A reserved command that produces no result at all — a
    truncated message, or a blocker that stops it before execution — never moves
    the session, because only a successful result confirms the directory exists.
  - A creation cannot start while another switch is already in flight, and a
    worktree command invoked after a reservation is refused by name until the turn
    settles. Neither case leaves a stray worktree or a silent session move.
  - A session without a session file cannot be replaced: the worktree stays on
    disk and the user is told that Pi cannot switch to it.
  - An explicit `/enter-worktree` or `enter_worktree` in the same message wins
    over the automatic move.
  - An aborted run drops the queued move and says so; the created worktree is
    kept. Pi 1.2.0 reports the abort on `agent_settled`; an older host that does
    not report it still applies the move.
  
  Commands that are not rewritten, such as a chained shell form or an
  already-managed path, never move the session.

### Patch Changes

- 8662e95: Use additive run-start prompt contributions instead of complete prompt overrides. Do not use custom messages for context injection. Handle custom startup without a user prompt. Keep unrelated workflow records and authorization checkpoints.
- 0010f51: Move the development Pi core cohort to 1.2.0 and stay type-correct on it. `before_agent_start` handlers in the goal runtime, Agent Teams and utils now test for the prompt instead of reading it directly, so they compile against both the older event shape and the current union Pi discriminates by run kind.
- 53cb34f: Stop `setActiveTools` toggle writes from deactivating tools the harness has not published yet.
  
  `setActiveTools` is an allowlist write: the caller passes the complete set the
  model may call, and anything absent is deactivated for the rest of the session.
  Every extension that toggled a tool read the active-tool snapshot, adjusted it,
  and wrote it back, so a snapshot that had not yet reported an extension's own
  registrations silently erased them. `pi-matt-pocock` then kept delivering routing
  prompts that name `matt_pocock_workflow`, instructing the model to call a tool it
  could not see.
  
  `@fradser/pi-kit` gains `setOwnedTools`, which re-asserts the extension's own
  tools instead of trusting the snapshot, and all five call sites now use it:
  `pi-matt-pocock`, `pi-monitor`, `pi-utils` sessions and worktree-session, and
  `@fradser/pi-agent-teams`' worker disclosure. Repeated identical writes are now
  idempotent rather than accumulating a duplicate entry.
- e86a44f: Read the last complete session entry when it exceeds the continuation read window. Report a rejected continuation delivery to the user instead of leaving it to the host. Replace source-text checks with behavior tests and share the test runner.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [2bba220]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0

## 0.5.2

### Patch Changes

- ad80757: Apply worktree transitions only after the old agent run settles, block competing tool calls while switching, and resume the task through the new worktree session context. Prevent stale absolute edit/write paths from modifying another checkout. Require Pi 0.85.1 or newer for expanded command dispatch.

## 0.5.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.5.0

### Minor Changes

- 919504f: Add private live-session discovery and replay-safe prompt delivery as an integrated pi-utils capability, with bounded Unix socket transport and explicit submission receipts.

### Patch Changes

- a79d85f: Bound the injected peer-session recap as a whole. Per-field limits still let five peers with long goals, recaps, and file lists add up, so the block now stops adding peers beyond a 1,500-character ceiling, always keeps the most recent one, and reports how many were omitted to keep the recap bounded instead of growing with the number of sessions.
- 9cabb0d: Bump every package by one patch version.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- cc24fd4: Make `/init` repository-agnostic by removing hardcoded Pi-kit dependency policies and host-specific loading claims. Discover tooling, shared modules, and contribution conventions from the target project, and handle directories without Git metadata.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- ac83f4e: Use one canonical, hashed directory-session identity across keyboard, recap, and utils. Verify registry ownership before reading or removing records, preserve per-command keyboard failures through the serial queue, pair recaps with the latest complete answer, and ignore pre-cancelled, auth-cancelled, or late provider responses.
- 5b4f51b: Make /init audit and simplify scoped contributor instructions, using task-specific references, evidence-based autonomy, and explicit completion boundaries instead of word quotas and mandatory templates.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- 9682969: Label injected peer-session context as untrusted data. The directory recap that reaches the system prompt now states that it is another session's own notes, possibly stale, and that directives inside it are never instructions. Peer goals, recaps, and file entries are bounded in length at the injection point, and a truncation boundary never emits half of a surrogate pair.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0

## 0.4.2

### Patch Changes

- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- 92944c1: Apply progressive tool disclosure across runtime packages. State-dependent capabilities are now hidden until their workflow state is active, and continual-learning no longer couples its guardrails to Matt Pocock workflow state.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- a446bbf: Hide `.pi/worktrees/` and its contents in editor file suggestions (`@` completions) in the main checkout session, and isolate managed worktree completions across sessions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.4.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.4.0

### Minor Changes

- 8905dbd: Add Claude Code-style EnterWorktree and ExitWorktree session switching. Pi can
  create or enter a git worktree through a replacement session, rebind built-in
  tools and @ completions to that worktree cwd, return to the parent session, and
  optionally clean up worktrees created by Pi.
- edccd2f: Block package publish and npm credential commands (`publish`, `login`/`adduser`/`logout`, `token create/revoke/delete`) from the agent's non-interactive bash tool. These flows cannot complete there — 2FA web-auth exits immediately with EOTP and dead tokens surface as masked 404 PUT failures — so the guard blocks the call and returns corrective steering that routes the interactive step to the user's own terminal and the `npm-package-first-release` skill procedure.
- 8905dbd: Add git worktree-aware @ completions: editor file suggestions now hide paths
  that resolve inside another git worktree. A session in main never sees linked
  worktree contents, and a session inside a linked worktree never sees sibling
  worktrees or the main checkout.

### Patch Changes

- dcf3806: Preserve paragraph and bullet line breaks in `/init` instructions while letting Pi's TUI wrap long lines to the available width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.3.7

### Patch Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.3.6

### Patch Changes

- 7ad11b4: Make /continue always retry with the current model and configuration: remove error classification gating that turned stale persisted failures into permanent refusals even after switching models or fixing config, drop the redundant auth preflight, strip consecutive failed assistant messages from retried context while keeping tool-call/result pairs intact, route the continuation keyword through the registered /continue command, and remove the internal __continue command from the command menu.
- 9edc0a6: Preserve the selected session-tree node when continuing: /continue reloads the same session only when the disk tip is unknown to the active session, while entries written by another process are still inherited before retrying.
- 7ad11b4: Render `list_directory_sessions` with the shared compact tool display pattern: self-rendered shell, empty call slot, and one `[sessions] listed · N other sessions in <dir>` result row styled like monitor terminal events (custom-message label color on the custom-message background). Expanding reveals a bounded block per session with status, pid, relative age, goal, recap, and recent files; every display field is sanitized with the new shared `safeDisplayText` and truncated to bounded lengths.
  
  Registry reads now normalize untrusted records on read (numeric pid/timestamps, known status union), merge records from multiple writers (extension state and keyboard glow state use different id conventions) into one logical session per owning process, and exclude records owned by the current process regardless of id, so counts and listings are no longer doubled.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.3.5

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.3.4

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.3.3

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.3.2

### Patch Changes

- 40d0127: Expand `/continue` recovery to handle provider/model API errors and truncated responses, preserving useful error details while avoiding repeated completed work.

## 0.3.1

### Patch Changes

- 89337a2: Rename to @fradser/pi-utils and publish for the first time.

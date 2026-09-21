# @fradser/pi-kit

## 0.5.1

### Patch Changes

- 52e25f9: Match Pi's typed mouse handler in the structural component contract. `PiMessageComponent.handleMouse` was declared as `(event: unknown) => unknown`, which stopped satisfying the host's `Component.handleMouse` once Pi typed it as `(event: TuiMouseEvent) => TuiMouseEventResult | undefined`, so a package returning a lifecycle component from `registerTool` or `registerMessageRenderer` no longer compiled against the current host. The interface now mirrors that result as the structural `PiMouseEventResult`, keeping kit free of Pi runtime imports while a consumer's type-checker accepts the component again.

## 0.5.0

### Minor Changes

- 28bdae2: Add `searchModelFromPicker`, an interactive type-to-filter model picker built on `ctx.ui.custom`. Packages can pass the full registry model list (e.g. `ctx.modelRegistry.getAll()`) instead of only scoped or available models; the picker offers live search, keyboard navigation, a current-model marker, and empty-list warning fallback.
  
  `pi-recap`, `pi-vision`, and `pi-continual-learning` model menus now use the searchable picker and enumerate all registered models instead of limiting selection to scoped models.
- 707c4c5: Add `verbatimSubject`, `subjectBlock`, and `bgToken` to the lifecycle spec so user-authored text renders raw on the band: one row per authored line, wrapping instead of merging, no `@name` recoloring, no expand hint for text that is already visible, an optional block layout (head row, blank band row, then the authored lines), and an opt-in band tint such as `userMessageBg`. Hidden details still expand and keep their hint.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.

### Patch Changes

- b0231e3: Render coordination message previews against the actual terminal width rather than a fixed character limit, reserving the complete configured expansion hint. Expanded message rows wrap the full message inline after the recipient and outcome exactly once instead of repeating a clipped preview above a duplicate body. Preserve semantic line breaks, native theme bands, and safe display text, including visible labels inside terminal OSC-8 hyperlinks. Keep literal JSON empty strings, punctuation spacing, and quoted newlines intact by separating handle replacement from prose cleanup. Reuse the same pi-kit lifecycle abstraction as context research; native Ctrl+O, mouse expansion, and terminal resizing are covered by isolated Pi integration tests.
- ac83f4e: Prevent pre-cancelled child workers from spawning, fail closed on bounded worker stream violations, and disable extension discovery for isolated side-question and research children.
- 9cabb0d: Bump every package by one patch version.
- 919504f: Remove the obsolete shared package-agent prompt helper from pi-kit.
- bcb0054: Move continual-learning planner protocols into package-owned prompt resources, add typed local builders with fail-closed placeholder validation, migrate every one-shot planner caller, and launch children with the shared minimal read-only Pi environment.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- 919504f: Wrap custom transcript lifecycle messages in host ToolExecutionComponent so mouse click toggling works symmetrically with tool result rows.
- 274cc90: Unify lifecycle expansion across normal and static tool/message renderers. Internal metadata and empty detail bodies no longer create empty expansion prompts; width-clipped titles and summaries reveal their full text through the injected native wrapper. Preserve full readbacks, paragraph spacing, error evidence, and the explicit legacy low-level host override.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- b0231e3: Replace the recap line with a single identity-only `Recapping...` activity row while a recap is generating instead of stacking the marker above a stale `✦ Recap:` line, and let pi-kit live activity widgets omit the `· <activity>` suffix when no fallback activity is configured.

## 0.4.2

### Patch Changes

- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- b28ef2d: Return a teammate's recorded terminal report in a pi-kit lifecycle event so the leader never needs to force a duplicate resend, and extend leader guidance against resend steers and task_list polling.
  
  Allow lifecycle renderers to explicitly preserve every expanded detail line for user-requested readbacks while retaining the default 50-line bound.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.

## 0.4.1

### Patch Changes

- Republish the shared lifecycle helpers, including `eventToolLifecycle` and `renderToolLifecycle`, in the package artifact.

## 0.4.0

### Minor Changes

- dcf3806: Converge lifecycle titles on the spec API and delete `formatToolEventLabel`: semantic verbs (`listed`, `created`, `gathered`, `to @name`) now ride `ToolLifecycleSpec.label` instead of an ever-growing kind union, so `formatToolLifecycleTitle` with the `startedToolLifecycle`/`eventToolLifecycle` builders is the only title path. Expand behavior keys off data inside `renderToolLifecycle`: any collapsed row carrying detail lines appends the configured hint and expands to reveal them. Monitor, utils/sessions/worktree-session, and pi-git-agent session_context migrate onto it.
- a7fbc11: Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.

### Patch Changes

- fde16ae: Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
- dcf3806: Preserve the configured expand hint for lifecycle tool rows when a result has structured details but an empty visible content body, such as teammate_spawn's `{ started: true }` result. The title truncates before the hint so `ctrl+o to expand` remains visible within the available TUI width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.

## 0.3.0

### Minor Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.

## 0.2.0

### Minor Changes

- 50c45ff: Share compact tool lifecycle labels through pi-kit and standardize monitor startup and terminal event rendering.
- 7ad11b4: Render `list_directory_sessions` with the shared compact tool display pattern: self-rendered shell, empty call slot, and one `[sessions] listed · N other sessions in <dir>` result row styled like monitor terminal events (custom-message label color on the custom-message background). Expanding reveals a bounded block per session with status, pid, relative age, goal, recap, and recent files; every display field is sanitized with the new shared `safeDisplayText` and truncated to bounded lengths.
  
  Registry reads now normalize untrusted records on read (numeric pid/timestamps, known status union), merge records from multiple writers (extension state and keyboard glow state use different id conventions) into one logical session per owning process, and exclude records owned by the current process regardless of id, so counts and listings are no longer doubled.

## 0.1.1

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.

# @fradser/pi-agent-teams

## 0.10.0

### Minor Changes

- 746bc7e: Bind worker communication and submissions to the Assignment Attempt that started the turn, so an old turn can never send or submit as replacement Work, hold the cancellation tool while a superseded lease must be acknowledged, and stop re-sending acknowledged cancellations. Failed, interrupted, or crash-released Work now returns as `pending/recovery-required` and is excluded from autonomous claim notices until the Leader explicitly assigns the next attempt. Nonterminal worker reports from a retired attempt stay in session history but no longer act as current leader instructions, while accepted terminal results and harness diagnostics keep their delivery contract. Leader and Worker guidance gained the two sentences that state the new contract; the governed prompt-budget ceilings for those sections were raised accordingly (5,250 and 2,150 with a 16,100 total).

### Patch Changes

- 67d7d19: Declare `type: "object"` on the union-root coordination tool schemas (`agent`, `work`, worker `work`). Google's GenerateContent API rejects a tool whose `parameters` carries `properties` without an object type (`parameters.properties: only allowed for OBJECT type`), so every Gemini-routed request that included those tools failed with a 400; OpenAI and Anthropic routes tolerated the omission.

## 0.9.2

### Patch Changes

- 906b5bc: Accept coordination tool parameters that arrive as JSON strings. A harness that JSON-parses each tool parameter by name reads the root schema's `properties`, but the `agent`, `work`, and worker `work` tools describe their per-action contracts as a root union, which exposes only `anyOf`, so `definition`, `target`, `dependsOn`, `resources`, and `supersedes` reached validation as unparsed strings and every branch rejected the call before its handler ran. Each root schema now mirrors the parameters of its branches as optional string-tolerant properties while every branch keeps its strict per-action contract, handlers parse those parameters back into objects and arrays before branching on them, and a structured parameter that cannot be parsed is rejected explicitly instead of being used as a literal.

## 0.9.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.9.0

### Minor Changes

- f177948: Keep the compact agent and agent_event interface while making new delegations independent Work Sessions. Add optional fork (fresh context by default), exact work and message routing for concurrent assignments, and runtime-owned final-answer reporting after execution settles. Completion evidence and finish announcements now belong to each assignment attempt rather than an entire resident process.
- 28c908c: Introduce persistent Agent delegation (`agent`) and symmetric shared communication (`agent_event`), transitioning from ephemeral teammates to cross-project persistent Agents.

### Patch Changes

- e614d0d: Close the leader coordination loop after Agent starts, steers, and deliberate presence inspections. Tool results and guidance now state that kickoffs are already delivered, routing acknowledgment does not require confirmation, presence is not a completion signal, and leaders should continue independent work or end the turn for automatic result delivery instead of echoing, polling, or requesting reports.
- b0231e3: Render coordination message previews against the actual terminal width rather than a fixed character limit, reserving the complete configured expansion hint. Expanded message rows wrap the full message inline after the recipient and outcome exactly once instead of repeating a clipped preview above a duplicate body. Preserve semantic line breaks, native theme bands, and safe display text, including visible labels inside terminal OSC-8 hyperlinks. Keep literal JSON empty strings, punctuation spacing, and quoted newlines intact by separating handle replacement from prose cleanup. Reuse the same pi-kit lifecycle abstraction as context research; native Ctrl+O, mouse expansion, and terminal resizing are covered by isolated Pi integration tests.
- b0231e3: Deliver explicit and automatic Work outcomes through the same attempt-bound acceptance path after execution settles. Prevent false finalization reminders, duplicate automatic submissions, stale-attempt acceptance, and implicit Work creation from ordinary messages. Expose bounded result evidence in Work lists and clarify push-based result delivery.
- b0231e3: Await native unassigned-resident readiness in the public start result so immediate exact-session Work assignment succeeds without polling. Surface startup failures and preserve the existing assignment when the same exact owner is assigned its still-claimed Work again. Later autonomous board acquisition remains enabled.
- b0231e3: Expose effective session tool grants and coordination-only warnings in lifecycle results, clarify canonical minimal capabilities and unknown-Agent recovery, and require explicit failed submissions for blocked work. Clarify ungated acceptance and actionable leader communication without expanding permissions or inferring outcomes from prose.
- d3180eb: Harden agent lifecycle coordination, durable intent handling, and transcript presentation:
  - Publish board intents atomically through a fully written temp file that is hard-linked into place, so a consumer can never observe or destroy a partial claim or submission record
  - Retry an unparseable intent while it is younger than the publish grace instead of deleting it, so an in-flight intent cannot strand its author
  - Archive and diagnose an unreadable persisted Work snapshot instead of silently continuing with an empty board
  - Rotate a fully consumed oversized inbox instead of truncating it, so a concurrently appended peer message is never lost
  - Abort an in-flight gate reviewer when a holding's authority is invalidated by release, stop, supersession, a new claim, or resumed owner execution
  - Reject a late passing gate while teammate shutdown is pending
  - Reject completed submissions during an unexpected-execution review park
  - Report the residual write window when Work is released while its holder is still working
  - Reconstruct the full brief — subject, description, criteria, and diagnostics — for an authorized verification revision
  - Route steer and delivery feedback to an active teammate when the leader releases its Work
  - Keep expanded agent delegate, inspect, and stop rows free of duplicated prompts, stale states, and retired activity
  - Drop the expanded inspect row's state word, which repeated the row's own header and could contradict it
  - State the coordination-only warning on delegate and start rows, matching the documented grant disclosure
  - Write each snapshot artifact only when it changed, and throttle the forensic whole-state file while a teammate streams, instead of rewriting every artifact twice a second
  - Bound the mailbox by total bytes as well as by message count, so long reports cannot grow the debug snapshot without limit
  - Bound confirmed-stop and finish bookkeeping per session instead of accumulating one entry per incarnation
  - Stop claiming the completion gate is read-only: its grant excludes edit and write, but a shell can still write
  - Carry a single-line Work subject with the complete brief retained as the Work description
- 43b51c5: Remove leader heartbeat and stall notices. Silence, spawn age, and usage stay as passive console telemetry in `/agent-teams` (roster "stalled" marker at `PI_TEAMMATE_STALL_SILENCE_MS`, default 5 minutes); the leader context is never interrupted by health prompts, and provider hangs surface only through the standard terminal close-path diagnostic. See `docs/adr/0002-no-leader-heartbeat-notices.md`.
- b0231e3: Start unassigned residents without a fabricated Work ID or an empty-assignment model turn. Establish idle readiness through a native RPC acknowledgement while preserving subsequent autonomous board claims. Clarify recovery by releasing and reassigning the same Work instead of delegating competing duplicate Work.
- 34c5b62: Start every new Assignment Attempt in a fresh correlated Pi RPC session before delivering its prompt, while preserving working memory for guidance within the same attempt and releasing work when the reset cannot be completed.
- ac83f4e: Prevent pre-cancelled child workers from spawning, fail closed on bounded worker stream violations, and disable extension discovery for isolated side-question and research children.
- 9cabb0d: Bump every package by one patch version.
- b0231e3: Clarify agent orchestration with scoped dependency-aware assignments, one integration verification owner, candidate-bound review evidence, and a finish line that waits for blocking review results. Distinguish review Work completion from an implementation PASS, describe `verify` accurately as a reviewer prompt, and refresh candidate briefs explicitly before bounded rechecks. Review-only assignments finish with their reports rather than implementation repairs; reuse completed Work only with an authoritative current-attempt brief, otherwise create a linked bounded follow-up. Make Matt Pocock reviews proportional and support confirmed conversation requirements plus scoped uncommitted baselines without changing runtime lifecycle or persisted state.
- d3efa47: Teach leaders to continue independent work or yield the turn while teammates run, relying on automatic result delivery instead of extending the turn with polling or wait commands.
- c5d658f: Render `agent`, `work`, and `agent_event` transcript rows for people instead of
  models. A started Agent now shows its name, role, the full kickoff text, granted
  tools, and model; inspect shows the live status and current activity; Work and
  message rows lead with the Work subject and show the message that was sent.
  Session, Work, and assignment handles stay in model-facing tool content and are
  scrubbed from every rendered line (a Work id becomes its subject, a session route
  becomes `@name`), while text a person wrote themselves is preserved verbatim.
- 6d21149: Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.
- 919504f: Fix agent presence and work control to use current-session state instead of reporting a fabricated idle result. Deliver leader direction through native priority steering that also starts idle execution, and isolate completion reports by assignment so an earlier PASS cannot close reopened work. Align first-delegation guidance, terminal-report rejection, and transport outcome wording with these contracts.
- 919504f: Wrap custom transcript lifecycle messages in host ToolExecutionComponent so mouse click toggling works symmetrically with tool result rows.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- bc42356: Keep requested Agent names unchanged when starting or delegating, without appending a UUID. Preserve incarnation-bound session handles.
- 2033c26: Remove unreachable legacy Agent control, unused internal helpers and constants,
  and the unused keyboard HID encoder (hardware commands already use via-rgb).
  Retain active entry points, shared public APIs, configuration compatibility,
  and behavioral regression coverage. Remove superseded planning documents and
  checks that only assert documentation wording or recreate implementation in tests.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.
- c5d658f: Run the verification-gate reviewer as a bare Pi child. `buildVerifyReviewWorkerOptions` now supplies the whole worker options with `minimal: true` and the read-only `VERIFY_REVIEW_TOOLS` grant (read, bash, grep, find, ls), so a gate review no longer loads the project's extensions, skills, prompt templates, context files, or themes, cannot trigger another package's automatic memory learning, and leaves no session record behind.
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

## 0.8.3

### Patch Changes

- c568d73: Apply customMessageLabel color only to the [agent] prefix in teammate spawn rows

## 0.8.2

### Patch Changes

- 91dfc9a: Optimize worker guidance and kickoff prompt so teammates with assigned tasks execute them directly without redundant task board queries.
- 731f1cd: Clarify agent and sub-agent conceptual equivalence in teammate_spawn tool descriptions and prompt guidance so third-party skills and workflows routing to agents hit teammate_spawn seamlessly.
- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- 92944c1: Apply progressive tool disclosure across runtime packages. State-dependent capabilities are now hidden until their workflow state is active, and continual-learning no longer couples its guardrails to Matt Pocock workflow state.
- b28ef2d: Return a teammate's recorded terminal report in a pi-kit lifecycle event so the leader never needs to force a duplicate resend, and extend leader guidance against resend steers and task_list polling.
  
  Allow lifecycle renderers to explicitly preserve every expanded detail line for user-requested readbacks while retaining the default 50-line bound.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.8.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.8.0

### Minor Changes

- dcf3806: Deliver every teammate report to the leader: intermediate send_message(to="leader") reports now reach the leader as their own follow-up turn instead of parking in the console-only mailbox, and queued reports are never coalesced — one message, one leader turn, in arrival order, with an authored-at timestamp in the envelope. Leader-relevant harness events ride the same channel: clean-shutdown summaries, worktree diff notices (bounded preview plus branch retrieval command), and verify-gate escalations; task outcome notices and operational diagnostics stay console-log only to avoid double reporting. Worktree cleanup now commits remaining work onto the kept branch before removing the directory — previously the branch deletion destroyed uncommitted captured work — while failed-spawn teardown still deletes the empty branch. Worker guidance rations messages by value instead of throttling: every leader-bound message costs a full turn, bare status pings are forbidden.
- 953f548: Two-tier stall watchdog: a working teammate silent since spawn with zero lifetime model output and no running tool — the provider-hang signature — is flagged after five minutes (`PI_TEAMMATE_SILENT_STALL_MS`, 0 disables) instead of the general thirty-minute window. Stall notices carry silence duration, spawn age, and lifetime token/cost diagnostics, and the zero-output notice names shutdown plus respawn as the effective remedy since steering cannot unstick an in-flight request. Streaming usage is now persisted to the roster, making zero-token hangs visible before shutdown.
- 9a80d93: Fixes from the first live analysis of the stall watchdog and tool-grant work, plus the delivery-gap root cause it surfaced: a spawned teammate runs its kickoff turn immediately, so marking prompt-less spawns idle at birth mislabeled an actively-running turn as idle — queued leader messages were then delivered into that running turn and lost (the teammate kept reporting "board empty" until a steer landed). Status now stays "starting" until real stream events arrive and flows starting→working→idle from stream truth. The provider-hang classifier now keys on recognized stream activity (text/thinking/toolcall/tool events) instead of usage totals — providers that omit usage after real output are no longer misclassified, and an empty message_end artifact never counts; usage stays diagnostics. The grant is flushed to both rosters before the kickoff is written, and historical spawn renders read persisted details only so name reuse cannot display another incarnation's allowlist.
- ab0feb8: Spawn surfaces now expose each teammate's effective tool allowlist: `teammate_spawn` records the granted tools in the roster before the first wake, the spawn result line and console detail name them, and a role derived inline without a `tools` field visibly shows its narrow capability-only grant. Leader guidance now requires matching definition tools to the assignment — file-inspecting work needs explicit `read`/`bash` — and prescribes shutdown-plus-respawn instead of steering when capabilities are missing. This prevents workers from burning turns discovering they cannot execute their kickoff.
- a7fbc11: Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.

### Patch Changes

- dcf3806: Dispatch the first teammate report to Pi's native follow-up queue even while the leader is active, rather than holding it in Agent Teams until the complete leader run settles. Later reports remain FIFO-serialized until the dispatched report settles.
- dcf3806: Keep requested teammate shutdowns in the tool lifecycle and console instead of emitting misleading agent-message follow-ups, and use an explicit harness-event envelope for lifecycle diagnostics that do wake the leader.
- fde16ae: The leader's send_message no longer rejects a stray `status` field with "status is reserved for worker reports to=leader". The shared message schema exposes `status` to leaders too, and leader models occasionally copy it from worker report patterns — which hard-failed the call and blocked teammate delivery (observed live in hud-playground). A stray status on a leader-sent message is now ignored with a one-line corrective note appended to the tool result, and the leader tool description no longer mentions `status` at all. Worker-side semantics are unchanged: status is still honored only for reports addressed to "leader".
- fde16ae: Clarify message routing truth: active control-stream writes render as `steered`, inbox/outbox and wake-up paths render as `queued`, and neither outcome implies recipient processing. Stall diagnostics now render independently as teammate health events instead of message suffixes.
- fde16ae: Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
- dcf3806: Reject non-finite teammate report timestamps and keep malformed metadata from interrupting follow-up delivery.
- dcf3806: End the current worker turn after a terminal leader report, and suppress subsequent reports until a new wake-up while preserving distinct intermediate reports and assignment boundaries.
- fde16ae: Clarify task creation handoff: `task_create` now reports that it never spawns teammates, identifies the current session board, immediately offers newly-created work to existing idle teammates, and explains how pending work proceeds when no teammate is available.
- dcf3806: Preserve the configured expand hint for lifecycle tool rows when a result has structured details but an empty visible content body, such as teammate_spawn's `{ started: true }` result. The title truncates before the hint so `ctrl+o to expand` remains visible within the available TUI width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.7.0

### Minor Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · steered|queued` row carries only the synchronous routing outcome, replacing the duplicated call-plus-sentence transcript rows. Teammate stall health renders independently as an `[agent] event` rather than decorating a message row. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.

### Patch Changes

- 82b8e8b: Honor multi-line YAML tool lists in agent frontmatter and make unfinalized teammate reports self-finalize before escalating. `parseFrontmatter` now parses dash-list `tools:` blocks — flush-left or indented items, interleaved blank/comment lines, no-space `-item` entries — which previously collapsed silently into an empty execution allowlist. When a teammate's sequence ends while its last leader-bound report lacks terminal status, the machine drains outboxes before deciding, sends one inbox finalize request per spawn incarnation instructing `status="completed"`/`status="failed"`, escalates to the leader reminder only on a second miss, cleans up nudge bookkeeping on every shutdown path, and the worker-side `send_message` result reminds when a leader-bound message carries no terminal status.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.6.0

### Minor Changes

- 7ad11b4: Rebuild Agent Teams as a Claude-Code-style collaborative organization layer: named resident teammates (long-lived RPC child processes), a shared task board with atomic self-claim and verify-gated completion, and direct peer-to-peer inbox messaging. The former DAG API (`teammate_run`, `teammate_fanout`, `teammate_cancel`, `teammate_retry`) remains removed. Simplify the new team surface to seven unique tool names: `send_message(to, message, status?)` is the one messaging primitive for worker reports, peer mail, and leader steering; `task_list` is shared by both sides; and `teammate_spawn` now accepts only name, agent, and optional prompt, with model/worktree moved to declarative agent frontmatter.
  Agent definitions gain a fourth scope for custom teammates: inside `.pi/agents/`, a `<name>.local.md` file declares a personal project-local override that stays out of version control, while `<name>.md` remains the git-managed team-shared layer; same-name pairs deduplicate into one definition with local winning. Precedence is project-local > project > user > bundled, and `resolveAgent` exposes each definition's scope and gitManaged flag so guidance and tooling can show provenance.
- 7ad11b4: Add an output-silence heartbeat for resident teammates. A teammate wedged mid-turn (for example, blocked forever in a provider request) never accumulates assistant turns and produces no RPC output, so nothing could alert anyone while the roster showed "working" indefinitely. The harness poll now tracks `lastOutputAt`: after 30 minutes without any output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) the leader receives one actionable notice per silence episode naming the teammate and its recovery options. The notice is the last automatic action — continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any stream activity or prompt delivery re-arms the watchdog. The health notice states that steer delivery may be uncertain without changing the message-routing result, and the widget, console roster, and detail views show how long a working teammate has been silent.
- acbadc7: Adopt full teammate autonomy as the package constitution: the harness detects and notifies, the leader model decides — no configuration may automatically terminate a working teammate. Remove the per-wake-up turn budget (the former 100-assistant-turn ceiling that silently killed long sequences) and do not ship any duration-based auto-reclaim. Turn counts and silence durations remain visible as telemetry and heartbeat signals; the stall notice is informational and names the recovery options (keep waiting, steer again, shut down, or respawn a successor whose prompt composes context from the original kickoff, mailbox reports, board claims, and the console detail transcript). Leader guidance gains a "recover, never punish" section teaching this workflow.

### Patch Changes

- 1503fdb: Use `teammate_message` for teammate completion and run notifications instead of the legacy `teammate-update` custom message type.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.5.2

### Patch Changes

- a1b37a0: Remove the `Console: /teammate` navigation hint from the `[teammate-update]` run summary follow-up message. The console affordance stays in the live widget, but the completion message no longer prompts the user to open the console.
- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.5.1

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.5.0

### Minor Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.4.0

### Minor Changes

- f3b5cd7: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - `teammate_run` dispatches a dependency-aware task graph in one call. Tasks support `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`; root nodes start immediately, downstream nodes auto-start when dependencies complete, and overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - The leader surface is `teammate_run`, `teammate_fanout`, `teammate_message` (for steering a running RPC worker), `teammate_cancel`, and `teammate_retry`.
  - The worker capability is `teammate_message` (progress, blockers, and final deliverables to the leader). There is no peer delivery, worker inbox, leader broadcast, or separate worker report capability.
  - Removed: `teammate_wait` (replaced by automatic completion follow-ups and inline gather), `teammate_cleanup`, `teammate_inbox`, and the legacy registry tools (`teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, `teammate_cancel_task`).
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Messages are validated through per-worker append-only outboxes and collected in one leader inbox; DAG handoffs inject upstream results into downstream prompts (`=== UPSTREAM HANDOFF ===`).
  - Advisory write-conflict coordination spans all runs in the session: overlapping shared-workspace write nodes are deferred unless worktree-isolated. `paths` and `access` are scheduling and prompt metadata, not filesystem permissions; there is no OS or container sandbox and no true read/write enforcement.
  - Full-screen `/teammate` console with live activity stream and mouse-wheel scrolling.
  - Worker protocol keeps per-spawn identity validation, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.

## 0.3.0

### Minor Changes

- e16cd3f: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - `teammate_run` dispatches a dependency-aware task graph in one call with `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`. Root nodes start immediately; downstream nodes auto-start after dependencies complete; overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - Automatic completion follow-ups for background runs, bounded inline gather, `teammate_fanout`, `teammate_cancel`, `teammate_retry`, and leader-side RPC steering through `teammate_message` provide the run lifecycle surface.
  - Removed: `teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, and `teammate_cancel_task`.
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Read-receipt protocol removed: messages have no read flags or receipt events.
  - Workers use the worker-only `teammate_message` capability for progress and final deliverables. Messages have one destination: the leader's inbox; there are no peer mailboxes, worker inboxes, leader broadcasts, or separate report capability. DAG prompt handoffs provide upstream results to dependent workers.
  - `paths` and `access` coordinate scheduling and prompt context only. Shared-workspace protection is advisory write/write coordination; it is not true read/write enforcement and does not provide an OS or container sandbox.
  - Worker protocol keeps per-spawn identity validation, one leader inbox, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.

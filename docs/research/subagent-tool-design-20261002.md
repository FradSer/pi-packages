# Subagent tool refactor: research and adversarial analysis

Date: 2026-10-02.
Status: accepted for implementation. The user approves the five-tool candidate on 2026-10-02.
The execution contract now lives in @packages/subagents/VISION.md; research evidence below remains scoped to its original checks.

## Scope and authority

The user requests broad research and adversarial analysis of the `agent` interface.
This report proposes a model-facing interface, migration steps, and acceptance checks.
It does not authorize publishing, credential changes, saved identity changes, or data migration.

Read @packages/subagents/VISION.md before implementation. It remains the execution contract.
Read @packages/subagents/AUTHORITY.md before changing grants, identity creation, or process controls.
The current contract still specifies one flat tool with six actions.
An adopted new model surface requires an explicit contract update; this report does not make that update.

## Method and evidence limits

Fifteen search queries cover schemas, tool selection, lifecycle, cancellation, security, caching, and evaluation.
The configured search provider is Gemini. Its generated summaries are discovery aids, not verified requirements.
Seventeen primary pages are fetched. Version-matched Codex source and previously fetched Claude documentation are also checked.
The recommendations below use exact primary passages, local source, and the existing execution contract.

The prior native probe uses Codex CLI 0.159.3 and Claude Code 2.1.287.
Codex returns two expected fixture markers. Its JSON trace directly records two completed wait calls.
Its other lifecycle calls are model-reported; the trace does not directly establish them.
Claude returns HTTP 401 before spawning a child. Its lifecycle behavior is not verified by that probe.

Read `/tmp/pi-native-agent-probe.fdrjYZ/REPORT.md` for the probe and its limits.

The adversarial analysis is a generator, critic, and revision exercise in this session.
It is not GAN training or an independent multi-agent review.
No comparative model benchmark is run for the proposed interface.
A further reflection pass replaces the preferred six-tool candidate with an explicit-intent five-tool proposal.
That revision requires accepted sequencing changes and is not an immediately implementable alias layer.

## Important corrections to earlier advice

1. More tools do not necessarily improve tool selection.
2. Shorter descriptions do not necessarily improve tool use.
3. A narrow schema does not prove permission, session existence, or current process state.
4. Cancellation of a caller's wait is not cancellation of accepted child work.
5. A stopped process and an idle conversation are different states.

Anthropic explicitly recommends consolidating related actions and detailed descriptions [S03].
OpenAI recommends clear functions, fewer initial functions, and combining operations that always occur together [S01].
Neither source establishes six separate tools as a universal best practice.
Codex provides a concrete split interface, not evidence that every package should copy it [S05].

## Competing designs

| Candidate | Benefit | Main risk | Decision |
| --- | --- | --- | --- |
| A: one `agent` with six actions | Small discovery surface; preserves the public contract | Unrelated fields share one schema; read and mutation hints remain mixed | Keep as the compatibility baseline |
| B: six narrow tools | Operation-specific fields and hints | The model still selects a state-dependent input operation | Retain as the low-risk implementation alternative |
| C: start, message, inspect, list, stop | Simple continuation | Automatic wake or steer can change input intent at a race boundary | Reject implicit state routing |
| D: narrow tools plus idle-open and turn-abort | Full lifecycle exposure | Adds operations without a demonstrated model need | Defer additional controls |
| E: start, input, stop, inspect, list | One input shape with explicit next or steer intent | Busy next-input delivery needs a new sequencing contract | Recommend for contract design, not immediate implementation |

Candidate E supersedes B as the preferred interface proposal after the user's reflection request.
It does not supersede the existing execution contract.
B remains the simpler choice if queued continuation is outside the accepted scope.
No comparative benchmark establishes either candidate as the best-performing interface.

## Further reflection: intent before transport

The earlier proposal maps internal branches to public tools too directly.
It reduces invalid parameter combinations but leaves the model responsible for asynchronous state decisions.
It also retains name as both an instance label and a saved identity selector.
Those are interface ambiguities, not only documentation problems.

Six public names repeat shared input rules and can increase prompt cost.
A permanent legacy-versus-narrow product setting would add maintenance cost.
Compatibility should have a supported transition path, not determine the target interface forever.

Combine operations only when they share an argument shape and retain explicit intent.
Next-input delivery and steering can share one tool; startup and continuation should not.
Do not let runtime state silently convert a next input into a steer.

## Adversarial analysis

### Round one: challenge a direct six-tool copy

| Initial proposal | Counterargument | Revision |
| --- | --- | --- |
| Split every action because Codex does | Anthropic advises consolidation; selection cost can increase | Split this bounded operation family, then compare it with the baseline |
| Make all descriptions short | Claude guidance requests details and at least three or four sentences | Keep a short namespace summary; retain operation rules and useful examples |
| Require each operation's parameters | Start permits either an anonymous prompt or a named idle child | Make prompted startup the proposed new model entry; preserve idle startup elsewhere |
| Merge send and steer without an intent field | A busy child can receive a different effect than an idle child | Preserve explicit intent, through separate tools or a delivery enum |
| Replace old names immediately | Existing transcripts, scripts, grants, and consumers use `agent` | Keep a legacy profile and the exported library API |

### Round two: attack the revised design

| Attack | Required response |
| --- | --- |
| A schema-valid handle names a retired incarnation | Resolve the exact incarnation at execution; never retarget by name |
| The child settles before its input acknowledgement returns | Report observed state; do not infer working from an accepted receipt |
| A cancelled startup later receives a positive acknowledgement | Retain the original reservation, control owner, and result owner |
| A stop wait ends before process closure is confirmed | Retain stop intent and control authority; do not report closure |
| A legacy name exclusion is bypassed by new tool names | Migrate the family policy explicitly; do not infer permission from registration |
| Both tool families appear through codemode | Keep the inactive direct family uncallable; hiding a declaration alone is insufficient |
| A provider rejects schema conditionals or optional fields | Use its supported schema subset; keep domain validation independent |
| A child result requests more authority | Treat child text as execution evidence, not user authorization |
| A finished agent is reused for unrelated work | Reuse for dependent follow-ups; create a separate child for independent context |
| A shorter receipt hides a role override or missing tools | Keep effective configuration and important override notices visible |
| An accepted operation exceeds a receipt budget | Treat it as a readback failure, not rejection or permission to repeat |
| Two children have different states | Validate each target; one child's state cannot define the global tool set |

The second round rejects a lifecycle rewrite disguised as tool renaming.
The existing reservation, acknowledgement, result delivery, and confirmed closure rules stay intact.

## Recommended interface candidate

Use the `subagents` namespace for discovery and shared instructions.
Use stable `agent_` names for hosts that present a flat tool list.
Pi already supports namespaces and tool exposure; do not add another registry [S15].

| Tool | Required input | Optional input | Effect |
| --- | --- | --- | --- |
| `agent_start` | `prompt` | `identity`, `label`, `instructions`, `tools`, `model`, `fork` | Start a child and confirm accepted kickoff input |
| `agent_input` | `session`, `prompt`, `delivery` | None | Deliver next input or steer, according to an explicit enum |
| `agent_stop` | `session` | None | Request process closure and confirm it before releasing control |
| `agent_inspect` | `session` | None | Read one retained incarnation's bounded facts |
| `agent_list` | None | `offset`, `limit` | Read a bounded page of sessions and offline definitions |

Delivery has two values: next and steer.
Require the enum in the canonical input schema; do not add an automatic state-based mode.
The everyday continuation uses next, whether the current child is idle or still executing.
Steer explicitly asks to influence the active sequence without aborting or replacing it.

No new tool accepts `action`, `authorized`, `persistent`, `memory`, or `worktree`.
All tools reject unknown fields before effects.
The existing tool grants and context policy remain unchanged.
Temporary children start without parent history unless fork is requested.
Disk identities can resume private project history; no-fork does not mean erasing that history.

### Separate identity, label, and control address

Identity selects an existing valid disk agent.md and its standing instructions, data, and grant ceiling.
An unknown explicit identity is refused; it never falls back to a temporary role.
A label identifies the run for display. It never selects or creates a disk identity.
The exact returned session is the only control address.

Instructions supplies standing guidance for a temporary role; prompt supplies the current work.
When identity is supplied, refuse conflicting instructions instead of silently dropping them.
Keep the saved-definition scope precedence for resolving identity.
Keep label separate from the private-data key and the role registry.
Do not infer support for concurrent runs of one identity from this separation; ownership policy remains unresolved.
The legacy name behavior stays unchanged in its compatibility adapter.

### Startup scope

The current start accepts an anonymous prompt or a named idle startup.
The proposed model entry requires a prompt and targets the normal delegation workflow.
Keep named idle startup in the existing library and compatibility path.
If idle creation is required in the new model surface, specify it separately before implementation.
No agent_open tool is added merely to preserve a tool-count preference.

### Input sequencing is a new contract

Current send refuses a busy child. Candidate E changes that behavior for delivery next.
This is not a rename or a wrapper over the current send operation.

For next, reserve one bounded input record on the exact incarnation and return a receipt.
If idle, start its sequence. If working, start it only after the current sequence settles.
Never reset the active sequence baseline merely because next input is queued.
Reserve an internal input ID before dispatch; use it for result provenance and delivery deduplication.
The model does not generate that ID and the ID is not a retry or acceptance token.

For steer, require an active sequence and retain its existing input ID.
An idle or stopping target is refused; a steer never becomes a new next input automatically.
Starting is not sufficient proof of active work when no input has been accepted.

Authorization and host policy apply to each input reservation; queued work cannot bypass assignment or verification guards.

Stop prevents new inputs and cancels records that have not started, with explicit terminal notices.
A parent shutdown closes the process and retains the existing delivery and durable-data rules.
Never acknowledge a queue record that the runtime cannot retain or terminate honestly.

Define queue capacity, input reservation ownership, late acknowledgement behavior, and stop handling before implementing Candidate E.
Capacity limits records and bytes; overflow is a clear refusal, not silent dropping or replacement.
Do not introduce a model-controlled queue policy, latest-wins option, or retry key without a known requirement.
Do not add general scheduling, task acceptance, or peer communication to implement this bounded input queue.
If this new contract is not accepted, use Candidate B and retain busy-input refusal.

## Schema and description practices

Use a closed root object and explicit required fields for each operation.
Use enums instead of incompatible boolean switches.
Keep handles, tokens, credentials, and runtime ownership out of model-inferred metadata.
The model supplies a returned session handle; the runtime owns its meaning and provenance.

OpenAI strict mode requires every property to be required and represents optional values with null [S01, S02].
OpenAI's schema subset also rejects root anyOf and several conditional keywords [S02].
General JSON Schema conditionals are valid standards features, but not a portable provider guarantee [S14].
Do not assume that Anthropic uses exactly the same optional-field rules [S12].
Verify the Pi provider adapter before adding strict-mode fields or null conversion.

If a provider adapter uses null for an omitted option, preserve the distinction between null and an explicit empty tools array.
Perform that documented conversion at the adapter boundary, not inside the legacy domain validator.
Preserve authored prompt and role bytes.
Retain runtime checks for grants, existence, state, and owner binding after schema validation.

Each description states purpose, permitted state, side effect, and result timing.
Give next and steer contrasting examples because they use the same input tool.
Give startup examples for a temporary child and an existing disk identity.
Put shared authorization and result-delivery rules in namespace instructions or shared guidelines.
Do not remove safety-critical information merely to meet a token target.

## Receipts and result delivery

Preserve the existing result contract for legacy callers.
Candidate B can keep that output schema while changing registrations.
Candidate E needs a separate versioned receipt for queued input; do not reinterpret legacy fields silently.
Output alias removal is a separate compatibility change.
The input description and receipt must state that steering does not abort a turn.

Separate control disposition from observed process state.
A receipt can report accepted while the same sequence has already settled and the child is idle.
Next-input receipts distinguish started, queued, rejected, and uncertain outcomes without claiming work completion.
Correlate later results with the reserved input ID; steering retains the sequence's original ID.

Normal receipt text contains only the facts needed for the next step:

- Whether native input or readiness is confirmed.
- The exact session handle.
- The effective role, model, and tool grant, with material override notices.
- How the complete result arrives.

Keep observed state and machine control facts in structuredContent.
Errors also expose dispatch certainty, pending intent, and the safe next action in model-visible text.
Use returned typed failures with isError rather than losing the data in an opaque exception [S07, S15].
Keep errors sanitized and bounded.

An accepted receipt is not a child answer or an acceptance verdict.
Keep one complete delivery for each settled input sequence.
An inspect preview can be shortened; the delivered final answer cannot be silently shortened.
Do not let a final answer's text establish authorization or process provenance.
Do not add a wait tool where automatic follow-up already meets the execution contract.

Request cancellation and child shutdown remain separate operations.
MCP's request cancellation rules are useful race guidance, not the same ownership policy as Pi [S09].
MCP Tasks demonstrate separate receipts and outcomes; their polling and durable handles are not requirements for this package [S10].

## Discovery, permissions, and caching

Keep one model-facing profile per active conversation branch:

- Legacy: `agent`, with the existing six-action contract.
- Intent-based: the five proposed tools, without model-facing `agent`.

The existing exported library API remains available in either profile.
Old codemode scripts calling tools.agent require the legacy profile.
Do not promise full script compatibility while making that tool inactive.

Preserve the profile recorded in established history.
Use the intent-based profile only in an explicitly selected fresh session during evaluation.
Treat compatibility profiles as a migration mechanism; do not promise permanent dual product modes.
Define a support window and a removal condition before retiring the legacy tool.
Do not replace tool names on reload or model switch merely to apply the new default.
Keep provider-compatible activation and stable tool order [S11, S13, S15].

`subagents_enable` selects the chosen family; it never authorizes delegation or starts a child.
Do not activate unknown, excluded, or unavailable family members.

Do not dynamically hide stop based on a guessed idle roster: pending startup can still need closure.
Different children can have different states; do not use one child's state to toggle the family's operations.

Give inspect and list read-only hints.
Give start, input, and stop conservative mutation hints.
Hints describe effects; the host permission policy remains authoritative.
Audit exact-name permission rules and saved grants before changing tool names.
Do not rewrite saved agent definitions or append new capabilities to bypass their ceilings.

## Proposed implementation sequence

1. Accept the identity-label separation, startup scope, and queued-input contract before updating the authoritative documents.
2. Write Given/When/Then contracts, add regression tests, and observe RED before changing the implementation.
3. Extract common lifecycle execution from the model-facing registration layer without changing legacy behavior.
4. Implement bounded per-incarnation input records and versioned receipts; test their callback and stop order.
5. Register the proposed tools and add profile-aware activation, guidance, and passive renderers.
6. Migrate consumers and evaluate the opt-in interface before changing defaults.

Keep each increment working and verified.
Use one lifecycle implementation, not copied control paths for each tool.
The queued-input layer requires explicit sequencing; a registration-only adapter cannot supply it.
Use the simpler six-tool candidate if queue changes are outside the accepted scope.
Output alias removal, turn-abort support, and alternate workspace isolation are separate changes.

The migration inventory includes:

- subagents extension registration, activation, schemas, and packaged guidance.
- agent-teams guidance, host controls, worker grants, and renderers.
- root registration, installation, prompt-budget, and structured-output checks.
- monitoring and recap code that classifies tool names.
- user-facing README files, examples, saved selection records, and release notes.

## Acceptance scenarios and evaluation

1. Given an idle or busy child, deliver next input; it runs once after the current sequence and retains its exact incarnation.
2. Given active work, deliver steer input; the current sequence and its input ID continue without abort or replacement.
3. Given dispatched input, cancel the caller's wait; late acknowledgement retains the original owner and reserved input ID.
4. Given a replacement or a stop, refuse old controls and emit explicit outcomes for accepted inputs that never start.
5. Given an explicit identity or a legacy branch, resolve only that declared identity and restore only the recorded tool family.

Run table-driven schema checks for valid, missing-field, and unrelated-field inputs.
Exercise native parsing and real acknowledgement order, not only mocked function calls.
Preserve unanswered classification, complete UTF-8 output, and management-output budgets.
Keep the existing prompt-less library startup checks.

Compare profiles with the same tasks, authorization, models, tool grants, and prompt variants.
Do not force the target tool when measuring tool selection.
Measure first-call validity, operation choice, task outcome, corrective calls, tokens, and elapsed time [S04].
Also measure duplicate startups, needless status calls, and retries during uncertain dispatch.
Separate cold schema cost from repeated-turn cached cost.
Check raw call traces; a model's account of its calls is not ground truth.

Accept no known safety regression in the tested scenarios.
Promote the new default only if it reduces relevant errors without materially worse task outcomes.
No numerical accuracy improvement is claimed until those evaluations run.
A fresh independent review is required before shipping this public-interface and concurrency-sensitive change.
Use a new temporary reviewer without fork; reopening a durable identity can resume history and does not establish independence.

For each runtime increment, run the affected Python and Node suites, pnpm typecheck, and the package pack dry-run.
Also run pnpm check:install, isolated native Pi print/RPC checks, and interactive TUI checks under the package contract.
Report pre-existing workspace failures separately; do not weaken unrelated task expectations to make the refactor pass.

## Current verification and remaining work

Three pure validator checks run against the current source:

- Named idle startup is accepted.
- Anonymous prompted startup is accepted.
- Role-only startup is refused.

These checks establish the existing startup modes; they do not validate the proposed tools.
Reflection also checks the existing name resolver and confirms busy send refusal and per-sequence transport baselines.
No candidate queue, identity-label split, or receipt version is implemented or verified.
Report paths and references receive local content checks.
Runtime code, package manifests, saved definitions, and credentials are unchanged by this research task.
Implementation, comparative model evaluation, and fresh independent review remain outstanding.
Existing cross-parent history ownership and broader workspace verification blockers remain separate.

## Primary source ledger

### S01: OpenAI function calling

https://developers.openai.com/api/docs/guides/function-calling

Relevant guidance: clear functions, required nullable fields in strict mode, consolidation, and limited initial tool count.
Exact passages include “Combine functions that are always called in sequence” and “Evaluate your performance”.
The fewer-than-20 recommendation is explicitly a soft suggestion, not a correctness rule.

### S02: OpenAI Structured Outputs

https://developers.openai.com/api/docs/guides/structured-outputs

Exact heading: “Root objects must not be `anyOf` and must be an object”.
The unsupported composition list includes allOf, not, dependentRequired, dependentSchemas, if, then, and else.
These restrictions concern the provider's structured generation subset, not all local result-schema validation.

### S03: Anthropic tool definitions

https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools

Exact guidance: “Consolidate related operations into fewer tools.”
It recommends an action parameter and at least three or four description sentences.
This is the primary counterexample to treating more tools or shorter descriptions as universal improvements.

### S04: Anthropic tool engineering and evaluations

https://www.anthropic.com/engineering/writing-tools-for-agents

The article recommends runtime, call-count, token, and error metrics alongside task accuracy.
It instructs readers to inspect raw transcripts because evaluation agents can misreport behavior.
Naming effects vary by model and need evaluation.

### S05: Codex 0.159.3 tool specifications

https://raw.githubusercontent.com/openai/codex/rust-v0.159.3/codex-rs/core/src/tools/handlers/multi_agents_spec.rs

V2 separates spawn_agent, followup_task, send_message, wait_agent, interrupt_agent, and list_agents.
Spawn requires task_name and message. Follow-up and messaging require target and message.
Wait returns a summary, not final content. Interrupt ends a turn but keeps the agent available.
This source is version-matched; it does not prove an unrecorded runtime call occurred.

### S06: Claude Code subagents

https://code.claude.com/docs/en/sub-agents

SendMessage resumes completed subagents under their existing IDs.
A user-stopped subagent does not automatically resume; a send is refused until the user restores it.
Name reuse checks prevent silently messaging a replacement.
These statements are documentation evidence, not successful local Claude execution.

### S07: MCP tools, 2026-07-28

https://modelcontextprotocol.io/specification/2026-07-28/server/tools

Output schemas define structured results. Execution errors use isError and actionable feedback.
Input validation and access control remain server responsibilities.
The current revision permits any JSON value for structuredContent; Pi can retain its existing object contract.

### S08: MCP schema, 2026-07-28

https://modelcontextprotocol.io/specification/2026-07-28/schema

ToolAnnotations defines readOnlyHint, destructiveHint, idempotentHint, and openWorldHint.
Pi's installed extension documentation states that these hints are not verified [S15].

### S09: MCP cancellation, 2026-07-28

https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/cancellation

The protocol distinguishes transports and acknowledges late-cancellation races.
Its request cancellation is not a promise that previously accepted external work is rolled back.
Do not substitute it for Pi's parent-owned child lifetime contract.

### S10: MCP Tasks extension

https://modelcontextprotocol.io/extensions/tasks/overview

Tasks separate a creation receipt from a later result and provide optional status notifications.
Their durable handles and polling model differ from Pi's parent-local incarnation roster.
No MCP Tasks integration or cross-restart child support is proposed here.

### S11: OpenAI tool search

https://developers.openai.com/api/docs/guides/tools-tool-search

Use namespaces where possible. Deferred definitions load after discovery and preserve cached prefixes.
The guide recommends comparing completion, tokens, and latency before choosing the loading strategy.
Discovery adds a step; six tools do not automatically justify another discovery mechanism.

### S12: Anthropic strict tool use

https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use

Strict mode constrains tool input syntax and types.
The supported JSON Schema subset still applies; runtime authority is a separate concern.

### S13: Anthropic tool search

https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool

Deferred tool definitions reduce initial context and preserve the static cached prefix.
Use this only through supported provider and Pi capabilities.

### S14: JSON Schema conditionals

https://json-schema.org/understanding-json-schema/reference/conditionals

The standard can express conditional requirements.
Provider structured generation may support a smaller subset [S02].

### S15: Installed Pi extension contract

`/Users/FradSer/.local/share/fnm/node-versions/v24.16.0/installation/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md`

Pi already provides namespace, exposure, annotations, outputSchema, and structuredContent.
Inactive direct tools are not callable.
Declarations hidden by prepareLoadout can remain callable; exposure set to hidden makes a tool unreachable.
Tool changes are transcript state and can force a provider checkpoint.

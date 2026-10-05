/**
 * The `agent` tool: child process lifecycle, and nothing else.
 *
 * Temporary delegation is the default. `start` accepts a prompt, `send`
 * continues an idle incarnation and `interrupt` steers a working one; `inspect`
 * and `stop` address one incarnation by its exact handle; `list` enumerates. No
 * action is named `prompt`: that word is the payload a caller hands over, and a
 * call that spells the verb and the field the same way reads as one thing.
 * There is no
 * action that records work, and none that talks to a peer — a task belongs to
 * `@fradser/pi-tasks` and a conversation to `@fradser/pi-agent-teams`.
 *
 * **Why `delegate` and `start` are one action.** They were the same operation
 * dispatched twice, and the only difference was whether a prompt was delivered.
 * Two names for one operation means the model has to decide which of two
 * identically-shaped spawn paths it meant, and the wrong one is invisible. One
 * action with an optional `prompt` makes the choice explicit and local: either
 * there is something to hand over now, or there is not.
 *
 * **Spawning does not create a task.** A prompted child's result arrives in the
 * caller's transcript. Anything that needs a record — dependencies, a completion
 * gate, a resource lease, survival across attempts — is a `task` the caller
 * creates, and a participant takes it. That is why no action here accepts a
 * verify gate, a resource list, or a subject: there is no task to attach them to.
 *
 * **The coordinator is optional.** A richer host (tasks notices, assignment
 * authority, a fresh session per assignment) publishes itself through
 * `setAgentHost` when a team runtime is loaded. Without one, this tool falls back
 * to the raw spawner, which is what makes `@fradser/pi-subagents` installable and
 * usable on its own.
 */

import { randomUUID } from "node:crypto";
import { discoverAgents, inlineDefinitionApplies, MODEL_INHERIT_ALIAS, registerSessionAgent, resolveAgent, type AgentDefinition, type AgentScope } from "./agents.ts";
import type { createStaticToolLifecycleResultRenderer } from "@fradser/pi-kit";
import { getAgent, listAgents, livingAgents, registerAgent, updateAgent, updateAgentProgress, type Agent } from "./roster.ts";
import { exactSessionRoute, parseExactSessionRoute, resolveExactSession } from "./session-route.ts";
import { validateAgentInput, type AgentInput } from "./agent-input.ts";
import { createAgentFailure, createAgentListPage, createAgentResult, limitAgentReadback,
  type AgentControlOutcome, type AgentErrorCode, type AgentFailureContext, type AgentResult, type AgentSessionView, type AgentToolData } from "./agent-output.ts";
import { boundedFinalDiagnostic, normalizeFinalStopReason, unansweredReason, type SessionNotice, type SessionNoticeSender, type SessionResultNotice, type SessionUnansweredNotice } from "./session-result.ts";
import { spawnResident, terminateAgent, resolveAgentTools, unknownAgentTools, unknownAgentToolsError } from "./spawner.ts";
import * as residentControl from "./spawner.ts";
import { assertPrivateSessionFiles, ensureAgentWorkspace, type AgentWorkspace } from "./workspace.ts";
import { SUBAGENT_EXTENSION_PATH, AGENT_MEMORY_CAPABILITY_TOOLS, SUBAGENT_ROLE_ENV, SUBAGENT_TOOLS_ENV, SUBAGENT_DEFINITION_ENV, SUBAGENT_SCOPE_ENV } from "./agent-extension.ts";
import { PARENT_MESSAGE_CAPABILITY_TOOLS, PARENT_MESSAGE_EXTENSION_PATH } from "./parent-message-extension.ts";
import { MAX_PARENT_MESSAGE_BODY_BYTES, MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES, PARENT_MESSAGE_TOOL_NAME, type ParentMessageNotice, type ParentMessagePayload } from "./parent-message.ts";
import { snapshotWorkContext } from "./work-context.ts";
import { STREAM_RECOVERY_EXTENSION_PATH } from "./stream-recovery.ts";
import { bindInputSequence, confirmInputSequence, currentInputId, endInputSequence, pendingInputCount, settleInputSequence } from "./input-sequences.ts";

const processParentSessionId = randomUUID();

/** What a caller may ask for when starting an agent. */
export interface AgentStartRequest {
  name: string;
  /** Deliver this immediately. Omit to leave the agent idle. */
  prompt?: string;
  /** Inline role for a name that has no persisted definition. */
  definition?: { description: string; prompt: string; tools?: string[]; model?: string };
  model?: string;
  tools?: string[];
  /** Seed the child with a snapshot of the caller's active context. */
  fork?: boolean;
}

/** A richer spawn/close path published by a team runtime.
 *
 * `start` may return a promise, and this tool awaits it. That is deliberate: a
 * team spawn has to prove the child is actually up before it reports a handle,
 * because "started" is the caller's only evidence that anything exists. The host
 * owns native readiness and input acknowledgements for its child; the standalone
 * path awaits the same confirmations supplied by spawnResident. A successful
 * host start must reserve its new roster incarnation synchronously before its
 * first await, so the caller can pin ownership while confirmation is pending. */
export interface AgentHost {
  start(request: AgentStartRequest):
  | { ok: true; session: string }
  | { ok: false; error: string }
  | Promise<{ ok: true; session: string } | { ok: false; error: string }>;
  /** Exact-incarnation input controls own reservation, acknowledgement and
   * uncertain/rejected state restoration. They must await correlated native RPC
   * acceptance. Older hosts may omit them, but cannot start a public resident. */
  send?(name: string, spawnId: string, message: string): Promise<{ ok: true } | { ok: false; error: string }>;
  interrupt?(name: string, spawnId: string, message: string): Promise<{ ok: true } | { ok: false; error: string }>;
  stop(name: string, spawnId: string): Promise<{ ok: true; body?: string } | { ok: false; error: string }>;
  /** Checks policy before queuing new input, and again immediately before delivery. */
  authorizeInput?(name: string, spawnId: string): { ok: true } | { ok: false; error: string };
}

/**
 * Where a published host is kept.
 *
 * On `globalThis` under a `Symbol.for` key, deliberately, and not in a module
 * variable. Pi loads each installed package with its own module root, so a team
 * runtime that imports `@fradser/pi-subagents` and the very same extension entry Pi
 * loaded through a `node_modules` path can end up with two module instances — and
 * a module-level variable set by one is invisible to the other. That is not
 * hypothetical here: it is exactly how a published host went missing, leaving
 * every spawn on the standalone path and every child's output discarded.
 *
 * `Symbol.for` rather than a plain string so two copies of this module still agree
 * on the key, and `globalThis` so they agree on the slot.
 */
const AGENT_HOST_KEY = Symbol.for("fradser.pi-subagents.agent-host");

interface AgentHostCarrier {
  [AGENT_HOST_KEY]?: AgentHost;
}

function carrier(): AgentHostCarrier {
  return globalThis as AgentHostCarrier;
}

/** Publish the coordinator's richer spawn path. Called by a team runtime at
 *  session start; absent leaves this tool on the raw spawner. */
export function setAgentHost(host: AgentHost | undefined): void {
  if (host === undefined) delete carrier()[AGENT_HOST_KEY];
  else carrier()[AGENT_HOST_KEY] = host;
}

export function resolveAgentHost(): AgentHost | undefined {
  return carrier()[AGENT_HOST_KEY];
}

export function authorizeAgentInput(session: string): { ok: true } | { ok: false; error: string } {
  const child = resolveExactSession(session, listAgents());
  if (!child || child.leaderRequestedEnd) return { ok: false, error: "The exact child is closed or stopping." };
  if (child.standalone) return { ok: true };
  const host = hostBindings.get(session);
  return host?.authorizeInput?.(child.name, child.spawnId)
    ?? { ok: false, error: "The original host does not support input reservation policy." };
}

const NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

/** What an idle resident is doing, in the row's own words. Mirrors the receipt
 *  line the model reads, so a person and the model are never told different
 *  things about a child that is up and waiting. */
const IDLE_NOTICE = "idle; send a prompt to its exact session handle";
const RESULT_NOTICE = "result · Input accepted; the complete Session Result arrives asynchronously. Continue independent work, or end the turn for automatic resumption.";
const INVALID_SESSION_NOTICE = "Invalid session handle. Use session:<name>:<incarnation>, copied in full from start or list, including the session: prefix.";
const MAX_PARENT_MESSAGES_PER_INPUT = 32;
const MAX_PARENT_MESSAGE_INPUT_BYTES = 64 * 1024;

interface ResidentBinding {
  prompt(message: string): Promise<boolean>;
  /** Mid-turn delivery without a new sequence; await native RPC acceptance. */
  steer(message: string): boolean | Promise<boolean>;
}
const RESIDENT_BINDINGS_KEY = Symbol.for("fradser.pi-subagents.resident-bindings");
const residentCarrier = globalThis as { [RESIDENT_BINDINGS_KEY]?: Map<string, ResidentBinding> };
const residentBindings = residentCarrier[RESIDENT_BINDINGS_KEY] ?? (residentCarrier[RESIDENT_BINDINGS_KEY] = new Map());

// Pin the control/result owner to an exact handle. Republishing the global host
// must not redirect input or shutdown for a predecessor to a different runtime.
const HOST_BINDINGS_KEY = Symbol.for("fradser.pi-subagents.host-bindings");
const hostCarrier = globalThis as { [HOST_BINDINGS_KEY]?: Map<string, AgentHost> };
const hostBindings = hostCarrier[HOST_BINDINGS_KEY] ?? (hostCarrier[HOST_BINDINGS_KEY] = new Map());

/** Release process-local context only after confirmed retirement. Parent
 * shutdown uses exact handles; a successor or uncertain close keeps its binding. */
export function retireAgentControls(session: string): boolean {
  const parsed = parseExactSessionRoute(session);
  if (!parsed) return false;
  const current = getAgent(parsed.name);
  if (current?.spawnId === parsed.spawnId && current.status !== "stopped") return false;
  residentBindings.delete(session);
  hostBindings.delete(session);
  return true;
}

/** One line describing how a child ended, for the roster entry it leaves behind. */
function describeExit(result: { exitCode?: number | null; signal?: string | null; stderr?: string }): string {
  if (result.signal) return `Child process ended on ${result.signal}.`;
  const code = result.exitCode ?? 0;
  const detail = result.stderr?.trim();
  return detail
    ? `Child process exited with ${code}: ${detail}`
    : `Child process exited with ${code}.`;
}

/** The one ROLE line a start receipt carries, if the call needs one.
 *
 *  A start that applied what the caller asked for needs no line: the role is
 *  doing its job. The case that needs words is the one where the caller's own
 *  words never reached the child because a user-owned definition outranked them.
 *  That is silent otherwise, and a child running instructions its author did not
 *  write is the failure a receipt exists to prevent.
 */
function roleReceipt(input: {
  owned: AgentDefinition | undefined;
  inline: { description: string; prompt: string } | undefined;
  resolved: AgentDefinition | undefined;
}): string | undefined {
  if (input.owned) {
    return `role · ${input.owned.scope} definition "${input.owned.name}" is the role; `
      + "any inline role passed here was not applied";
  }
  if (input.inline) {
    return input.inline.prompt.trim()
      ? undefined
      : `role · ${input.inline.description} · no standing instructions given; this child has only its prompt`;
  }
  if (input.resolved) return undefined;
  return "role · none given; this child has only its prompt";
}

/**
 * The role description a receipt and a row report.
 *
 * A synthesised definition carries its own name in the description slot as
 * bookkeeping, so the name is never reported: the subject line already carries
 * it, and a `role · <name>` line spends the one place a row has for meaning on
 * repeating what it just said.
 */
function reportedRoleDescription(definition: { name: string; description: string }): string | undefined {
  const value = definition.description.trim();
  return value && value !== definition.name ? value : undefined;
}

/** The first line of a prompt, for a one-line row. A prompt is the deliverable
 *  of a start, so naming it matters more than its length. */
function firstLine(text: string): string {
  const line = text.trim().split("\n")[0] ?? "";
  return line.length > 120 ? `${line.slice(0, 117)}…` : line;
}

export type { AgentInput } from "./agent-input.ts";
export type { ChildOperation, AgentErrorCode, AgentResult, AgentSessionView, AgentToolData } from "./agent-output.ts";
export { AGENT_TOOL_OUTPUT_SCHEMA, CHILD_OPERATIONS } from "./agent-output.ts";

type AgentToolResult = AgentResult;
type AgentSuccessReceipt<T extends AgentToolData = AgentToolData> = T extends { ok: true }
  ? Omit<T, "ok" | "state" | "nextActor"> & Partial<Pick<T, "state" | "nextActor">> : never;

function ok(body: string, receipt: AgentSuccessReceipt): AgentToolResult {
  const parsed = receipt.session ? parseExactSessionRoute(receipt.session) : undefined;
  const observed = parsed ? listAgents().find(agent => agent.name === parsed.name && agent.spawnId === parsed.spawnId) : undefined;
  const state = receipt.state ?? observed?.status ?? (receipt.operation === "list" ? "read-only" : "unknown");
  const pending = (state === "starting" || state === "working")
    && (receipt.operation === "input" || (receipt.operation === "start" && receipt.prompted));
  // The intent a caller is waiting on is the delivery, not the operation: both
  // deliveries share one operation, and a caller must still see which one it asked for.
  const data: Extract<AgentToolData, { ok: true }> = { ...receipt, ok: true, state,
    ...(pending ? { pendingIntent: receipt.operation === "input" && "delivery" in receipt ? receipt.delivery : receipt.operation } : {}),
    nextActor: receipt.nextActor ?? (pending ? "runtime" : "caller") };
  return createAgentResult(body, data);
}

/** The projected view of one child. `tools` is included because the effective
 *  grant is the one thing a caller routinely gets wrong by assumption. */
function project(agent: Agent): AgentSessionView {
  return {
    name: agent.name,
    sequenceEnded: agent.sequenceEnded === true,
    session: agent.spawnId ? exactSessionRoute(agent.name, agent.spawnId) : undefined,
    status: agent.status,
    role: agent.role,
    ...(agent.label ? { label: agent.label } : {}),
    ...(agent.identity ? { identity: agent.identity } : {}),
    ...(agent.inputId ? { inputId: agent.inputId, pendingInputs: pendingInputCount(exactSessionRoute(agent.name, agent.spawnId)) } : {}),
    ...(agent.scope ? { scope: agent.scope } : {}),
    ...(agent.source ? { source: agent.source } : {}),
    ...(agent.cwd ? { cwd: agent.cwd } : {}),
    ...(agent.projectCwd ? { projectCwd: agent.projectCwd } : {}),
    ...(agent.workspacePath ? { workspacePath: agent.workspacePath } : {}),
    ...(agent.sessionDir ? { sessionDir: agent.sessionDir } : {}),
    ...(agent.currentTaskId ? { currentTaskId: agent.currentTaskId } : {}),
    ...(agent.assignment ? { assignment: agent.assignment } : {}),
    ...(agent.tools ? { tools: agent.tools } : {}),
    ...(agent.model ? { model: agent.model } : {}),
    ...(agent.activeTool ? { activeTool: agent.activeTool } : {}),
    ...(agent.resultKind ? { resultKind: agent.resultKind } : {}),
    ...(agent.unansweredReason ? { unansweredReason: agent.unansweredReason } : {}),
    ...(agent.stopReason ? { stopReason: agent.stopReason } : {}),
    ...(agent.finalDiagnostic ? { finalDiagnostic: agent.finalDiagnostic } : {}),
    // Output owns the aggregate UTF-8/line/JSON budget and original-size
    // metadata. Pass raw evidence without mutating or pre-truncating the roster.
    ...(agent.liveText?.trim() ? { liveText: agent.liveText } : {}),
    ...(agent.pid ? { pid: agent.pid } : {}),
    ...(agent.error ? { error: agent.error } : {}),
  };
}

/**
 * The row for one `agent` result.
 *
 * Built as a named spec rather than inline so the renderer can be attached only
 * when the caller can supply real terminal geometry. A row built without geometry
 * renders in every offline test and then fails on the first real repaint, because
 * `--print` never paints a frame.
 */
export interface ChildExecutionOptions {
  cwd?: string;
  /** Trusted parent identity for private history. Native tools use Pi's session ID. */
  parentSessionId?: string;
  /** Trusted new-interface startup selection. Not model-controlled legacy input. */
  startup?: { identity?: string; label?: string; definition?: AgentDefinition; inputId: string };
  /** Cancels the caller's wait, never a dispatched resident's lifetime. */
  signal?: AbortSignal;
  /** Injectable so the surface is testable without a real child process. */
  /**
   * Builds the result renderer from a spec. Supplied by the extension entry, which
   * is the only layer allowed to import the TUI: a row needs real terminal
   * geometry, and a renderer without it builds a layout the host cannot draw.
   *
   * Absent means no custom renderer at all, so a headless caller gets Pi's own
   * default rather than a row that would fail on the first repaint.
   */
  renderResult?: (spec: { createSpec: Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"] }) =>
    ReturnType<typeof createStaticToolLifecycleResultRenderer>;
  spawn?: typeof spawnResident;
  terminate?: typeof terminateAgent;
  /**
   * Hands one settled child turn, or one child that ended without one, to the
   * Leader's session. Supplied by the loaded extension entry, which is the only
   * layer holding the session API; absent means the library spawns and records
   * without delivering, which is what a consumer embedding it directly gets.
   *
   * Ignored only for a hosted incarnation: its host owns that spawn and result.
   * A standalone disk identity keeps this sender even with a host installed.
  */
  deliverSessionResult?: SessionNoticeSender;
  /** Delivers bounded intermediate child messages independently of final results. */
  deliverParentMessage?: (notice: ParentMessageNotice) => void | Promise<void>;
  contextMessages?: () => unknown;
  /** OS/runtime seams; no coordination capability is required. */
  prompt?: (name: string, message: string) => Promise<boolean>;
  /** Mid-turn steer for a working child: the OS seam beside `prompt`. */
  steer?: (name: string, message: string) => boolean | Promise<boolean>;
  workspace?: typeof ensureAgentWorkspace;
  leaderModel?: () => string | undefined;
  thinking?: () => string | undefined;
}

/** The library entry validates as strictly as the native schema boundary. */
export async function executeChildIntent(
  params: unknown,
  options: ChildExecutionOptions = {},
): Promise<AgentToolResult> {
  const validated = validateAgentInput(params);
  if (!validated.ok) {
    // Strict refusal can still point a mistaken name-only inspection at the
    // known exact handle; this is guidance, not fallback name resolution.
    const named = typeof params === "object" && params !== null && "name" in params && typeof params.name === "string"
      ? params.name.trim() : undefined;
    const inspect = typeof params === "object" && params !== null && "operation" in params && params.operation === "inspect";
    const known = inspect && named ? getAgent(named) : undefined;
    const operation = typeof params === "object" && params !== null && !Array.isArray(params)
      ? !Object.hasOwn(params, "operation") ? "start" : "operation" in params && typeof params.operation === "string" ? params.operation : "invalid"
      : "invalid";
    return createAgentFailure(operation, "invalid-parameters",
      validated.error + (known ? ` @${known.name} is ${exactSessionRoute(known.name, known.spawnId)}.` : ""),
      { nextActor: "caller", dispatched: false, controlOutcome: "not-dispatched" });
  }
  const input = validated.value;
  const operation = input.operation;
  let dispatched = false;
  let exactSession: string | undefined;
  const cancellation = (): AgentToolResult => {
    const parsed = exactSession ? parseExactSessionRoute(exactSession) : undefined;
    const known = parsed ? listAgents().find(agent => agent.name === parsed.name && agent.spawnId === parsed.spawnId) : undefined;
    const message = dispatched
      ? "Tool wait cancelled after dispatch. Acceptance or closure may still settle; no input was repeated and no process was ended. Inspect the exact handle before retrying."
      : "Tool invocation cancelled before dispatch; no process control was sent.";
    return createAgentFailure(operation, "cancelled", message, {
      outcome: "cancelled", state: known?.status ?? "unknown", dispatched,
      controlOutcome: dispatched ? "uncertain" : "not-dispatched",
      ...(exactSession ? { session: exactSession } : {}),
      ...(dispatched ? { pendingIntent: operation, nextActor: "runtime" } : { nextActor: "caller" }),
    });
  };
  if (options.signal?.aborted) return cancellation();
  return new Promise(resolve => {
    let returned = false;
    let cancelledWait = false;
    const finish = (result: AgentToolResult): void => {
      if (returned) {
        // A cancelled wait cannot consume the eventual control diagnostic. The
        // operation may return a failure instead of rejecting its promise; both
        // paths remain evidence for only the originally pinned incarnation.
        if (cancelledWait && !result.structuredContent.ok && result.structuredContent.code !== "output-limit"
          && exactSession && result.structuredContent.session === exactSession) {
          const parsed = parseExactSessionRoute(exactSession);
          if (parsed && getAgent(parsed.name)?.spawnId === parsed.spawnId) {
            const diagnostic = boundedFinalDiagnostic(result.structuredContent.error);
            if (diagnostic) updateAgent(parsed.name, { error: diagnostic });
          }
        }
        return;
      }
      returned = true;
      options.signal?.removeEventListener("abort", abort);
      resolve(result);
    };
    // Deferring to the microtask boundary lets a synchronous native dispatch
    // finish pinning its exact reservation before we report cancellation.
    const abort = (): void => {
      queueMicrotask(() => {
        if (returned) return;
        cancelledWait = true;
        finish(cancellation());
      });
    };
    options.signal?.addEventListener("abort", abort, { once: true });
    // Observe completion even after the caller stopped waiting. The native RPC
    // acknowledgement/close still owns state, bindings and automatic delivery.
    void executeAgentOperation(input, options, session => {
      dispatched = true;
      exactSession = session;
    }).then(finish, error => {
      const diagnostic = boundedFinalDiagnostic(error instanceof Error ? error.message : String(error)) ?? "Agent operation failed.";
      const parsed = exactSession ? parseExactSessionRoute(exactSession) : undefined;
      if (parsed && getAgent(parsed.name)?.spawnId === parsed.spawnId) updateAgent(parsed.name, { error: diagnostic });
      finish(createAgentFailure(operation, "operation-failed", diagnostic, {
        state: parsed && getAgent(parsed.name)?.spawnId === parsed.spawnId ? getAgent(parsed.name)?.status : "unknown",
        dispatched, controlOutcome: dispatched ? "uncertain" : "not-dispatched", nextActor: "caller",
        ...(exactSession ? { session: exactSession } : {}),
      }));
    });
  });
}

async function executeAgentOperation(
  params: AgentInput,
  options: ChildExecutionOptions,
  onDispatch: (session?: string) => void,
): Promise<AgentToolResult> {
  const operation = params.operation;
  let dispatched = false;
  let operationSession: string | undefined;
  const dispatch = (session?: string): void => {
    dispatched = true;
    if (session) operationSession = session;
    onDispatch(operationSession);
  };
  const fail = (message: string, code: AgentErrorCode = "operation-failed", controlOutcome?: AgentControlOutcome): AgentToolResult => {
    const session = operationSession ?? ("session" in params ? params.session : undefined);
    const parsed = session ? parseExactSessionRoute(session) : undefined;
    const known = parsed ? listAgents().find(agent => agent.name === parsed.name && agent.spawnId === parsed.spawnId) : undefined;
    const outcome = controlOutcome ?? (dispatched ? "uncertain" : "not-dispatched");
    const pending = dispatched && (outcome === "uncertain" || outcome === "unconfirmed");
    const facts: AgentFailureContext = { state: known?.status ?? "unknown", nextActor: "caller", dispatched,
      controlOutcome: outcome, ...(session ? { session } : {}),
      ...(known ? { name: known.name, status: known.status, tools: known.tools, scope: known.scope } : {}),
      ...(pending && (known?.status !== "stopped" || known?.leaderRequestedEnd) ? { pendingIntent: operation } : {}),
    };
    return createAgentFailure(operation, code, message, facts);
  };
  const fields: Record<string, unknown> = { ...params };
  // Identifiers were normalized by validation; authored instruction text was not.
  const str = (key: string): string | undefined => typeof fields[key] === "string" ? fields[key] : undefined;

  if (operation === "start") {
    const name = str("name") ?? `subagent-${randomUUID().slice(0, 8)}`;
    if (!NAME_PATTERN.test(name)) {
      return fail(`Invalid agent name "${name}". Use letters, digits, dots, dashes, underscores.`);
    }
    const description = str("description");
    const rolePrompt = str("role_prompt");
    // Read once: an explicit `[]` is a decision, and the receipt and the row both
    // have to be able to tell it apart from a grant nobody named.
    const requestedTools = params.tools;
    if (str("model") && /[\r\n]/.test(str("model")!)) return fail("Model must be a single-line provider/model reference.");
    const resolved = options.startup ? options.startup.definition : resolveAgent(name, options.cwd);
    // A filesystem definition is user-owned, so it is this name's role whatever
    // this call passes. A session role is not: it is this process's own residue
    // from an earlier spawn of the same name, so a role asked for now replaces
    // it. Letting the residue win hands the child the previous call's standing
    // instructions and reports a start as if this call's role had been used.
    const ownedByDefinition = resolved && !inlineDefinitionApplies(resolved) ? resolved : undefined;
    // Scope is the identity contract, not an invocation switch. Data directories
    // alone never declare an identity and this tool never writes agent.md.
    const scope: AgentScope = ownedByDefinition?.scope ?? "session";
    if (!str("prompt") && !str("name")) return fail("Temporary delegation requires a prompt.");
    // Either half of an inline role is a role. A description says what the child is
    // for; a role_prompt says how it behaves; a caller holding only one is not
    // holding a broken role, and refusing it left them no legal way to state the
    // purpose. The receipt says which half is missing, so a role that instructs
    // nothing is never mistaken for one that does.
    const inlineRole = description !== undefined || rolePrompt !== undefined
      ? {
        description: description ?? options.startup?.label ?? resolved?.description ?? name,
        prompt: rolePrompt ?? "",
        tools: requestedTools ?? resolved?.tools ?? [],
        ...(str("model") ? { model: str("model") } : {}),
      }
      : undefined;
    // The role the child actually runs, resolved once so the request, the roster,
    // the receipt and the row cannot disagree about it.
    const definition = ownedByDefinition
      ?? (inlineRole ? { ...inlineRole, name } : undefined)
      ?? resolved
      ?? { name, description: description ?? options.startup?.label ?? name, prompt: "", tools: requestedTools ?? [], ...(str("model") ? { model: str("model") } : {}) };
    // A prompt is sufficient for temporary delegation. An explicitly named
    // prompt-less start retains the low-level idle-session path for callers
    // that will submit input later; it creates no durable data by itself.
    const synthesised = !ownedByDefinition;
    const roleLine = roleReceipt({ owned: ownedByDefinition, inline: inlineRole, resolved });
    const reportedRole = reportedRoleDescription(definition);
    const request: AgentStartRequest = {
      name,
      ...(str("prompt") ? { prompt: str("prompt") } : {}),
      // A half role reaches the host as a definition: the role registry accepts a
      // role with no instructions, so a description-only start is spawnable on
      // both paths rather than only the standalone one.
      ...(inlineRole && !ownedByDefinition ? { definition: { ...inlineRole } } : {}),
      ...(str("model") ? { model: str("model") } : {}),
      ...(requestedTools ? { tools: requestedTools } : {}),
      ...(params.fork === true ? { fork: true } : {}),
    };

    const ceiling = resolved;
    if (requestedTools && ceiling) {
      const widened = requestedTools.filter((tool) => !ceiling.tools.includes(tool));
      if (widened.length > 0) return fail(`The role "${ceiling.name}" does not grant: ${widened.join(", ")}. Explicit tools may only narrow its grant.`, "grant-denied");
    }

    // Prefer the coordinator for session roles: it owns its assignment authority,
    // tasks notices and result delivery, while public send retains child history.
    const host = resolveAgentHost();
    const requestedGrant = requestedTools ?? definition.tools;
    // A host has no durable private-data contract. It may own session roles,
    // never silently replace a disk identity's standalone result owner.
    if (host && scope === "session") {
      if (requestedGrant.includes(PARENT_MESSAGE_TOOL_NAME)) {
        return fail("agent_message is available only for standalone children; the hosted child cannot claim parent-message support.", "unsupported-control");
      }
      if (options.signal?.aborted) return fail("Start cancelled before host dispatch.");
      if (!host.send || !host.interrupt) return fail("The published host does not support acknowledged send and interrupt controls; no resident was started.", "unsupported-control");
      const predecessor = getAgent(name)?.spawnId;
      dispatch();
      const startup = host.start(request);
      // Native hosts reserve synchronously before their first await. Pin only
      // a new exact reservation from this start, never the previous occupant.
      const reserved = getAgent(name);
      const candidateSession = reserved && reserved.spawnId !== predecessor && reserved.status !== "stopped" && reserved.standalone !== true
        ? exactSessionRoute(reserved.name, reserved.spawnId) : undefined;
      // host.start can synchronously reenter another start before returning.
      // A previously bound record belongs to that other invocation, even if it
      // uses the same host object. Check before writing or pinning its handle.
      const reservedSession = candidateSession && !hostBindings.has(candidateSession) ? candidateSession : undefined;
      if (reservedSession) {
        if (options.startup) {
          updateAgent(name, { label: options.startup.label, identity: options.startup.identity });
          bindInputSequence(reservedSession, options.startup.inputId, options.deliverSessionResult);
        }
        // Closure authority starts with the reservation, not its later ACK.
        // This check/set is synchronous and invokes no host/roster callbacks.
        hostBindings.set(reservedSession, host);
        dispatch(reservedSession);
      }
      let started: Awaited<ReturnType<AgentHost["start"]>>;
      try { started = await startup; }
      catch (error) {
        if (reservedSession && options.startup) endInputSequence(reservedSession, "Hosted startup acknowledgement failed; queued input did not start.");
        throw error;
      }
      if (!started.ok) {
        if (reservedSession && options.startup) endInputSequence(reservedSession, "Hosted startup was not accepted; queued input did not start.");
        return fail(started.error, "host-failed");
      }
      const handle = parseExactSessionRoute(started.session);
      const current = resolveExactSession(started.session, listAgents());
      const owner = hostBindings.get(started.session);
      if (!handle || handle.name !== name || !current || current.standalone === true || current.leaderRequestedEnd
        || reservedSession === undefined || started.session !== reservedSession
        || owner !== host) {
        if (reservedSession && options.startup) endInputSequence(reservedSession, "Hosted startup confirmation was invalid; queued input did not start.");
        return fail("The host did not return a living exact incarnation owned by its control path; startup could not be confirmed.", "host-invalid-start");
      }
      dispatch(started.session);
      hostBindings.set(started.session, host);
      if (options.startup) confirmInputSequence(started.session);
      updateAgent(name, { scope: "session" });
      // Report the grant the roster recorded, not the one that was asked for.
      // The two can differ when a coordinator narrows a request, and a caller
      // that assumed a tool it did not get is the failure this prevents — so
      // this is read back rather than echoed.
      const recorded = getAgent(name);
      const grant = recorded?.tools ?? [];
      return ok(
        [
          `child · ${name} · started · ${started.session}`,
          ...(request.prompt ? [`working · ${firstLine(request.prompt)}`, RESULT_NOTICE] : [`idle · ${IDLE_NOTICE}`]),
          // The row states the child's model, and the Leader is the one choosing the
          // next one: a cost-bearing fact belongs in the receipt the model reads, not
          // only in the row a person expands.
          ...(recorded?.model ? [`model · ${recorded.model}`] : []),
          `tools · ${grant.length > 0 ? grant.join(", ") : "coordination only"}`,
          // Say so plainly when the caller's own role words did not reach the
          // child, on this path too. It is the caller's only signal, and a later
          // turn spent re-explaining it is a turn wasted.
          ...(roleLine ? [roleLine] : []),
        ].join("\n"),
        {
          operation: "start", outcome: "started", name, session: started.session,
          prompted: Boolean(request.prompt),
          // What the child is for, not the name it was filed under: a row already
          // reads `@<name>` in its subject, and the role is the part a reader
          // cannot get from the roster.
          ...(reportedRole ? { role: reportedRole } : {}),
          ...(request.prompt ? { prompt: request.prompt } : {}),
          ...(recorded?.model ? { model: recorded.model } : {}),
          grant, scope, synthesisedRole: synthesised,
        },
      );
    }

    // Standalone: the raw spawner, with the roster as the only coordination.
    const spawn = options.spawn ?? spawnResident;
    // The role's own grant and model are the contract its author wrote; the
    // caller's parameters narrow them, they do not replace them. Inheritance
    // is resolved from the supplied parent context, never by forwarding an alias.
    const grant = requestedGrant;
    const requestedModel = str("model") ?? definition.model;
    const model = requestedModel && requestedModel !== MODEL_INHERIT_ALIAS
      ? requestedModel
      : options.leaderModel?.();
    const memoryEnabled = scope !== "session";
    const parentMessageEnabled = grant.includes(PARENT_MESSAGE_TOOL_NAME);
    const capabilityTools = [
      ...(memoryEnabled ? AGENT_MEMORY_CAPABILITY_TOOLS : []),
      ...(parentMessageEnabled ? PARENT_MESSAGE_CAPABILITY_TOOLS : []),
    ];
    const effectiveTools = resolveAgentTools(grant, capabilityTools);
    // A bare child is launched with `--no-extensions`, so a tool id nothing
    // registers there is dropped by its own allowlist filter and the receipt
    // would name a grant the child does not have. Refusing before the name is
    // claimed is what keeps that refusal clean: no process, and no name held by
    // nothing running under it.
    const unknown = unknownAgentTools(grant, capabilityTools);
    if (unknown.length > 0) return fail(unknownAgentToolsError(unknown, capabilityTools), "unknown-tools");
    const roleBody = definition.prompt;
    const projectCwd = options.cwd ?? process.cwd();

    // Claim the name *before* spawning, and *before* registering anything. The
    // roster is the only thing standing between two same-named children, and
    // checking after the spawn would leave an orphan process running with no
    // roster entry to stop it by. Registering the role first let a refused call
    // rewrite the role of a child that is still running, so the claim decides
    // whether this start is allowed to touch the role registry at all.
    const spawnId = randomUUID();
    const now = Date.now();
    // Delivery bookkeeping for this incarnation only. A replacement incarnation
    // under the same name gets a fresh closure, so a retired child's late frame
    // can neither deliver nor be counted as the successor's.
    const session = exactSessionRoute(name, spawnId);
    const displayName = options.startup?.label ?? name;
    const deliverSessionResult = options.deliverSessionResult;
    let roleDelivered = Boolean(request.prompt);
    let settledTurns = 0;
    let deliveredThisTurn = false;
    // Whether the turn now in flight has been answered. Per turn, not per
    // incarnation: a Work Session that answered turn 1 and then died answering
    // turn 2 has still left the Leader a question with no answer.
    let turnAnswered = false;
    let inputSequence = 0;
    let activeInput = Boolean(request.prompt);
    let parentInputKey: string | undefined;
    let parentInputToolCalls = new Set<string>();
    let parentInputCount = 0;
    let parentInputBytes = 0;
    let parentMessageSequence = 0;
    /** Only the incarnation that holds the name may write to it. A late close
     *  from a retired child must not stop its living replacement. */
    const isCurrent = () => getAgent(name)?.spawnId === spawnId;
    const notice = (result: SessionNotice): boolean => {
      if (!deliverSessionResult) return false;
      try {
        deliverSessionResult(result);
        return true;
      } catch (error) {
        // A delivery failure must not take the roster with it: the Work Session
        // is real whether or not the Leader's session accepted its answer, and
        // the roster still holds the text.
        if (isCurrent()) {
          updateAgent(name, {
            error: `Session Result delivery failed: ${error instanceof Error ? error.message : String(error)}`,
          });
        }
        return false;
      }
    };
    const currentParentInputKey = (entry: Agent | undefined): string | undefined => {
      if (!entry) return undefined;
      return currentInputId(session) ?? entry.inputId ?? `standalone:${inputSequence}`;
    };
    const parentMessageFailure = (key: string, error: unknown): void => {
      // Read the owner again when the sender settles. A successor input may
      // already be accepted without having emitted its first message, so the
      // quota cache's last key is not sufficient to authorize this diagnostic.
      const entry = getAgent(name);
      if (!entry || entry.spawnId !== spawnId || currentParentInputKey(entry) !== key) return;
      updateAgent(name, {
        error: boundedFinalDiagnostic(error instanceof Error ? error.message : String(error))
          ?? "Parent message delivery failed.",
      });
    };
    const routeParentMessage = (payload: ParentMessagePayload, _transportSequence: number): void => {
      if (!parentMessageEnabled || !options.deliverParentMessage || !activeInput) return;
      const entry = getAgent(name);
      if (!entry || entry.spawnId !== spawnId || entry.status === "stopped" || entry.leaderRequestedEnd
        || entry.sequenceEnded === true || deliveredThisTurn) return;
      const inputId = currentInputId(session) ?? entry.inputId;
      const key = inputId ?? `standalone:${inputSequence}`;
      if (parentInputKey !== key) {
        parentInputKey = key;
        parentInputToolCalls = new Set<string>();
        parentInputCount = 0;
        parentInputBytes = 0;
      }
      if (Buffer.byteLength(payload.toolCallId, "utf8") > MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES) {
        parentMessageFailure(key, `Parent message rejected: toolCallId exceeds the ${MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES} UTF-8 byte limit.`);
        return;
      }
      if (parentInputToolCalls.has(payload.toolCallId)) return;
      if (parentInputCount >= MAX_PARENT_MESSAGES_PER_INPUT) {
        parentMessageFailure(key, `Parent message quota exceeded: at most ${MAX_PARENT_MESSAGES_PER_INPUT} messages per input.`);
        return;
      }
      const bytes = Buffer.byteLength(payload.text, "utf8");
      if (bytes > MAX_PARENT_MESSAGE_BODY_BYTES) {
        parentMessageFailure(key, `Parent message rejected: body exceeds the ${MAX_PARENT_MESSAGE_BODY_BYTES} byte limit.`);
        return;
      }
      if (parentInputBytes + bytes > MAX_PARENT_MESSAGE_INPUT_BYTES) {
        parentMessageFailure(key, `Parent message quota exceeded: at most ${MAX_PARENT_MESSAGE_INPUT_BYTES} bytes (${MAX_PARENT_MESSAGE_INPUT_BYTES / 1024} KiB) per input.`);
        return;
      }
      parentInputToolCalls.add(payload.toolCallId);
      parentInputCount += 1;
      parentInputBytes += bytes;
      const acceptedSequence = ++parentMessageSequence;
      const delivered: ParentMessageNotice = {
        kind: "intermediate",
        name: displayName,
        session,
        ...(inputId ? { inputId } : {}),
        sequence: acceptedSequence,
        text: payload.text,
        deliveredAt: Date.now(),
      };
      try {
        const pending = options.deliverParentMessage(delivered);
        if (pending && typeof (pending as Promise<void>).then === "function") {
          void Promise.resolve(pending).catch((error) => parentMessageFailure(key, error));
        }
      } catch (error) {
        parentMessageFailure(key, error);
      }
    };
    if (options.signal?.aborted) return fail("Start cancelled before reserving an incarnation.");
    const reservation = registerAgent({
      name,
      role: definition.name,
      ...(options.startup?.label ? { label: options.startup.label } : {}),
      ...(options.startup?.identity ? { identity: options.startup.identity } : {}),
      spawnId,
      pid: 0,
      status: "starting",
      standalone: true,
      scope,
      ...(ownedByDefinition?.source ? { source: ownedByDefinition.source } : {}),
      tools: effectiveTools,
      ...(model ? { model } : {}),
      ...(request.fork ? { context: "fork" as const } : {}),
      createdAt: now,
      updatedAt: now,
    });
    if (!reservation.ok) return fail(reservation.error, "duplicate-name");
    // This exact reservation commits startup. From here cancellation releases
    // only the caller wait; role/storage/native setup still settle the intent.
    dispatch(session);
    if (options.startup) bindInputSequence(session, options.startup.inputId, deliverSessionResult);

    // The name is this start's to claim, so the role registry can be written now.
    // A role with a purpose but no instructions is registered too: it is the
    // record of what this name is, and a later spawn of the same name inherits
    // it. A start with no role at all registers nothing, and the receipt says so.
    if (inlineRole && scope === "session") {
      try {
        registerSessionAgent({
          name,
          description: definition.description,
          prompt: definition.prompt,
          tools: definition.tools,
          // The role's own declaration, `inherit` included: this registry records
          // what the role asks for, and the spawn above is where an unresolvable
          // `inherit` is deliberately left out.
          ...(definition.model ? { model: definition.model } : {}),
        });
      } catch (error) {
        // The name is claimed by a child that will not exist. Release it, or the
        // refusal leaves a name held by nothing.
        updateAgent(name, { status: "stopped", error: `Role registration failed: ${error instanceof Error ? error.message : String(error)}` });
        return fail(error instanceof Error ? error.message : String(error), "role-registration-failed", "rejected");
      }
    }

    let workspace: AgentWorkspace | undefined;
    let context: ReturnType<typeof snapshotWorkContext> | undefined;
    let hasSavedSession = false;
    try {
      if (request.fork) {
        if (!options.contextMessages) throw new Error("Fork context unavailable: leader session manager is unavailable.");
        context = options.contextMessages() as ReturnType<typeof snapshotWorkContext>;
      }
      if (scope !== "session") {
        workspace = (options.workspace ?? ensureAgentWorkspace)({
          agentName: name, cwd: projectCwd, parentSessionId: options.parentSessionId ?? processParentSessionId,
        });
        hasSavedSession = assertPrivateSessionFiles(workspace.sessionDir);
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      updateAgent(name, { status: "stopped", error: reason });
      return fail(reason, "workspace-failed", "rejected");
    }
    const cwd = workspace?.cwd ?? projectCwd;
    const sessionDir = workspace?.sessionDir;
    updateAgent(name, { cwd, projectCwd, ...(workspace ? { workspacePath: workspace.workspacePath, sessionDir } : {}) });
    // A scratch directory is not a checkout or a sandbox. The child always knows
    // where project edits land; these launch instructions reach it on input 1 only.
    const instructions = [
      roleBody ? `=== ROLE (${definition.name}) ===\n${roleBody}` : "",
      `=== EXECUTION PATHS ===\nLaunch cwd: ${cwd}\nOriginal project: ${projectCwd}`,
      workspace ? `Scratch workspace: ${workspace.workspacePath}\nThe scratch workspace is an ordinary directory, not a checkout. Project edits directly change the original working tree; no Git isolation or automatic commit applies.` : "",
    ].filter(Boolean).join("\n\n");
    const kickoff = request.prompt ? `${instructions}\n\n${request.prompt}` : undefined;

    // The kickoff prompt is the spawn's own `description`: the spawner writes it
    // to the child's control stream and opens the turn baseline there.
    // Delivering it a second time through `deliverPrompt` ran the same turn
    // twice — twice the child's tokens, and twice the Leader's turns once a
    // settled turn is delivered as a Session Result.
    let spawned: ReturnType<typeof spawnResident>;
    try {
      dispatch(session);
      spawned = spawn({
        agentName: name,
        ...(kickoff ? { description: kickoff } : {}),
        ...(model ? { model } : {}),
        tools: grant,
        capabilityTools,
        extensions: [
          STREAM_RECOVERY_EXTENSION_PATH,
          ...(memoryEnabled ? [SUBAGENT_EXTENSION_PATH] : []),
          ...(parentMessageEnabled ? [PARENT_MESSAGE_EXTENSION_PATH] : []),
        ],
        ...(parentMessageEnabled ? { onParentMessage: routeParentMessage } : {}),
        cwd,
        session: scope !== "session" ? (hasSavedSession ? "resume" : "persist") : "none",
        ...(sessionDir ? { sessionDir } : {}),
        ...(options.thinking?.() ? { thinking: options.thinking() } : {}),
        ...(context ? { context } : {}),
        env: {
          PI_SUBAGENT_PROJECT_CWD: projectCwd,
          ...(workspace ? { PI_SUBAGENT_WORKSPACE_PATH: workspace.workspacePath } : {}),
          ...(memoryEnabled ? {
            [SUBAGENT_ROLE_ENV]: name,
            [SUBAGENT_TOOLS_ENV]: effectiveTools.join(","),
            [SUBAGENT_DEFINITION_ENV]: ownedByDefinition?.source,
            [SUBAGENT_SCOPE_ENV]: scope,
          } : {}),
        },
        // A settled turn is one result, not one per frame. The dedupe is armed by
        // the turn and released by the next one, and a settle carrying no text
        // does neither: a real child settles empty before it settles with its
        // answer, and treating that empty settle as the turn's result would
        // suppress the answer for the life of the Work Session.
        onUpdate: (update) => {
          if (!isCurrent()) return;
          updateAgentProgress(name, spawnId, {
            liveText: update.text,
            liveThinking: update.liveThinking,
            activeTool: update.activeTool,
            turns: update.turns,
            sequenceEnded: update.finalResponse,
            modelOutputSeen: update.modelOutputSeen,
            usage: update.usage,
          });
          if (update.finalResponse === false) {
            activeInput = true;
            if (deliveredThisTurn) inputSequence += 1;
            deliveredThisTurn = false;
            turnAnswered = false;
            if (!getAgent(name)?.leaderRequestedEnd && getAgent(name)?.status !== "stopped") updateAgent(name, { status: "working", resultKind: undefined, unansweredReason: undefined, stopReason: undefined, finalDiagnostic: undefined });
            return;
          }
          if (update.finalResponse === true && !getAgent(name)?.leaderRequestedEnd && getAgent(name)?.status !== "stopped") {
            activeInput = false;
            updateAgent(name, { status: "idle", activeTool: undefined });
          }
          // Nothing to say is not a result, and it is not this turn's one delivery
          // either: a real child settles empty before it settles with its answer, and
          // consuming the dedupe on that frame suppressed the answer for the life of
          // the Work Session.
          if (update.finalResponse !== true || deliveredThisTurn) return;
          if (!update.text.trim() && !update.answerComplete && !update.missingFinal) return;
          deliveredThisTurn = true;
          settledTurns += 1;
          // Counted as answered only once the Leader's session has taken it: a
          // result lost in delivery is still lost, and pretending otherwise would
          // also silence the notice a later death owes the Leader.
          const stopReason = normalizeFinalStopReason(update.stopReason);
          const reason = unansweredReason({ ...update, stopReason });
          const diagnostic = boundedFinalDiagnostic(update.errorMessage);
          const inputId = currentInputId(session) ?? getAgent(name)?.inputId;
          const evidence = { name: displayName, session, turn: settledTurns, text: update.text,
            ...(inputId ? { inputId } : {}),
            ...(update.usage ? { usage: update.usage } : {}), deliveredAt: Date.now() };
          const result: SessionResultNotice | SessionUnansweredNotice = reason
            ? { ...evidence, kind: "unanswered", reason,
                ...(stopReason ? { stopReason } : {}),
                ...(diagnostic ? { errorMessage: diagnostic } : {}) }
            : { ...evidence, kind: "result" };
          updateAgent(name, { resultKind: result.kind, unansweredReason: reason, stopReason, finalDiagnostic: diagnostic });
          const resultSequence = inputSequence;
          const delivered = notice(result);
          settleInputSequence(session);
          if (delivered) {
            if (inputSequence === resultSequence) turnAnswered = true;
          } else if (deliverSessionResult) {
            // A bounded retry retains the authoritative answer independently of
            // streamed progress. It never launches another child or model turn.
            queueMicrotask(() => {
              if (!isCurrent()) return;
              if (notice(result)) {
                if (inputSequence === resultSequence) turnAnswered = true;
                updateAgent(name, { error: undefined });
              } else {
                notice({ kind: "ended", name: displayName, session, reason: "The answer is preserved on the roster but result delivery failed twice.", deliveredAt: Date.now() });
              }
            });
          }
        },
        // A child that exits leaves the roster. Without this the name stays held by a
        // process that no longer exists, and a later start of the same name is
        // refused against a dead entry.
        onExit: (result) => {
          endInputSequence(session, "The child exited; queued input did not start.");
          residentBindings.delete(session);
          if (!isCurrent()) return;
          const reason = describeExit(result);
          // A shutdown the Leader asked for is not news: it already has a receipt
          // from `action=stop`, and painting it on the failure band would report a
          // planned stop as a death. Decided before the entry is written, because
          // the error is what `list` and `inspect` read as a failure — a stopped
          // child the Leader asked to stop is not one.
          const requestedEnd = Boolean(getAgent(name)?.leaderRequestedEnd);
          const planned = requestedEnd || (turnAnswered && !result.signal && result.exitCode === 0);
          updateAgent(name, planned
            ? { status: "stopped" }
            : { status: "stopped", error: reason });
          if (planned || turnAnswered) return;
          // A death the Leader never heard about is a request that will never be
          // answered. Visible, but not a turn: recoverable execution stays internal.
          notice({ kind: "ended", name: displayName, session, reason, deliveredAt: Date.now() });
        },
        onError: (error) => {
          if (!isCurrent()) return;
          updateAgent(name, { error: error.message, leaderRequestedEnd: true });
          void (async () => {
            try {
              const closed = await (options.terminate ?? terminateAgent)(name);
              if (isCurrent() && closed.outcome !== "unconfirmed") { residentBindings.delete(session); updateAgent(name, { status: "stopped" }); }
            } catch {}
          })();
          if (turnAnswered) return;
          notice({
            kind: "ended", name: displayName, session,
            reason: `The Work Session could not be confirmed: ${error.message}`,
            deliveredAt: Date.now(),
          });
        },
      });
    } catch (error) {
      spawned = { error: error instanceof Error ? error.message : String(error) };
    }
    if ("error" in spawned) {
      // Release the reservation. A name that stays reserved by a child which
      // never started is the worst outcome: the name looks taken and nothing is
      // running under it — and the reason belongs on the entry, or the roster
      // holds a name that looks taken with nothing to explain it.
      updateAgent(name, { status: "stopped", error: spawned.error });
      return fail(`${spawned.error} @${name} was not started.`, "spawn-failed", "rejected");
    }
    const spawnError = getAgent(name)?.error;
    if (spawnError && (spawned.pid === 0 || getAgent(name)?.status === "stopped")) {
      await Promise.resolve();
      return fail(spawnError, "spawn-failed", "rejected");
    }
    updateAgent(name, { pid: spawned.pid, ...(spawned.envPolicy ? { envPolicy: spawned.envPolicy } : {}) });
    const confirmation = request.prompt ? spawned.accepted : spawned.readiness;
    let confirmed = true;
    try { confirmed = confirmation ? await confirmation : true; } catch { confirmed = false; }
    if (!confirmed) {
      if (isCurrent()) updateAgent(name, { leaderRequestedEnd: true });
      let closed: Awaited<ReturnType<typeof terminateAgent>> = { outcome: "unconfirmed" };
      try { closed = isCurrent() ? await (options.terminate ?? terminateAgent)(name) : { outcome: "missing" }; } catch {}
      const error = request.prompt ? "The child did not accept its initial prompt." : "Resident startup readiness could not be confirmed.";
      if (isCurrent()) updateAgent(name, { status: closed.outcome === "unconfirmed" ? "starting" : "stopped", error });
      return fail(error, "startup-unconfirmed", closed.outcome === "unconfirmed" ? "unconfirmed" : "rejected");
    }
    if (options.startup) confirmInputSequence(session);
    if (!isCurrent() || getAgent(name)?.status === "stopped" || getAgent(name)?.leaderRequestedEnd) {
      return fail("Resident exited, was replaced or is stopping before startup confirmation completed.", "startup-unconfirmed");
    }
    if (!request.prompt) updateAgent(name, { status: "idle" });
    residentBindings.set(session, {
      // A steer lands in the turn already running, so it carries no role prefix:
      // the role reached this child when its first input did.
      steer: (message: string) => {
        const entry = getAgent(name);
        if (!entry || entry.spawnId !== spawnId || entry.leaderRequestedEnd || entry.status === "stopped") return false;
        return (options.steer ?? residentControl.deliverResidentSteer)(name, message);
      },
      prompt: async (message: string) => {
        const entry = getAgent(name);
        if (!entry || entry.spawnId !== spawnId || entry.status !== "idle" || entry.leaderRequestedEnd) return false;
        updateAgent(name, { status: "starting" });
        const previousDelivery = deliveredThisTurn;
        const previouslyAnswered = turnAnswered;
        const previousSequence = inputSequence;
        const previousActiveInput = activeInput;
        inputSequence += 1;
        activeInput = true;
        deliveredThisTurn = false;
        turnAnswered = false;
        const input = !roleDelivered ? `${instructions}\n\n${message}` : message;
        let accepted = false;
        let confirmed = false;
        try {
          accepted = await (options.prompt ?? residentControl.deliverResidentPrompt)(name, input);
          confirmed = true;
          if (!accepted) {
            deliveredThisTurn = previousDelivery; turnAnswered = previouslyAnswered;
            inputSequence = previousSequence;
            activeInput = previousActiveInput;
            if (isCurrent() && !getAgent(name)?.leaderRequestedEnd && getAgent(name)?.status !== "stopped") updateAgent(name, { status: "idle" });
          }
        } finally {
          if (confirmed && isCurrent() && getAgent(name)?.status === "starting") updateAgent(name, { status: accepted ? "working" : "idle" });
        }
        // Callback order matters: an answer can settle before the ack resolves.
        // Its delivery state was armed before sending and must not be reset here.
        if (accepted) roleDelivered = true;
        return accepted;
      },
    });
    // An idle standalone resident has no kickoff, so the role it was just
    // registered with is still unread: the child is up and has never been told
    // what it is for. One line here is cheaper than a later turn spent assuming
    // otherwise.
    const undeliveredRole = roleBody && !request.prompt
      ? `role · ${reportedRole ?? definition.name} is registered, but this resident has no kickoff and reads no role until a prompt reaches it`
      : undefined;
    return ok(
      [
        `child · ${name} · started · ${session}`,
        ...(request.prompt ? [`working · ${firstLine(request.prompt)}`, RESULT_NOTICE] : [`idle · ${IDLE_NOTICE}`]),
        // The row states the child's model, and the Leader is the one choosing the
        // next one, so the receipt says it too.
        ...(model ? [`model · ${model}`] : []),
        `tools · ${effectiveTools.length > 0 ? effectiveTools.join(", ") : "no tools"}`,
        `scope · ${scope}`,
        ...(ownedByDefinition?.source ? [`source · ${ownedByDefinition.source}`] : []),
        `cwd · ${cwd}`,
        ...(workspace ? [`workspace · ${workspace.workspacePath}`] : []),
        // Say so plainly when the caller's own role words did not reach the
        // child, on this path too. It is the caller's only signal, and a later
        // turn spent re-explaining it is a turn wasted.
        ...(roleLine ? [roleLine] : undeliveredRole ? [undeliveredRole] : []),
      ].join("\n"),
      {
        operation: "start", outcome: "started", name, session,
        prompted: Boolean(request.prompt), standalone: true,
        ...(request.prompt ? { prompt: request.prompt } : {}),
        // What the child is for, not the name it was filed under.
        ...(reportedRole ? { role: reportedRole } : {}),
        ...(model ? { model } : {}),
        cwd, projectCwd, scope,
        ...(ownedByDefinition?.source ? { source: ownedByDefinition.source } : {}),
        ...(workspace ? { workspacePath: workspace.workspacePath, sessionDir } : {}),
        grant: effectiveTools, synthesisedRole: synthesised,
      },
    );
  }

  // One operation with its delivery, because the intent surface has one
  // `agent_input` tool: `next` queues a later turn, `steer` redirects the turn in
  // flight. The two paths differ in the child's state requirement, not in kind.
  if (operation === "input") {
    const delivery = str("delivery") === "steer" ? "steer" : "next";
    const session = str("session");
    const message = str("prompt");
    if (!session || !message) return fail("Sending input to a resident requires its exact session handle and a non-empty prompt.");
    // The one case a queued delivery refuses is a child already mid-turn, and it
    // is the case a Leader most often needs: the child is on the wrong path and
    // re-explaining after the turn is a turn wasted. A steer is not stopping — the
    // turn keeps running, and its settled answer still returns exactly once.
    if (delivery === "steer") {
  {
      const session = str("session");
      const message = str("prompt");
      if (!session || !message) return fail("Interrupting a resident requires its exact session handle and non-empty input.");
      if (!parseExactSessionRoute(session)) return fail(INVALID_SESSION_NOTICE);
      const matched = resolveExactSession(session, listAgents());
      if (!matched) return fail(`No living session "${session}".`, "not-found");
      // `starting` is steerable because a kickoff turn is already in flight even
      // though no frame has been parsed yet. `idle` and `stopped` have no turn to
      // steer, and the idle case has an action of its own.
      if (matched.status === "idle" || matched.status === "stopped") {
        return fail(`@${matched.name} is ${matched.status}; there is no turn in flight to steer. Use agent_input with delivery "next" and its exact session handle.`, "not-working");
      }
      if (matched.leaderRequestedEnd) return fail(`@${matched.name} is stopping; a steer would not reach a turn that is ending.`, "stopping");
      const binding = residentBindings.get(session);
      const host = hostBindings.get(session);
      if (!binding && !host?.interrupt) return fail(matched.standalone === true
        ? "This standalone session has no resident control binding; no steer was sent."
        : "The host owning this session does not support interrupt; no standalone steer was sent.");
      let accepted = false;
      try {
        dispatch(session);
        if (binding) accepted = await binding.steer(message);
        else {
          if (!host?.interrupt) return fail("The host owning this session lost its interrupt capability; no steer was sent.");
          const result = await host.interrupt(matched.name, matched.spawnId, message);
          if (!result.ok) return fail(result.error, "delivery-failed");
          accepted = true;
        }
      } catch (error) {
        return fail(`Steering failed: ${error instanceof Error ? error.message : String(error)}`, "delivery-failed");
      }
      // A steer that never landed leaves the turn exactly as it was, so saying so is
      // the difference between a Leader that retries and one that believes the child
      // was redirected.
      if (!accepted) return fail(`@${matched.name} did not accept the steer; the turn continues unchanged.`, "steer-rejected", "rejected");
      return ok(`child · ${matched.name} · interrupted · ${session}\nworking · ${firstLine(message)}`, {
        operation: "input", outcome: "interrupted", name: matched.name, session, prompt: message, steering: true, delivery,
      });
    }
    }

    if (!parseExactSessionRoute(session)) return fail(INVALID_SESSION_NOTICE);
    const matched = resolveExactSession(session, listAgents());
    if (!matched) return fail(`No living session "${session}".`, "not-found");
    if (matched.leaderRequestedEnd) return fail(`@${matched.name} is stopping; closure is not confirmed and no new input is permitted.`, "stopping");
    if (matched.status !== "idle") return fail(`@${matched.name} is ${matched.status}; input requires an idle resident.`, "not-idle");
    const binding = residentBindings.get(session);
    const host = hostBindings.get(session);
    if (!binding && !host?.send) return fail(matched.standalone === true
      ? "This standalone session has no resident input binding; no input was sent."
      : "The host owning this session does not support send; no standalone input was sent.");
    try {
      dispatch(session);
      if (binding) {
        if (!await binding.prompt(message)) return fail(`@${matched.name} did not accept the prompt; no input turn was confirmed.`, "input-rejected", "rejected");
      } else {
        // Host owns the sequence/attempt reservation and distinguishes a native
        // negative ack from uncertainty. Pre-marking starting defeats its idle
        // guard; restoring idle on every error would permit duplicate input.
        if (!host?.send) return fail("The host owning this session lost its send capability; no input was sent.");
        const accepted = await host.send(matched.name, matched.spawnId, message);
        if (!accepted.ok) return fail(accepted.error, "delivery-failed");
      }
    } catch (error) {
      // A missing acknowledgement may still have started execution. Retain busy
      // authority until inspect/stop or authoritative progress resolves it.
      return fail(`Prompt delivery failed: ${error instanceof Error ? error.message : String(error)}`, "delivery-failed");
    }
    return ok(`child · ${matched.name} · prompted · ${session}\nworking · ${firstLine(message)}\n${RESULT_NOTICE}`, {
      operation: "input", outcome: "prompted", name: matched.name, session, prompt: message, prompted: true, delivery,
    });
  }

  // The one case `send` refuses is a child already mid-turn, and it is the case a
  // Leader most often needs: the child is on the wrong path, and re-explaining
  // after the turn is a turn wasted. Steering is not stopping — the turn keeps
  // running, and its settled answer still returns exactly once.

  if (operation === "inspect") {
    const session = str("session");
    if (!session) {
      const named = str("name");
      const live = named ? livingAgents().find((t) => t.name === named) : undefined;
      const living = livingAgents();
      return fail(
        "Inspecting an agent requires its exact session handle, so a retired incarnation cannot be "
        + `mistaken for its replacement.${live ? ` @${live.name} is ${exactSessionRoute(live.name, live.spawnId!)}.` : ""}`
        + (living.length > 0 ? ` Run agent operation=list to see the current handles.` : ""),
      );
    }
    const parsed = parseExactSessionRoute(session);
    if (!parsed) return fail(INVALID_SESSION_NOTICE);
    // Inspection reads retained facts, not process authority. A stopped entry
    // is still known; controls keep the living-only resolveExactSession path.
    const matched = listAgents().find(agent => agent.name === parsed.name && agent.spawnId === parsed.spawnId);
    if (!matched) {
      const replacement = livingAgents().find((t) => t.name === parsed.name);
      return fail(
        replacement
          ? `No known session "${session}". @${replacement.name} is now ${exactSessionRoute(replacement.name, replacement.spawnId!)}.`
          : `No known session "${session}".`,
        "not-found",
      );
    }
    return limitAgentReadback(project(matched));
  }

  if (operation === "list") {
    const all = listAgents().map(project);
    const living = new Set(all.filter(agent => agent.status !== "stopped").map(agent => agent.name));
    // Discovery reads valid agent.md files only. Private data homes and session
    // roles are not offline durable identities, and listing provisions nothing.
    const definitions = [...discoverAgents(options.cwd).values()]
      .filter((definition): definition is AgentDefinition & { scope: Exclude<AgentScope, "session"> } =>
        definition.scope !== "session" && !living.has(definition.name))
      .map(definition => ({ name: definition.name, status: "offline" as const, scope: definition.scope,
        source: definition.source, description: definition.description, tools: definition.tools,
        ...(definition.model ? { model: definition.model } : {}) }));
    return createAgentListPage(all, definitions, { offset: params.offset, limit: params.limit });
  }

  if (operation === "stop") {
    const session = str("session");
    if (!session) return fail("Stopping an agent requires its exact session handle. Run agent operation=list to see the current handles.");
    if (!parseExactSessionRoute(session)) return fail(INVALID_SESSION_NOTICE);
    const matched = resolveExactSession(session, listAgents());
    if (!matched) return fail(`No living session named "${session}".`, "not-found");
    const wasWorking = matched.status === "working" || matched.status === "starting";
    dispatch(session);
    updateAgent(matched.name, { leaderRequestedEnd: true });
    endInputSequence(session, "The child is stopping; queued input did not start.");
    const host = hostBindings.get(session);
    let closed: { ok: true; body?: string } | { ok: false; error: string };
    try {
      if (host) {
        closed = await host.stop(matched.name, matched.spawnId);
      } else if (matched.standalone !== true && !residentBindings.has(session)) {
        closed = { ok: false, error: "The host owning this session has no exact control binding; closure was not confirmed." };
      } else {
        // A missing process releases the name; an uncertain close retains it.
        const outcome = await (options.terminate ?? terminateAgent)(matched.name);
        closed = outcome.outcome === "missing"
          ? { ok: true, body: `No child process named "${matched.name}" was running; its name is released.` }
          : outcome.outcome === "unconfirmed"
            ? { ok: false, error: `@${matched.name} did not confirm it closed. Inspect the process before assuming it stopped.` }
            : { ok: true };
      }
    } catch (error) {
      closed = { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
    if (!closed.ok) return fail(closed.error, "stop-unconfirmed", "unconfirmed");
    // Mark the ending as requested before the close lands, so the child's exit
    // is recognised as the shutdown it is rather than reported as a death the
    // Leader never heard about. `action=stop`'s own receipt is the report.
    if (getAgent(matched.name)?.spawnId === matched.spawnId) {
      updateAgent(matched.name, { status: "stopped", leaderRequestedEnd: true });
    }
    retireAgentControls(session);
    return ok(
      `child · @${matched.label ?? matched.identity ?? matched.name} · stopped`,
      // A stopped process is not a completed task. Saying so here is cheaper
      // than the model inferring completion from a silent process exit.
      { operation: "stop", outcome: "stopped", session, name: matched.name, agent: matched.name,
        ...(closed.body ? { body: closed.body } : {}),
        // What completion means, stated positively: this receipt reports the
        // process, and the work is complete where its own result says so. A
        // negated form of the same guardrail ("this is not evidence…") drags the
        // inference it forbids into the reader's head.
        evidence: "Process terminated. Its work is complete where its own result or a completed task says so.",
        // A stop during a live turn is the one interleaving worth surfacing: the
        // child had work in flight, and a turn it has already settled still comes
        // back as a late delivery.
        ...(wasWorking
          ? { interrupted: "This child was working when stopped. A turn it has already settled still arrives, marked as a late delivery." }
          : {}), },
    );
  }

  return fail(`Unknown agent operation "${operation}". Use start, input, steer, inspect, list, or stop.`);
}

/** The single registrant of `agent`. */
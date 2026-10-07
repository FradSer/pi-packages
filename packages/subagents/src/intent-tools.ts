/** Five model operations with explicit identity and input intent. */
import { randomUUID } from "node:crypto";
import type { ExtensionAPI, AgentToolResult, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { emptyToolCall, safeDisplayText, type ToolLifecycleSpec } from "@fradser/pi-kit";
import { executeChildIntent, authorizeAgentInput, type ChildExecutionOptions } from "./child-execution.ts";
import { AGENT_TOOL_OUTPUT_SCHEMA, boundedToolText, createAgentFailure, createAgentResult, type AgentToolData, type AgentOutputState, type AgentListPage } from "./agent-output.ts";
import { discoverAgents } from "./agents.ts";
import { getAgent } from "./roster.ts";
import { parseExactSessionRoute } from "./session-route.ts";
import { validateAgentInput } from "./agent-input.ts";
import { currentInputId, hasActiveInput, pendingInputCount, reserveNextInput } from "./input-sequences.ts";
import { snapshotWorkContext } from "./work-context.ts";
import { unansweredSummary, type UnansweredReason } from "./session-result.ts";

export const INTENT_TOOL_NAMES = ["agent_start", "agent_input", "agent_stop", "agent_list"] as const;
export type IntentToolName = typeof INTENT_TOOL_NAMES[number];
export type InputDisposition = "started" | "queued" | "steered" | "stopped" | "listed" | "rejected" | "uncertain";
export type IntentToolData = {
  version: 1; operation: IntentToolName; ok: boolean; disposition: InputDisposition;
  state: AgentOutputState; nextActor: "runtime" | "caller"; session?: string; inputId?: string;
  identity?: string; label?: string; pendingInputs?: number; code?: string; error?: string;
} & Partial<Omit<AgentToolData, "operation" | "outcome" | "ok" | "state" | "nextActor" | "code">>;
export type IntentResult = AgentToolResult<IntentToolData> & { structuredContent: IntentToolData };
const text = { type: "string", minLength: 1 } as const;
const session = { ...text, description: "Copy the complete returned session handle. It addresses one exact incarnation." };
export const INTENT_TOOL_SCHEMAS = {
  agent_start: { type: "object", properties: {
    prompt: { ...text, description: "The work for this child's first input. Accepted input is not a completed result." },
    // Declared without `minLength` or a pattern, because this field is optional and
    // a caller choosing the temporary path has to express absence somehow. The
    // extension reads an empty value as no identity (`fields.identity.trim()`),
    // so a schema that refused it contradicted the code: the one legal
    // alternative to a saved identity was reachable only by omitting the key, and
    // nothing said so.
    identity: { type: "string", description: "Existing disk agent.md identity. Omit this field for a temporary role; an empty value is read as absent. A name that is not a saved identity is refused by name. Missing identities never become temporary roles." },
    label: { ...text, maxLength: 120, description: "Display label only. It never selects or creates an identity." },
    instructions: { ...text, description: "Temporary standing instructions. Do not combine with a saved identity." },
    // The grantable ids are a fixed set, and a project-extension tool is not in it.
    // Both facts used to appear only in the refusal of a real call, so a caller
    // learned the contract by spending one.
    tools: { type: "array", items: text, description: "Minimal tools. Grantable ids: read, bash, edit, write, grep, find, ls, powershell, agent_memory. Defaults to none or the identity grant. Explicit lists only narrow saved grants; agent_message is standalone-only and must be explicitly granted for intermediate progress. A child runs a bare pi process, so a project-extension or MCP tool never reaches it: perform that work in the leader session." },
    model: { ...text, description: "Optional provider/model override. Omit to inherit." },
    fork: { type: "boolean", description: "Copy safe parent context without parent tool authority. Omit for no parent history." },
  }, required: ["prompt"], additionalProperties: false },
  agent_input: { type: "object", properties: { session, prompt: text,
    delivery: { type: "string", enum: ["next", "steer"], description: "next starts a later input after current work; steer guides active work without abort or a new sequence." },
  }, required: ["session", "prompt", "delivery"], additionalProperties: false },
  agent_stop: { type: "object", properties: { session }, required: ["session"], additionalProperties: false },
  agent_list: { type: "object", properties: {
    offset: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 1, maximum: 50 },
  }, required: [], additionalProperties: false },
} as const;
export const INTENT_OUTPUT_SCHEMA = {
  type: "object", properties: {
    ...AGENT_TOOL_OUTPUT_SCHEMA.properties,
    version: { const: 1 }, operation: { type: "string", enum: INTENT_TOOL_NAMES },
    disposition: { type: "string", enum: ["started", "queued", "steered", "stopped", "listed", "rejected", "uncertain"] },
    inputId: text, identity: text, label: text, pendingInputs: { type: "integer", minimum: 0 }, code: { type: "string" },
  }, required: ["version", "operation", "ok", "disposition", "state", "nextActor"], additionalProperties: false,
} as const;

type IntentSessionRow = {
  name?: unknown; label?: unknown; identity?: unknown; session?: unknown;
  status?: unknown; activeTool?: unknown; pendingInputs?: unknown; inputId?: unknown;
  model?: unknown; grant?: unknown; tools?: unknown; scope?: unknown; source?: unknown;
  cwd?: unknown; workspacePath?: unknown; resultKind?: unknown; liveText?: unknown; error?: unknown;
  unansweredReason?: UnansweredReason; stopReason?: string; finalDiagnostic?: unknown;
  previewNotice?: unknown; description?: unknown;
};
type IntentRenderDetails = IntentToolData & {
  name?: string; agent?: string; message?: string;
  sessions?: readonly IntentSessionRow[]; agents?: readonly IntentSessionRow[];
  definitions?: readonly IntentSessionRow[];
  page?: AgentListPage; total?: number;
};

function displayText(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const text = safeDisplayText(value).trim();
  return text || undefined;
}

function displayName(value: unknown, fallback = "child"): string {
  const name = displayText(value) ?? fallback;
  return name.startsWith("@") ? name : `@${name}`;
}

function sessionRows(details: IntentRenderDetails): IntentSessionRow[] {
  const rows = details.sessions ?? details.agents;
  return rows ? [...rows] : [];
}

function rowName(row: IntentSessionRow): string {
  return displayName(row.label ?? row.identity ?? row.name);
}

/** Keep exact control addresses in expanded metadata, never in a title. */
function subjectFor(details: IntentRenderDetails): string {
  const direct = displayText(details.label) ?? displayText(details.identity);
  if (direct) return displayName(direct);
  const current = details.session ? observed(details.session) : undefined;
  if (current) return displayName(current.label ?? current.identity ?? current.name);
  const name = displayText(details.name) ?? displayText(details.agent);
  if (name) return displayName(name);
  // The roster never reaches this: it is a set rather than a child, and
  // `collapsedSubject` answers for it before asking for a subject here. `@` is the
  // prefix of a real child's name, so a set must not borrow it — `@children` read
  // as a child called "children" on a row where every other subject is one agent.
  return "@child";
}

function withoutExactHandle(value: string, session?: string): string {
  const safe = safeDisplayText(value);
  const replaced = session ? safe.split(session).join("the exact child") : safe;
  return replaced.replace(/\bsession:[^\s.,;)}\]]+/g, "the exact child");
}

/** The states a collapsed child row may carry; anything else is expansion detail. */
const CHILD_STATES = new Set(["starting", "idle", "working", "stopped"]);

/** One collapsed row per result: the child, then the state word the label lacks.
 *  A roster has no state and no child's state becomes its subject, so a roster row
 *  carries the page count instead — and only when the page omits something.
 *  "4 of 4" answers a question the absence of a count already answers, while a
 *  page that hides entries is the case that has to say so without being opened. */
function collapsedSubject(operation: IntentToolName, details: IntentRenderDetails, label: string): string {
  if (operation === "agent_list") {
    const page = details.page;
    if (!page || page.omitted <= 0) return "";
    return `${page.returned} of ${page.totalSessions + page.totalDefinitions}`;
  }
  const subject = subjectFor(details);
  const state = displayText(details.state);
  if (!state || !CHILD_STATES.has(state) || state === label) return subject;
  return `${subject} · ${state}`;
}

function rowDetails(row: IntentSessionRow): string[] {
  return [
    ...(displayText(row.session) ? [`session · ${displayText(row.session)}`] : []),
    ...(displayText(row.status) ? [`status · ${displayText(row.status)}`] : []),
    ...(displayText(row.activeTool) ? [`active tool · ${displayText(row.activeTool)}`] : []),
    ...(displayText(row.inputId) ? [`input · ${displayText(row.inputId)}`] : []),
    ...(typeof row.pendingInputs === "number" && Number.isSafeInteger(row.pendingInputs)
      ? [`queued · ${row.pendingInputs}`] : []),
    ...(displayText(row.model) ? [`model · ${displayText(row.model)}`] : []),
    ...(Array.isArray(row.grant) ? [`tools · ${row.grant.join(", ") || "none"}`] : []),
    ...(Array.isArray(row.tools) && !Array.isArray(row.grant) ? [`tools · ${row.tools.join(", ") || "none"}`] : []),
    ...(displayText(row.scope) ? [`scope · ${displayText(row.scope)}`] : []),
    ...(displayText(row.source) ? [`source · ${displayText(row.source)}`] : []),
    ...(displayText(row.cwd) ? [`cwd · ${displayText(row.cwd)}`] : []),
    ...(displayText(row.workspacePath) ? [`workspace · ${displayText(row.workspacePath)}`] : []),
    ...(displayText(row.resultKind) ? [`result · ${displayText(row.resultKind)}`] : []),
    ...(row.resultKind === "unanswered" && row.unansweredReason
      ? [`unanswered · ${unansweredSummary({ reason: row.unansweredReason, stopReason: row.stopReason })}`] : []),
    ...(displayText(row.finalDiagnostic) ? [`diagnostic · ${displayText(row.finalDiagnostic)}`] : []),
    ...(displayText(row.liveText) ? [`output · ${displayText(row.liveText)}`] : []),
    ...(displayText(row.error) ? [`error · ${displayText(row.error)}`] : []),
    ...(displayText(row.description) ? [`description · ${displayText(row.description)}`] : []),
    ...(displayText(row.previewNotice) ? [`preview · ${displayText(row.previewNotice)}`] : []),
  ];
}

function intentSummary(operation: IntentToolName, details: IntentRenderDetails, content: string, expanded: boolean): string[] {
  if (!details.ok) {
    const diagnostic = displayText(details.error) ?? displayText(details.message) ?? displayText(content) ?? "The child control could not be confirmed.";
    return [withoutExactHandle(diagnostic, details.session)];
  }
  if (typeof details.prompt === "string" && details.prompt.length > 0) {
    return [expanded ? details.prompt : withoutExactHandle(details.prompt, details.session)];
  }
  // Identity and state already sit on the collapsed row. A body line here would
  // either repeat the child's name or restate a receipt the model already read.
  if (operation === "agent_list" || operation === "agent_stop") {
    const retained = sessionRows(details).length + (details.definitions ?? []).length;
    if (retained > 0 || operation === "agent_stop") return [];
    const page = details.page;
    if (operation === "agent_list" && page && page.totalSessions + page.totalDefinitions === 0) {
      // An empty definition list is a state the caller has to act on, and the
      // reachable path was the user scope under the agent home. Name the project
      // path and the path that needs no file at all.
      return ["No saved identity on disk. A temporary role needs none: omit identity and pass instructions. A saved identity lives at .pi/agents/<name>/agent.md in this repository."];
    }
    return [operation === "agent_list" && page
      ? `No entries on this page (${page.totalSessions + page.totalDefinitions} total).`
      : "No retained child record."];
  }
  const text = withoutExactHandle(content, details.session);
  return text ? [text] : [];
}

function intentDetails(operation: IntentToolName, details: IntentRenderDetails): string[] {
  const rows = sessionRows(details);
  const common = [
    ...(details.session ? [`session · ${details.session}`] : []),
    ...(details.inputId ? [`input · ${details.inputId}`] : []),
    ...(details.state ? [`state · ${details.state}`] : []),
    ...(details.pendingInputs !== undefined ? [`queued · ${details.pendingInputs}`] : []),
    ...(details.nextActor ? [`next · ${details.nextActor}`] : []),
    // The applied role description, when the executor reported one. The receipt
    // carries the description rather than the role name, so this line cannot
    // repeat the name the subject already shows.
    ...(displayText(details.role) ? [`role · ${displayText(details.role)}`] : []),
    ...(details.pendingIntent ? [`pending · ${details.pendingIntent}`] : []),
    ...(details.previewNotice ? [`preview · ${details.previewNotice}`] : []),
    ...(details.page ? [`page · ${details.page.returned} returned · ${details.page.remaining} remaining${details.page.nextOffset !== undefined ? ` · next offset ${details.page.nextOffset}` : ""}`] : []),
    ...(!details.ok && details.prompt ? [`input · ${details.prompt}`] : []),
    ...(details.model ? [`model · ${details.model}`] : []),
    ...(details.grant ? [`tools · ${details.grant.join(", ") || "none"}`] : []),
    ...(details.evidence ? [`evidence · ${details.evidence}`] : []),
    ...(details.interrupted ? [`interrupted · ${details.interrupted}`] : []),
    ...(operation === "agent_stop" && details.ok
      ? ["note · Completion belongs to the child result or task record."] : []),
    ...(details.body ? [`detail · ${details.body}`] : []),
    ...(details.error ? [`error · ${details.error}`] : []),
  ];
  if (operation === "agent_list") {
    // One naming header per child, then only the facts the common block and that
    // header do not already carry. The expanded row must not print a fact twice.
    const block = (row: IntentSessionRow, offline = false): string[] => {
      const addressed = Boolean(details.session) && displayText(row.session) === details.session;
      const header = `${rowName(row)} · ${offline ? "offline" : (displayText(row.status) ?? "unknown")}`;
      const lines = rowDetails(row).filter(line => {
        const key = line.slice(0, line.indexOf(" · "));
        return key !== "status" && !(addressed && key === "session");
      });
      return [header, ...lines];
    };
    return common.concat(rows.flatMap(row => block(row)), (details.definitions ?? []).flatMap(row => block(row, true)));
  }
  return common;
}

function observed(session?: string) {
  const parsed = session ? parseExactSessionRoute(session) : undefined;
  const agent = parsed ? getAgent(parsed.name) : undefined;
  return agent?.spawnId === parsed?.spawnId ? agent : undefined;
}
function displayIdentity(session?: string): Pick<IntentToolData, "label" | "identity"> {
  const child = observed(session);
  return child ? { label: child.label ?? child.identity ?? child.name,
    ...(child.identity ? { identity: child.identity } : {}) } : {};
}
function project(operation: IntentToolName, result: ReturnType<typeof createAgentResult>, extras: Partial<IntentToolData> = {}): IntentResult {
  const raw = result.structuredContent;
  const { operation: childOperation, outcome, ...fields } = raw;
  const disposition: InputDisposition = raw.ok
    ? operation === "agent_input" ? outcome === "interrupted" ? "steered" : "started"
      : operation === "agent_start" ? "started" : operation === "agent_stop" ? "stopped"
        : "listed"
    : raw.controlOutcome === "uncertain" || raw.controlOutcome === "unconfirmed" ? "uncertain" : "rejected";
  const data: IntentToolData = { ...fields, version: 1, operation, disposition, ...extras };
  const content = raw.ok && operation === "agent_start" ? [{ type: "text" as const, text: [
    `Input accepted. Session: ${data.session}. Input: ${data.inputId}.`,
    `Role: ${data.identity ?? "temporary"}. Label: ${data.label ?? "child"}. Tools: ${raw.grant?.join(", ") || "none"}.`,
    ...(raw.model ? [`Model: ${safeDisplayText(raw.model)}.`] : []),
    "The complete result arrives automatically; this receipt is not the answer.",
  ].map(safeDisplayText).join("\n") }]
    : result.content;
  return { ...result, content, details: data, structuredContent: data };
}
function refuse(operation: IntentToolName, error: string, code = "invalid-parameters", session?: string,
  display = displayIdentity(session)): IntentResult {
  const result = project(operation, createAgentFailure("invalid", "invalid-parameters", error, {
    state: observed(session)?.status ?? "unknown", ...(session ? { session } : {}),
  }), display);
  result.structuredContent.code = code;
  return result;
}
function validate(operation: IntentToolName, value: unknown): { ok: true; fields: Record<string, unknown> } | { ok: false; error: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ok: false, error: "Tool input must be an object." };
  // Copied, because the normalization below removes keys, and a caller's own
  // params object is not this function's to edit.
  const fields = { ...(value as Record<string, unknown>) };
  const allowed = INTENT_TOOL_SCHEMAS[operation].properties;
  for (const key of Reflect.ownKeys(fields)) {
    if (typeof key !== "string" || !Object.hasOwn(allowed, key)) return { ok: false, error: `Unknown parameter ${String(key)} for ${operation}.` };
  }
  if (operation === "agent_start") {
    // A blank optional string is absence, not a value. The extension reads an
    // empty identity as no identity, so `identity: ""` is the temporary path
    // spelled out; refusing it here contradicted that read, and refused the one
    // shape a caller reaches for when it has no saved identity to name.
    for (const key of ["identity", "label", "instructions", "model"]) {
      if (typeof fields[key] === "string" && !fields[key].trim()) delete fields[key];
    }
    if (typeof fields.prompt !== "string" || !fields.prompt.trim()) return { ok: false, error: "prompt must be a nonempty string for agent_start." };
    for (const key of ["prompt", "identity", "label", "instructions", "model"]) {
      if (key !== "prompt" && !Object.hasOwn(fields, key)) continue;
      if (typeof fields[key] !== "string") return { ok: false, error: `${key} must be a string.` };
    }
    if (typeof fields.label === "string" && (fields.label.length > 120 || /[\x00-\x1f\x7f]/.test(fields.label))) return { ok: false, error: "A display label must be one safe line of at most 120 characters." };
    if (fields.identity !== undefined && fields.instructions !== undefined) return { ok: false, error: "Saved identity and temporary instructions cannot be combined." };
    const shape = validateAgentInput({ prompt: fields.prompt,
      ...(fields.identity !== undefined ? { name: fields.identity } : {}),
      ...(fields.instructions !== undefined ? { role_prompt: fields.instructions } : {}),
      ...Object.fromEntries(["tools", "model", "fork"].filter(key => Object.hasOwn(fields, key)).map(key => [key, fields[key]])),
    });
    if (!shape.ok) return shape;
  } else {
    if (operation === "agent_input" && fields.delivery !== "next" && fields.delivery !== "steer") return { ok: false, error: "delivery must be next or steer." };
    // One execution operation per intent tool; `agent_input` keeps its delivery.
    const shape = validateAgentInput({ ...fields, operation: operation === "agent_input" ? "input" : operation.slice(6) });
    if (!shape.ok) return shape;
  }
  return { ok: true, fields };
}

export async function executeIntentTool(operation: IntentToolName, params: unknown, options: ChildExecutionOptions = {}): Promise<IntentResult> {
  const input = validate(operation, params);
  if (!input.ok) return refuse(operation, input.error);
  const fields = input.fields;
  const session = typeof fields.session === "string" ? fields.session.trim() : undefined;
  // A transcript receipt keeps the name of its exact incarnation after replacement.
  const display = displayIdentity(session);
  if (options.signal?.aborted) return refuse(operation, "Cancelled before dispatch; no child control was sent.", "cancelled", session, display);
  const prompt = typeof fields.prompt === "string" ? fields.prompt : undefined;
  if (operation === "agent_start") {
    // Trimmed to absence, not to an empty string: the fallback name below is
    // reached with `??`, which an empty string would satisfy, and the child would
    // then carry no name at all.
    const identity = typeof fields.identity === "string" ? (fields.identity.trim() || undefined) : undefined;
    const definition = identity ? discoverAgents(options.cwd).get(identity) : undefined;
    if (identity && (!definition || definition.scope === "session")) return refuse(operation, `No saved identity named ${identity}.`, "identity-not-found");
    if (definition && fields.tools !== undefined) {
      const requested = fields.tools as string[];
      const widened = requested.filter(tool => !definition.tools.includes(tool.trim()));
      if (widened.length) return refuse(operation, `The saved identity does not grant ${widened.join(", ")}.`, "grant-denied");
    }
    const name = identity ?? `subagent-${randomUUID().slice(0, 8)}`;
    const label = typeof fields.label === "string" ? fields.label : identity ?? name;
    const inputId = randomUUID();
    const result = await executeChildIntent({ operation: "start", name, prompt,
      // A temporary child with a prompt needs a role, and a role needs both halves:
      // the label is its description and its standing instructions are the request's
      // instructions when given, otherwise the prompt it was started with. A half
      // role is refused by a coordinator host, and a child with no instructions and
      // nothing to wait for reports a result nobody asked for.
      ...(!identity ? { description: label, role_prompt: fields.instructions ?? prompt } : {}),
      ...Object.fromEntries(["tools", "model", "fork"].filter(key => Object.hasOwn(fields, key)).map(key => [key, fields[key]])),
    }, { ...options, startup: { identity, label, definition, inputId } });
    return project(operation, result, { inputId, label, ...(identity ? { identity } : {}) });
  }
  const agent = observed(session);
  if (operation !== "agent_input") {
    const result = await executeChildIntent({ ...fields, operation: operation.slice(6) }, options);
    const exactSession = typeof fields.session === "string" ? fields.session : undefined;
    return project(operation, result, {
      ...(exactSession ? { session: exactSession } : {}),
      ...(operation === "agent_stop" ? display : {}),
    });
  }
  if (!agent || agent.status === "stopped" || agent.leaderRequestedEnd) return refuse(operation, "The exact child is closed, replaced, or stopping.", "not-found", session, display);
  const authorized = authorizeAgentInput(session!);
  if (!authorized.ok) return refuse(operation, authorized.error, "policy-refused", session, display);
  if (fields.delivery === "steer") {
    const inputId = currentInputId(session!);
    if (!inputId || !hasActiveInput(session!) || agent.status === "idle") return refuse(operation, "There is no active input to steer. Use delivery next.", "not-working", session, display);
    // The current sequence can settle and advance while its steering ACK waits.
    return project(operation, await executeChildIntent({ operation: "input", delivery: "steer", session, prompt }, options), { inputId, ...display });
  }
  if (options.signal?.aborted) return refuse(operation, "Cancelled before input reservation; no input was sent.", "cancelled", session, display);
  const reserved = reserveNextInput(session!, prompt!, async () => {
    // A reservation outlives its caller's wait. Preserve the original options and owner.
    const result = await executeChildIntent({ operation: "input", delivery: "next", session, prompt }, { ...options, signal: undefined });
    return { ok: result.structuredContent.ok,
      uncertain: !result.structuredContent.ok && result.structuredContent.controlOutcome === "uncertain",
      ...(!result.structuredContent.ok ? { error: result.structuredContent.error } : {}) };
  }, () => authorizeAgentInput(session!));
  if (!reserved.ok) return refuse(operation, reserved.error, reserved.code, session, display);
  const receipt = (uncertain = false): IntentResult => {
    const child = observed(session);
    const promptPreview = boundedToolText(prompt!, { maxBytes: 4096, maxLines: 50 });
    const data: IntentToolData = { version: 1, operation, ok: !uncertain,
      disposition: uncertain ? "uncertain" : reserved.queued ? "queued" : "started",
      state: child?.status ?? "unknown", nextActor: "runtime", session, inputId: reserved.inputId,
      pendingInputs: pendingInputCount(session!),
      ...(child?.name ? { name: child.name } : {}),
      ...display,
      ...(promptPreview ? {
        prompt: promptPreview.text,
        ...(promptPreview.truncation ? { truncation: { fields: [{ field: "prompt", ...promptPreview.truncation }], omittedFields: [] } } : {}),
      } : {}),
      ...(uncertain ? { code: "cancelled", error: "Caller wait cancelled. The reserved input can still settle; do not repeat it." } : {}) };
    const message = uncertain ? data.error! : `Input ${data.disposition}. Session: ${session}. Input: ${reserved.inputId}. The complete result arrives automatically.`;
    return { content: [{ type: "text", text: message }], details: data, structuredContent: data, ...(uncertain ? { isError: true } : {}) };
  };
  const confirmation = reserved.confirmation;
  if (!confirmation) return receipt();
  return new Promise(resolve => {
    let returned = false;
    const finish = (result: IntentResult) => { if (returned) return; returned = true; options.signal?.removeEventListener("abort", abort); resolve(result); };
    const abort = () => finish(receipt(true));
    options.signal?.addEventListener("abort", abort, { once: true });
    if (options.signal?.aborted) abort();
    void confirmation.then(result => {
      if (result && !result.ok) {
        const failure = refuse(operation, result.error ?? "Input was not confirmed.", "input-rejected", session, display);
        failure.structuredContent.inputId = reserved.inputId;
        if (result.uncertain) failure.structuredContent.disposition = "uncertain";
        finish(failure);
      } else finish(receipt());
    }, error => finish(refuse(operation, String(error), "operation-failed", session, display)));
  });
}

const DESCRIPTIONS: Record<IntentToolName, string> = {
  agent_start: "Start one child with work. identity selects an existing disk role; label only names the display. Temporary instructions cannot replace a saved role. The receipt confirms accepted input only: the child's answer arrives automatically and asynchronously in a later turn, so continue independent work or end the turn for automatic resumption. Never poll this child with agent_inspect or agent_list to wait for its answer, never sleep, and never start a duplicate child for the same work.",
  agent_input: "Continue or guide the same exact child. delivery next starts after current work and can queue bounded input. delivery steer changes active work without abort or a new sequence. A receipt is not a final answer: the child's answer arrives automatically and asynchronously in a later turn, so do not poll with agent_inspect or agent_list to wait for it, and never repeat uncertain input.",
  agent_stop: "Close one exact child. Pending inputs receive cancellation notices. Confirmed closure does not undo file changes or establish task completion. Caller cancellation ends waiting, not the close operation. A closed child's answer is still delivered when it settles, so a stop is not a way to skip a result.",
  agent_list: "List bounded session summaries and offline saved identities when you need the roster or an exact handle. Follow page.nextOffset for more entries. Discovery creates no identity, storage, or process. Use returned exact session handles for controls, and do not re-list a child whose answer is on its way.",
};
export function registerIntentTools(pi: ExtensionAPI, options: ChildExecutionOptions = {}): void {
  for (const name of INTENT_TOOL_NAMES) {
    const spec = (result: AgentToolResult<IntentToolData>, expanded: boolean, isError: boolean): ToolLifecycleSpec => {
      const details = (result.details ?? {}) as IntentRenderDetails;
      const content = result.content.flatMap(part => part.type === "text" ? [part.text] : []).join("\n");
      const label = details.disposition ?? "result";
      return {
        kind: "event", tool: "agent", subject: collapsedSubject(name, details, label),
        label,
        summary: intentSummary(name, details, content, expanded),
        details: intentDetails(name, details),
        ...(isError || result.isError || !details.ok ? { bgToken: "toolErrorBg" as const } : {}),
      };
    };
    const renderFactory = options.renderResult;
    // Keep the intent's disposition and subject on native error rows. The spec
    // supplies the error background without replacing the model-facing receipt.
    const renderResult = renderFactory
      ? ((result, state, theme, context) => renderFactory({
        createSpec: value => spec(value as AgentToolResult<IntentToolData>, state.expanded === true, context.isError === true),
      })(result, state, theme, { ...context, isError: false })) as ToolDefinition<typeof INTENT_TOOL_SCHEMAS[typeof name], IntentToolData>["renderResult"]
      : undefined;
    pi.registerTool<typeof INTENT_TOOL_SCHEMAS[typeof name], IntentToolData>({
      name, label: name.replaceAll("_", " "), parameters: INTENT_TOOL_SCHEMAS[name], outputSchema: INTENT_OUTPUT_SCHEMA,
      namespace: { name: "subagents", description: "Create children, continue exact sessions, close them, and read their state.",
        instructions: "Delegate only under an explicit user request or the instructions that apply. Reuse a child for dependent follow-ups. Results arrive automatically and asynchronously: continue independent work, or end the turn for automatic resumption. Never confirm a result without polling, sleeping, or inferring acceptance from a receipt, and never spend duplicate starts on a child you already hold; `agent_list` is how you ask what exists, and a running child is answered by its own Session Result." },
      description: DESCRIPTIONS[name], exposure: "direct", renderShell: "self", renderCall: emptyToolCall,
      annotations: name === "agent_list"
        ? { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
        : { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
      ...(renderResult ? { renderResult } : {}),
      execute: async (_id, params, signal, _update, ctx) => executeIntentTool(name, params, {
        ...options, signal: signal ?? options.signal, cwd: options.cwd ?? ctx?.cwd,
        parentSessionId: options.parentSessionId ?? ctx?.sessionManager?.getSessionId?.(),
        leaderModel: options.leaderModel ?? (() => ctx?.model ? `${ctx.model.provider}/${ctx.model.id}` : undefined),
        thinking: options.thinking ?? (() => ctx?.thinkingLevel),
        contextMessages: options.contextMessages ?? (() => snapshotWorkContext(ctx?.sessionManager)),
      }),
    });
  }
}

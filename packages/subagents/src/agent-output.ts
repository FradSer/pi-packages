/** Typed, bounded management receipts. Never use these builders for Session Result delivery. */
import { Buffer } from "node:buffer";
import type { AgentToolResult } from "@earendil-works/pi-coding-agent";
import { safeDisplayText } from "@fradser/pi-kit";
import type { AgentScope } from "./agents.ts";
import type { AgentStatus } from "./roster.ts";
import { boundedFinalDiagnostic, normalizeFinalStopReason, unansweredSummary, type UnansweredReason } from "./session-result.ts";

export const AGENT_TEXT_MAX_BYTES = 16 * 1024;
export const AGENT_TEXT_MAX_LINES = 200;
export const AGENT_JSON_MAX_BYTES = 32 * 1024;
export const AGENT_LIST_DEFAULT_LIMIT = 20;
export const AGENT_LIST_MAX_LIMIT = 50;
export const AGENT_PREVIEW_MARKER = "[management preview truncated; raw record unchanged]";
export const AGENT_LIVE_PREVIEW_MARKER = "... [preview truncated; delivered Session Result is complete]";
/** One entry per intent tool. `agent_input` carries its delivery, so the
 *  execution boundary has five operations rather than the legacy six verbs. */
export const CHILD_OPERATIONS = ["start", "input", "list", "stop"] as const;
export type ChildOperation = typeof CHILD_OPERATIONS[number];
export type AgentOutputOperation = ChildOperation | "invalid";
export type AgentOutputState = AgentStatus | "accepted" | "unknown" | "read-only";
export const AGENT_ERROR_CODES = [
  "invalid-parameters", "invalid-action", "invalid-name", "invalid-model", "invalid-session",
  "unknown-parameters", "missing-session", "missing-prompt", "not-found", "not-idle", "not-working",
  "stopping", "grant-denied", "unknown-tools", "duplicate-name", "unsupported-control", "no-control-binding",
  "host-failed", "host-invalid-start", "role-registration-failed", "context-unavailable", "workspace-failed",
  "spawn-failed", "startup-unconfirmed", "input-rejected", "delivery-failed", "steer-rejected",
  "stop-unconfirmed", "operation-failed", "output-limit", "cancelled",
] as const;
export type AgentErrorCode = typeof AGENT_ERROR_CODES[number];
export type AgentControlOutcome = "uncertain" | "not-dispatched" | "unconfirmed" | "rejected" | "accepted" | "closed" | "missing";

export type AgentTextTruncation = {
  truncated: true;
  reason: "bytes" | "lines" | "diagnostic" | "summary";
  originalBytes: number;
  originalLines: number;
  outputBytes: number;
  outputLines: number;
  marker: string;
};
export type AgentFieldTruncation = AgentTextTruncation & { field: string };
export type AgentOutputTruncation = {
  text?: AgentTextTruncation;
  fields: AgentFieldTruncation[];
  omittedFields: string[];
};
export type AgentAssignmentView = { id: string; kind: "direct" | "task"; resources: string[]; closed?: boolean };

type PreviewFields = {
  prompt?: string; role?: string; body?: string; evidence?: string; interrupted?: string;
  description?: string; activeTool?: string; liveText?: string; error?: string;
  finalDiagnostic?: string; requestedOperation?: string;
  previewNotice?: string; truncation?: AgentOutputTruncation;
};
export type AgentSessionView = PreviewFields & {
  name: string; session?: string; status: AgentStatus; sequenceEnded?: boolean;
  label?: string; identity?: string; inputId?: string; pendingInputs?: number;
  scope?: AgentScope; source?: string; cwd?: string; projectCwd?: string;
  workspacePath?: string; sessionDir?: string; currentTaskId?: string;
  assignment?: AgentAssignmentView; tools?: string[]; grant?: string[]; model?: string; pid?: number;
  resultKind?: "result" | "unanswered"; unansweredReason?: UnansweredReason; stopReason?: string;
};
export type AgentDefinitionView = PreviewFields & {
  name: string; status: "offline"; scope: Exclude<AgentScope, "session">;
  source?: string; description: string; tools: string[]; model?: string;
};
export type AgentListPage = {
  offset: number; limit: number; returned: number; omitted: number; before: number; remaining: number;
  totalSessions: number; totalDefinitions: number; omittedSessions?: number; omittedDefinitions?: number;
  nextOffset?: number;
};
export type AgentOutputLimit = {
  maxTextBytes: number; maxTextLines: number; maxJsonBytes: number;
  omittedFields: string[]; offset?: number;
};
export type AgentFailureContext = {
  state?: AgentOutputState; outcome?: "error" | "cancelled";
  name?: string; agent?: string; session?: string; status?: AgentStatus;
  model?: string; grant?: string[]; tools?: string[]; scope?: AgentScope; source?: string;
  cwd?: string; projectCwd?: string; workspacePath?: string; sessionDir?: string;
  currentTaskId?: string; assignment?: AgentAssignmentView;
  dispatched?: boolean; controlOutcome?: AgentControlOutcome;
  pendingIntent?: ChildOperation | "next" | "steer"; nextActor?: "runtime" | "caller";
};
type CommonData = PreviewFields & Omit<AgentFailureContext, "state" | "outcome" | "nextActor"> & {
  state: AgentOutputState; nextActor: "runtime" | "caller";
};
export type AgentStartedData = CommonData & {
  operation: "start"; ok: true; outcome: "started"; name: string; session: string;
  prompted: boolean; standalone?: boolean; synthesisedRole?: boolean;
};
/** One `agent_input` operation with two outcomes: a queued delivery the child
 *  accepted (`prompted`) and a steer that redirected the turn in flight
 *  (`interrupted`). The operation names the intent tool; the outcome names what
 *  the delivery did. */
export type AgentPromptedData = CommonData & {
  operation: "input"; ok: true; outcome: "prompted" | "interrupted";
  name: string; session: string; prompt: string; delivery: "next" | "steer"; prompted?: true; steering?: true;
};
export type AgentStoppedData = CommonData & { operation: "stop"; ok: true; outcome: "stopped"; name: string; session: string };
export type AgentListedData = CommonData & {
  operation: "list"; ok: true; outcome: "listed";
  /** Compatibility: all sessions on the supplied roster, not only this page. */
  count: number; total: number; totalDefinitions?: number; omitted?: number;
  agents: AgentSessionView[]; sessions: AgentSessionView[]; definitions: AgentDefinitionView[]; page: AgentListPage;
};
export type AgentFailureData = CommonData & {
  operation: AgentOutputOperation; ok: false; outcome: "error" | "cancelled";
  code: AgentErrorCode; message: string; error: string; limit?: AgentOutputLimit;
};
export type AgentToolData = AgentStartedData | AgentPromptedData | AgentStoppedData
  | AgentListedData | AgentFailureData;
export type AgentResult = Omit<AgentToolResult<AgentToolData>, "content" | "structuredContent"> & {
  content: Array<{ type: "text"; text: string }>;
  structuredContent: AgentToolData;
};

const stringSchema = { type: "string" } as const;
const booleanSchema = { type: "boolean" } as const;
const numberSchema = { type: "number" } as const;
const countSchema = { type: "integer", minimum: 0 } as const;
const stringsSchema = { type: "array", items: stringSchema } as const;
const scopeSchema = { type: "string", enum: ["user", "project", "project-local", "session"] } as const;
const statusSchema = { type: "string", enum: ["starting", "idle", "working", "stopped"] } as const;
const textTruncationProperties = {
  truncated: { const: true }, reason: { type: "string", enum: ["bytes", "lines", "diagnostic", "summary"] },
  originalBytes: countSchema, originalLines: countSchema, outputBytes: countSchema, outputLines: countSchema, marker: stringSchema,
} as const;
const textTruncationSchema = {
  type: "object", properties: textTruncationProperties, required: Object.keys(textTruncationProperties), additionalProperties: false,
} as const;
const truncationSchema = {
  type: "object", properties: {
    text: textTruncationSchema,
    fields: { type: "array", items: { type: "object", properties: { ...textTruncationProperties, field: stringSchema },
      required: [...Object.keys(textTruncationProperties), "field"], additionalProperties: false } },
    omittedFields: stringsSchema,
  }, required: ["fields", "omittedFields"], additionalProperties: false,
} as const;
const assignmentSchema = {
  type: "object", properties: { id: stringSchema, kind: { type: "string", enum: ["direct", "task"] },
    resources: stringsSchema, closed: booleanSchema }, required: ["id", "kind", "resources"], additionalProperties: false,
} as const;
const previewProperties = {
  prompt: stringSchema, role: stringSchema, body: stringSchema, evidence: stringSchema, interrupted: stringSchema,
  description: stringSchema, activeTool: stringSchema, liveText: stringSchema, error: stringSchema,
  finalDiagnostic: stringSchema, requestedOperation: stringSchema, previewNotice: stringSchema, truncation: truncationSchema,
} as const;
const authorityProperties = {
  name: stringSchema, session: stringSchema, status: statusSchema, scope: scopeSchema, source: stringSchema,
  cwd: stringSchema, projectCwd: stringSchema, workspacePath: stringSchema, sessionDir: stringSchema,
  currentTaskId: stringSchema, assignment: assignmentSchema, tools: stringsSchema, grant: stringsSchema, model: stringSchema,
} as const;
const sessionProperties = {
  ...previewProperties, ...authorityProperties, sequenceEnded: booleanSchema, pid: numberSchema,
  label: stringSchema, identity: stringSchema, inputId: stringSchema, pendingInputs: countSchema,
  resultKind: { type: "string", enum: ["result", "unanswered"] },
  unansweredReason: { type: "string", enum: ["empty", "error", "aborted", "length", "incomplete", "missing-final"] },
  stopReason: { type: "string", enum: ["pending", "stop", "length", "toolUse", "error", "aborted", "deferred", "unknown"] },
} as const;
const sessionSchema = { type: "object", properties: sessionProperties, required: ["name", "status"], additionalProperties: false } as const;
const definitionProperties = {
  ...previewProperties, name: stringSchema, status: { const: "offline" },
  scope: { type: "string", enum: ["user", "project", "project-local"] }, source: stringSchema, tools: stringsSchema, model: stringSchema,
} as const;
const definitionSchema = { type: "object", properties: definitionProperties,
  required: ["name", "status", "scope", "description", "tools"], additionalProperties: false } as const;
const pageProperties = {
  offset: countSchema, limit: { type: "integer", minimum: 1, maximum: AGENT_LIST_MAX_LIMIT },
  returned: countSchema, omitted: countSchema, before: countSchema, remaining: countSchema,
  totalSessions: countSchema, totalDefinitions: countSchema, omittedSessions: countSchema, omittedDefinitions: countSchema, nextOffset: countSchema,
} as const;
function successSchema(operation: ChildOperation, outcome: string, required: string[]) {
  return { properties: { operation: { const: operation }, ok: { const: true }, outcome: { const: outcome } }, required };
}
/** Native structural JSON Schema is accepted by Pi 1.0's TSchema/defineTool without a runtime dependency. */
export const AGENT_TOOL_OUTPUT_SCHEMA = {
  type: "object", properties: {
    ...previewProperties, ...authorityProperties,
    operation: { type: "string", enum: [...CHILD_OPERATIONS, "invalid"] }, ok: booleanSchema,
    outcome: { type: "string", enum: ["started", "prompted", "interrupted", "listed", "stopped", "error", "cancelled"] },
    state: { type: "string", enum: ["accepted", "idle", "starting", "working", "stopped", "unknown", "read-only"] },
    agent: stringSchema, prompt: stringSchema, delivery: { type: "string", enum: ["next", "steer"] },
    prompted: booleanSchema, steering: booleanSchema, standalone: booleanSchema, synthesisedRole: booleanSchema,
    dispatched: booleanSchema, controlOutcome: { type: "string", enum: ["uncertain", "not-dispatched", "unconfirmed", "rejected", "accepted", "closed", "missing"] },
    pendingIntent: { type: "string", enum: [...CHILD_OPERATIONS, "next", "steer"] },
    nextActor: { type: "string", enum: ["runtime", "caller"] },
    agents: { type: "array", items: sessionSchema }, sessions: { type: "array", items: sessionSchema },
    definitions: { type: "array", items: definitionSchema }, count: countSchema, total: countSchema,
    totalDefinitions: countSchema, omitted: countSchema,
    page: { type: "object", properties: pageProperties,
      required: ["offset", "limit", "returned", "omitted", "before", "remaining", "totalSessions", "totalDefinitions"], additionalProperties: false },
    code: { type: "string", enum: AGENT_ERROR_CODES }, message: stringSchema,
    limit: { type: "object", properties: { maxTextBytes: countSchema, maxTextLines: countSchema,
      maxJsonBytes: countSchema, omittedFields: stringsSchema, offset: countSchema },
      required: ["maxTextBytes", "maxTextLines", "maxJsonBytes", "omittedFields"], additionalProperties: false },
  }, required: ["operation", "ok", "outcome", "state", "nextActor"], additionalProperties: false,
  oneOf: [
    successSchema("start", "started", ["name", "session", "prompted"]),
    successSchema("input", "prompted", ["name", "session", "prompt", "delivery", "prompted"]),
    successSchema("input", "interrupted", ["name", "session", "prompt", "delivery", "steering"]),
    successSchema("stop", "stopped", ["name", "session"]),
    successSchema("list", "listed", ["count", "total", "agents", "sessions", "definitions", "page"]),
    { properties: { ok: { const: false }, outcome: { enum: ["error", "cancelled"] } }, required: ["code", "message", "error"] },
  ],
} as const;

function lineCount(text: string): number {
  return text ? (text.match(/\r\n|\r|\n/g)?.length ?? 0) + 1 : 0;
}
function jsonBytes(value: object): number { return Buffer.byteLength(JSON.stringify(value), "utf8"); }
export type AgentTextLimits = { maxBytes?: number; maxLines?: number; marker?: string };
/** Includes the marker in both budgets; a one-line preview uses an inline marker. */
export function boundedToolText(text: string, limits: AgentTextLimits = {}): { text: string; truncation?: AgentTextTruncation } {
  const maxBytes = Math.min(limits.maxBytes ?? AGENT_TEXT_MAX_BYTES, AGENT_TEXT_MAX_BYTES);
  const maxLines = Math.min(limits.maxLines ?? AGENT_TEXT_MAX_LINES, AGENT_TEXT_MAX_LINES);
  const marker = limits.marker ?? AGENT_PREVIEW_MARKER;
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || !Number.isSafeInteger(maxLines) || maxLines < 1) {
    throw new RangeError("Preview budgets must be positive safe integers.");
  }
  const originalBytes = Buffer.byteLength(text, "utf8"), originalLines = lineCount(text);
  if (originalBytes <= maxBytes && originalLines <= maxLines) return { text };
  const markerBytes = Buffer.byteLength(marker, "utf8");
  if (lineCount(marker) !== 1 || markerBytes > maxBytes) throw new RangeError("Preview budget cannot contain its explicit marker.");
  const separator = maxLines > 1 && maxBytes > markerBytes ? "\n" : "";
  const byteBudget = maxBytes - markerBytes - separator.length;
  const lineBudget = maxLines - (separator ? 1 : 0);
  let end = 0, usedBytes = 0, usedLines = 1, previousCR = false;
  for (const point of text) {
    const pointBytes = Buffer.byteLength(point, "utf8");
    const newLine = point === "\r" || (point === "\n" && !previousCR);
    if (usedBytes + pointBytes > byteBudget || usedLines + Number(newLine) > lineBudget) break;
    usedBytes += pointBytes; usedLines += Number(newLine); end += point.length;
    previousCR = point === "\r";
  }
  const prefix = text.slice(0, end).replace(/[\r\n]+$/, "");
  const output = prefix + (prefix ? separator : "") + marker;
  return { text: output, truncation: { truncated: true, reason: originalBytes > maxBytes ? "bytes" : "lines",
    originalBytes, originalLines, outputBytes: Buffer.byteLength(output, "utf8"), outputLines: lineCount(output), marker } };
}

function truncation(value: PreviewFields): AgentOutputTruncation {
  return value.truncation ?? (value.truncation = { fields: [], omittedFields: [] });
}
function omitted(value: PreviewFields, fields: string[]): void {
  if (!fields.length) return;
  const info = truncation(value);
  for (const field of fields) if (!info.omittedFields.includes(field)) info.omittedFields.push(field);
  value.previewNotice = `Preview omitted fields: ${info.omittedFields.join(", ")}. Exact authority is never shortened.`;
}
/** Select only declared fields before copying; an extra huge nested object never enters the output. */
function selectKnown<T extends PreviewFields>(raw: T, properties: object): T {
  const value = { ...raw };
  const extra: string[] = [];
  for (const key of Object.keys(value)) {
    if (!Object.hasOwn(properties, key)) {
      Reflect.deleteProperty(value, key);
      if (extra.length < 16) extra.push(boundedToolText(safeDisplayText(key), { maxBytes: 128, maxLines: 1 }).text);
    }
  }
  const copy = structuredClone(value);
  omitted(copy, extra);
  return copy;
}
const displayFields = ["prompt", "role", "body", "evidence", "interrupted", "description", "activeTool", "liveText", "error", "finalDiagnostic", "requestedOperation"] as const;
function trimPreviews(value: PreviewFields, summary = false): void {
  for (const field of displayFields) {
    const raw = value[field];
    if (raw === undefined) continue;
    const maxBytes = field === "requestedOperation" ? 512 : summary
      ? (field === "description" ? 256 : 192)
      : field === "liveText" ? 8192 : field === "prompt" ? 4096 : 2048;
    const maxLines = summary ? 1 : field === "liveText" ? 80 : field === "prompt" ? 50 : 12;
    const previous = value.truncation?.fields.find(entry => entry.field === field);
    const diagnostic = field === "error" || field === "finalDiagnostic";
    // Metadata is descriptive, never permission to bypass budgets. Reuse an
    // already bounded preview only when its actual bytes/lines/marker agree.
    const previousValid = previous && previous.outputBytes === Buffer.byteLength(raw, "utf8")
      && previous.outputLines === lineCount(raw) && safeDisplayText(raw) === raw
      && (diagnostic
        ? raw.length <= 1024 && previous.reason === "diagnostic" && raw.endsWith("… [diagnostic truncated]")
        : Buffer.byteLength(raw, "utf8") <= maxBytes && lineCount(raw) <= maxLines
          && raw.endsWith(field === "liveText" ? AGENT_LIVE_PREVIEW_MARKER : AGENT_PREVIEW_MARKER));
    if (previousValid && !(summary && field === "liveText")) continue;
    if (previous) value.truncation!.fields = value.truncation!.fields.filter(entry => entry.field !== field);
    if (summary && field === "liveText") {
      delete value.liveText;
      truncation(value).fields.push({ field, truncated: true, reason: "summary", originalBytes: Buffer.byteLength(raw, "utf8"),
        originalLines: lineCount(raw), outputBytes: 0, outputLines: 0, marker: "[status summary; the answer arrives with the Session Result]" });
      omitted(value, [field]);
      continue;
    }
    let text = raw;
    if (field === "error" || field === "finalDiagnostic") {
      const safe = safeDisplayText(raw);
      text = boundedFinalDiagnostic(safe) ?? "";
      // The existing diagnostic helper counts UTF-16 units. Repair only its cut boundary.
      if (safe.length > 1000 && /[\ud800-\udbff]/.test(safe[999]) && /[\udc00-\udfff]/.test(safe[1000])) {
        text = text.slice(0, 999) + text.slice(1000);
      }
      if (safe.length > 1000) truncation(value).fields.push({ field, truncated: true, reason: "diagnostic",
        originalBytes: Buffer.byteLength(safe, "utf8"), originalLines: lineCount(safe),
        outputBytes: Buffer.byteLength(text, "utf8"), outputLines: lineCount(text), marker: "… [diagnostic truncated]" });
      value[field] = text;
      continue;
    }
    const bounded = boundedToolText(field === "requestedOperation" ? safeDisplayText(text) : text, {
      maxBytes, maxLines, ...(field === "liveText" ? { marker: AGENT_LIVE_PREVIEW_MARKER } : {}),
    });
    value[field] = bounded.text;
    if (bounded.truncation) truncation(value).fields.push({ field, ...bounded.truncation });
  }
}
function sessionView(raw: AgentSessionView, summary = false): AgentSessionView {
  const view = selectKnown(raw, sessionProperties);
  if (view.stopReason !== undefined) view.stopReason = normalizeFinalStopReason(view.stopReason);
  trimPreviews(view, summary);
  return view;
}
function definitionView(raw: AgentDefinitionView): AgentDefinitionView {
  const view = selectKnown(raw, definitionProperties);
  trimPreviews(view, true);
  return view;
}
function wrap(text: string, data: AgentToolData): AgentResult {
  return { content: [{ type: "text", text }], details: data, structuredContent: data, ...(data.ok ? {} : { isError: true }) };
}

const exactContextFields = ["session", "name", "agent", "status", "scope", "model", "grant", "tools", "source", "cwd", "projectCwd",
  "workspacePath", "sessionDir", "currentTaskId", "assignment", "dispatched", "controlOutcome", "pendingIntent", "nextActor"] as const;
function limitFailure(operation: AgentOutputOperation, context: Omit<AgentFailureContext, "outcome">, omittedFields: string[] = [], offset?: number): AgentResult {
  const message = "Agent management output exceeds its limit; exact authority fields cannot be shortened. This is a readback limit, not a process outcome.";
  const data: AgentFailureData = { operation, ok: false, outcome: "error", state: context.state ?? "unknown",
    nextActor: context.nextActor ?? "caller", code: "output-limit", message, error: message,
    limit: { maxTextBytes: AGENT_TEXT_MAX_BYTES, maxTextLines: AGENT_TEXT_MAX_LINES, maxJsonBytes: AGENT_JSON_MAX_BYTES,
      omittedFields: [...omittedFields], ...(offset !== undefined ? { offset } : {}) } };
  for (const field of exactContextFields) {
    const value = context[field];
    if (value === undefined) continue;
    const candidate = { ...data, [field]: value };
    if (jsonBytes(candidate) <= AGENT_JSON_MAX_BYTES - 1024) Object.assign(data, { [field]: structuredClone(value) });
    else if (!data.limit!.omittedFields.includes(field)) data.limit!.omittedFields.push(field);
  }
  return wrap(message, data);
}

/** Parent supplies observed state/control facts. Unknown actions become `invalid`, never guessed `start`. */
export function createAgentFailure(operation: string, code: AgentErrorCode, message: string, context: AgentFailureContext = {}): AgentResult {
  const knownOperation = CHILD_OPERATIONS.find(value => value === operation) ?? "invalid";
  const data: AgentFailureData = { ...context, operation: knownOperation, ok: false,
    outcome: context.outcome ?? (code === "cancelled" ? "cancelled" : "error"), state: context.state ?? "unknown",
    nextActor: context.nextActor ?? "caller", code, message, error: message, ...(knownOperation === "invalid" && operation !== "invalid" ? { requestedOperation: operation } : {}) };
  trimPreviews(data);
  data.message = data.error!;
  return createAgentResult(data.message, data);
}

/** Normalize known receipt metadata, not lifecycle semantics. No state or acknowledgement is inferred here. */
export function createAgentResult(body: string, raw: AgentToolData): AgentResult {
  const data = selectKnown(raw, AGENT_TOOL_OUTPUT_SCHEMA.properties);
  trimPreviews(data);
  if (data.operation === "list" && data.ok) {
    data.sessions = data.sessions.map(view => sessionView(view, true));
    data.agents = data.agents.map(view => sessionView(view, true));
    data.definitions = data.definitions.map(definitionView);
  }
  if (!data.ok) data.message = data.error;
  const bounded = boundedToolText(safeDisplayText(body));
  if (bounded.truncation) truncation(data).text = bounded.truncation;
  // A single record may have very large exact authority. Only display previews can be omitted.
  for (const field of displayFields) {
    if (jsonBytes(data) <= AGENT_JSON_MAX_BYTES) break;
    if (field === "error" && !data.ok) continue;
    // Required successful input previews may be shortened, never removed. If
    // exact grants plus the preview cannot fit, return explicit output-limit.
    if (field === "prompt" && data.ok && data.operation === "input") continue;
    if (data[field] !== undefined) { delete data[field]; omitted(data, [field]); }
  }
  if (jsonBytes(data) > AGENT_JSON_MAX_BYTES) return limitFailure(data.operation, data);
  return wrap(bounded.text, data);
}

function readback(view: AgentSessionView): string[] {
  return [
    ...(view.activeTool ? [`active tool · ${safeDisplayText(view.activeTool)}`] : []),
    ...(view.resultKind === "unanswered" && view.unansweredReason
      ? [`unanswered · ${unansweredSummary({ reason: view.unansweredReason, stopReason: view.stopReason })}`,
        ...(view.finalDiagnostic ? [`diagnostic · ${view.finalDiagnostic}`] : []),
        ...(view.liveText ? [`output · ${view.liveText}`] : [])]
      : view.liveText ? [`${view.sequenceEnded ? "result" : "output"} · ${view.liveText}`] : []),
    ...(view.error ? [`error · ${view.error}`] : []),
    ...(view.previewNotice ? [`preview · ${view.previewNotice}`] : []),
  ];
}
/** One known record; preserves exact authority or explicitly refuses to represent it within the budgets. */

export type AgentListOptions = { offset?: number; limit?: number };
const LIST_NOTICE = "Status summary only; a running child's complete answer arrives with its Session Result.";
function listData(sessions: AgentSessionView[], definitions: AgentDefinitionView[], totalSessions: number, totalDefinitions: number,
  offset: number, limit: number): AgentListedData {
  const total = totalSessions + totalDefinitions, returned = sessions.length + definitions.length;
  const remaining = total - offset - returned;
  return { operation: "list", ok: true, outcome: "listed", state: "read-only", nextActor: "caller", count: totalSessions, total, totalDefinitions,
    omitted: total - returned, agents: sessions, sessions, definitions, previewNotice: LIST_NOTICE,
    page: { offset, limit, returned, omitted: total - returned, before: offset, remaining, totalSessions, totalDefinitions,
      omittedSessions: totalSessions - sessions.length, omittedDefinitions: totalDefinitions - definitions.length,
      ...(remaining ? { nextOffset: offset + returned } : {}) } };
}
function listText(data: AgentListedData): string {
  return ["sessions · live and stopped · status summary",
    ...(data.sessions.length ? data.sessions.flatMap(view => [
      `- @${view.name} · ${view.status} · ${view.session ?? "(no incarnation)"}`, ...readback(view),
    ]) : ["child · none on this page"]),
    "definitions · offline",
    ...(data.definitions.length ? data.definitions.map(view =>
      `- @${view.name} · offline · ${view.scope}${view.source ? ` · ${view.source}` : ""}${view.description ? ` · ${view.description}` : ""}`)
      : ["child · none on this page"]),
    `preview · ${LIST_NOTICE}`,
    `page · offset ${data.page.offset} · returned ${data.page.returned}/${data.total} · omitted ${data.page.omitted}`
      + (data.page.nextOffset !== undefined ? ` · nextOffset ${data.page.nextOffset}` : " · end"),
  ].map(safeDisplayText).join("\n");
}
/** Caller-supplied order, sessions followed by definitions. Only returned records consume the cursor. */
export function createAgentListPage(allSessions: readonly AgentSessionView[], allDefinitions: readonly AgentDefinitionView[],
  options: AgentListOptions = {}): AgentResult {
  const requestedOffset = options.offset ?? 0, requestedLimit = options.limit ?? AGENT_LIST_DEFAULT_LIMIT;
  if (!Number.isSafeInteger(requestedOffset) || requestedOffset < 0 || !Number.isSafeInteger(requestedLimit) || requestedLimit < 1) {
    return createAgentFailure("list", "invalid-parameters", "List offset must be a non-negative integer and limit must be a positive integer.", { state: "read-only" });
  }
  const total = allSessions.length + allDefinitions.length;
  const offset = Math.min(requestedOffset, total), limit = Math.min(requestedLimit, AGENT_LIST_MAX_LIMIT);
  const sessions: AgentSessionView[] = [], definitions: AgentDefinitionView[] = [];
  let data = listData(sessions, definitions, allSessions.length, allDefinitions.length, offset, limit);
  let text = listText(data);
  for (let index = offset; index < total && index < offset + limit; index++) {
    const isSession = index < allSessions.length;
    const view = isSession ? sessionView(allSessions[index], true) : definitionView(allDefinitions[index - allSessions.length]);
    const candidateSessions = isSession ? [...sessions, view as AgentSessionView] : sessions;
    const candidateDefinitions = isSession ? definitions : [...definitions, view as AgentDefinitionView];
    const candidate = listData(candidateSessions, candidateDefinitions, allSessions.length, allDefinitions.length, offset, limit);
    const candidateText = listText(candidate);
    if (jsonBytes(candidate) > AGENT_JSON_MAX_BYTES || Buffer.byteLength(candidateText, "utf8") > AGENT_TEXT_MAX_BYTES
      || lineCount(candidateText) > AGENT_TEXT_MAX_LINES) {
      if (data.page.returned === 0) return limitFailure("list", { ...view, status: isSession ? (view as AgentSessionView).status : undefined,
        state: "read-only" }, [], index);
      break;
    }
    if (isSession) sessions.push(view as AgentSessionView); else definitions.push(view as AgentDefinitionView);
    data = candidate; text = candidateText;
  }
  return wrap(text, data);
}

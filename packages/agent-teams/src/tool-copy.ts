/**
 * Human-facing transcript copy for the coordination tools.
 *
 * The model keeps the exact handles it needs — `session:<name>:<spawn>`,
 * `work:<uuid>`, `direct:<uuid>` — in tool content. A person reading the
 * transcript should instead see the Agent name, the text they passed, the Work
 * subject, and a plain state word. `plainText` is the safety net for free-form
 * strings (errors, harness events) whose identifiers cannot be re-derived.
 */

import { contentDetailLines, detailField, displayText, fieldBlock, fieldLine, safeDisplayText, scrubHandles } from "@fradser/pi-kit";
import { resolveAgent } from "./agents.ts";
import { runningTeammateActivity } from "./activity.ts";
import { parseExactSessionRoute } from "./recipient.ts";
import { getTask, getTeammate } from "./state.ts";
import { resolveWorkerTools } from "./spawner.ts";
import type { BoardTask, Teammate } from "./types.ts";

/** One rendered lifecycle row: the collapsed line plus its expanded body. */
export interface CoordinationRow {
  subject: string;
  /** Replace the collapsed subject inline, retaining its semantic line breaks. */
  expandedSubject?: string;
  body: string[];
}

const COLLAPSED_TASK_LIMIT = 90;
/** A kickoff prompt is shown in full up to this size, then clipped. */
const FIELD_LIMIT = 2000;

/** Package resolver: a known Work handle becomes its subject. Only prefixed
 * handles are machine identifiers; a bare UUID can be a person's own text
 * (a commit, an id under review) and survives verbatim inside kit. */
function workHandle(handle: string): string | undefined {
  return getTask(handle)?.subject;
}

/** Scalar model text only: a renderer must not stringify an object argument
 * into the transcript, and identifiers become the words a person expects. */
export function plainText(value: unknown): string {
  return scrubHandles(value, workHandle)
    .replace(/"\s*"/g, "")
    .replace(/[ \t]+([.,;:!?])/g, "$1");
}

function collapse(value: unknown): string {
  return displayText(value).replace(/\s+/g, " ").trim();
}

function oneLine(value: unknown): string {
  return collapse(plainText(value));
}

function clipLines(value: unknown): string {
  return displayText(value).split("\n").map((line) => plainText(line)).join("\n");
}

function shortTask(value: unknown): string {
  const text = displayText(value);
  const firstLine = text.split("\n").map((l) => plainText(l).trim()).find(Boolean) ?? "";
  const line = collapse(firstLine);
  return line.length <= COLLAPSED_TASK_LIMIT ? line : `${line.slice(0, COLLAPSED_TASK_LIMIT - 1).trimEnd()}…`;
}

/** Array fields also arrive untyped from a model call. */
function strings(value: unknown): string[] {
  return (Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]).map((entry) => oneLine(entry)).filter(Boolean);
}

function labeled(label: string, value: unknown): string {
  return fieldLine(label, oneLine(value));
}

/** Multi-line field: the label heads the first line, the rest follow verbatim. */
function labeledBlock(label: string, value: unknown, limit = FIELD_LIMIT): string[] {
  return fieldBlock(label, clipLines(value), limit);
}

function bodyLines(value: unknown): string[] {
  return contentDetailLines({ content: [{ type: "text", text: clipLines(value) }] })
    .map((line) => dedupeSegments(collapse(line)))
    .filter(Boolean);
}

/** Scrubbing a Work id into its subject can repeat what the line already says. */
function dedupeSegments(line: string): string {
  const parts = line.split(" · ");
  return parts.filter((part, index) => parts.indexOf(part) === index).join(" · ");
}

const STATUS_WORDS: Record<string, string> = {
  starting: "starting",
  working: "working",
  idle: "idle",
  stopped: "stopped",
  pending: "pending",
  claimed: "claimed",
  completed: "completed",
  superseded: "superseded",
  sent: "sent",
  routed: "delivered",
  queued: "queued",
  "not-sent": "not delivered",
  "fresh-session-pending": "waiting for a fresh session",
  created: "created",
  assigned: "assigned",
  released: "released",
  reopened: "reopened",
  listed: "listed",
};

function stateWord(value: unknown): string {
  const key = oneLine(value);
  return STATUS_WORDS[key] ?? key.replace(/[_-]+/g, " ");
}

function workOf(teammate: Teammate | undefined, task?: BoardTask): string | undefined {
  const source = task ?? (teammate?.workId ? getTask(teammate.workId) : undefined);
  if (!source) return undefined;
  const owner = source.claimedBy ? ` · @${source.claimedBy}` : "";
  return `${shortTask(source.subject)} · ${stateWord(source.status)}${owner}`;
}

// ── agent ─────────────────────────────────────────────────────────

export interface AgentRowArgs {
  action?: string;
  name?: string;
  prompt?: string;
  session?: string;
  model?: string;
  resources?: string[];
  verify?: string;
  fork?: boolean;
  definition?: {
    description?: string;
    tools?: string[];
    model?: string;
    verify?: string;
    worktree?: boolean;
    persist?: boolean;
    persistScope?: string;
  };
}

function agentName(args: AgentRowArgs, details: unknown): string {
  if (args.name) return args.name;
  const route = detailField<{ id?: string }>(details, "session")?.id ?? args.session ?? "";
  return parseExactSessionRoute(route)?.name ?? "agent";
}

function roleLine(args: AgentRowArgs, name: string): string | undefined {
  const generated = args.definition;
  if (generated?.description) {
    return generated.persist
      ? `${oneLine(generated.description)} · saved as ${generated.persistScope ?? "project-local"} role`
      : `${oneLine(generated.description)} · new role for this session`;
  }
  const resolved = resolveAgent(name);
  return resolved ? `${oneLine(resolved.description) || "role"} · ${resolved.scope} role` : undefined;
}

function agentStateWord(args: AgentRowArgs, teammate: Teammate | undefined, details: unknown, flags: { isError?: boolean; isPartial?: boolean }): string {
  if (flags.isError) return "failed";
  const action = args.action ?? "agent";
  const live = teammate ? stateWord(teammate.status) : undefined;
  if (flags.isPartial) {
    if (action === "stop") return "stopping";
    if (action === "inspect") return live ?? "checking";
    return "starting";
  }
  if (action === "inspect") {
    if (teammate?.status === "working") return "working";
    const sessions = detailField<Array<{ status?: string }>>(details, "sessions");
    const sessionStatus = sessions?.[0]?.status;
    if (sessionStatus) return stateWord(sessionStatus);
    return live ?? "no living session";
  }
  if (action === "stop") return "stopped";
  return "started";
}

/** One `agent` tool row: who acted, what state they reached, and the task text. */
export function agentRow(
  args: AgentRowArgs,
  details: unknown,
  flags: { isError?: boolean; isPartial?: boolean } = {},
): CoordinationRow {
  const name = agentName(args, details);
  const teammate = getTeammate(name);
  const action = args.action ?? "agent";
  let task: string | undefined;
  if (action === "delegate") {
    task = args.prompt || (teammate?.workId ? getTask(teammate.workId)?.subject : undefined)
      || args.definition?.description || resolveAgent(name)?.description;
  } else if (action === "start") {
    task = args.definition?.description || resolveAgent(name)?.description;
  } else if (action === "inspect") {
    const sessions = detailField<Array<{ status?: string; workId?: string }>>(details, "sessions");
    const sessStatus = sessions?.[0]?.status ?? teammate?.status;
    const workId = sessions?.[0]?.workId ?? teammate?.workId;
    if ((sessStatus === "working" || teammate?.status === "working") && workId) {
      task = getTask(workId)?.subject;
    }
  }
  const subject = [`@${name}`, agentStateWord(args, teammate, details, flags), task ? shortTask(task) : ""]
    .filter(Boolean)
    .join(" · ");
  return { subject, body: agentBody(args, name, teammate, details, flags) };
}

function agentBody(
  args: AgentRowArgs,
  name: string,
  teammate: Teammate | undefined,
  details: unknown,
  flags: { isError?: boolean },
): string[] {
  if (flags.isError) return [];
  const action = args.action ?? "agent";
  const work = workOf(teammate, teammate?.workId ? getTask(teammate.workId) : undefined);
  if (action === "inspect") {
    const sessions = detailField<Array<{ tools?: string[]; id?: string; status?: string; warning?: string; workId?: string }>>(details, "sessions");
    const sess = sessions?.[0];
    const status = sess?.status ?? teammate?.status;
    const isWorking = status === "working" || teammate?.status === "working";
    const sessionTools = sess?.tools ?? teammate?.tools;
    const warning = sess?.warning;
    return [
      ...(status ? [labeled("status", stateWord(status))] : []),
      ...(isWorking && teammate ? [labeled("now", shortTask(runningTeammateActivity(teammate)))] : []),
      ...(work && isWorking ? [labeled("work", work)] : []),
      ...(sessionTools ? [labeled("tools", sessionTools.join(", "))] : []),
      ...(warning ? [labeled("warning", warning)] : []),
    ];
  }
  if (action === "stop") {
    return bodyLines(detailField<string>(details, "body") ?? teammate?.error ?? "");
  }
  const role = roleLine(args, name);
  const resources = strings(args.resources);
  const granted = teammate?.tools ?? resolveWorkerTools(strings(args.definition?.tools).length > 0 ? strings(args.definition?.tools) : resolveAgent(name)?.tools);
  return [
    ...(role ? labeledBlock("role", role) : []),
    ...(args.prompt ? labeledBlock("task", args.prompt) : []),
    labeled("model", teammate?.model ?? args.model ?? args.definition?.model ?? "team default"),
    labeled("tools", granted.join(", ")),
    ...(teammate?.isolation === "worktree" ? [labeled("isolation", "dedicated git worktree")] : []),
    ...(teammate?.context === "fork" || args.fork ? [labeled("context", "forked from this session")] : []),
    ...(resources.length > 0 ? [labeled("resources", resources.join(", "))] : []),
    ...(() => {
      const verify = args.verify ?? resolveAgent(name)?.verify;
      return verify ? labeledBlock("verify", verify) : [];
    })(),
    ...(!args.prompt && work ? [labeled("work", work)] : []),
  ];
}

// ── work ──────────────────────────────────────────────────────────

/** One leader `work` row: the Work subject leads, identifiers never appear. */
export function leaderWorkRow(
  args: Record<string, unknown>,
  details: unknown,
  flags: { isError?: boolean } = {},
): CoordinationRow {
  const action = detailField<string>(details, "action") ?? String(args.action ?? "work");
  const works = detailField<Array<{ id: string; subject: string; state: string; claimedBy?: string }>>(details, "works");
  if (action === "list") {
    const items = Array.isArray(works) ? works : [];
    return {
      subject: `${items.length} work item${items.length === 1 ? "" : "s"}`,
      body: items.map((item) => `- ${shortTask(item.subject)} · ${stateWord(item.state)}${item.claimedBy ? ` · @${item.claimedBy}` : ""}`),
    };
  }
  const work = detailField<{ subject?: string; state?: string; resources?: string[] }>(details, "work");
  const referenced = [...strings(args.dependsOn), ...strings(args.supersedes)];
  const requested = typeof args.subject === "string" ? args.subject : undefined;
  const subject = requested ?? work?.subject
    ?? (typeof args.id === "string" ? getTask(args.id)?.subject : undefined)
    ?? referenced.map((id) => getTask(id)?.subject).find(Boolean)
    ?? "Work";
  const outcome = detailField<string>(details, "outcome") ?? action;
  const notified = strings(detailField<unknown>(details, "notifiedTeammates"));
  const assignment = detailField<{ owner?: string }>(details, "assignment");
  const superseded = strings(detailField<unknown>(details, "supersededWorkIds"));
  const workResources = strings(detailField<unknown>(work, "resources"));
  const stillRunning = detailField<string>(details, "holderStillRunning");
  return {
    subject: `${shortTask(subject)} · ${flags.isError ? "failed" : stateWord(outcome)}`,
    body: [
      ...(work?.state ? [labeled("state", stateWord(work.state))] : []),
      ...(stillRunning ? [labeled("risk", `@${stillRunning} was still working; an in-flight batch may still write inside the released scope`)] : []),
      ...(action === "create" || action === "supersede"
        ? [labeled("routing", notified.length > 0 ? notified.map((entry) => `@${entry}`).join(", ") : "no living teammate notified")]
        : []),
      ...(assignment?.owner ? [labeled("owner", `@${assignment.owner}`)] : []),
      ...(superseded.length > 0
        ? [labeled("replaces", superseded.map((id) => oneLine(getTask(id)?.subject ?? "Work")).join(", "))]
        : []),
      ...(workResources.length > 0 ? [labeled("resources", workResources.join(", "))] : []),
      ...(typeof args.reason === "string" ? labeledBlock("reason", args.reason) : []),
    ],
  };
}

// ── agent_event ───────────────────────────────────────────────────

/** One `agent_event` row: who receives it and what was actually said. */
export function messageRow(
  args: { to?: string; message?: string; intent?: string },
  details: unknown,
  options: { isError?: boolean } = {},
): CoordinationRow {
  const to = oneLine(detailField<string>(details, "to") ?? args.to ?? "leader").replace(/^@+/, "");
  const outcome = detailField<string>(details, "outcome");
  // Messages are literal readbacks, not prose to clean up. Only terminal
  // controls and runtime handles change; the shared renderer owns truncation.
  const message = scrubHandles(safeDisplayText(displayText(args.message)), workHandle);
  const prefix = [`to @${to}`, options.isError ? "failed" : outcome ? stateWord(outcome) : undefined]
    .filter(Boolean).join(" · ");
  return {
    subject: [prefix, collapse(message)].filter(Boolean).join(" · "),
    expandedSubject: [prefix, message].filter(Boolean).join(" · "),
    body: detailField<string>(details, "terminalReport") ? [labeled("note", "terminal report recorded for this Work")] : [],
  };
}

// ── worker surfaces ───────────────────────────────────────────────

/** One worker `work` row: the task subject leads, never the task id. */
export function workerWorkRow(
  args: { action?: string; id?: string },
  details: unknown,
  content: string,
  flags: { isError?: boolean } = {},
): CoordinationRow {
  const action = String(args.action ?? detailField<string>(details, "action") ?? "work");
  const owned = detailField<string>(details, "taskId") ?? detailField<string>(details, "id");
  const subject = detailField<string>(details, "subject") ?? (owned ? getTask(owned)?.subject : undefined);
  const outcome = detailField<string>(details, "outcome") ?? detailField<string>(details, "status");
  const leads = action === "claim" && !args.id
    ? "next claimable Work"
    : action === "list" || action === "submit" || action === "release"
      ? "current Work"
      : undefined;
  return {
    subject: `${shortTask(subject ?? leads ?? "Work")} · ${flags.isError ? "failed" : workerStateWord(action, outcome)}`,
    body: bodyLines(content).slice(1),
  };
}

const WORKER_QUEUE_WORDS: Record<string, string> = {
  claim: "claim queued",
  submit: "submission queued",
  release: "released",
  list: "listed",
};

function workerStateWord(action: string, outcome: string | undefined): string {
  if (outcome === "queued") return WORKER_QUEUE_WORDS[action] ?? "queued";
  return stateWord(outcome ?? action);
}

/** Render-ready body for a failed call, whose details never reach the renderer. */
export function failureBody(result: { content: Array<{ type: string; text?: string }> }): string[] {
  return bodyLines(result.content.find((part) => part.type === "text")?.text ?? "");
}

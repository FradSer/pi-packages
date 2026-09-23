/**
 * Teammate capabilities. A single addressed agent_event primitive covers
 * leader reports and peer mail. Task-list registration is shared by leader
 * and worker processes; claiming and submitting remain worker-only.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { truncateTail, type ExtensionAPI, type MessageEndEvent } from "@earendil-works/pi-coding-agent";
import { messageRow, workerWorkRow } from "./tool-copy.ts";
import { emptyToolCall, renderCoordinationRow, textOf } from "./tool-render.ts";
import { resolveRecipient } from "./recipient.ts";
import { appendInboxMessage, appendWorkerEvent, createTaskIntent, readBoardFile, readRoster } from "./statefile.ts";
import {
  AgentEventParams,
  LEADER_RECIPIENT,
  messageTitle,
  WorkerWorkToolParams,
  type BoardTask,
} from "./types.ts";

const BOARD_DISCLOSURE_TOOLS = ["work"] as const;
type BoardDisclosure = "none" | "notice" | "claimed";

export interface WorkerToolDisclosure {
  update(prompt: string): void;
  reset(): void;
}

function createWorkerToolDisclosure(pi: ExtensionAPI): WorkerToolDisclosure {
  let state: BoardDisclosure = "none";
  const apply = () => {
    if (typeof pi.getActiveTools !== "function" || typeof pi.setActiveTools !== "function") return;
    const active = pi.getActiveTools();
    const withoutBoardControls = active.filter((tool) => !BOARD_DISCLOSURE_TOOLS.includes(tool as typeof BOARD_DISCLOSURE_TOOLS[number]));
    const revealed = state === "notice" || state === "claimed" ? ["work"] : [];
    pi.setActiveTools([...withoutBoardControls, ...revealed]);
  };
  return {
    update(prompt) {
      const binding = workerBinding();
      const rosterEntry = binding
        ? readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker)
        : undefined;
      const assignment = rosterEntry?.assignment;
      // A superseded holder still owns cancellation authority and must be
      // able to acknowledge it; hiding work here strands its resource lease.
      if (binding && rosterEntry && rosterEntry.spawnId === binding.spawnId
        && rosterEntry.status !== "stopped" && assignment) {
        state = "claimed";
      } else if (!assignment && prompt.includes("=== BOARD NOTICE ===")) state = "notice";
      else state = "none";
      apply();
    },
    reset() {
      state = "none";
      apply();
    },
  };
}

export interface WorkerBinding {
  worker: string;
  spawnId: string;
  outbox: string;
  inbox: string;
  rosterFile: string;
  boardFile: string;
  claimsDir: string;
  submissionsDir: string;
}

const REQUIRED_ENV = [
  "PI_TEAMMATE_WORKER_NAME",
  "PI_TEAMMATE_SPAWN_ID",
  "PI_TEAMMATE_OUTBOX_FILE",
  "PI_TEAMMATE_INBOX_FILE",
  "PI_TEAMMATE_ROSTER_FILE",
  "PI_TEAMMATE_BOARD_FILE",
  "PI_TEAMMATE_CLAIMS_DIR",
  "PI_TEAMMATE_SUBMISSIONS_DIR",
] as const;

export function workerBinding(): WorkerBinding | undefined {
  const values = REQUIRED_ENV.map((name) => process.env[name]);
  if (values.some((value) => !value)) return undefined;
  const [worker, spawnId, outbox, inbox, rosterFile, boardFile, claimsDir, submissionsDir] = values as string[];
  return { worker, spawnId, outbox, inbox, rosterFile, boardFile, claimsDir, submissionsDir };
}

function loadBoardTasks(binding: WorkerBinding): BoardTask[] {
  const board = readBoardFile(binding.boardFile);
  return Object.values(board?.tasks ?? {}).sort((a, b) => a.id.localeCompare(b.id));
}

function dependenciesMet(task: BoardTask, tasks: Map<string, BoardTask>): boolean {
  return task.dependsOn.every((dep) => tasks.get(dep)?.status === "completed");
}

function taskCounts(tasks: BoardTask[], byId: Map<string, BoardTask>): string {
  const counts = { pending: 0, claimed: 0, completed: 0, superseded: 0 };
  for (const task of tasks) counts[task.status] += 1;
  const claimable = tasks.filter((task) => task.status === "pending" && !task.recoveryRequired && dependenciesMet(task, byId)).length;
  return `tasks=${tasks.length} · pending=${counts.pending} (${claimable} claimable) · claimed=${counts.claimed} · completed=${counts.completed} · superseded=${counts.superseded}`;
}

function resourcesConflict(left: readonly string[] | undefined, right: readonly string[] | undefined): boolean {
  return (left ?? []).some((a) => (right ?? []).some((b) => a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`)));
}

function claimRejection(binding: WorkerBinding, task: BoardTask): string | undefined {
  const self = readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker);
  if (self?.assignment) {
    const state = self.assignment.closed ? "closed pending leader reopen" : "active";
    return `You already own ${state} ${self.assignment.kind} assignment "${self.assignment.id}". Finish it through its matching protocol before claiming board work.`;
  }
  const conflict = readRoster(binding.rosterFile).find((entry) => entry.name !== binding.worker
    && entry.assignment && !entry.assignment.closed
    && resourcesConflict(task.resources, entry.assignment.resources));
  if (conflict) {
    return `Task "${task.id}" conflicts with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}".`;
  }
  return undefined;
}

function taskStatusLabel(task: BoardTask, tasks: Map<string, BoardTask>): string {
  if (task.status === "pending") return task.recoveryRequired ? "pending/recovery-required" : dependenciesMet(task, tasks) ? "pending/claimable" : "pending/blocked";
  return task.status;
}

export function renderTaskBoard(tasks: BoardTask[]): string {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const lines = [`BOARD · current session`, `SUMMARY · ${taskCounts(tasks, byId)}`];
  if (tasks.length === 0) return `${lines.join("\n")}\nTASKS\n(no tasks)`;
  lines.push("TASKS");
  for (const task of tasks) {
    const deps = task.dependsOn.length > 0
      ? ` · depends=${task.dependsOn.join(",")} (${dependenciesMet(task, byId) ? "met" : "blocked"})`
      : "";
    const holder = task.claimedBy ? ` · claimant=@${task.claimedBy}` : "";
    lines.push(`- ${task.id} · ${taskStatusLabel(task, byId)} · ${task.subject}${holder}${deps}`);
  }
  return lines.join("\n");
}

type AssistantResponse = Extract<MessageEndEvent["message"], { role: "assistant" }>;
type AutomaticResult = { status: "completed" | "failed"; body: string };

function executionResult(message?: AssistantResponse): AutomaticResult {
  if (message?.stopReason === "error" || message?.stopReason === "aborted") {
    return { status: "failed", body: message.errorMessage?.trim() || `Execution ${message.stopReason} without a final answer.` };
  }
  if (message?.stopReason === "length") return { status: "failed", body: "Execution reached the response length limit without a complete final answer." };
  if (message && message.stopReason !== "stop" && message.stopReason !== "toolUse") {
    return { status: "failed", body: `Execution settled with an incomplete response (${message.stopReason}) and no final answer.` };
  }
  const body = message?.content.filter((part) => part.type === "text").map((part) => part.text).join("\n") ?? "";
  if (message?.stopReason === "stop" && !message.content.some((part) => part.type === "toolCall") && body.trim()) {
    return { status: "completed", body };
  }
  return { status: "failed", body: "Execution settled without a final answer." };
}

function automaticResultBody(binding: WorkerBinding, assignmentId: string, body: string): string {
  if (Buffer.byteLength(JSON.stringify(body), "utf-8") <= 48 * 1024) return body;
  const key = createHash("sha256").update(binding.spawnId).update("\0").update(assignmentId).digest("hex");
  const file = path.join(path.dirname(binding.outbox), `${key}.result.txt`);
  const temporary = `${file}.${process.pid}.tmp`;
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  try {
    fs.writeFileSync(temporary, body, { encoding: "utf-8", mode: 0o600 });
    fs.renameSync(temporary, file);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
  const preview = truncateTail(body, { maxBytes: 8 * 1024, maxLines: 200 });
  return `${preview.content}\n\n[Result truncated; ${preview.totalBytes} bytes total]\nFull result: ${file}`;
}

function createWorkerReports(pi: ExtensionAPI) {
  const initial = workerBinding();
  const initialSelf = initial ? readRoster(initial.rosterFile).find((entry) => entry.name === initial.worker && entry.spawnId === initial.spawnId) : undefined;
  const initialAssignment = initialSelf?.assignment;
  let assignmentId = initialAssignment?.id;
  let taskId = initialSelf?.currentTaskId;
  let reportClosed = initialAssignment?.closed === true;
  let terminalOutcome: "completed" | "failed" | undefined;
  let pending: { binding: WorkerBinding; assignmentId: string; timestamp: number; awaitingFinal?: boolean; outcome?: AutomaticResult } | undefined;
  const finalizedMessages = new WeakSet<AssistantResponse>();
  const currentAssignment = (binding: WorkerBinding) => {
    const self = readRoster(binding.rosterFile)
      .find((entry) => entry.name === binding.worker && entry.spawnId === binding.spawnId);
    const assignment = self?.assignment;
    return !reportClosed && self?.spawnId === binding.spawnId && self.status !== "stopped"
      && assignment && assignment.id === assignmentId && !assignment.closed ? assignment : undefined;
  };
  const close = (outcome: "completed" | "failed") => {
    reportClosed = true;
    terminalOutcome = outcome;
    pending = undefined;
  };
  const authorize = (binding: WorkerBinding, cancellation = false) => {
    const sameBinding = initial && binding.worker === initial.worker && binding.spawnId === initial.spawnId
      && binding.outbox === initial.outbox && binding.rosterFile === initial.rosterFile;
    const self = readRoster(binding.rosterFile)
      .find((entry) => entry.name === binding.worker && entry.spawnId === binding.spawnId);
    if (!sameBinding || !self || self.status === "stopped") {
      throw new Error("Work authority rejected: this is not the bound living worker incarnation.");
    }
    if (self.assignment?.id !== assignmentId || (taskId !== undefined && self.currentTaskId !== taskId)) {
      throw new Error("Work authority rejected: this turn belongs to a different assignment. Wait for its fresh assignment marker.");
    }
    const cancelled = cancellation && assignmentId && self.currentTaskId
      && (self.assignment?.closed || loadBoardTasks(binding).some((task) => task.id === self.currentTaskId && task.status === "superseded"));
    if ((reportClosed || self.assignment?.closed) && !(cancelled && terminalOutcome !== "failed")) {
      throw new Error("Leader report rejected: this assignment already has a terminal report or is closed. Stop; no repeated acknowledgment is required.");
    }
    return { assignmentId, taskId: taskId ?? self.currentTaskId };
  };
  pi.on("message_start", ({ message }) => {
    const binding = workerBinding();
    if (!binding) return;
    if (message.role === "user") {
      const content = message.content;
      const text = typeof content === "string" ? content : content.filter((part) => part.type === "text").map((part) => part.text).join("\n");
      const marker = /^\[agent-teams-assignment:([^\n]+)\]\n/.exec(text);
      const self = readRoster(binding.rosterFile)
        .find((entry) => entry.name === binding.worker && entry.spawnId === binding.spawnId);
      const current = self?.assignment;
      if (marker) {
        const id = marker[1] === "none" ? undefined : marker[1];
        if (id !== current?.id) return;
        if (id !== assignmentId) {
          reportClosed = current?.closed === true;
          terminalOutcome = undefined;
        }
        assignmentId = id;
        taskId = self?.currentTaskId;
        pending = undefined;
      } else if (!current) {
        // The harness retired this attempt without a replacement marker: this is a
        // fresh unassigned turn (peer mail, board notice, ordinary discussion).
        // Holding the previous terminal state here would dead-end the worker.
        assignmentId = undefined;
        taskId = undefined;
        reportClosed = false;
        terminalOutcome = undefined;
        pending = undefined;
      }
      const assignment = currentAssignment(binding);
      if (assignment) pending = { binding, assignmentId: assignment.id, timestamp: message.timestamp };
    } else if (message.role === "assistant" && pending && message.timestamp >= pending.timestamp) {
      pending.timestamp = message.timestamp;
      pending.awaitingFinal = true;
      pending.outcome = undefined;
    }
  });
  pi.on("agent_start", () => {
    if (pending) {
      pending.outcome = undefined;
      pending.awaitingFinal = false;
    }
  });
  pi.on("message_end", ({ message }) => {
    if (message.role !== "assistant" || !pending?.awaitingFinal || message.timestamp < pending.timestamp
      || finalizedMessages.has(message) || !currentAssignment(pending.binding)) return;
    finalizedMessages.add(message);
    pending.timestamp = message.timestamp;
    pending.awaitingFinal = false;
    pending.outcome = executionResult(message);
  });
  pi.on("agent_settled", (_event, ctx) => {
    if (!pending || !ctx.isIdle()) return;
    const binding = workerBinding();
    if (!binding || binding.worker !== pending.binding.worker || binding.spawnId !== pending.binding.spawnId
      || binding.outbox !== pending.binding.outbox || pending.assignmentId !== assignmentId || !currentAssignment(binding)) return;
    const result = pending.outcome ?? executionResult();
    appendWorkerEvent(binding.outbox, {
      id: randomUUID(), type: "message", worker: binding.worker, spawnId: binding.spawnId,
      assignmentId: pending.assignmentId, timestamp: Date.now(), status: result.status,
      body: automaticResultBody(binding, pending.assignmentId, result.body),
    });
    close(result.status);
  });
  return {
    close,
    authorize,
    send(binding: WorkerBinding, body: string, status: import("./types.ts").WorkerReportEvent["status"]) {
      const authority = authorize(binding, status === "failed");
      appendWorkerEvent(binding.outbox, {
        assignmentId: authority.assignmentId, id: randomUUID(), type: "message",
        worker: binding.worker, spawnId: binding.spawnId, body, status, timestamp: Date.now(),
      });
      const isTerminal = status === "completed" || status === "failed";
      if (isTerminal) close(status);
      return isTerminal;
    },
    reset() { pending = undefined; },
  };
}

export function registerWorkerCapabilities(pi: ExtensionAPI): WorkerToolDisclosure {
  const disclosure = createWorkerToolDisclosure(pi);
  const reports = createWorkerReports(pi);
  pi.registerTool({
    name: "agent_event",
    promptSnippet: "Send an event or message to a participant",
    label: "Agent Event",
    description: "Communication-only interface across Leader, Worker, and Peers. Work completion is reported automatically after settlement or uses work action=submit.",
    parameters: AgentEventParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      return renderCoordinationRow(
        result, options, theme, context,
        "message",
        messageRow(context.args as { to?: string; message?: string }, result.details, { isError: context.isError }),
      );
    },
    async execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      const authority = reports.authorize(binding);
      if (!params.to || params.to === LEADER_RECIPIENT) {
        appendWorkerEvent(binding.outbox, {
          assignmentId: authority.assignmentId, id: randomUUID(), type: "message", worker: binding.worker, spawnId: binding.spawnId,
          body: params.message, status: params.intent ?? "inform", timestamp: Date.now(),
        });
        return {
          content: [{ type: "text", text: `MESSAGING\nREPORT · to=leader · intent=${params.intent ?? "inform"}\nNEXT · harness will deliver this message; Work completion is automatic or uses work submit` }],
          details: { to: LEADER_RECIPIENT, intent: params.intent ?? "inform", outcome: "queued" },
        };
      }
      const recipient = resolveRecipient(params.to, readRoster(binding.rosterFile));
      const to = recipient.name;
      if (to === binding.worker) throw new Error("You are already the recipient — no need to message yourself.");
      const recipientInbox = path.join(path.dirname(binding.inbox), `inbox-${encodeURIComponent(to)}.jsonl`);
      appendInboxMessage(recipientInbox, {
        id: randomUUID(),
        from: binding.worker,
        subject: messageTitle(params.message),
        body: params.message,
        ...(recipient.spawnId ? { toSpawnId: recipient.spawnId } : {}),
      });
      return {
        content: [{ type: "text", text: `MESSAGING\nQUEUED · to=@${to}\nNEXT · harness will route the inbox message into a recipient turn` }],
        details: { to, outcome: "queued", intent: params.intent ?? "inform" },
      };
    },
  });

  async function queueWorkClaim(id: string | undefined, presentation: "board" | "work") {
    const binding = workerBinding();
    if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
    // Claims pass the same attempt authority as sends and submissions: a closed or
    // terminal attempt must not queue new board work even when work is re-disclosed.
    reports.authorize(binding);
    const label = presentation === "work" ? "Work Item" : "Task";
    const empty = presentation === "work" ? "No claimable Work Item right now." : "No claimable task right now.";
    const race = presentation === "work" ? "All candidate Work Items were claimed in the race. Check Work again." : "All candidate tasks were claimed in the race. Check the board again.";
    const tasks = loadBoardTasks(binding);
    const byId = new Map(tasks.map((task) => [task.id, task]));
    const candidates = id
      ? tasks.filter((task) => task.id === id)
      : tasks.filter((task) => task.status === "pending" && !task.recoveryRequired && dependenciesMet(task, byId));
    if (candidates.length === 0) {
      // Say why nothing is claimable: a board whose only pending Work is held for
      // Leader recovery must not read as an ordinary empty board.
      const held = loadBoardTasks(binding).filter((task) => task.status === "pending" && task.recoveryRequired);
      if (!id && held.length > 0) {
        throw new Error(`No claimable ${label.toLowerCase()} right now. Held for explicit leader recovery: ${held.map((task) => task.id).join(", ")}.`);
      }
      throw new Error(id ? `${label} "${id}" was not found${presentation === "board" ? " on the board" : ""}.` : empty);
    }
    for (const task of candidates) {
      if (task.recoveryRequired) {
        if (id) throw new Error(`Work Item "${task.id}" requires explicit leader Work assignment after failure.`);
        continue;
      }
      if (task.status !== "pending" || !dependenciesMet(task, byId)) continue;
      const rejected = claimRejection(binding, task);
      if (rejected) {
        if (id) throw new Error(rejected);
        continue;
      }
      const won = createTaskIntent(binding.claimsDir, task.id, {
        taskId: task.id, worker: binding.worker, spawnId: binding.spawnId, timestamp: Date.now(),
      });
      if (won) {
        const content = presentation === "work"
          ? `WORK · current session\nCLAIM INTENT QUEUED · ${task.id} · ${task.subject}\nREQUESTER · @${binding.worker}\nNEXT · wait for harness claim acceptance before starting Work`
          : `BOARD · current session\nCLAIM INTENT QUEUED · ${task.id} · ${task.subject}\nREQUESTER · @${binding.worker}\nNEXT · wait for harness Claim accepted feedback; do not start work until it arrives`;
        const details = presentation === "work"
          ? { action: "claim", outcome: "queued", id: task.id, subject: task.subject, worker: binding.worker }
          : { taskId: task.id, subject: task.subject, worker: binding.worker };
        return { content: [{ type: "text" as const, text: content }], details };
      }
      if (id) throw new Error(`${label} "${task.id}" was claimed by someone else first.`);
    }
    throw new Error(race);
  }

  pi.registerTool({
    name: "work",
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const params = context.args as { action?: string; id?: string };
      return renderCoordinationRow(
        result, options, theme, context,
        "work",
        workerWorkRow(params, result.details, textOf(result), { isError: context.isError }),
      );
    },
    promptSnippet: "Claim pending Work or submit owned Work",
    label: "Work",
    description: "Queue a claim for pending Work or submit the current owned Work Item. The harness remains the authority for claim acceptance and completion.",
    parameters: WorkerWorkToolParams,
    execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      if (params.action === "list") {
        const tasks = loadBoardTasks(binding);
        const byId = new Map(tasks.map((task) => [task.id, task]));
        const lines = tasks.map((task) => `- ${task.id} · ${taskStatusLabel(task, byId)} · ${task.subject}`);
        return Promise.resolve({ content: [{ type: "text", text: `WORK · current session\nWORK ITEMS\n${lines.join("\n") || "(none)"}` }], details: { action: "list", outcome: "listed", count: tasks.length } });
      }
      if (params.action === "claim") return queueWorkClaim(params.id, "work");
      const self = readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker);
      if (!self?.assignment || !self.currentTaskId) throw new Error("You do not own a claimed Work Item.");
      if (params.action === "release") {
        return queueWorkSubmission({ taskId: self.currentTaskId, status: "failed", result: params.result, presentation: "work" });
      }
      return queueWorkSubmission({ taskId: self.currentTaskId, status: params.outcome === "success" ? "completed" : "failed", result: params.result, presentation: "work" });
    },
  });

  async function queueWorkSubmission(input: { taskId: string; status: "completed" | "failed"; result?: string; presentation: "board" | "work" }) {
    const binding = workerBinding();
    if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
    const authority = reports.authorize(binding, input.status === "failed");
    if (!authority.assignmentId || authority.taskId !== input.taskId) throw new Error("This turn does not own the submitted Work Item.");
    const assignmentId = authority.assignmentId;
    const won = createTaskIntent(binding.submissionsDir, input.taskId, {
      taskId: input.taskId, worker: binding.worker, spawnId: binding.spawnId, assignmentId,
      status: input.status, result: input.result, timestamp: Date.now(),
    });
    if (!won) throw new Error(`A submission for "${input.taskId}" is already pending.`);
    reports.close(input.status);
    disclosure.reset();
    const task = loadBoardTasks(binding).find((candidate) => candidate.id === input.taskId);
    const roleVerify = process.env.PI_TEAMMATE_VERIFY_DEFAULT?.trim();
    const verify = input.status === "completed"
      ? task?.verify
        ? "VERIFY · queued (task gate)"
        : roleVerify
          ? "VERIFY · queued (role gate)"
          : "VERIFY · none configured"
      : "VERIFY · skipped (failed submission)";
    const next = "NEXT · End this turn. The harness settles the outcome; do not repeat submission or cancellation acknowledgments.";
    const content = input.presentation === "work"
      ? `WORK · current session\nSUBMISSION INTENT QUEUED · ${input.taskId} · ${input.status === "completed" ? "success" : "failed"}\n${verify}\n${next}`
      : `BOARD · current session\nSUBMITTED · ${input.taskId} · ${input.status}\n${verify}\n${next}`;
    // The subject rides along in details: a worker process never hydrates the
    // leader's in-memory board, so its row cannot look the task up by itself.
    const details = input.presentation === "work"
      ? { action: "submit", outcome: "queued", id: input.taskId, subject: task?.subject, status: input.status === "completed" ? "success" : "failed", verify: Boolean(task?.verify || roleVerify) }
      : { taskId: input.taskId, subject: task?.subject, status: input.status, verify: Boolean(task?.verify || roleVerify) };
    return { content: [{ type: "text" as const, text: content }], details, terminate: true };
  }

  return {
    update: disclosure.update,
    reset() {
      disclosure.reset();
      reports.reset();
    },
  };
}

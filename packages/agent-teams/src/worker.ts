/**
 * Teammate capabilities. A single addressed send_message primitive covers
 * leader reports and peer mail. Task-list registration is shared by leader
 * and worker processes; claiming and submitting remain worker-only.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { truncateTail, type ExtensionAPI, type MessageEndEvent } from "@earendil-works/pi-coding-agent";
import { detailField, eventToolLifecycle } from "@fradser/pi-kit";
import { emptyToolCall, renderLifecycleResult } from "./tool-render.ts";
import { livingTeammates, listTasks } from "./state.ts";
import { resolveRecipient } from "./recipient.ts";
import { appendInboxMessage, appendWorkerEvent, createTaskIntent, readBoardFile, readRoster } from "./statefile.ts";
import {
  AgentEventParams,
  LEADER_RECIPIENT,
  messageTitle,
  SendMessageParams,
  TaskClaimParams,
  TaskListParams,
  TaskSubmitParams,
  type BoardTask,
} from "./types.ts";

const BOARD_DISCLOSURE_TOOLS = ["task_list", "task_claim", "task_submit"] as const;
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
    const revealed = state === "notice"
      ? ["task_list", "task_claim"]
      : state === "claimed"
        ? ["task_submit"]
        : [];
    pi.setActiveTools([...withoutBoardControls, ...revealed]);
  };
  return {
    update(prompt) {
      const binding = workerBinding();
      const rosterEntry = binding
        ? readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker)
        : undefined;
      const assignment = rosterEntry?.assignment;
      if (assignment?.kind === "board" && !assignment.closed) state = "claimed";
      else if (!assignment && prompt.includes("=== BOARD NOTICE ===")) state = "notice";
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
  const claimable = tasks.filter((task) => task.status === "pending" && dependenciesMet(task, byId)).length;
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
  if (task.status === "pending") return dependenciesMet(task, tasks) ? "pending/claimable" : "pending/blocked";
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

function renderRoster(roster: string): string {
  return `ROSTER\n${roster || "(none)"}`;
}

/** One registration shared by leader and worker; binding chooses the data source. */
export function registerTaskListTool(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "task_list",
    promptSnippet: "Read the shared task board",
    label: "Task Board",
    description: "Read the current session board as grouped task state plus a compact roster. Pending tasks with met dependencies are claimable.",
    parameters: TaskListParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const count = detailField<number>(result.details, "count") ?? 0;
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "board",
        `${count} task${count === 1 ? "" : "s"}`,
        { label: "listed" },
      ));
    },
    async execute() {
      const binding = workerBinding();
      const tasks = binding ? loadBoardTasks(binding) : listTasks();
      // Both sides get a roster tail: peer discovery is zero-cost for workers.
      const roster = binding
        ? readRoster(binding.rosterFile)
            .filter((entry) => entry.status !== "stopped")
            .map((entry) => `@${entry.name} (${entry.agent}, ${entry.status}${entry.assignment ? `, ${entry.assignment.kind} ${entry.assignment.id}` : ""})`)
            .join("\n")
        : livingTeammates().map((t) => `@${t.name} (${t.agent}, ${t.status}${t.currentTaskId ? `, task ${t.currentTaskId}` : ""})`).join("\n");
      const leaderHint = !binding && !roster && tasks.some((task) => task.status === "pending")
        ? "NEXT · leader: teammate_spawn; workers then use task_claim"
        : tasks.some((task) => task.status === "pending")
          ? "NEXT · workers use task_claim for pending/claimable tasks"
          : "NEXT · no claimable work";
      return {
        content: [{ type: "text", text: `${renderTaskBoard(tasks)}\n${leaderHint}\n\n${renderRoster(roster)}` }],
        details: { count: tasks.length },
      };
    },
  });
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
  const initialAssignment = initial ? readRoster(initial.rosterFile).find((entry) => entry.name === initial.worker)?.assignment : undefined;
  let assignmentId = initialAssignment?.id;
  let reportClosed = initialAssignment?.closed === true;
  let pending: { binding: WorkerBinding; assignmentId: string; timestamp: number; awaitingFinal?: boolean; outcome?: AutomaticResult } | undefined;
  const finalizedMessages = new WeakSet<AssistantResponse>();
  const currentDirect = (binding: WorkerBinding) => {
    const self = readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker);
    const assignment = self?.assignment;
    return !reportClosed && self?.spawnId === binding.spawnId && self.status !== "stopped"
      && assignment?.kind === "direct" && assignment.id === assignmentId && !assignment.closed ? assignment : undefined;
  };
  const close = () => {
    reportClosed = true;
    pending = undefined;
  };
  const reportAssignment = (binding: WorkerBinding) => {
    const current = readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker)?.assignment;
    if (current?.kind === "board" && current.id !== assignmentId) {
      assignmentId = current.id;
      reportClosed = false;
      pending = undefined;
    }
    if (reportClosed) throw new Error("Leader report rejected: this assignment already has a terminal report. Wait for an explicit leader assignment.");
    return assignmentId;
  };
  pi.on("message_start", ({ message }) => {
    const binding = workerBinding();
    if (!binding) return;
    if (message.role === "user") {
      const content = message.content;
      const text = typeof content === "string" ? content : content.filter((part) => part.type === "text").map((part) => part.text).join("\n");
      const marker = /^\[agent-teams-assignment:([^\n]+)\]\n/.exec(text);
      const current = readRoster(binding.rosterFile).find((entry) => entry.name === binding.worker)?.assignment;
      if (marker) {
        const id = marker[1] === "none" ? undefined : marker[1];
        if (id !== current?.id) return;
        if (id !== assignmentId || current?.kind === "board") reportClosed = current?.closed === true;
        assignmentId = id;
        pending = undefined;
      }
      const assignment = currentDirect(binding);
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
      || finalizedMessages.has(message) || !currentDirect(pending.binding)) return;
    finalizedMessages.add(message);
    pending.timestamp = message.timestamp;
    pending.awaitingFinal = false;
    pending.outcome = executionResult(message);
  });
  pi.on("agent_settled", (_event, ctx) => {
    if (!pending || !ctx.isIdle()) return;
    const binding = workerBinding();
    if (!binding || binding.worker !== pending.binding.worker || binding.spawnId !== pending.binding.spawnId
      || binding.outbox !== pending.binding.outbox || pending.assignmentId !== assignmentId || !currentDirect(binding)) return;
    const result = pending.outcome ?? executionResult();
    appendWorkerEvent(binding.outbox, {
      id: randomUUID(), type: "message", worker: binding.worker, spawnId: binding.spawnId,
      assignmentId: pending.assignmentId, timestamp: Date.now(), status: result.status,
      body: automaticResultBody(binding, pending.assignmentId, result.body),
    });
    close();
  });
  return {
    send(binding: WorkerBinding, body: string, status: import("./types.ts").WorkerReportEvent["status"]) {
      appendWorkerEvent(binding.outbox, {
        assignmentId: reportAssignment(binding), id: randomUUID(), type: "message",
        worker: binding.worker, spawnId: binding.spawnId, body, status, timestamp: Date.now(),
      });
      const isTerminal = status === "completed" || status === "failed";
      if (isTerminal) close();
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
    description: "Shared communication interface across Leader, Worker, and Peers. A direct assignment's final answer is reported automatically after Pi settles; no finalization call is needed. Explicit terminal reports remain available. Board tasks still require task_submit.",
    parameters: AgentEventParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const to = String((context.args as { to?: string }).to ?? "leader");

      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "message",
        detailField<"steered" | "queued">(result.details, "outcome") ?? "queued",
        { label: `to @${to}` },
      ));
    },
    async execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      if (!params.to || params.to === LEADER_RECIPIENT) {
        const isTerminal = reports.send(binding, params.message, params.status);
        return {
          content: [{ type: "text", text: isTerminal
            ? `MESSAGING\nREPORT · to=leader · status=${params.status}\nNEXT · harness will deliver this report`
            : `MESSAGING\nREPORT · to=leader · status=${params.status ?? "inform"}\nNEXT · continue the assignment; the direct final answer is reported automatically after Pi settles; board work still requires task_submit` }],
          details: { to: LEADER_RECIPIENT, status: params.status ?? "inform", outcome: "queued" },
          terminate: isTerminal,
        };
      }
      if (params.status === "completed" || params.status === "failed") throw new Error('terminal status is valid only when to="leader".');
      const to = resolveRecipient(params.to, readRoster(binding.rosterFile));
      if (to === binding.worker) throw new Error("You are already the recipient — no need to message yourself.");
      const recipientInbox = path.join(path.dirname(binding.inbox), `inbox-${encodeURIComponent(to)}.jsonl`);
      appendInboxMessage(recipientInbox, {
        id: randomUUID(),
        from: binding.worker,
        subject: messageTitle(params.message),
        body: params.message,
      });
      return {
        content: [{ type: "text", text: `MESSAGING\nQUEUED · to=@${to}\nNEXT · harness will route the inbox message into a recipient turn` }],
        details: { to, outcome: "queued", status: params.status ?? "inform" },
      };
    },
  });

  pi.registerTool({
    name: "send_message",
    promptSnippet: "Send a message to the leader or a teammate",
    label: "Send Message",
    description: "Use to=\"leader\" for reports; use a teammate name for direct peer mail. status is valid only for leader reports. A direct assignment's final answer is reported automatically after Pi settles; no finalization call is needed. Board tasks still require task_submit.",
    parameters: SendMessageParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const to = String((context.args as { to?: string }).to ?? "");

      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "message",
        detailField<"steered" | "queued">(result.details, "outcome") ?? "queued",
        { label: `to @${to}` },
      ));
    },
    async execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      if (params.to === LEADER_RECIPIENT) {
        const isTerminal = reports.send(binding, params.message, params.status);
        return {
          content: [{ type: "text", text: isTerminal
            ? `MESSAGING\nREPORT · to=leader · status=${params.status}\nNEXT · harness will deliver this report`
            : `MESSAGING\nREPORT · to=leader · status=${params.status ?? "in_progress"}\nNEXT · continue the assignment; the direct final answer is reported automatically after Pi settles; board work still requires task_submit` }],
          details: { to: LEADER_RECIPIENT, status: params.status ?? "in_progress", outcome: "queued" },
          terminate: isTerminal,
        };
      }
      if (params.status) throw new Error('status is valid only when to="leader".');
      const to = resolveRecipient(params.to, readRoster(binding.rosterFile));
      if (to === binding.worker) throw new Error("You are already the recipient — no need to message yourself.");
      const recipientInbox = path.join(path.dirname(binding.inbox), `inbox-${encodeURIComponent(to)}.jsonl`);
      appendInboxMessage(recipientInbox, {
        id: randomUUID(),
        from: binding.worker,
        subject: messageTitle(params.message),
        body: params.message,
      });
      return {
        content: [{ type: "text", text: `MESSAGING\nQUEUED · to=@${to}\nNEXT · harness will route the inbox message into a recipient turn` }],
        details: { to, outcome: "queued" },
      };
    },
  });

  registerTaskListTool(pi);

  pi.registerTool({
    name: "task_claim",
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const taskId = String((context.args as { taskId?: string }).taskId ?? "first claimable");
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "board",
        taskId,
        { label: "claim queued" },
      ));
    },
    promptSnippet: "Self-claim a pending board task",
    label: "Claim Task",
    description: "Atomically claim a pending task whose dependencies are met. Omit taskId to claim the first claimable task.",
    parameters: TaskClaimParams,
    async execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      const tasks = loadBoardTasks(binding);
      const byId = new Map(tasks.map((task) => [task.id, task]));
      const candidates = params.taskId
        ? tasks.filter((task) => task.id === params.taskId)
        : tasks.filter((task) => task.status === "pending" && dependenciesMet(task, byId));
      if (candidates.length === 0) {
        throw new Error(params.taskId ? `Task "${params.taskId}" was not found on the board.` : "No claimable task right now.");
      }
      for (const task of candidates) {
        if (task.status !== "pending" || !dependenciesMet(task, byId)) continue;
        const rejected = claimRejection(binding, task);
        if (rejected) {
          if (params.taskId) throw new Error(rejected);
          continue;
        }
        const won = createTaskIntent(binding.claimsDir, task.id, {
          taskId: task.id,
          worker: binding.worker,
          spawnId: binding.spawnId,
          timestamp: Date.now(),
        });
        if (won) {
          return {
            content: [{ type: "text", text: `BOARD · current session\nCLAIM INTENT QUEUED · ${task.id} · ${task.subject}\nREQUESTER · @${binding.worker}\nNEXT · wait for harness Claim accepted feedback; do not start work until it arrives` }],
            details: { taskId: task.id, subject: task.subject, worker: binding.worker },
          };
        }
        if (params.taskId) throw new Error(`Task "${task.id}" was claimed by someone else first.`);
      }
      throw new Error("All candidate tasks were claimed in the race. Check the board again.");
    },
  });

  pi.registerTool({
    name: "task_submit",
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const taskId = String((context.args as { taskId?: string }).taskId ?? "task");
      const status = String((context.args as { status?: string }).status ?? "submitted");
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "board",
        taskId,
        { label: status },
      ));
    },
    promptSnippet: "Submit a claimed task outcome",
    label: "Submit Task",
    description: "Submit a task you claimed. completed runs its verify gate; failed releases the task back to the board.",
    parameters: TaskSubmitParams,
    async execute(_toolCallId, params) {
      const binding = workerBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      const won = createTaskIntent(binding.submissionsDir, params.taskId, {
        taskId: params.taskId,
        worker: binding.worker,
        spawnId: binding.spawnId,
        status: params.status,
        result: params.result,
        timestamp: Date.now(),
      });
      if (!won) throw new Error(`A submission for "${params.taskId}" is already pending.`);
      disclosure.reset();
      const task = loadBoardTasks(binding).find((candidate) => candidate.id === params.taskId);
      const roleVerify = process.env.PI_TEAMMATE_VERIFY_DEFAULT?.trim();
      const verify = params.status === "completed"
        ? task?.verify
          ? "VERIFY · queued (task gate)"
          : roleVerify
            ? "VERIFY · queued (role gate)"
            : "VERIFY · none configured"
        : "VERIFY · skipped (failed submission)";
      const next = params.status === "completed"
        ? "NEXT · wait for the harness result"
        : "NEXT · task returns to pending";
      return {
        content: [{ type: "text", text: `BOARD · current session\nSUBMITTED · ${params.taskId} · ${params.status}\n${verify}\n${next}` }],
        details: { taskId: params.taskId, status: params.status, verify: Boolean(task?.verify || roleVerify) },
      };
    },
  });

  return {
    update: disclosure.update,
    reset() {
      disclosure.reset();
      reports.reset();
    },
  };
}

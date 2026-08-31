/**
 * Teammate capabilities. A single addressed send_message primitive covers
 * leader reports and peer mail. Task-list registration is shared by leader
 * and worker processes; claiming and submitting remain worker-only.
 */

import { randomUUID } from "node:crypto";
import * as path from "node:path";
import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { detailField, eventToolLifecycle } from "@fradser/pi-kit";
import { emptyToolCall, renderLifecycleResult } from "./tool-render.ts";
import { livingTeammates, listTasks } from "./state.ts";
import { appendInboxMessage, appendWorkerEvent, createTaskIntent, readBoardFile, readRoster } from "./statefile.ts";
import {
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

function livingRecipients(binding: WorkerBinding): Set<string> {
  return new Set(readRoster(binding.rosterFile)
    .filter((entry) => entry.status !== "stopped")
    .map((entry) => entry.name));
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

export function registerWorkerCapabilities(pi: ExtensionAPI): WorkerToolDisclosure {
  const disclosure = createWorkerToolDisclosure(pi);
  pi.registerTool({
    name: "send_message",
    promptSnippet: "Send a message to the leader or a teammate",
    label: "Send Message",
    description: "The only messaging primitive. Use to=\"leader\" for reports; use a teammate name for direct peer mail. status is valid only for leader reports.",
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
        appendWorkerEvent(binding.outbox, {
          id: randomUUID(),
          type: "message",
          worker: binding.worker,
          spawnId: binding.spawnId,
          body: params.message,
          status: params.status,
          timestamp: Date.now(),
        });
        return {
          content: [{ type: "text", text: params.status
            ? `MESSAGING\nREPORT · to=leader · status=${params.status}\nNEXT · harness will deliver this report`
            : 'MESSAGING\nREPORT · to=leader · status=in_progress\nNEXT · send status="completed" or status="failed" to end the assignment' }],
          details: { to: LEADER_RECIPIENT, status: params.status ?? "in_progress", outcome: "queued" },
          terminate: params.status === "completed" || params.status === "failed",
        };
      }
      if (params.status) throw new Error('status is valid only when to="leader".');
      if (params.to === binding.worker) throw new Error("You are already the recipient — no need to message yourself.");
      if (!livingRecipients(binding).has(params.to)) {
        throw new Error(`No living teammate named "${params.to}". Check the roster or ask the leader.`);
      }
      const recipientInbox = path.join(path.dirname(binding.inbox), `inbox-${encodeURIComponent(params.to)}.jsonl`);
      appendInboxMessage(recipientInbox, {
        id: randomUUID(),
        from: binding.worker,
        subject: messageTitle(params.message),
        body: params.message,
      });
      return {
        content: [{ type: "text", text: `MESSAGING\nQUEUED · to=@${params.to}\nNEXT · harness will route the inbox message into a recipient turn` }],
        details: { to: params.to, outcome: "queued" },
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

  return disclosure;
}

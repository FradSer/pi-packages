/**
 * Teammate capabilities. A single addressed send_message primitive covers
 * leader reports and peer mail. Task-list registration is shared by leader
 * and worker processes; claiming and submitting remain worker-only.
 */

import { randomUUID } from "node:crypto";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
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

export function renderTaskBoard(tasks: BoardTask[]): string {
  if (tasks.length === 0) return "(the task board is empty)";
  const byId = new Map(tasks.map((task) => [task.id, task]));
  return tasks.map((task) => {
    const deps = task.dependsOn.length > 0
      ? ` | depends on ${task.dependsOn.join(", ")} (${dependenciesMet(task, byId) ? "met" : "unmet"})`
      : "";
    const holder = task.claimedBy ? ` by @${task.claimedBy}` : "";
    const verify = task.verify ? ` | verify: ${task.verify}` : "";
    const description = task.description ? `\n    ${task.description.slice(0, 2000)}` : "";
    return `- [${task.id}] ${task.status}${holder}: ${task.subject}${deps}${verify}${description}`;
  }).join("\n");
}

/** One registration shared by leader and worker; binding chooses the data source. */
export function registerTaskListTool(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "task_list",
    promptSnippet: "Read the shared task board",
    label: "Task Board",
    description: "Read board tasks with status, dependencies, and verify gates. Pending tasks with met dependencies are claimable.",
    parameters: TaskListParams,
    async execute() {
      const binding = workerBinding();
      const tasks = binding ? loadBoardTasks(binding) : listTasks();
      // Both sides get a roster tail: peer discovery is zero-cost for workers.
      const roster = binding
        ? readRoster(binding.rosterFile)
            .filter((entry) => entry.status !== "stopped")
            .map((entry) => `@${entry.name} (${entry.agent}, ${entry.status})`)
            .join("\n")
        : livingTeammates().map((t) => `@${t.name} (${t.agent}, ${t.status}${t.currentTaskId ? `, task ${t.currentTaskId}` : ""})`).join("\n");
      return { content: [{ type: "text", text: `${renderTaskBoard(tasks)}\n\nRoster:\n${roster || "(none)"}` }], details: {} };
    },
  });
}

export function registerWorkerCapabilities(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "send_message",
    promptSnippet: "Send a message to the leader or a teammate",
    label: "Send Message",
    description: "The only messaging primitive. Use to=\"leader\" for reports; use a teammate name for direct peer mail. status is valid only for leader reports.",
    parameters: SendMessageParams,
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
        });
        return { content: [{ type: "text", text: "Queued message to leader." }], details: {} };
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
      return { content: [{ type: "text", text: `Delivered to @${params.to}'s inbox.` }], details: {} };
    },
  });

  registerTaskListTool(pi);

  pi.registerTool({
    name: "task_claim",
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
        const won = createTaskIntent(binding.claimsDir, task.id, {
          taskId: task.id,
          worker: binding.worker,
          spawnId: binding.spawnId,
          timestamp: Date.now(),
        });
        if (won) {
          return { content: [{ type: "text", text: `You won [${task.id}] "${task.subject}". Submit with task_submit.` }], details: {} };
        }
        if (params.taskId) throw new Error(`Task "${task.id}" was claimed by someone else first.`);
      }
      throw new Error("All candidate tasks were claimed in the race. Check the board again.");
    },
  });

  pi.registerTool({
    name: "task_submit",
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
      return { content: [{ type: "text", text: `Submitted ${params.status} for [${params.taskId}].` }], details: {} };
    },
  });
}

import { randomUUID } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { appendWorkerEvent } from "./statefile";
import { TeammateMessageParams, type WorkerEvent } from "./types";

export interface WorkerBinding {
  worker: string;
  taskId: string;
  spawnId: string;
  outbox: string;
}

export function workerOutboxBinding(): WorkerBinding | undefined {
  const worker = process.env.PI_TEAMMATE_WORKER_NAME;
  const taskId = process.env.PI_TEAMMATE_TASK_ID;
  const spawnId = process.env.PI_TEAMMATE_SPAWN_ID;
  const outbox = process.env.PI_TEAMMATE_OUTBOX_FILE;
  return worker && taskId && spawnId && outbox ? { worker, taskId, spawnId, outbox } : undefined;
}

export function isWorkerEvent(value: unknown): value is WorkerEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<WorkerEvent>;
  return typeof event.id === "string"
    && event.type === "message"
    && typeof event.worker === "string"
    && typeof event.spawnId === "string"
    && typeof event.subject === "string"
    && typeof event.body === "string"
    && (event.status === undefined || ["in_progress", "completed", "failed"].includes(event.status))
    && (event.data === undefined || typeof event.data === "object")
    ;
}

export function registerWorkerCapabilities(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Report progress or a final deliverable to the team leader",
    label: "Teammate Report",
    description: "Worker-only report channel. Send progress, blockers, or the final deliverable to the team leader. Set status=\"completed\" or \"failed\" for the terminal report.",
    parameters: TeammateMessageParams,
    async execute(_toolCallId, params) {
      const binding = workerOutboxBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      appendWorkerEvent(binding.outbox, {
        id: randomUUID(),
        type: "message",
        worker: binding.worker,
        spawnId: binding.spawnId,
        subject: params.subject,
        body: params.body,
        status: params.status,
        data: params.data,
      });
      const statusNote = params.status ? ` with status "${params.status}"` : "";
      return { content: [{ type: "text", text: `Queued report to team-leader${statusNote}.` }], details: {} };
    },
  });
}

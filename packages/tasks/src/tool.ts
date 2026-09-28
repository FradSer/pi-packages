/**
 * The `task` tool: the model-facing surface of the task board.
 *
 * Built on the store's public transitions rather than on a tool-local board, so
 * a single-session board and a spawned agent's board are the same code. The tool
 * owns two things only: validating input, and turning a store refusal into text
 * a model can act on.
 *
 * Two decisions here are what make the surface small.
 *
 * **The caller is the holder.** `take` and `complete` fill the holder from the
 * caller's own runtime identity, so there is no parameter through which a model
 * could name a different participant. That is why this file has no `assignee`
 * field at any action, and why a leader cannot hand work to a named agent: the
 * board states what must be done, and a participant raises a hand by taking it.
 *
 * **The action set is closed.** `create`, `list`, `update`, `complete`, and
 * `reopen` are the whole vocabulary. `assign`, `claim`, `release`, `abandon`,
 * `reclaim`, `submit`, `supersede`, and `get` are absent because each is either
 * a status transition the store already expresses, or a release the runtime
 * performs automatically.
 *
 * `list` reports per-task state a model would otherwise have to infer: who holds
 * it, whether a recovery hold is set, and what it depends on. Without those, a
 * pending task the model must not take looks identical to one it may.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  completeTaskWithOutcome,
  createTask,
  MAIN_SESSION,
  getTask,
  listTasks,
  reopenTask,
  takeTask,
  updateTask,
} from "./store.ts";
import type { BoardTask } from "./types.ts";
import type { WorkContext } from "./context.ts";

/** Tool ids this extension registers. Declared so a spawner can grant it
 *  without hardcoding a name, mirroring the subagents worker extension. */
export const TASK_CAPABILITY_TOOLS: readonly string[] = ["task"];

const STATUS_ENUM = ["pending", "in_progress", "completed", "superseded"] as const;

const stringArray = (description: string) => ({
  type: "array",
  items: { type: "string", minLength: 1 },
  description,
});

/** A flat schema, one object per action.
 *
 * Flat on purpose: the earlier tool nested `target.session` inside an object,
 * which some harnesses deliver as a JSON string, and a union root then forces a
 * tolerance layer in every consumer. The only nesting left is `definition`-shaped
 * data, which is genuinely structured. */
export const TASK_TOOL_PARAMS = {
  type: "object",
  properties: {
    action: {
      type: "string",
      enum: ["create", "list", "update", "complete", "reopen"],
      description: "create records a task; list reads the board; update edits content or takes a task; complete delivers an outcome; reopen returns a completed task to pending.",
    },
    subject: { type: "string", minLength: 1, description: "create: what must be done." },
    id: { type: "string", minLength: 1, description: "update, complete, reopen: the task id." },
    outcome: {
      type: "string",
      enum: ["success", "failed"],
      description: "complete: success delivers the result; failed returns the task to pending under a recovery hold and retains the blocker as evidence.",
    },
    result: { type: "string", description: "complete: the evidence for the outcome." },
    reason: {
      type: "string",
      description: "update: required to take a task under a recovery hold; reopen: why it is being reopened.",
    },
    description: { type: "string", description: "update: the full brief." },
    verify: { type: "string", description: "create/update: an independent completion gate, as a prompt rather than a command." },
    resources: stringArray("create/update: tags that cannot overlap while both tasks are in progress."),
    dependsOn: stringArray("create: task ids that must complete first."),
    supersedes: stringArray("create: task ids this one replaces atomically."),
    status: {
      type: "string",
      enum: ["in_progress", "pending"],
      description: "update: in_progress takes the task for you; pending returns a completed one.",
    },
    context: { type: "object", description: "update: per-task working context." },
    status_filter: {
      type: "array",
      items: { type: "string", enum: STATUS_ENUM },
      description: "list: restrict to these statuses.",
    },
    claimable: { type: "boolean", description: "list: restrict to tasks that can be taken right now." },
    limit: { type: "number", description: "list: cap the number of tasks returned." },
  },
  required: ["action"],
  additionalProperties: false,
} as const;

/** The call line is shown by the host, so the extension draws nothing itself. */
const emptyCall = () => undefined as never;

/** Bounded so a long-lived board cannot make one tool result the whole context. */
export const MAX_LISTED_TASKS = 40;

/** Per-task projection. Every field here is something a model would otherwise
 *  have to infer and get wrong; `recoveryRequired` in particular is the reason
 *  a pending task can be untakeable. */
function project(task: BoardTask) {
  return {
    id: task.id,
    subject: task.subject,
    ...(task.description ? { description: task.description } : {}),
    status: task.status,
    ...(task.claimedBy ? { holder: task.claimedBy } : {}),
    ...(task.recoveryRequired ? { recoveryRequired: true } : {}),
    ...(task.recoveryNote ? { recoveryNote: task.recoveryNote } : {}),
    dependsOn: task.dependsOn,
    ...(task.verify ? { verify: task.verify } : {}),
    ...(task.resources.length > 0 ? { resources: task.resources } : {}),
    ...(task.result ? { result: task.result } : {}),
    ...(task.supersededBy ? { supersededBy: task.supersededBy } : {}),
  };
}

interface TaskToolResult {
  content: Array<{ type: "text"; text: string }>;
  details: Record<string, unknown>;
  isError?: boolean;
}

function text(body: string): TaskToolResult["content"] {
  return [{ type: "text", text: body }];
}

function fail(message: string): TaskToolResult {
  return { content: text(message), details: { ok: false, error: message }, isError: true };
}

function ok(body: string, details: Record<string, unknown>): TaskToolResult {
  return { content: text(body), details: { ...details, ok: true } };
}

/** The caller's board identity. A spawned agent binds through the environment;
 *  anything else is the main session. Derived, never supplied by the model. */
export function callerIdentity(env: NodeJS.ProcessEnv = process.env): string {
  const worker = env.PI_TEAMMATE_WORKER_NAME?.trim();
  if (worker) return worker;
  return MAIN_SESSION;
}

export async function executeTaskTool(
  params: Record<string, unknown>,
  options: { env?: NodeJS.ProcessEnv; limit?: number } = {},
): Promise<TaskToolResult> {
  const me = callerIdentity(options.env);
  const limit = Math.min(options.limit ?? MAX_LISTED_TASKS, MAX_LISTED_TASKS);
  const str = (key: string): string | undefined => {
    const value = params[key];
    return typeof value === "string" && value.trim() ? value.trim() : undefined;
  };
  const list = (key: string): string[] | undefined => {
    const value = params[key];
    if (value === undefined) return undefined;
    if (!Array.isArray(value)) throw new Error(`Parameter "${key}" must be an array of strings.`);
    return value.map((entry) => {
      if (typeof entry !== "string" || !entry.trim()) throw new Error(`Parameter "${key}" must contain non-empty strings.`);
      return entry.trim();
    });
  };

  const action = str("action");

  if (action === "create") {
    const subject = str("subject");
    if (!subject) return fail("Creating a task requires a subject stating what must be done.");
    const dependsOn = list("dependsOn") ?? [];
    const unknown = dependsOn.filter((id) => !getTask(id));
    if (unknown.length > 0) return fail(`Unknown task id in dependsOn: ${unknown.join(", ")}.`);
    const created = createTask({
      subject,
      ...(str("description") ? { description: str("description") } : {}),
      dependsOn,
      ...(list("resources") ? { resources: list("resources") } : {}),
      ...(str("verify") ? { verify: str("verify") } : {}),
      ...(list("supersedes") ? { supersedes: list("supersedes") } : {}),
    });
    if (!created.ok) return fail(created.error);
    const replaced = created.superseded.map((task) => task.id);
    return ok(
      [
        `TASK · ${created.task.id} · ${created.task.status} · ${created.task.subject}`,
        ...(replaced.length > 0 ? [`REPLACED · ${replaced.join(", ")}`] : []),
        "NEXT · take it with update status=in_progress, or list to find work others have not taken",
      ].join("\n"),
      { action: "create", id: created.task.id, status: created.task.status, task: project(created.task), replaced },
    );
  }

  if (action === "list") {
    const statuses = list("status_filter");
    const claimableOnly = params.claimable === true;
    const matching = listTasks().filter((task) => {
      if (statuses && !statuses.includes(task.status)) return false;
      if (!claimableOnly) return true;
      return task.status === "pending"
        && !task.recoveryRequired
        && task.dependsOn.every((id) => getTask(id)?.status === "completed");
    });
    const shown = matching.slice(0, limit);
    return ok(
      shown.length === 0
        ? "TASK · none"
        : shown.map((task) => {
          const held = task.claimedBy ? ` · @${task.claimedBy}` : "";
          const hold = task.recoveryRequired ? " · recovery hold" : "";
          const deps = task.dependsOn.length > 0 ? ` · depends=${task.dependsOn.join(",")}` : "";
          return `- ${task.id} · ${task.status}${held}${hold}${deps} · ${task.subject}`;
        }).join("\n"),
      {
        action: "list",
        count: matching.length,
        shown: shown.length,
        truncated: matching.length > shown.length,
        tasks: shown.map(project),
      },
    );
  }

  if (action === "update") {
    const id = str("id");
    if (!id) return fail("Updating a task requires its id.");
    const status = str("status");
    if (status === "in_progress") {
      const taken = takeTask(id, me, { ...(str("reason") ? { reason: str("reason") } : {}) });
      if (!taken.ok) return fail(taken.reason);
      return ok(`TASK · ${id} · in_progress · @${me}`, { action: "take", id, status: taken.task.status, task: project(taken.task) });
    }
    if (status === "pending") {
      const reopened = reopenTask(id);
      if (!reopened.ok) return fail(reopened.reason);
      return ok(`TASK · ${id} · pending · reopened`, { action: "reopen", id, status: reopened.task.status, task: project(reopened.task) });
    }
    const patch: Parameters<typeof updateTask>[1] = {
      ...(params.description !== undefined ? { description: str("description") ?? "" } : {}),
      ...(params.verify !== undefined ? { verify: str("verify") ?? "" } : {}),
      ...(params.resources !== undefined ? { resources: list("resources") ?? [] } : {}),
      ...(params.context !== undefined ? { context: params.context as WorkContext } : {}),
    };
    if (Object.keys(patch).length === 0) {
      return fail("Update a task with status, or with at least one of description, verify, resources, context.");
    }
    const updated = updateTask(id, patch);
    if (!updated.ok) return fail(updated.reason);
    return ok(`TASK · ${id} · updated`, { action: "update", id, status: updated.task.status, task: project(updated.task) });
  }

  if (action === "complete") {
    const id = str("id");
    if (!id) return fail("Completing a task requires its id.");
    const outcome = str("outcome");
    if (outcome !== "success" && outcome !== "failed") {
      return fail("outcome is required and must be success or failed. A blocker recorded as an ordinary answer is not a failure.");
    }
    const delivered = completeTaskWithOutcome(id, me, outcome, str("result"));
    if (!delivered.ok) return fail(delivered.reason);
    const task = delivered.task;
    return ok(
      outcome === "success"
        ? `TASK · ${id} · completed`
        : `TASK · ${id} · pending · recovery hold · blocker retained`,
      { action: "complete", id, outcome, status: task.status, task: project(task) },
    );
  }

  if (action === "reopen") {
    const id = str("id");
    if (!id) return fail("Reopening a task requires its id.");
    const reopened = reopenTask(id);
    if (!reopened.ok) return fail(reopened.reason);
    return ok(`TASK · ${id} · pending · reopened`, { action: "reopen", id, status: reopened.task.status, task: project(reopened.task) });
  }

  return fail(`Unknown task action "${action ?? ""}". Use create, list, update, complete, or reopen.`);
}

/** The single registrant of `task`. Registers unconditionally and owns no other
 *  tool; a collaborator that wants to be told about board changes subscribes to
 *  `pi.events` rather than being called from here. */
export function registerTaskTool(pi: ExtensionAPI, options: { env?: NodeJS.ProcessEnv } = {}): void {
  pi.registerTool({
    name: "task",
    label: "Task",
    promptSnippet: "Record, take, and deliver work on the shared task board",
    description: "The shared task board. Record what must be done with create, find work with list, take it with update status=in_progress, deliver it with complete outcome=success, and report a blocker with complete outcome=failed. This tool never starts or stops an agent and never dispatches work to a named participant: it states what must be done, and a participant takes it.",
    parameters: TASK_TOOL_PARAMS as never,
    renderShell: "self",
    // A task row is a plain summary line, so the default shell already shows
    // everything; rendering it again would only duplicate the text.
    renderCall: emptyCall,
    async execute(_toolCallId, params) {
      return executeTaskTool(params as Record<string, unknown>, { env: options.env });
    },
  });
}

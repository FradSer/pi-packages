import { createHash } from "node:crypto";
/**
 * The model-facing surface: four tools over one store.
 *
 * One tool per operation: `create_task`, `get_task`, `list_tasks`, `update_task`.
 * The shape follows Claude Code's task tools, for one reason that matters more
 * than the resemblance — a lifecycle position is reachable by exactly one call,
 * and a refusal can name the call that earned it.
 *
 * The names follow this workspace rather than Claude Code's. `create_task` sits
 * beside `create_goal` and `get_task` beside `get_goal`: verb first, the noun as
 * the object, snake_case. A PascalCase name imported from another product reads
 * as someone else's vocabulary in a session where every other tool here is
 * snake_case.
 *
 * The single `task` tool this replaces had one parameterization standing in for
 * two: `update status=pending` and `reopen` were the same call. Its `update` also
 * carried a `status` field the store had deliberately refused, because an open
 * status lets a caller bypass the preconditions the named transitions enforce.
 *
 * **The caller is the holder.** `update_task` fills the holder from the caller's
 * own runtime identity, so no parameter anywhere lets a model name a different
 * participant. A task states what must be done; a participant takes it.
 *
 * **`update_task` is the fat one, and that is inherited on purpose.** It moves a
 * task between states, changes its content, and edits its brief — the same
 * division Claude Code uses, where one declaration covers four operations rather
 * than four declarations competing for the prompt. What it does not inherit is
 * the rest; the differences are listed where they occur, because each one is a
 * deliberate refusal rather than an oversight.
 *
 * `list_tasks` reports per-task state a model would otherwise have to infer: who
 * holds it, whether a recovery hold is set, and what it depends on. Without
 * those, a pending task the model must not take looks identical to one it may.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { emptyToolCall } from "@fradser/pi-kit";
import {
  ALL_COMPLETION_CHECKS,
  MAIN_SESSION,
  blockedDependencies,
  blockTask,
  claimableTasks,
  completableTasks,
  completionRequirements,
  storeNotice,
  completeTaskWithOutcome,
  createTask,
  getTask,
  listTasks,
  reopenTask,
  takeTask,
  updateTask,
} from "./store.ts";
import { TASK_STATUSES, type CompletionVerdict, type Task, type TaskStatus } from "./types.ts";
import { formatTaskHandoff, normalizeTaskContext } from "./context.ts";
import {
  TASK_DISPLAY_LABEL,
  taskBlockedByLines,
  taskDependencyLines,
  taskDisplayHeading,
  taskDisplayIndex,
  taskDisplayReference,
  taskSummaryLines,
} from "./display.ts";

/** Tool ids this extension registers. Declared so a spawner can grant them
 *  without hardcoding names, mirroring the subagents extension. */
export const TASK_CAPABILITY_TOOLS: readonly string[] = ["create_task", "get_task", "list_tasks", "update_task"];

/** The statuses the declared result and the list filter may name.
 *
 *  The store's own list, not a copy of it: a status added to `TASK_STATUSES`
 *  reaches the declared schema, the list filter and the restored-status check at
 *  once, which is what keeps a projection from failing its own declaration. */
const STATUS_ENUM = TASK_STATUSES;

const stringArray = (description: string) => ({
  type: "array",
  items: { type: "string", minLength: 1 },
  description,
});

const idField = { type: "string", minLength: 1, description: "The task id, copied from create_task or list_tasks." };

/** The per-task context a caller may record, as a schema rather than a cast.
 *
 *  Declared because the model is the caller: a bare `object` leaves it guessing
 *  field names, and it guessed `handOff` once already. The shape is also what
 *  `normalizeTaskContext` checks, so the schema and the store cannot drift into
 *  accepting a context the budget cannot account for. */
/** The context parameter, declared open at every level below the top.
 *
 *  A closed schema here makes the validator the author of the refusal, and its
 *  refusal reads like a schema rejection without field names: it names neither
 *  the field's home nor what the field accepts. This package's own reader answers
 *  both questions, so the shape stays open and `normalizeTaskContext` writes the
 *  message. A handoff field written one level too high is moved into the handoff,
 *  and a field no layer owns is refused by name, next to the fields that do exist. */
const CONTEXT_PARAMS = {
  type: "object",
  properties: {
    workspacePath: { type: "string", description: "The workspace this task ran in. Pi resolves the session from it." },
    handoff: {
      type: "object",
      properties: {
        candidate: { type: "string", description: "The revision or scoped snapshot the outgoing attempt checked." },
        delta: { type: "string", description: "What the outgoing attempt changed, in its own words." },
        verification: { type: "string", description: "Checks that ran and their outcomes." },
        priorFindings: stringArray("Findings a successor must not lose. Added to, never replaced."),
        outstanding: stringArray("Work known to be unfinished or unverified."),
      },
      description: "The brief a successor receives. Fields merge with whatever the task already carries.",
    },
    refs: {
      type: "array",
      items: {
        type: "object",
        properties: {
          kind: { type: "string", enum: ["work", "report", "file"], description: "What kind of thing is referenced." },
          id: { type: "string", description: "Task id, report id, or repository-relative path." },
          note: { type: "string", description: "Why this reference matters." },
        },
        required: ["kind", "id"],
      },
      description: "Prior work, reports, and files this task builds on.",
    },
    budgetBytes: {
      type: "number",
      minimum: 1,
      maximum: 64 * 1024,
      description: "Byte ceiling for this task's retained context. A task may be held to less than the default, never to more.",
    },
  },
} as const;

/** The shape of a Task as a result carries it. Every field is something a caller
 *  would otherwise have to infer and get wrong; `blocked` in particular is
 *  a state of its own, and a Task in it cannot be taken without a reason.
 *
 *  A type alias rather than an interface: this is plain JSON on its way to
 *  `structuredContent`, and only an alias carries the implicit index signature
 *  that lets it. An interface here would need a cast at the one boundary that
 *  wants JSON, which is the cast this shape exists to remove. */
export type TaskProjection = {
  recordKind?: "task" | "execution";
  id: string;
  subject: string;
  description?: string;
  status: TaskStatus;
  holder?: string;
  recoveryNote?: string;
  dependsOn: string[];
  /** Among `dependsOn`, the ones not yet completed. Absent when none are. */
  blockedBy?: string[];
  verify?: string;
  result?: string;
  supersededBy?: string;
  replacementUnresolved?: boolean;
  blockedReason?: string;
  failureEvidence?: string;
  completionVerdict?: CompletionVerdict;
};

/** List items omit the detailed body, acceptance gate, and completion evidence. */
export type TaskSummary = Omit<TaskProjection, "description" | "verify" | "result" | "completionVerdict">;

/** What a result says, as data.
 *
 *  Declared because these tools are queried by things that are not a model
 *  reading prose: a codemode script asking which work is claimable, a coordinator
 *  waking a participant, a test asserting a transition. The text is the same
 *  information for a model; this is the information, and
 *  `TASK_TOOL_OUTPUT_SCHEMA` promises the two agree. */
export type TaskToolDetails = {
  ok: boolean;
  /** Present on a refusal, and the only field a refusal carries besides `ok`. */
  error?: string;
  tool?: string;
  id?: string;
  status?: string;
  outcome?: string;
  verdict?: CompletionVerdict;
  task?: TaskProjection;
  tasks?: TaskSummary[];
  /** The successor brief, rendered. Only `get_task` carries it. */
  brief?: string;
  replaced?: string[];
  invalidated?: TaskProjection[];
  withdrawn?: string[];
  count?: number;
  shown?: number;
  truncated?: boolean;
  cursor?: string;
  offset?: number;
  notice?: string;
  /** What a completion of this task must carry, named when the task is taken.
   *  The checks refuse a completion, so they are reported before the attempt
   *  instead of after it. */
  requirements?: string[];
};

/** The per-task projection as the declared result describes it.
 *
 *  Spelled out rather than left as a bare `object`, because the consumer this
 *  exists for is a codemode script: a schema with no properties here hands the
 *  script an untyped bag and puts it back to reading the text. */
const TASK_PROJECTION_SCHEMA = {
  type: "object",
  properties: {
    recordKind: { type: "string", enum: ["task", "execution"], description: "Execution history does not trigger task reminders or autonomous claims." },
    id: { type: "string", description: "Task id, derived from the subject unless one was given." },
    subject: { type: "string", description: "What must be done." },
    description: { type: "string", description: "The full brief." },
    status: { type: "string", enum: STATUS_ENUM, description: "Where the task is in its lifecycle." },
    holder: { type: "string", description: "The participant that took it." },
    recoveryNote: { type: "string", description: "Why a recovery hold was cleared." },
    dependsOn: { type: "array", items: { type: "string" }, description: "Task ids that must complete first." },
    blockedBy: { type: "array", items: { type: "string" }, description: "Among dependsOn, the ones not completed. Absent when none are." },
    verify: { type: "string", description: "The completion gate a fresh reviewer answers." },
    result: { type: "string", description: "Evidence recorded for the current or last attempt." },
    blockedReason: { type: "string", description: "Why work cannot continue." },
    failureEvidence: { type: "string", description: "Evidence of the last failed attempt." },
    replacementUnresolved: { type: "boolean", description: "Legacy replacement target is missing; this history is inactive." },
    supersededBy: { type: "string", description: "The replacement that made this task obsolete." },
    completionVerdict: { type: "string", enum: ["pass", "fail"], description: "The gate verdict recorded at completion, when the task declared a gate." },
  },
  required: ["id", "subject", "status", "dependsOn"],
  additionalProperties: false,
} as const;

const TASK_SUMMARY_SCHEMA = {
  ...TASK_PROJECTION_SCHEMA,
  properties: {
    recordKind: TASK_PROJECTION_SCHEMA.properties.recordKind,
    id: TASK_PROJECTION_SCHEMA.properties.id,
    subject: TASK_PROJECTION_SCHEMA.properties.subject,
    status: TASK_PROJECTION_SCHEMA.properties.status,
    holder: TASK_PROJECTION_SCHEMA.properties.holder,
    recoveryNote: TASK_PROJECTION_SCHEMA.properties.recoveryNote,
    blockedReason: TASK_PROJECTION_SCHEMA.properties.blockedReason,
    dependsOn: TASK_PROJECTION_SCHEMA.properties.dependsOn,
    blockedBy: TASK_PROJECTION_SCHEMA.properties.blockedBy,
    supersededBy: TASK_PROJECTION_SCHEMA.properties.supersededBy,
    replacementUnresolved: TASK_PROJECTION_SCHEMA.properties.replacementUnresolved,
  },
} as const;

/** The declared result, mirroring `TaskToolDetails` field for field.
 *
 *  Closed on purpose: a result carrying a field this does not name is a result a
 *  caller was told it could rely on and cannot, and the tests drive every tool to
 *  keep the two in step. */
export const TASK_TOOL_OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    ok: { type: "boolean", description: "Whether the requested change was carried out." },
    error: { type: "string", description: "Why a refusal happened." },
    tool: { type: "string", description: "The tool this result answers." },
    id: { type: "string", description: "The task this result is about." },
    status: { type: "string", description: "The task's status after the change." },
    outcome: { type: "string", enum: ["success", "failed"], description: "The outcome a completion delivered." },
    verdict: { type: "string", enum: ["pass", "fail"], description: "The answer to the task's declared completion gate." },
    task: TASK_PROJECTION_SCHEMA,
    tasks: { type: "array", items: TASK_SUMMARY_SCHEMA, description: "Task summaries. Use get_task for the detailed body and evidence." },
    brief: { type: "string", description: "The successor brief, rendered for whoever picks this task up." },
    replaced: { type: "array", items: { type: "string" }, description: "Tasks a creation made obsolete." },
    invalidated: { type: "array", items: TASK_PROJECTION_SCHEMA, description: "Tasks blocked after a dependency was reopened." },
    withdrawn: { type: "array", items: { type: "string" }, description: "Ids of tasks blocked after a dependency was reopened." },
    count: { type: "number", description: "How many tasks matched a list." },
    shown: { type: "number", description: "How many of them this result carries." },
    truncated: { type: "boolean", description: "Whether more tasks remain after this page." },
    cursor: { type: "string", description: "Pass to list_tasks to read the next page." },
    offset: { type: "number", description: "Number of matching tasks before this page." },
    notice: { type: "string", description: "A store-level fact the caller needs, such as an unreadable file." },
    requirements: { type: "array", items: { type: "string" }, description: "What a completion of this task must carry, named when the task is taken." },
  },
  required: ["ok"],
  additionalProperties: false,
} as const;

export const TASK_CREATE_PARAMS = {
  type: "object",
  properties: {
    subject: { type: "string", minLength: 1, description: "What must be done." },
    description: { type: "string", description: "The full brief." },
    verify: { type: "string", description: "An independent completion gate, as a prompt rather than a command." },
    dependsOn: stringArray("Task ids that must complete first."),
    supersedes: stringArray("Task ids this one replaces atomically."),
  },
  required: ["subject"],
  additionalProperties: false,
} as const;

export const TASK_GET_PARAMS = {
  type: "object",
  properties: { id: idField },
  required: ["id"],
  additionalProperties: false,
} as const;

export const TASK_LIST_PARAMS = {
  type: "object",
  properties: {
    statusFilter: {
      type: "array",
      items: { type: "string", enum: STATUS_ENUM },
      description: "Restrict to these statuses.",
    },
    claimable: { type: "boolean", description: "Restrict to tasks that can be taken right now." },
    ready: { type: "boolean", description: "Restrict to tasks that could be completed right now: an attempt on the record, every dependency done." },
    cursor: { type: "string", description: "Next page cursor from list_tasks; filters are carried with it." },
    limit: { type: "number", minimum: 0, description: "Cap the number of tasks returned. 0 returns none. Bounded by the store either way." },
  },
  additionalProperties: false,
} as const;

/** The positions `update_task` can move a task to. A named list rather than
 *  `TaskStatus`, because this is not a status of the record: it is the three
 *  routes a caller may take, and `superseded` is not among them. Declared above
 *  the parameter object that spreads it, and used again by the handler that has
 *  to refuse anything outside it. */
const TASK_UPDATE_STATUSES = ["in_progress", "completed", "pending", "blocked"] as const;

export const TASK_UPDATE_PARAMS = {
  type: "object",
  properties: {
    id: idField,
    // The one fat field, inherited from Claude Code's update_task. It routes to
    // the named store transition rather than assigning a value, so every
    // precondition still applies and each position is still reachable one way:
    //   in_progress -> take    (requires `reason` while a recovery hold is set)
    //   completed   -> complete (requires `outcome`; a completion is a judgement)
    //   pending     -> reopen   (only from completed)
    status: {
      type: "string",
      enum: [...TASK_UPDATE_STATUSES],
      description: "Move the task. in_progress takes it for you, completed delivers it and needs an outcome, pending reopens a completed one; blocked records a blocker and requires reason.",
    },
    outcome: {
      type: "string",
      enum: ["success", "failed"],
      description: "With status=completed: success delivers the result; failed records blocked work and retains the blocker as evidence.",
    },
    result: { type: "string", description: "With status=completed: the evidence for the outcome. Required: a success with no result is refused." },
    verdict: {
      type: "string",
      enum: ["pass", "fail"],
      description: "With status=completed: the answer to this task's declared completion gate. Required when the task has a gate.",
    },
    reason: { type: "string", description: "With status=blocked: the blocker. With status=in_progress: required to resume blocked work, stating how the blocker was addressed." },
    subject: { type: "string", minLength: 1, description: "Without status: replace the task name. The id stays unchanged." },
    description: { type: "string", description: "Without status: replace the full task body." },
    dependsOn: stringArray("Without status: replace the prerequisite ids. Use [] to clear them. Unknown ids and cycles are refused."),
    verify: { type: "string", description: "Without status: replace the independent completion gate." },
    context: CONTEXT_PARAMS,
  },
  required: ["id"],
  additionalProperties: false,
} as const;

/** Bounded so a long-lived store cannot make one result the whole context. */
export const MAX_LISTED_TASKS = 40;

/** Channels a transition is announced on.
 *
 * A coordinator subscribes to these instead of being called, so this package
 * never has to know what a participant is. With nobody listening the emit is a
 * no-op, which is the correct degradation: a standalone store records the change
 * and nobody is notified, rather than failing because a host is absent. */
export const TASK_EVENTS = {
  created: "pi-tasks:task-created",
  taken: "pi-tasks:task-taken",
  completed: "pi-tasks:task-completed",
  reopened: "pi-tasks:task-reopened",
  updated: "pi-tasks:task-updated",
} as const;

/** The per-task projection, exactly as the declared result describes it. */
function project(task: Task): TaskProjection {
  return {
    ...summarize(task),
    ...(task.description ? { description: task.description } : {}),
    ...(task.verify ? { verify: task.verify } : {}),
    ...(task.result ? { result: task.result } : {}),
    ...(task.failureEvidence ? { failureEvidence: task.failureEvidence } : {}),
    ...(task.completionVerdict ? { completionVerdict: task.completionVerdict } : {}),
  };
}

function summarize(task: Task): TaskSummary {
  const blockedBy = blockedDependencies(task);
  return {
    ...(task.recordKind ? { recordKind: task.recordKind } : {}),
    id: task.id,
    subject: task.subject,
    status: task.status,
    ...(task.claimedBy ? { holder: task.claimedBy } : {}),
    ...(task.recoveryNote ? { recoveryNote: task.recoveryNote } : {}),
    ...(task.status === "blocked" && (task.blockedReason || task.recoveryNote || task.result)
      ? { blockedReason: task.blockedReason ?? task.recoveryNote ?? task.result } : {}),
    dependsOn: task.dependsOn,
    // Which of the declared edges are unfinished, so a caller does not have to
    // hold a list in its head to answer "can I finish this yet".
    ...(blockedBy.length > 0 ? { blockedBy } : {}),
    ...(task.supersededBy ? { supersededBy: task.supersededBy } : {}),
    ...(task.replacementUnresolved ? { replacementUnresolved: true } : {}),
  };
}

interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  details: TaskToolDetails;
  /** The same information as `details`, under the name a declared output schema
   *  puts it at. A caller that is not reading prose receives this; the model
   *  receives `content`. */
  structuredContent?: TaskToolDetails;
  isError?: boolean;
}

function text(body: string): ToolResult["content"] {
  return [{ type: "text", text: body }];
}

/** A refusal. `task` is supplied when an edit in the same call was recorded
 *  before the refusal, so the caller sees what it kept and what it must retry
 *  rather than resending a payload the task set already accepted. */
function fail(tool: string, message: string, task?: TaskProjection): ToolResult {
  const details: TaskToolDetails = { ok: false, tool, error: message, ...(task ? { task } : {}) };
  return { content: text(message), details, structuredContent: details, isError: true };
}

function ok(body: string, details: Omit<TaskToolDetails, "ok">): ToolResult {
  const complete: TaskToolDetails = { ...details, ok: true };
  return { content: text(body), details: complete, structuredContent: complete };
}

/** The environment variable a spawned participant binds through.
 *
 * Named and owned here rather than read from whatever prefix a spawner happens
 * to use. The child gets this from its spawner, and a spawner that names its own
 * vocabulary here would couple this package to that package's internals: renaming
 * an env var on one side would silently turn every participant's take into a
 * take by the main session. Exported so the spawner spells it by import. */
export const TASK_HOLDER_ENV = "PI_TASK_HOLDER";

/** The caller's identity. A spawned participant binds through the environment;
 * anything else is the main session. Derived, never supplied by the model. */
export function callerIdentity(env: NodeJS.ProcessEnv = process.env): string {
  const participant = env[TASK_HOLDER_ENV]?.trim();
  if (participant) return participant;
  return MAIN_SESSION;
}

/** What every tool shares: a reader for its own parameters, the caller's
 *  identity, a host-supplied cap, and the event bus. */
interface CallOptions {
  env?: NodeJS.ProcessEnv;
  limit?: number;
  emit?: (channel: string, payload: unknown) => void;
}

function readers(params: Record<string, unknown>) {
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
  return { str, list };
}

/** `create_task`: record what must be done. */
export async function executeTaskCreate(
  params: Record<string, unknown>,
  options: CallOptions = {},
): Promise<ToolResult> {
  const { str, list } = readers(params);
  const me = callerIdentity(options.env);
  const subject = str("subject");
  if (!subject) return fail("create_task", "Creating a task requires a subject stating what must be done.");
  const dependsOn = list("dependsOn") ?? [];
  const unknown = dependsOn.filter((id) => !getTask(id));
  if (unknown.length > 0) return fail("create_task", `Unknown task id in dependsOn: ${unknown.join(", ")}.`);
  const created = createTask({
    subject,
    // From the caller's own context, never from a parameter: this is what makes
    // the creator accountable for work it finishes without taking it, and a
    // model-supplied value would make that accountability spoofable.
    createdBy: me,
    ...(str("description") ? { description: str("description") } : {}),
    dependsOn,
    ...(str("verify") ? { verify: str("verify") } : {}),
    ...(list("supersedes") ? { supersedes: list("supersedes") } : {}),
  });
  if (!created.ok) return fail("create_task", created.reason);
  const replaced = created.superseded.map((task) => task.id);
  options.emit?.(TASK_EVENTS.created, {
    id: created.task.id,
    resources: created.task.resources,
    status: created.task.status,
    replaced,
  });
  return ok(
    [
      `TASK · ${created.task.id} · ${created.task.status} · ${created.task.subject}`,
      // What a creation made obsolete is state a person wants. How to spell the
      // next call is not: that is the tool descriptions' job, and they are in the
      // prompt either way.
      ...(replaced.length > 0 ? [`REPLACED · ${replaced.join(", ")}`] : []),
    ].join("\n"),
    { tool: "create_task", id: created.task.id, status: created.task.status, task: project(created.task), replaced },
  );
}

/** `get_task`: one task in full, including the brief a successor needs.
 *
 *  The reason this exists rather than a wider `list_tasks`: a list is bounded, so
 *  it leaves the brief out, and without a way to read the brief a handoff is
 *  written for nobody. */
export async function executeTaskGet(
  params: Record<string, unknown>,
  _options: CallOptions = {},
): Promise<ToolResult> {
  const { str } = readers(params);
  const id = str("id");
  if (!id) return fail("get_task", "Reading a task requires its id.");
  const task = getTask(id);
  if (!task) return fail("get_task", `Task "${id}" does not exist.`);
  const brief = formatTaskHandoff(task.context?.handoff);
  return ok(
    [
      `TASK · ${task.id} · ${task.status} · ${task.subject}`,
      ...(task.status === "blocked" ? [`BLOCKED · ${task.recoveryNote ?? "take it with a reason stating how the blocker was addressed"}`] : []),
      ...(task.dependsOn.length > 0 ? [`DEPENDS ON · ${task.dependsOn.join(", ")}`] : []),
      ...(blockedDependencies(task).length > 0 ? [`BLOCKED BY · ${blockedDependencies(task).join(", ")}`] : []),
      ...(task.description ? [task.description] : []),
      ...(task.verify ? [`VERIFY · ${task.verify}`] : []),
      ...(brief ? ["", brief] : []),
      ...(task.result ? ["", `EVIDENCE · ${task.result}`] : []),
    ].join("\n"),
    {
      tool: "get_task",
      id: task.id,
      status: task.status,
      task: project(task),
      ...(brief ? { brief } : {}),
    },
  );
}

/** `list_tasks`: the tasks, bounded by whichever cap is tightest. */
export async function executeTaskList(
  params: Record<string, unknown>,
  options: CallOptions = {},
): Promise<ToolResult> {
  const { list } = readers(params);
  // Every stated cap applies, and the store's own ceiling applies whether anyone
  // asked or not. A `limit` a caller sent is a real bound: reading only the host
  // option meant a model asking for three tasks got forty and had no way to know
  // the parameter it was given did nothing.
  //
  // Floored before it is applied and refused below zero, because a cap of `0.5`
  // is not a cap of half a task: floored to 0 it returned an empty list that
  // claimed to be a truncated one. `0` is a legitimate request and is honoured
  // as the empty list it asks for.
  if (typeof params.limit === "number" && Number.isFinite(params.limit) && params.limit < 0) {
    return fail("list_tasks", "limit must not be negative; omit it for the store's own ceiling, or pass 0 for no tasks.");
  }
  const limit = [
    MAX_LISTED_TASKS,
    ...(typeof options.limit === "number" && Number.isFinite(options.limit) && options.limit >= 0
      ? [Math.floor(options.limit)]
      : []),
    ...(typeof params.limit === "number" && Number.isFinite(params.limit) && params.limit >= 0
      ? [Math.floor(params.limit)]
      : []),
  ].reduce((smallest, cap) => Math.min(smallest, cap));

  let query = { statuses: list("statusFilter"), claimable: params.claimable === true, ready: params.ready === true };
  let offset = 0;
  let fingerprint: string | undefined;
  if (params.cursor !== undefined) {
    try {
      if (typeof params.cursor !== "string" || params.cursor.length > 4096) throw new Error();
      const page = JSON.parse(Buffer.from(params.cursor, "base64url").toString("utf8"));
      if (!Number.isSafeInteger(page.offset) || page.offset <= 0 || typeof page.fingerprint !== "string" ||
          !page.query || typeof page.query.claimable !== "boolean" || typeof page.query.ready !== "boolean" ||
          (page.query.statuses !== undefined && (!Array.isArray(page.query.statuses) || !page.query.statuses.every((status: unknown) => typeof status === "string" && STATUS_ENUM.includes(status as TaskStatus))))) throw new Error();
      if (["statusFilter", "claimable", "ready"].some(key => params[key] !== undefined) && JSON.stringify(query) !== JSON.stringify(page.query)) throw new Error();
      query = page.query; offset = page.offset; fingerprint = page.fingerprint;
    } catch { return fail("list_tasks", "Invalid page cursor or changed filters. Read list_tasks again without a cursor."); }
  }
  const claimableIds = query.claimable ? new Set(claimableTasks().map(task => task.id)) : undefined;
  const readyIds = query.ready ? new Set(completableTasks().map(task => task.id)) : undefined;
  const matching = listTasks().filter(task => (!query.statuses || query.statuses.includes(task.status)) &&
    (!claimableIds || claimableIds.has(task.id)) && (!readyIds || readyIds.has(task.id)));
  const currentFingerprint = createHash("sha256").update(JSON.stringify([query, matching.map(summarize)])).digest("hex");
  if (fingerprint && (fingerprint !== currentFingerprint || offset >= matching.length)) {
    return fail("list_tasks", "The task list changed; read it again without a cursor.");
  }
  const shown = matching.slice(offset, offset + limit);
  const end = offset + shown.length;
  const cursor = limit > 0 && end < matching.length
    ? Buffer.from(JSON.stringify({offset: end, fingerprint: currentFingerprint, query})).toString("base64url") : undefined;
  const notice = storeNotice();
  return ok(
    shown.length === 0
      ? "TASK · none"
      : shown.map((task) => {
        const deps = task.dependsOn.length > 0 ? ` · depends=${task.dependsOn.join(",")}` : "";
        return `- ${task.id} · ${task.status}${deps} · ${task.subject}`;
      }).join("\n"),
    {
      tool: "list_tasks",
      count: matching.length,
      shown: shown.length,
      truncated: end < matching.length,
      offset,
      ...(cursor ? { cursor } : {}),
      // A file that could not be read is a fact the model needs: it is looking
      // at an empty set of tasks that is not empty on disk.
      ...(notice ? { notice } : {}),
      tasks: shown.map(summarize),
    },
  );
}

/** `update_task`: move a task, or change what it says.
 *
 *  `status` routes to the named store transition rather than assigning a value.
 *  That is the whole reason the single `task` tool's `update` was wrong: it
 *  reassigned the field and so had to re-implement each precondition by hand,
 *  while the store's own `update_task` interface refused the field outright. */
export async function executeTaskUpdate(
  params: Record<string, unknown>,
  options: CallOptions = {},
): Promise<ToolResult> {
  const me = callerIdentity(options.env);
  const { str, list } = readers(params);
  const id = str("id");
  if (!id) return fail("update_task", "Updating a task requires its id.");
  const status = str("status");

  // A status that is not one of the three is refused by name rather than
  // falling through to the content branch, where a caller would be told it had
  // supplied nothing to change — while it had in fact supplied a status this
  // the task store does not define. Name the supported statuses in the refusal.
  if (status !== undefined && !TASK_UPDATE_STATUSES.includes(status as (typeof TASK_UPDATE_STATUSES)[number])) {
    return fail("update_task", `status "${status}" is not a position this task set knows; use ${TASK_UPDATE_STATUSES.join(", ")}.`);
  }

  // The content half runs first and is recorded before the status half is
  // attempted. The two used to be refused outright when they arrived together,
  // and the cost was real: a recorded session lost a whole evidence body to that
  // refusal, resent it, and then decided the task list was not worth the round
  // trips. A refusal now reports what it kept.
  const patch: Parameters<typeof updateTask>[1] = {
    ...(params.subject !== undefined ? { subject: str("subject") ?? "" } : {}),
    ...(params.description !== undefined ? { description: str("description") ?? "" } : {}),
    ...(params.dependsOn !== undefined ? { dependsOn: list("dependsOn") } : {}),
    ...(params.verify !== undefined ? { verify: str("verify") ?? "" } : {}),
  };
  if (params.context !== undefined) {
    // Read, not cast. The context arrives from a model, and a cast would store
    // whatever spelling it used: a `handOff` key is then retained on the Task
    // forever, read by no brief and measured by no budget.
    const context = normalizeTaskContext(params.context);
    if (!context.ok) return fail("update_task", context.error);
    patch.context = context.value;
  }
  // Validated and applied before the status is read, so a refused status cannot
  // discard an edit that was accepted, and a refused edit records neither half.
  const edited = Object.keys(patch).length > 0 ? updateTask(id, patch) : undefined;
  if (edited && !edited.ok) return fail("update_task", edited.reason);
  if (edited) options.emit?.(TASK_EVENTS.updated, { id });

  /** Name both halves: the edit that stands, and the status that must be retried. */
  const refuseStatus = (reason: string): ToolResult => edited
    ? fail("update_task", `${reason} The content edit in this call was recorded; the status change must be a separate call, so retry it once it can succeed.`, project(edited.task))
    : fail("update_task", reason);

  if (status === undefined) {
    if (!edited) return fail("update_task", "Supply status, or edit at least one of subject, description, dependsOn, verify, context.");
    return ok(`TASK · ${id} · updated`, { tool: "update_task", id, status: edited.task.status, task: project(edited.task) });
  }

  if (status === "blocked") {
    const blocked = blockTask(id, me, str("reason"));
    if (!blocked.ok) return refuseStatus(blocked.reason);
    options.emit?.(TASK_EVENTS.updated, { id, status: "blocked" });
    return ok(`TASK · ${id} · blocked`, { tool: "update_task", id, status: "blocked", task: project(blocked.task) });
  }

  if (status === "in_progress") {
    const taken = takeTask(id, me, { ...(str("reason") ? { reason: str("reason") } : {}) });
    if (!taken.ok) return refuseStatus(taken.reason);
    options.emit?.(TASK_EVENTS.taken, { id, holder: me, resources: taken.task.resources });
    // What would refuse a completion is named here, before the attempt, so an
    // honest caller satisfies it in the call it was going to make anyway rather
    // than discovering it one refusal at a time.
    const requirements = completionRequirements(taken.task);
    return ok(
      [
        `TASK · ${id} · in_progress`,
        ...(requirements.length > 0 ? [`REQUIRED AT COMPLETION · ${requirements.join("; ")}`] : []),
      ].join("\n"),
      {
        tool: "update_task",
        id,
        status: taken.task.status,
        task: project(taken.task),
        ...(requirements.length > 0 ? { requirements } : {}),
      },
    );
  }

  if (status === "completed") {
    const outcome = str("outcome");
    if (outcome !== "success" && outcome !== "failed") {
      return fail("update_task", "outcome is required and must be success or failed. A blocker recorded as an ordinary answer is not a failure.");
    }
    // The tasks's own facts decide whether this completion is supportable:
    // dependencies finished, evidence recorded, an attempt on the record, and a
    // declared gate answered. It does not run the gate — a gate is a prompt, and
    // a task set that evaluates prompts runs agents. It demands the answer and
    // records it, so the omission is impossible even though the answer itself is
    // taken on trust, and a completed task says afterwards which kind of done it
    // was.
    const delivered = completeTaskWithOutcome(id, me, outcome, str("result"), {
      checks: ALL_COMPLETION_CHECKS,
      result: str("result"),
      ...(str("verdict") ? { verdict: str("verdict") as CompletionVerdict } : {}),
    });
    if (!delivered.ok) return refuseStatus(delivered.reason);
    const task = delivered.task;
    options.emit?.(TASK_EVENTS.completed, { id, outcome, holder: me, status: task.status });
    return ok(
      outcome === "success"
        ? `TASK · ${id} · completed`
        : `TASK · ${id} · blocked · blocker retained`,
      {
        tool: "update_task",
        id,
        outcome,
        status: task.status,
        task: project(task),
        ...(task.completionVerdict ? { verdict: task.completionVerdict } : {}),
      },
    );
  }

  if (status === "pending") {
    const reopened = reopenTask(id);
    if (!reopened.ok) return refuseStatus(reopened.reason);
    options.emit?.(TASK_EVENTS.reopened, { id, invalidated: reopened.invalidated.map((task) => task.id) });
    // What the reopen withdrew is named, not left for the model to discover on
    // the next list: a conclusion drawn on a premise that just moved is the thing
    // most likely to be missed, and it is the thing most expensive to miss.
    return ok(
      [
        `TASK · ${id} · pending · reopened`,
        ...(reopened.invalidated.length > 0
          ? [`WITHDRAWN · ${reopened.invalidated.map((task) => task.id).join(", ")} · blocked: they were completed on a premise this reopening withdraws`]
          : []),
      ].join("\n"),
      {
        tool: "update_task",
        id,
        status: reopened.task.status,
        task: project(reopened.task),
        ...(reopened.invalidated.length > 0
          ? { invalidated: reopened.invalidated.map((task) => project(task)), withdrawn: reopened.invalidated.map((task) => task.id) }
          : {}),
      },
    );
  }

  return fail("update_task", `status "${status}" is unhandled.`);
}

/**
 * The row for one result.
 *
 * The subject is the work, not the id: a reader looking at a row asks what is
 * being done, and the id is what they look up when they act on it.
 */
export const TASK_ROW_SPEC: import("./rows.ts").TaskRowSpec = (result) => {
  const details = (result.details ?? {}) as TaskToolDetails;
  const content = (result.content ?? []) as Array<{ text?: string }>;
  const body = content.map((part) => part.text ?? "").join("\n");
  const count = details.count ?? details.tasks?.length ?? 0;
  const displayIndex = taskDisplayIndex([
    ...listTasks(),
    ...(details.task ? [details.task] : []),
    ...(details.tasks ?? []),
    ...(details.invalidated ?? []),
  ]);
  const subject = details.task
    ? taskDisplayHeading({
      ...details.task,
      status: details.task.status ?? details.status ?? details.outcome ?? "unknown",
    }, displayIndex)
    : details.tasks
      ? count === 0 ? "No tasks" : `${count} task${count === 1 ? "" : "s"}`
      : "task";
  const summary = details.tasks
    ? details.tasks.flatMap(task => taskSummaryLines(task, displayIndex))
    : details.task
      ? [
        ...(details.replaced?.length
          ? [`Replaced: ${details.replaced.map(id => taskDisplayReference(id, displayIndex)).join(", ")}`]
          : []),
        ...(details.withdrawn?.length
          ? [`Invalidated: ${details.withdrawn.map(id => taskDisplayReference(id, displayIndex)).join(", ")}`]
          : []),
      ]
      : body.split("\n").filter(Boolean).filter(line => !/^TASK · /.test(line));
  const spec = {
    kind: "started" as const,
    tool: TASK_DISPLAY_LABEL,
    label: details.tool?.replace(/_tasks?$/, "") ?? "status",
    subject,
    summary,
    details: [
      ...(details.notice ? [`Notice: ${details.notice}`] : []),
      ...(details.task?.description ? ["Description:", ...details.task.description.split("\n"), ""] : []),
      ...(details.task?.verify ? ["Verify:", ...details.task.verify.split("\n"), ""] : []),
      ...(details.task ? taskDependencyLines(details.task, displayIndex) : []),
      ...(details.task ? taskBlockedByLines(details.task, displayIndex) : []),
      ...(details.task?.status === "blocked" && (!details.task.result || details.task.blockedReason !== details.task.result) ? [`Reason: ${details.task.blockedReason ?? details.task.recoveryNote ?? details.task.result ?? "Recovery is required."}`] : []),
      ...(details.task?.supersededBy
        ? [`Replaced by ${taskDisplayReference(details.task.supersededBy, displayIndex)}`]
        : []),
      ...(details.task?.replacementUnresolved ? ["Replacement target unresolved; this historical task is inactive."] : []),
      ...(details.tool === "get_task" && details.brief ? details.brief.split("\n") : []),
      ...(details.task?.result ? [`Evidence: ${details.task.result}`] : []),
      ...(details.task?.recoveryNote ? [`Recovery: ${details.task.recoveryNote}`] : []),
      ...(details.shown !== undefined && (details.truncated || details.offset)
        ? [`Showing ${(details.offset ?? 0) + 1}–${(details.offset ?? 0) + details.shown} of ${count} matching tasks.`] : []),
      ...(details.cursor ? [`Next page: list_tasks with cursor=${details.cursor}`] : []),
      ...(details.requirements?.length ? [`Required at completion: ${details.requirements.join("; ")}`] : []),
      ...(details.task?.failureEvidence && details.task.failureEvidence !== details.task.result
        ? [`Previous failure: ${details.task.failureEvidence}`] : []),
    ],
  };
  return { ...spec, verbatimSubject: true, fullSummary: true, summary: [...spec.summary, ...spec.details], details: [] };
};

/** Injected geometry for the rows, supplied by the extension entry — the only
 *  layer allowed to import the TUI. Absent means no custom renderer, so a
 *  headless caller gets Pi's own default. */
type RenderResult = (spec: { createSpec: typeof TASK_ROW_SPEC }) => unknown;

interface Registration {
  name: string;
  label: string;
  promptSnippet: string;
  description: string;
  parameters: unknown;
  execute: (params: Record<string, unknown>, options: CallOptions) => Promise<ToolResult>;
}

/** The four tools, in the order a model meets them: record, find, read, change. */
const TOOLS: readonly Registration[] = [
  {
    name: "create_task",
    label: "Task create",
    promptSnippet: "Create a task for work spanning several steps, files, or turns",
    description: "Record one task with a subject and optional description. Use when a request has several steps or several files, or when the work outlives this turn; a single edit is not a task. A task is not a goal: a goal is one objective that keeps running until it is met, and a task is one unit of work in a list you order, take, and finish. Use dependsOn to name prerequisite task ids. Independent tasks can run in parallel; dependent tasks wait until every prerequisite completes. Returns an id derived from the subject. supersedes replaces unfinished tasks and redirects their dependents atomically. verify states the completion requirements as a prompt, not a command.",
    parameters: TASK_CREATE_PARAMS,
    execute: executeTaskCreate,
  },
  {
    name: "get_task",
    label: "Task get",
    promptSnippet: "Read one task's name, detailed content, dependencies, and evidence",
    description: "Read one task by id. Returns its name, full description, status, dependencies, unfinished prerequisites, completion evidence, and successor brief. list_tasks returns bounded summaries; use get_task for the full task body.",
    parameters: TASK_GET_PARAMS,
    execute: executeTaskGet,
  },
  {
    name: "list_tasks",
    label: "Task list",
    promptSnippet: "List task names, status, dependencies, and blockers",
    description: "List bounded task summaries: id, name, status, dependencies, unfinished prerequisites, and blockers. Runtime holder information remains available as data. Use get_task for detailed content and evidence. Filter by status, claimable work, or completion readiness, and set limit to cap the page. Pass the returned cursor to read the next page.",
    parameters: TASK_LIST_PARAMS,
    execute: executeTaskList,
  },
  {
    name: "update_task",
    label: "Task update",
    promptSnippet: "Update task content, dependencies, status, or completion evidence",
    description: "Update one task. status=in_progress starts your attempt only when all prerequisites are completed. Perform the actual work before calling status=completed. Completion needs outcome=success or failed; success requires result evidence and a pass verdict when verify is declared. Failure records the blocker and sets blocked. Resuming blocked work needs an explicit recovery reason. status=blocked records reason and releases your attempt. status=pending reopens a completed task and invalidates dependent attempts and completions. Without status, edit subject, description, dependsOn, verify, or context. The id stays unchanged after a rename. dependsOn replaces prerequisite ids; [] clears them. Dependency edits reject unknown ids, self-dependencies, and cycles. An active or completed task cannot gain unfinished prerequisites. One call may carry a content edit and a status change: the content half is validated and recorded first, and a refused status keeps the edit and names the half to retry. This tool never starts or stops a participant and never dispatches work to a named one.",
    parameters: TASK_UPDATE_PARAMS,
    execute: executeTaskUpdate,
  },
];

/** The single registrant of all four. Registers unconditionally and owns no other
 *  tool; a collaborator that wants to be told about changes subscribes to
 *  `pi.events` rather than being called from here. */
export function registerTaskTools(
  pi: ExtensionAPI,
  options: {
    env?: NodeJS.ProcessEnv;
    /** Builds the result renderer from a spec. Supplied by the extension entry,
     *  the only layer allowed to import the TUI. */
    renderResult?: RenderResult;
  } = {},
): void {
  // Resolved once, defensively. Announcing a transition is optional, so a host
  // without an event bus must degrade to the same no-op as a host with nobody
  // subscribed — never to a failed tasks action.
  const emit = typeof pi.events?.emit === "function"
    ? (channel: string, payload: unknown) => { pi.events.emit(channel, payload); }
    : undefined;
  for (const tool of TOOLS) {
    pi.registerTool({
      name: tool.name,
      label: tool.label,
      promptSnippet: tool.promptSnippet,
      description: tool.description,
      parameters: tool.parameters as never,
      // Declared so the result is read as data by everything that is not the
      // model: a codemode script asking which work is claimable receives the
      // projections rather than a text block it has to take apart.
      outputSchema: TASK_TOOL_OUTPUT_SCHEMA as never,
      // Every call touches one file under this session's own directory and
      // nothing else, so the tool says it does not reach beyond this machine
      // rather than leaving a permission extension to assume it might. It makes
      // no claim about destructiveness, because it cannot keep one: reopening
      // erases the result a completion recorded, and superseding has no inverse
      // verb.
      annotations: { readOnlyHint: false, idempotentHint: false, openWorldHint: false },
      renderShell: "self",
      renderCall: emptyToolCall,
      // Attached only when the caller can supply real geometry. A row built
      // without it renders in tests and takes the terminal down on the first
      // repaint.
      ...(options.renderResult ? { renderResult: options.renderResult({ createSpec: TASK_ROW_SPEC }) as never } : {}),
      async execute(_toolCallId: string, params: never) {
        const result = await tool.execute(params as Record<string, unknown>, { env: options.env, ...(emit ? { emit } : {}) });
        const notice = storeNotice();
        if (!notice || result.details.notice === notice) return result;
        const details = { ...result.details, notice };
        return { ...result, details, structuredContent: details };
      },
    } as never);
  }
}

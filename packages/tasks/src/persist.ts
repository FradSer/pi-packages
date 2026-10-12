/**
 * Durable Task persistence.
 *
 * Layout (persists across restarts, never auto-cleaned):
 *   ~/.pi/agent/tasks/<sessionKey>/tasks.json            sole-writer task file
 *   ~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      exclusive-create claim intents
 *   ~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json exclusive-create submit intents
 *
 * Concurrency: the task file has exactly one writer, replaced atomically. A
 * participant never writes it; it expresses intent through an exclusive-create
 * marker file, so exactly one racer wins a contested claim.
 *
 * Loading and writes use only `tasks.json`. No other filename participates in
 * task persistence.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import {
  createExclusiveJsonFile,
  DEFAULT_INTENT_BYTES,
  DEFAULT_INTENT_PUBLISH_GRACE_MS,
  sessionKey,
  takeJsonIntent,
  writeJsonAtomic,
  type IntentValidation,
} from "@fradser/pi-kit";
import { TASKS_FILE_VERSION, type Task, type TaskIntent } from "./types.ts";

/** Intent label used in diagnostics, so an operator reads the same wording this
 * package has always produced. */
const INTENT_LABEL = "task intent";

/** The one file this session's tasks live in. */
const TASKS_FILE = "tasks.json";

/** An unparseable intent younger than this may still be mid-publish elsewhere,
 * so it is retried rather than destroyed. Re-exported under the name this
 * package has always used; the value and semantics are pi-kit's default. */
export const INTENT_PUBLISH_GRACE_MS = DEFAULT_INTENT_PUBLISH_GRACE_MS;

/** Root of all per-session task directories. */
export function tasksRoot(): string {
  return path.join(getAgentDir(), "tasks");
}

export { sessionKey };

export function tasksDir(sessionFile: string | undefined, cwd: string): string {
  return path.join(tasksRoot(), sessionKey(sessionFile, cwd));
}

export function tasksFilePath(sessionFile: string | undefined, cwd: string): string {
  return path.join(tasksDir(sessionFile, cwd), TASKS_FILE);
}

export function claimsDir(taskDirectory: string): string {
  return path.join(taskDirectory, "claims");
}

export function submissionsDir(taskDirectory: string): string {
  return path.join(taskDirectory, "submissions");
}

/** Read the persisted tasks. An absent file is a fresh store; a present but
 *  unreadable one is an error, never an empty store — silently treating it as
 *  empty would discard durable Tasks. */
export function readTasksFile(file: string): { tasks: Record<string, Task> } | undefined {
  let raw: string;
  try {
    raw = fs.readFileSync(file, "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw new Error(`The task file at ${file} could not be read: ${error instanceof Error ? error.message : String(error)}`);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`The task file at ${file} is not valid JSON; refusing to treat it as empty.`);
  }
  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === "object" && value !== null && !Array.isArray(value);
  if (!isRecord(parsed) || !isRecord(parsed.tasks) || !Object.values(parsed.tasks).every(isRecord)) {
    throw new Error(`The task file at ${file} has no valid tasks map; refusing to treat it as empty.`);
  }
  if (parsed.runtimeVersion !== TASKS_FILE_VERSION) {
    throw new Error(`Incompatible task file version ${String(parsed.runtimeVersion)}; expected ${TASKS_FILE_VERSION}.`);
  }
  return { tasks: parsed.tasks as Record<string, Task> };
}

export function writeTasksFile(file: string, tasks: Record<string, Task>): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, { runtimeVersion: TASKS_FILE_VERSION, tasks });
}

/**
 * Express a task intent through an exclusive-create marker file. Returns true
 * exactly when this caller won the race for the Task id.
 */
export function createTaskIntent(dir: string, taskId: string, intent: TaskIntent): boolean {
  return createExclusiveJsonFile(dir, taskId, intent, {
    maxBytes: DEFAULT_INTENT_BYTES,
    label: "Task intent",
  });
}

/** Field checks that make a parsed marker a usable intent. A record missing its
 *  holder identity cannot be attributed, so it is rejected rather than guessed. */
function validateTaskIntent(parsed: unknown): IntentValidation<TaskIntent> {
  const candidate = parsed as Partial<TaskIntent> | null;
  if (
    typeof candidate?.taskId !== "string" || candidate.taskId.trim() === ""
    || typeof candidate.participant !== "string" || candidate.participant.trim() === ""
    || typeof candidate.spawnId !== "string" || candidate.spawnId.trim() === ""
    || typeof candidate.timestamp !== "number" || !Number.isFinite(candidate.timestamp)
  ) {
    return { ok: false, reason: "requires non-empty taskId/participant/spawnId and finite timestamp" };
  }
  if (candidate.status !== undefined && candidate.status !== "completed" && candidate.status !== "failed") {
    return { ok: false, reason: "invalid submission status" };
  }
  if (typeof candidate.result !== "undefined" && typeof candidate.result !== "string") {
    return { ok: false, reason: "invalid submission result" };
  }
  if (
    typeof candidate.verdict !== "undefined"
    && candidate.verdict !== "pass"
    && candidate.verdict !== "fail"
  ) {
    return { ok: false, reason: "invalid submission verdict" };
  }
  return { ok: true, value: candidate as TaskIntent };
}

/**
 * Drain one pending intent file. Malformed records are consumed and reported so
 * one broken file can never block the queue; a record that cannot be parsed yet
 * is retried while it is younger than the publish grace, because destroying an
 * in-flight intent would leave its author waiting forever.
 */
export function takeTaskIntent(dir: string): { intent?: TaskIntent; diagnostic?: string } {
  return takeJsonIntent(dir, validateTaskIntent, { label: INTENT_LABEL });
}

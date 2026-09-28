/**
 * Durable Work Item persistence.
 *
 * Board layout (persists across restarts, never auto-cleaned):
 *   ~/.pi/agent/tasks/<sessionKey>/board.json           leader-owned board file
 *   ~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      exclusive-create claim intents
 *   ~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json exclusive-create submit intents
 *
 * Concurrency: the leader is the sole writer of `board.json`, replaced
 * atomically. A worker never writes the board; it expresses intent through an
 * exclusive-create marker file, so exactly one racer wins a contested claim.
 *
 * Operator-visible wording says "Work snapshot", not "Agent Teams": this package
 * owns the file and may be installed without the team runtime.
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
import { WORK_RUNTIME_VERSION, type BoardTask, type TaskIntent } from "./types.ts";

/** Intent label used in diagnostics, so an operator reads the same wording this
 * package has always produced. */
const INTENT_LABEL = "task intent";

/** An unparseable intent younger than this may still be mid-publish elsewhere,
 * so it is retried rather than destroyed. Re-exported under the name this
 * package has always used; the value and semantics are pi-kit's default. */
export const INTENT_PUBLISH_GRACE_MS = DEFAULT_INTENT_PUBLISH_GRACE_MS;

/** Root of all per-session board directories. */
export function tasksRoot(): string {
  return path.join(getAgentDir(), "tasks");
}

export { sessionKey };

export function boardDir(sessionFile: string | undefined, cwd: string): string {
  return path.join(tasksRoot(), sessionKey(sessionFile, cwd));
}

export function boardFilePath(sessionFile: string | undefined, cwd: string): string {
  return path.join(boardDir(sessionFile, cwd), "board.json");
}

export function claimsDir(boardDirectory: string): string {
  return path.join(boardDirectory, "claims");
}

export function submissionsDir(boardDirectory: string): string {
  return path.join(boardDirectory, "submissions");
}

/** Read the persisted board. An absent file is a fresh session; a present but
 * unreadable one is an error, never an empty board — silently treating it as
 * empty would discard durable Work. */
export function readBoardFile(file: string): { tasks: Record<string, BoardTask> } | undefined {
  let raw: string;
  try {
    raw = fs.readFileSync(file, "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw new Error(`Work snapshot at ${file} could not be read: ${error instanceof Error ? error.message : String(error)}`);
  }
  let parsed: { runtimeVersion?: number; tasks?: Record<string, BoardTask> };
  try {
    parsed = JSON.parse(raw) as { runtimeVersion?: number; tasks?: Record<string, BoardTask> };
  } catch {
    throw new Error(`Work snapshot at ${file} is not valid JSON; refusing to treat it as an empty board.`);
  }
  if (parsed.tasks && parsed.runtimeVersion !== WORK_RUNTIME_VERSION) {
    throw new Error(`Incompatible Work snapshot version ${String(parsed.runtimeVersion)}; expected ${WORK_RUNTIME_VERSION}.`);
  }
  return parsed.tasks ? { tasks: parsed.tasks } : undefined;
}

export function writeBoardFile(file: string, tasks: Record<string, BoardTask>): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, { runtimeVersion: WORK_RUNTIME_VERSION, tasks });
}

/**
 * Express a board intent through an exclusive-create marker file. Returns true
 * exactly when this caller won the race for the Work id.
 */
export function createTaskIntent(dir: string, taskId: string, intent: TaskIntent): boolean {
  return createExclusiveJsonFile(dir, taskId, intent, {
    maxBytes: DEFAULT_INTENT_BYTES,
    label: "Task intent",
  });
}

/** Field checks that make a parsed marker a usable intent. A record missing its
 * holder identity cannot be attributed, so it is rejected rather than guessed. */
function validateTaskIntent(parsed: unknown): IntentValidation<TaskIntent> {
  const candidate = parsed as Partial<TaskIntent> | null;
  if (
    typeof candidate?.taskId !== "string" || candidate.taskId.trim() === ""
    || typeof candidate.worker !== "string" || candidate.worker.trim() === ""
    || typeof candidate.spawnId !== "string" || candidate.spawnId.trim() === ""
    || typeof candidate.timestamp !== "number" || !Number.isFinite(candidate.timestamp)
  ) {
    return { ok: false, reason: "requires non-empty taskId/worker/spawnId and finite timestamp" };
  }
  if (candidate.status !== undefined && candidate.status !== "completed" && candidate.status !== "failed") {
    return { ok: false, reason: "invalid submission status" };
  }
  if (typeof candidate.result !== "undefined" && typeof candidate.result !== "string") {
    return { ok: false, reason: "invalid submission result" };
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

/**
 * Shared session files for the leader-owned snapshot, teammate outboxes and
 * inboxes, and the persistent task board.
 *
 * Runtime layout (removed at session shutdown):
 *   ~/.pi/agent/teammate/<sessionKey>/state.json      leader-owned snapshot
 *   ~/.pi/agent/teammate/<sessionKey>/events/*.jsonl  per-spawn report outboxes
 *   ~/.pi/agent/teammate/<sessionKey>/mail/*.jsonl    peer inbox files
 *   ~/.pi/agent/teammate/<sessionKey>/roster.json     living teammates, worker-readable
 *
 * Board layout (persists across restarts, never auto-cleaned):
 *   ~/.pi/agent/tasks/<sessionKey>/board.json         leader-owned board file
 *   ~/.pi/agent/tasks/<sessionKey>/claims/*.json      exclusive-create claim intents
 *   ~/.pi/agent/tasks/<sessionKey>/submissions/*.json exclusive-create submit intents
 *
 * Concurrency: the parent is the sole writer of state.json and board.json
 * (atomic tmp+rename). Teammates append only to their own outbox, append to
 * recipient inboxes, and express board intent through exclusive-create files.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import type { TaskIntent, TeamState, WorkerEvent } from "./types.ts";

const MAX_WORKER_EVENT_BYTES = 64 * 1024;
const MAX_INBOX_MESSAGE_BYTES = 64 * 1024;
const MAX_OUTBOX_READ_BYTES = 256 * 1024;
const MAX_INTENT_BYTES = 16 * 1024;

export function sessionKey(sessionFile: string | undefined, cwd: string): string {
  return crypto
    .createHash("sha256")
    .update(sessionFile ?? cwd)
    .digest("hex")
    .slice(0, 16);
}

export function sessionStateDir(sessionFile: string | undefined, cwd: string): string {
  return path.join(getAgentDir(), "teammate", sessionKey(sessionFile, cwd));
}

export function stateFilePath(sessionFile: string | undefined, cwd: string): string {
  return path.join(sessionStateDir(sessionFile, cwd), "state.json");
}

/** Write the leader-owned debug snapshot atomically (tmp + rename). */
export function writeStateFile(file: string, state: TeamState): void {
  writeJsonAtomic(file, state);
}

// ── Peer mail ─────────────────────────────────────────────────────

function safeName(name: string): string {
  return encodeURIComponent(name);
}

export function mailDir(stateFile: string): string {
  return path.join(path.dirname(stateFile), "mail");
}

export function inboxPath(stateFile: string, teammateName: string): string {
  return path.join(mailDir(stateFile), `inbox-${safeName(teammateName)}.jsonl`);
}

export function rosterPath(stateFile: string): string {
  return path.join(path.dirname(stateFile), "roster.json");
}

/** Append one message to a teammate inbox. Sent means this write succeeded. */
export function appendInboxMessage(file: string, message: { id: string; from: string; subject: string; body: string }): void {
  const record = `${JSON.stringify(message)}\n`;
  if (Buffer.byteLength(record, "utf-8") > MAX_INBOX_MESSAGE_BYTES) {
    throw new Error(`Message exceeds ${MAX_INBOX_MESSAGE_BYTES} bytes.`);
  }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.appendFileSync(file, record, { encoding: "utf-8", mode: 0o600 });
}

/** Publish the worker-readable roster of living teammates. */
export function writeRoster(file: string, teammates: Array<{ name: string; agent: string; status: string }>): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, { teammates });
}

/** Read the roster from inside a teammate process; unknown roster = empty. */
export function readRoster(file: string): Array<{ name: string; agent: string; status: string }> {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as { teammates?: Array<{ name: string; agent: string; status: string }> };
    return Array.isArray(parsed.teammates) ? parsed.teammates : [];
  } catch {
    return [];
  }
}

/** Read complete JSONL records after byteOffset (shared by outboxes and inboxes). */
export function readJsonlBatch(file: string, byteOffset: number): {
  records: unknown[];
  nextOffset: number;
  diagnostics: string[];
} {
  let fd: number | undefined;
  try {
    fd = fs.openSync(file, "r");
    const size = fs.fstatSync(fd).size;
    // A truncated/recreated file starts at zero; message ids make replay safe.
    const offset = byteOffset > size ? 0 : Math.max(0, byteOffset);
    const toRead = Math.min(MAX_OUTBOX_READ_BYTES, size - offset);
    if (toRead === 0) return { records: [], nextOffset: offset, diagnostics: [] };
    const raw = Buffer.allocUnsafe(toRead);
    const bytesRead = fs.readSync(fd, raw, 0, toRead, offset);
    const unread = raw.subarray(0, bytesRead);
    const lastNewline = unread.lastIndexOf(0x0a);
    if (lastNewline < 0) {
      // A line larger than the batch cap is malformed for this protocol; skip
      // this chunk so one sender cannot block draining indefinitely.
      return {
        records: [],
        nextOffset: bytesRead === MAX_OUTBOX_READ_BYTES ? offset + bytesRead : offset,
        diagnostics: ["malformed or unterminated record was consumed"],
      };
    }
    const complete = unread.subarray(0, lastNewline).toString("utf-8");
    const records: unknown[] = [];
    const diagnostics: string[] = [];
    for (const line of complete.split("\n")) {
      if (!line.trim()) continue;
      try {
        records.push(JSON.parse(line));
      } catch {
        diagnostics.push("malformed JSON record was consumed");
      }
    }
    return { records, nextOffset: offset + lastNewline + 1, diagnostics };
  } catch {
    return { records: [], nextOffset: 0, diagnostics: [] };
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

// ── Report outboxes ───────────────────────────────────────────────

/** Per-teammate append-only report log. Its filename cannot escape the dir. */
export function workerOutboxPath(stateFile: string, workerName: string, spawnId: string): string {
  return path.join(path.dirname(stateFile), "events", `${safeName(workerName)}.${safeName(spawnId)}.jsonl`);
}

/** Delete a drained per-spawn outbox after its final snapshot is published. */
export function removeWorkerOutbox(stateFile: string, workerName: string, spawnId: string): void {
  fs.rmSync(workerOutboxPath(stateFile, workerName, spawnId), { force: true });
}

/** Append one teammate report event. Workers never replace leader state. */
export function appendWorkerEvent(file: string, event: WorkerEvent): void {
  const record = `${JSON.stringify(event)}\n`;
  if (Buffer.byteLength(record, "utf-8") > MAX_WORKER_EVENT_BYTES) {
    throw new Error(`Worker event exceeds ${MAX_WORKER_EVENT_BYTES} bytes.`);
  }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.appendFileSync(file, record, { encoding: "utf-8", mode: 0o600 });
}

// ── Persistent task board ─────────────────────────────────────────

/** Root of all per-session board dirs (`~/.pi/agent/tasks/`). */
export function tasksRoot(): string {
  return path.join(getAgentDir(), "tasks");
}

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

export function readBoardFile(file: string): { tasks: Record<string, import("./types").BoardTask> } | undefined {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as { tasks?: Record<string, import("./types").BoardTask> };
    return parsed.tasks ? { tasks: parsed.tasks } : undefined;
  } catch {
    return undefined;
  }
}

export function writeBoardFile(file: string, tasks: Record<string, import("./types").BoardTask>): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, { tasks });
}

/**
 * Express a board intent through an exclusive-create marker file. Returns
 * true exactly when this caller won the race for the taskId.
 */
export function createTaskIntent(dir: string, taskId: string, intent: TaskIntent): boolean {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = path.join(dir, `${safeName(taskId)}.json`);
  const payload = JSON.stringify(intent);
  if (Buffer.byteLength(payload, "utf-8") > MAX_INTENT_BYTES) {
    throw new Error(`Task intent exceeds ${MAX_INTENT_BYTES} bytes.`);
  }
  try {
    fs.writeFileSync(file, payload, { encoding: "utf-8", mode: 0o600, flag: "wx" });
    return true;
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "EEXIST") return false;
    throw error;
  }
}

/**
 * Drain one pending intent file. Malformed records are consumed and reported
 * so one broken file can never block the queue.
 */
export function takeTaskIntent(dir: string): { intent?: TaskIntent; diagnostic?: string } {
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(dir).filter((name) => name.endsWith(".json")).sort();
  } catch {
    return {};
  }
  for (const name of entries) {
    const file = path.join(dir, name);
    try {
      const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as Partial<TaskIntent>;
      fs.rmSync(file, { force: true });
      if (
        typeof parsed.taskId !== "string"
        || typeof parsed.worker !== "string"
        || typeof parsed.spawnId !== "string"
      ) {
        return { diagnostic: `malformed task intent "${name}" was consumed (missing taskId/worker/spawnId)` };
      }
      return { intent: parsed as TaskIntent };
    } catch {
      fs.rmSync(file, { force: true });
      return { diagnostic: `unreadable task intent "${name}" was consumed` };
    }
  }
  return {};
}

// ── Atomic JSON IO ────────────────────────────────────────────────

function writeJsonAtomic(file: string, value: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(value), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

// ── Expired runtime-dir cleanup ───────────────────────────────────

/** Root of all per-session teammate runtime dirs (`~/.pi/agent/teammate/`). */
export function stateDirsRoot(): string {
  return path.join(getAgentDir(), "teammate");
}

/** Remove the current session's runtime dir (called on session_shutdown). */
export function removeSessionStateDir(sessionFile: string | undefined, cwd: string): void {
  fs.rmSync(sessionStateDir(sessionFile, cwd), { recursive: true, force: true });
}

/**
 * Sweep runtime dirs whose last write is older than maxAgeMs. Board dirs are
 * never swept. Called on session_start so abandoned sessions never pile up.
 */
export function cleanupExpiredStateDirs(maxAgeMs: number): number {
  const root = stateDirsRoot();
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(root);
  } catch {
    return 0; // root missing — nothing to clean
  }
  const now = Date.now();
  let removed = 0;
  for (const name of entries) {
    const full = path.join(root, name);
    try {
      const st = fs.statSync(full);
      if (st.isDirectory() && now - st.mtimeMs > maxAgeMs) {
        fs.rmSync(full, { recursive: true, force: true });
        removed++;
      }
    } catch {
      // Unreadable entries are skipped, not fatal.
    }
  }
  return removed;
}

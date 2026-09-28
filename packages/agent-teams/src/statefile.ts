/**
 * Shared session files for the leader-owned snapshot, teammate outboxes and
 * inboxes. The persistent task board lives in @fradser/pi-tasks; `sessionKey` comes from
 * pi-kit so both packages agree on which session a directory belongs to.
 *
 * Runtime layout (removed at session shutdown):
 *   ~/.pi/agent/teammate/<sessionKey>/state.json      leader-owned snapshot
 *   ~/.pi/agent/teammate/<sessionKey>/events/*.jsonl  per-spawn report outboxes
 *   ~/.pi/agent/teammate/<sessionKey>/mail/*.jsonl    peer inbox files
 *   ~/.pi/agent/teammate/<sessionKey>/roster.json     living teammates, worker-readable
 *
 * Concurrency: the parent is the sole writer of state.json and board.json
 * (atomic tmp+rename). Teammates append only to their own outbox, append to
 * recipient inboxes, and express board intent through exclusive-create files.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import {
  appendJsonlLine,
  readJsonlBatch,
  safeFileName,
  sessionKey,
  writeJsonAtomic,
} from "@fradser/pi-kit";
// Re-exported so consumers of this module keep one import site for session
// files. The implementations are pi-kit's: an incremental JSONL read and an
// atomic replace are not agent-teams concepts.
export { readJsonlBatch, writeJsonAtomic };
import type { TeamState, WorkerEvent } from "./types.ts";

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

export function mailDir(stateFile: string): string {
  return path.join(path.dirname(stateFile), "mail");
}

export function inboxPath(stateFile: string, teammateName: string): string {
  return path.join(mailDir(stateFile), `inbox-${safeFileName(teammateName)}.jsonl`);
}

export function rosterPath(stateFile: string): string {
  return path.join(path.dirname(stateFile), "roster.json");
}

/** Append one message to a teammate inbox. Sent means this write succeeded. */
export function appendInboxMessage(file: string, message: { id: string; from: string; subject: string; body: string }): void {
  appendJsonlLine(file, message, { label: "Message" });
}

/** Publish the worker-readable roster of living teammates. */
export function writeRoster(file: string, teammates: Array<{ name: string; agent: string; spawnId?: string; status: string; tools?: string[]; currentTaskId?: string; assignment?: import("./types.ts").WorkerAssignment }>): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, { teammates });
}

/** Read the roster from inside a teammate process; unknown roster = empty. */
export function readRoster(file: string): Array<{ name: string; agent: string; spawnId?: string; status: string; tools?: string[]; currentTaskId?: string; assignment?: import("./types.ts").WorkerAssignment }> {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as { teammates?: Array<{ name: string; agent: string; spawnId?: string; status: string; tools?: string[]; currentTaskId?: string; assignment?: import("./types.ts").WorkerAssignment }> };
    return Array.isArray(parsed.teammates) ? parsed.teammates : [];
  } catch {
    return [];
  }
}

// ── Report outboxes ───────────────────────────────────────────────

/** Per-teammate append-only report log. Its filename cannot escape the dir. */
export function workerOutboxPath(stateFile: string, workerName: string, spawnId: string): string {
  return path.join(path.dirname(stateFile), "events", `${safeFileName(workerName)}.${safeFileName(spawnId)}.jsonl`);
}

/** Delete a drained per-spawn outbox after its final snapshot is published. */
export function removeWorkerOutbox(stateFile: string, workerName: string, spawnId: string): void {
  fs.rmSync(workerOutboxPath(stateFile, workerName, spawnId), { force: true });
}

/** Append one teammate report event. Workers never replace leader state. */
export function appendWorkerEvent(file: string, event: WorkerEvent): void {
  appendJsonlLine(file, event, { label: "Worker event" });
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

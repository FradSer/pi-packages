/**
 * Shared session files for the leader-owned debug snapshot and worker outboxes.
 *
 * Layout: `~/.pi/agent/teammate/<sessionKey>/state.json`, sessionKey derived
 * from the session file (or cwd for ephemeral sessions) so different sessions
 * never share a board file.
 *
 * Concurrency: the parent is the sole writer of state.json (atomic tmp+rename).
 * Workers append requests only to their own JSONL outbox; the state snapshot is
 * not a worker inbox or a communication channel.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import type { TeammateState, WorkerEvent } from "./types";

const MAX_WORKER_EVENT_BYTES = 64 * 1024;
const MAX_OUTBOX_READ_BYTES = 256 * 1024;

export function sessionStateDir(sessionFile: string | undefined, cwd: string): string {
  const key = crypto
    .createHash("sha256")
    .update(sessionFile ?? cwd)
    .digest("hex")
    .slice(0, 16);
  return path.join(getAgentDir(), "teammate", key);
}

export function stateFilePath(sessionFile: string | undefined, cwd: string): string {
  return path.join(sessionStateDir(sessionFile, cwd), "state.json");
}

/** Write the leader-owned debug snapshot atomically (tmp + rename). */
export function writeStateFile(file: string, state: TeammateState): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

/** Per-run append-only event log. Its filename cannot escape the session dir. */
export function workerOutboxPath(stateFile: string, workerName: string, runId: string): string {
  return path.join(path.dirname(stateFile), "events", `${encodeURIComponent(workerName)}.${encodeURIComponent(runId)}.jsonl`);
}

/** Delete a drained per-run outbox after its final snapshot is safely published. */
export function removeWorkerOutbox(stateFile: string, workerName: string, runId: string): void {
  fs.rmSync(workerOutboxPath(stateFile, workerName, runId), { force: true });
}

/** Append one worker event. Workers never replace the leader-owned state snapshot. */
export function appendWorkerEvent(file: string, event: WorkerEvent): void {
  const record = `${JSON.stringify(event)}\n`;
  if (Buffer.byteLength(record, "utf-8") > MAX_WORKER_EVENT_BYTES) {
    throw new Error(`Worker event exceeds ${MAX_WORKER_EVENT_BYTES} bytes.`);
  }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.appendFileSync(file, record, { encoding: "utf-8", mode: 0o600 });
}

/** Read a bounded batch of complete JSONL records after byteOffset. */
export function readWorkerEvents(file: string, byteOffset: number): { events: unknown[]; nextOffset: number; diagnostics: string[] } {
  let fd: number | undefined;
  try {
    fd = fs.openSync(file, "r");
    const size = fs.fstatSync(fd).size;
    // A truncated/recreated outbox starts at zero; event IDs make replay safe.
    const offset = byteOffset > size ? 0 : Math.max(0, byteOffset);
    const toRead = Math.min(MAX_OUTBOX_READ_BYTES, size - offset);
    if (toRead === 0) return { events: [], nextOffset: offset, diagnostics: [] };
    const raw = Buffer.allocUnsafe(toRead);
    const bytesRead = fs.readSync(fd, raw, 0, toRead, offset);
    const unread = raw.subarray(0, bytesRead);
    const lastNewline = unread.lastIndexOf(0x0a);
    if (lastNewline < 0) {
      // A line larger than the batch cap is malformed for this protocol; skip
      // this chunk so one worker cannot block event draining indefinitely.
      return {
        events: [],
        nextOffset: bytesRead === MAX_OUTBOX_READ_BYTES ? offset + bytesRead : offset,
        diagnostics: ["malformed or unterminated worker outbox record was consumed"],
      };
    }
    const complete = unread.subarray(0, lastNewline).toString("utf-8");
    const events: unknown[] = [];
    const diagnostics: string[] = [];
    for (const line of complete.split("\n")) {
      if (!line.trim()) continue;
      try {
        events.push(JSON.parse(line));
      } catch {
        diagnostics.push("malformed worker outbox JSON record was consumed");
      }
    }
    return { events, nextOffset: offset + lastNewline + 1, diagnostics };
  } catch {
    return { events: [], nextOffset: 0, diagnostics: [] };
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

// ── Expired state-dir cleanup ───────────────────────────────────────

/** Root of all per-session teammate state dirs (`~/.pi/agent/teammate/`). */
export function stateDirsRoot(): string {
  return path.join(getAgentDir(), "teammate");
}

/** Remove the current session's state dir (called on session_shutdown). */
export function removeSessionStateDir(sessionFile: string | undefined, cwd: string): void {
  fs.rmSync(sessionStateDir(sessionFile, cwd), { recursive: true, force: true });
}

/**
 * Sweep state dirs whose last write is older than maxAgeMs. Returns how many
 * were removed. Called on session_start so abandoned sessions never pile up.
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

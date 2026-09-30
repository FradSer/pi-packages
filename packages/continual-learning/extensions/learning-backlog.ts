/**
 * The learning backlog: settled work that was never learned from.
 *
 * Learning today is opportunistic. A task is learned when it settles, if
 * auto-learning is on and the zero-token screen finds durable evidence.
 * Everything else is dropped: a task that settled with the toggle off, one the
 * screen judged valueless, one that arrived before this package was installed.
 * That is a heuristic screen making an irreversible discard, and the gap is
 * permanent — nothing ever revisits those tasks.
 *
 * Closing it needs three things this module provides: a queue of references, a
 * cursor, and an explicit entry point to drain it. It deliberately does *not*
 * run from the automatic path. A backlog that drains itself would spend an
 * unbounded amount of the user's tokens at a moment they did not choose, which
 * is the same reason the zero-token screen exists in the first place.
 *
 * **References, not content.** An entry records where the task lives — session
 * file and entry indices — never the text. That keeps the backlog a small index
 * rather than a second copy of the user's conversations, and it makes the
 * failure mode honest: when a session file is gone the entry is reported as
 * unlearnable instead of silently disappearing or being reconstructed from
 * something we no longer have.
 */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { resolveMemoryPaths } from "./memory-paths";

/** Bounded so a long-lived install cannot grow an unbounded private file. */
export const MAX_BACKLOG_BYTES = 4 * 1024 * 1024;
const MAX_BACKLOG_RECORD_BYTES = 4_096;

/** Why a task was not learned when it settled. */
export type BacklogReason = "auto-memory-off" | "screen-found-nothing" | "no-session-reference";

export interface BacklogEntry {
  version: 1;
  /** The session file the task's entries live in. Read at drain time. */
  sessionFile: string;
  /** Inclusive entry index where the task starts. */
  from: number;
  /** Inclusive entry index where it ends. */
  to: number;
  /** Digest of the referenced slice, so a drained task is recognisable. */
  digest: string;
  reason: BacklogReason;
  queuedAt: string;
  /** Whether the pointer still resolves. */
  readable?: boolean;
}

export function backlogFile(cwd: string, agentDir = getAgentDir()): string {
  // The private root, beside Memory and never inside a Memory root: that root
  // admits only regular `.md` children.
  return path.join(resolveMemoryPaths(cwd, agentDir).agentDir, "learning", "backlog.jsonl");
}

function rotateIfNeeded(file: string, incoming: number): void {
  let size: number;
  try {
    size = fs.statSync(file).size;
  } catch {
    return;
  }
  if (size + incoming <= MAX_BACKLOG_BYTES) return;
  let raw: Buffer;
  try {
    raw = fs.readFileSync(file);
  } catch {
    return;
  }
  const lines = raw.toString("utf-8").split("\n");
  if (lines[lines.length - 1] !== "") lines.pop();
  const kept = lines.slice();
  while (kept.length > 1 && Buffer.byteLength(`${kept.join("\n")}\n`, "utf-8") + incoming > MAX_BACKLOG_BYTES) {
    kept.shift();
  }
  try {
    const temporary = `${file}.${process.pid}.rotate.tmp`;
    fs.writeFileSync(temporary, `${kept.join("\n")}\n`, { mode: 0o600 });
    fs.renameSync(temporary, file);
  } catch {
    // Rotation is best-effort: a backlog that cannot be trimmed still queues.
  }
}

/** Queue one settled task. Returns false rather than throwing: losing a
 *  measurement must never fail the run that produced it. */
export function enqueueBacklog(input: {
  cwd: string;
  sessionFile?: string;
  from: number;
  to: number;
  digest: string;
  reason: BacklogReason;
  agentDir?: string;
}): boolean {
  if (!input.sessionFile) return false;
  const entry: BacklogEntry = {
    version: 1,
    sessionFile: input.sessionFile,
    from: input.from,
    to: input.to,
    digest: input.digest,
    reason: input.reason,
    queuedAt: new Date().toISOString(),
  };
  const file = backlogFile(input.cwd, input.agentDir);
  const line = `${JSON.stringify(entry)}\n`;
  if (Buffer.byteLength(line, "utf-8") > MAX_BACKLOG_RECORD_BYTES) return false;
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    rotateIfNeeded(file, Buffer.byteLength(line, "utf-8"));
    fs.appendFileSync(file, line, { encoding: "utf-8", mode: 0o600 });
    return true;
  } catch {
    return false;
  }
}

export interface BacklogRead {
  entries: BacklogEntry[];
  /** Entries whose session file no longer resolves. Never reconstructed. */
  unlearnable: BacklogEntry[];
  malformed: number;
  /** How many records a previous drain already consumed. */
  consumed: number;
}

const CURSOR_FILE = "learning-backlog.cursor.json";

export function readBacklog(cwd: string, agentDir = getAgentDir()): BacklogRead {
  const file = backlogFile(cwd, agentDir);
  let raw: string;
  try {
    raw = fs.readFileSync(file, "utf-8");
  } catch {
    return { entries: [], unlearnable: [], malformed: 0, consumed: 0 };
  }
  const entries: BacklogEntry[] = [];
  let malformed = 0;
  for (const line of raw.split("\n")) {
    if (!line) continue;
    try {
      const value = JSON.parse(line) as BacklogEntry;
      if (value && value.version === 1 && typeof value.sessionFile === "string") entries.push(value);
      else malformed += 1;
    } catch {
      malformed += 1;
    }
  }
  // A pointer whose session file is gone is reported, not dropped and not
  // guessed at. Silently discarding it would make the backlog look drained.
  const readable: BacklogEntry[] = [];
  const unlearnable: BacklogEntry[] = [];
  for (const entry of entries) {
    (fs.existsSync(entry.sessionFile) ? readable : unlearnable).push(entry);
  }
  return { entries: readable, unlearnable, malformed, consumed: readCursor(cwd, agentDir) };
}

/** The drain cursor: how many entries the backlog's head has already served. */
export function readCursor(cwd: string, agentDir = getAgentDir()): number {
  try {
    const value = JSON.parse(fs.readFileSync(cursorPath(cwd, agentDir), "utf-8")) as { consumed?: unknown };
    return typeof value.consumed === "number" && Number.isSafeInteger(value.consumed) && value.consumed >= 0
      ? value.consumed
      : 0;
  } catch {
    return 0;
  }
}

export function advanceCursor(cwd: string, consumed: number, agentDir = getAgentDir()): boolean {
  try {
    const file = cursorPath(cwd, agentDir);
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.writeFileSync(file, `${JSON.stringify({ consumed })}\n`, { mode: 0o600 });
    return true;
  } catch {
    return false;
  }
}

function cursorPath(cwd: string, agentDir: string): string {
  return path.join(path.dirname(backlogFile(cwd, agentDir)), CURSOR_FILE);
}

/** What a drain would do, without doing it. */
export function backlogStatus(cwd: string, agentDir = getAgentDir()): {
  pending: number;
  unlearnable: number;
  malformed: number;
  consumed: number;
  reason: "empty" | "ready" | "unlearnable-only";
} {
  const read = readBacklog(cwd, agentDir);
  const pending = Math.max(0, read.entries.length - read.consumed);
  return {
    pending,
    unlearnable: read.unlearnable.length,
    malformed: read.malformed,
    consumed: read.consumed,
    reason: read.entries.length === 0
      ? (read.unlearnable.length ? "unlearnable-only" : "empty")
      : pending > 0 ? "ready" : "empty",
  };
}

/**
 * Shared state file — the medium that lets spawned worker processes (separate
 * Pi processes) see and update the teammate mailbox/task board that lives in
 * the parent session.
 *
 * Layout: `~/.pi/agent/teammate/<sessionKey>/state.json`, sessionKey derived
 * from the session file (or cwd for ephemeral sessions) so different sessions
 * never share a board file.
 *
 * Concurrency: writes are atomic (write temp file + rename) so a worker's
 * read-modify-write never leaves partial JSON for the parent (or a sibling
 * worker) to read.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";
import type { TeammateState } from "./types";

export function sessionStateDir(sessionFile: string | undefined, cwd: string): string {
  const key = crypto
    .createHash("sha256")
    .update(sessionFile ?? cwd)
    .digest("hex")
    .slice(0, 16);
  return path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "teammate", key);
}

export function stateFilePath(sessionFile: string | undefined, cwd: string): string {
  return path.join(sessionStateDir(sessionFile, cwd), "state.json");
}

/** Write the full state snapshot atomically (tmp + rename). */
export function writeStateFile(file: string, state: TeammateState): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

/** Read a state snapshot; returns undefined when missing/corrupt. */
export function readStateFile(file: string): TeammateState | undefined {
  try {
    const raw = fs.readFileSync(file, "utf-8");
    const parsed = JSON.parse(raw) as TeammateState;
    if (!parsed || typeof parsed !== "object") return undefined;
    return parsed;
  } catch {
    return undefined;
  }
}

// ── Expired state-dir cleanup ───────────────────────────────────────

/** Root of all per-session teammate state dirs (`~/.pi/agent/teammate/`). */
export function stateDirsRoot(): string {
  return path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "teammate");
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

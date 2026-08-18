import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { KeyboardState } from "./types";

export interface SessionGlowRecord {
  sessionId: string;
  pid: number;
  cwd: string;
  status: "running" | "idle" | "settled" | "error" | "need_approval" | "exited";
  hasUnread: boolean;
  updatedAt: number;
}

export function getRegistryDir(): string {
  // Test seam: allow pointing at an isolated registry so tests never touch the
  // real ~/.pi/agent/directory-sessions directory.
  const override = process.env.PI_DIRECTORY_SESSIONS_DIR;
  if (override) return override;
  return path.join(os.homedir(), ".pi", "agent", "directory-sessions");
}

export function getSessionFileKey(cwd: string): string {
  const normalized = path.resolve(cwd || process.cwd());
  return `--${normalized.replace(/^[/\\\\]/, "").replace(/[/\\\\:]/g, "-")}--`;
}

export function getDirectoryRegistryPath(cwd: string): string {
  return path.join(getRegistryDir(), getSessionFileKey(cwd));
}

export function isProcessAlive(pid: number): boolean {
  if (!pid || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Writes or updates the session's active glow and unread state in the registry.
 */
export function writeSessionGlowState(record: SessionGlowRecord): void {
  try {
    const dir = getDirectoryRegistryPath(record.cwd);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const filePath = path.join(dir, `${record.sessionId}.json`);
    const tmpPath = `${filePath}.tmp.${Date.now()}`;

    // Merge with existing session data if present to avoid overwriting other fields
    let merged: Record<string, unknown> = { ...record };
    if (fs.existsSync(filePath)) {
      try {
        const existing = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        if (existing && typeof existing === "object") {
          merged = { ...existing, ...record };
        }
      } catch {
        // use fresh record
      }
    }

    fs.writeFileSync(tmpPath, JSON.stringify(merged, null, 2), "utf-8");
    fs.renameSync(tmpPath, filePath);
  } catch {
    // Best-effort write
  }
}

/**
 * Removes the session record upon clean shutdown.
 */
export function removeSessionGlowState(cwd: string, sessionId: string): void {
  try {
    const filePath = path.join(getDirectoryRegistryPath(cwd), `${sessionId}.json`);
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
  } catch {
    // Best-effort remove
  }
}

/**
 * Sweeps the whole registry and removes glow records whose owning process is no
 * longer alive. Sessions that exit unexpectedly (crash, SIGKILL, terminal closed
 * without a clean session_shutdown) never run removeSessionGlowState, so their
 * leftover unread (settled) records would otherwise pile up and keep the green
 * light on. Called at session start to clear that residue before evaluating.
 *
 * Deliberately cleans only dead-process records: a genuinely live session that
 * is still unread keeps its glow record (and green light). No time-based expiry.
 */
export function pruneOrphanedGlowStates(): number {
  const baseDir = getRegistryDir();
  if (!fs.existsSync(baseDir)) return 0;

  let removed = 0;
  try {
    const dirEntries = fs.readdirSync(baseDir, { withFileTypes: true });
    for (const dirEntry of dirEntries) {
      if (!dirEntry.isDirectory()) continue;
      const subDirPath = path.join(baseDir, dirEntry.name);
      let sessionFiles: string[] = [];
      try {
        sessionFiles = fs.readdirSync(subDirPath);
      } catch {
        continue;
      }

      for (const file of sessionFiles) {
        if (!file.endsWith(".json")) continue;
        const filePath = path.join(subDirPath, file);
        try {
          const content = fs.readFileSync(filePath, "utf-8");
          const record = JSON.parse(content) as SessionGlowRecord;
          if (!record || typeof record !== "object" || typeof record.pid !== "number") continue;
          if (!isProcessAlive(record.pid)) {
            try {
              fs.unlinkSync(filePath);
              removed++;
            } catch {}
          }
        } catch {
          // Ignore unreadable / non-glow files (all .json in the shared dir)
        }
      }
    }
  } catch {
    // Best-effort sweep
  }
  return removed;
}

export interface GlobalStateSummary {
  effectiveState: KeyboardState;
  hasAnyUnread: boolean;
  hasAnyRunning: boolean;
  hasAnyError: boolean;
  hasAnyNeedApproval: boolean;
  activeSessionCount: number;
}

/**
 * Reads all active sessions across all project directories, prunes dead PIDs,
 * and determines the single authoritative global lighting state.
 *
 * Precedence:
 * 1. Fatal Error (any session has fatal error) -> "error" (Red Blinking)
 * 2. Need Approval (any session is waiting for user confirmation) -> "need_approval" (Yellow Blinking)
 * 3. Unread Chat (ANY active session has unread messages) -> "unread_chat" (Green Breathing)
 * 4. Thinking / Running (any session is actively executing) -> "thinking" (Blue Breathing)
 * 5. Idle (all sessions are read and idle) -> "idle" (White Breathing)
 */
export function evaluateGlobalLightingState(
  selfSessionId?: string,
  selfRecord?: Partial<SessionGlowRecord>,
): GlobalStateSummary {
  const baseDir = getRegistryDir();
  const now = Date.now();
  const maxStaleAgeMs = 5 * 60 * 1000; // 5 minutes

  const allRecords: SessionGlowRecord[] = [];

  if (fs.existsSync(baseDir)) {
    try {
      const dirEntries = fs.readdirSync(baseDir, { withFileTypes: true });
      for (const dirEntry of dirEntries) {
        if (!dirEntry.isDirectory()) continue;

        const subDirPath = path.join(baseDir, dirEntry.name);
        let sessionFiles: string[] = [];
        try {
          sessionFiles = fs.readdirSync(subDirPath);
        } catch {
          continue;
        }

        for (const file of sessionFiles) {
          if (!file.endsWith(".json")) continue;
          const filePath = path.join(subDirPath, file);

          try {
            const content = fs.readFileSync(filePath, "utf-8");
            const record = JSON.parse(content) as SessionGlowRecord;

            if (!record || typeof record !== "object") continue;

            // Prune dead process IDs
            if (!isProcessAlive(record.pid)) {
              try {
                fs.unlinkSync(filePath);
              } catch {}
              continue;
            }

            // Skip stale records
            if (now - (record.updatedAt || 0) > maxStaleAgeMs) {
              continue;
            }

            // If this is self, use the latest in-memory selfRecord values
            if (selfSessionId && record.sessionId === selfSessionId && selfRecord) {
              allRecords.push({ ...record, ...selfRecord } as SessionGlowRecord);
            } else {
              allRecords.push(record);
            }
          } catch {
            // Ignore unreadable files
          }
        }
      }
    } catch {
      // Ignore base scan errors
    }
  }

  // Ensure self record is included if not found on disk yet
  if (selfSessionId && selfRecord && !allRecords.some((r) => r.sessionId === selfSessionId)) {
    allRecords.push({
      sessionId: selfSessionId,
      pid: process.pid,
      cwd: process.cwd(),
      status: "idle",
      hasUnread: false,
      updatedAt: now,
      ...selfRecord,
    } as SessionGlowRecord);
  }

  let hasAnyError = false;
  let hasAnyNeedApproval = false;
  let hasAnyUnread = false;
  let hasAnyRunning = false;

  for (const r of allRecords) {
    if (r.status === "error") {
      hasAnyError = true;
    }
    if (r.status === "need_approval") {
      hasAnyNeedApproval = true;
    }
    if (r.hasUnread) {
      hasAnyUnread = true;
    }
    if (r.status === "running") {
      hasAnyRunning = true;
    }
  }

  let effectiveState: KeyboardState = "idle";
  if (hasAnyError) {
    effectiveState = "error";
  } else if (hasAnyNeedApproval) {
    effectiveState = "need_approval";
  } else if (hasAnyUnread) {
    effectiveState = "unread_chat";
  } else if (hasAnyRunning) {
    effectiveState = "thinking";
  } else {
    effectiveState = "idle";
  }

  return {
    effectiveState,
    hasAnyUnread,
    hasAnyRunning,
    hasAnyError,
    hasAnyNeedApproval,
    activeSessionCount: allRecords.length,
  };
}

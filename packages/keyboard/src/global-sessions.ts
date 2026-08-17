import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export interface SessionRecord {
  sessionId: string;
  pid: number;
  cwd: string;
  status: "running" | "idle" | "settled" | "exited";
  updatedAt: number;
}

export function getRegistryDir(): string {
  return path.join(os.homedir(), ".pi", "agent", "directory-sessions");
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
 * Scans all directory session registries to check if any other session is currently running.
 * Automatically checks PID vitality and excludes dead or stale processes.
 */
export function hasOtherRunningSessions(excludePid: number = process.pid): boolean {
  const baseDir = getRegistryDir();
  if (!fs.existsSync(baseDir)) return false;

  const now = Date.now();
  const maxStaleAgeMs = 5 * 60 * 1000; // 5 minutes max stale threshold

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
          const record = JSON.parse(content) as SessionRecord;

          if (!record || typeof record !== "object") continue;
          if (record.pid === excludePid) continue;

          // Check if process is alive and actively running
          if (record.status === "running" && isProcessAlive(record.pid)) {
            if (now - (record.updatedAt || 0) < maxStaleAgeMs) {
              return true;
            }
          }
        } catch {
          // Ignore unreadable or corrupt temp files
        }
      }
    }
  } catch {
    return false;
  }

  return false;
}

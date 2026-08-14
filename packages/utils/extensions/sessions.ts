/**
 * @fradser/pi-utils — cross-session awareness and directory recap extension.
 *
 * Provides multi-session awareness for Pi sessions operating in the same project directory.
 * - Registers session status, latest goal, and recap in ~/.pi/agent/directory-sessions/
 * - Prunes dead session process IDs (PIDs) automatically
 * - Injects cross-session recaps into system prompt when starting and per-turn context before LLM calls
 * - Updates a passive TUI widget above the editor to show live active sessions in cwd
 * - Provides /sessions and /recap commands to inspect directory sessions
 * - Registers the list_directory_sessions tool for agents to query other active sessions
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export interface SessionInfo {
  sessionId: string;
  sessionFile?: string;
  sessionName?: string;
  pid: number;
  cwd: string;
  startedAt: number;
  updatedAt: number;
  status: "running" | "idle" | "settled" | "exited";
  latestGoal?: string;
  recap?: string;
  modifiedFiles?: string[];
}

/**
 * Returns the base directory where session registry files are stored.
 */
export function getRegistryDir(): string {
  return path.join(os.homedir(), ".pi", "agent", "directory-sessions");
}

/**
 * Encodes a cwd path into a file-system safe directory key.
 * E.g. "/Users/foo/bar" -> "--Users-foo-bar--"
 */
export function getSessionFileKey(cwd: string): string {
  const normalized = path.resolve(cwd);
  return `--${normalized.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")}--`;
}

/**
 * Returns the directory path for a specific cwd in the session registry.
 */
export function getDirectoryRegistryPath(cwd: string): string {
  return path.join(getRegistryDir(), getSessionFileKey(cwd));
}

/**
 * Checks if a process with the given PID is currently alive on the OS.
 */
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
 * Writes or updates a session's metadata in the registry.
 */
export function writeSessionInfo(info: SessionInfo): void {
  try {
    const dir = getDirectoryRegistryPath(info.cwd);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const filePath = path.join(dir, `${info.sessionId}.json`);
    const tmpPath = `${filePath}.tmp.${Date.now()}`;
    fs.writeFileSync(tmpPath, JSON.stringify(info, null, 2), "utf-8");
    fs.renameSync(tmpPath, filePath);
  } catch {
    // Best-effort registry write
  }
}

/**
 * Removes a session file from the registry.
 */
export function removeSessionInfo(cwd: string, sessionId: string): void {
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
 * Reads, cleans up dead PIDs, and returns all registered sessions for a directory.
 */
export function cleanAndListDirectorySessions(
  cwd: string,
  excludeSessionId?: string,
  maxStaleAgeMs: number = 60 * 60 * 1000 // 1 hour
): SessionInfo[] {
  const dir = getDirectoryRegistryPath(cwd);
  if (!fs.existsSync(dir)) return [];

  const now = Date.now();
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return [];
  }

  const sessions: SessionInfo[] = [];

  for (const file of entries) {
    if (!file.endsWith(".json")) continue;
    const filePath = path.join(dir, file);
    try {
      const raw = fs.readFileSync(filePath, "utf-8");
      const info: SessionInfo = JSON.parse(raw);

      // Exclude self if requested
      if (excludeSessionId && info.sessionId === excludeSessionId) {
        continue;
      }

      // Check PID liveness
      if (!isProcessAlive(info.pid)) {
        // Process is dead. If stale or marked exited, clean up file
        if (info.status === "exited" || now - info.updatedAt > maxStaleAgeMs) {
          try {
            fs.unlinkSync(filePath);
          } catch {}
          continue;
        } else {
          // Mark as exited and update
          info.status = "exited";
          try {
            fs.writeFileSync(filePath, JSON.stringify(info, null, 2), "utf-8");
          } catch {}
        }
      } else if (now - info.updatedAt > maxStaleAgeMs) {
        // Alive but inactive for over an hour: mark settled
        if (info.status === "running") {
          info.status = "settled";
        }
      }

      sessions.push(info);
    } catch {
      // Malformed file, prune
      try {
        fs.unlinkSync(filePath);
      } catch {}
    }
  }

  // Sort by updatedAt descending (most recent first)
  sessions.sort((a, b) => b.updatedAt - a.updatedAt);
  return sessions;
}

/**
 * Formats a list of sessions into a concise markdown recap for prompt injection or display.
 */
export function formatCrossSessionRecap(sessions: SessionInfo[]): string {
  if (sessions.length === 0) {
    return "";
  }

  // Cap at top 5 most recent sessions to bound token consumption
  const cappedSessions = sessions.slice(0, 5);

  const now = Date.now();
  const lines: string[] = [
    "### Other Sessions in Directory",
    "The following other Pi coding sessions are active or recently updated in this directory:",
  ];

  for (const s of cappedSessions) {
    const name = s.sessionName ? `"${s.sessionName}"` : `Session [${s.sessionId.slice(0, 8)}]`;
    const ageSec = Math.max(0, Math.round((now - s.updatedAt) / 1000));
    let timeAgo = `${ageSec}s ago`;
    if (ageSec >= 60) {
      const ageMin = Math.round(ageSec / 60);
      timeAgo = `${ageMin}m ago`;
    }

    const statusLabel = s.status.toUpperCase();
    lines.push(`- **${name}** (PID ${s.pid}, status: ${statusLabel}, updated ${timeAgo}):`);
    if (s.latestGoal) {
      lines.push(`  - **Goal**: ${s.latestGoal}`);
    }
    if (s.recap) {
      lines.push(`  - **Recap**: ${s.recap}`);
    }
    if (s.modifiedFiles && s.modifiedFiles.length > 0) {
      lines.push(`  - **Recent files**: ${s.modifiedFiles.slice(0, 5).join(", ")}`);
    }
  }

  lines.push("\nUse this context to avoid conflicting edits and build on work done in parallel sessions.");
  return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
  let currentSessionId: string = `sess-${process.pid}-${Date.now().toString(36)}`;
  let currentSessionName: string | undefined = undefined;
  let currentGoal: string | undefined = undefined;
  let currentRecap: string | undefined = undefined;
  const currentStartedAt: number = Date.now();
  const currentModifiedFiles: Set<string> = new Set();

  function updateSelf(ctxCwd: string, status: SessionInfo["status"]) {
    const info: SessionInfo = {
      sessionId: currentSessionId,
      sessionFile: undefined,
      sessionName: currentSessionName,
      pid: process.pid,
      cwd: ctxCwd,
      startedAt: currentStartedAt,
      updatedAt: Date.now(),
      status,
      latestGoal: currentGoal,
      recap: currentRecap,
      modifiedFiles: Array.from(currentModifiedFiles),
    };
    writeSessionInfo(info);
  }

  pi.on("session_start", async (_event, ctx) => {
    const file = ctx.sessionManager?.getSessionFile();
    if (file) {
      currentSessionId = path.basename(file, ".jsonl");
    }
    updateSelf(ctx.cwd, "idle");
  });

  pi.on("session_info_changed", async (event, ctx) => {
    currentSessionName = event.name;
    updateSelf(ctx.cwd, "idle");
  });

  pi.on("before_agent_start", async (event, ctx) => {
    const file = ctx.sessionManager?.getSessionFile();
    if (file) {
      currentSessionId = path.basename(file, ".jsonl");
    }

    currentGoal = event.prompt.trim().slice(0, 300);
    updateSelf(ctx.cwd, "running");

    const otherSessions = cleanAndListDirectorySessions(ctx.cwd, currentSessionId);
    if (otherSessions.length > 0) {
      const recapText = formatCrossSessionRecap(otherSessions);
      return {
        systemPrompt: event.systemPrompt + "\n\n" + recapText,
      };
    }
  });

  pi.on("agent_settled", async (_event, ctx) => {
    updateSelf(ctx.cwd, "idle");
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    removeSessionInfo(ctx.cwd, currentSessionId);
  });

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName === "edit" || event.toolName === "write") {
      const filePath = (event.input as { path?: string })?.path;
      if (typeof filePath === "string") {
        currentModifiedFiles.add(path.relative(ctx.cwd, filePath));
        if (currentModifiedFiles.size > 20) {
          const first = currentModifiedFiles.values().next().value;
          if (first) currentModifiedFiles.delete(first);
        }
        updateSelf(ctx.cwd, "running");
      }
    }
  });

  const commandHandler = async (_args: string, ctx: ExtensionCommandContext) => {
    const otherSessions = cleanAndListDirectorySessions(ctx.cwd, currentSessionId);
    const selfSession: SessionInfo = {
      sessionId: currentSessionId,
      sessionName: currentSessionName,
      pid: process.pid,
      cwd: ctx.cwd,
      startedAt: currentStartedAt,
      updatedAt: Date.now(),
      status: "running",
      latestGoal: currentGoal,
      recap: currentRecap,
      modifiedFiles: Array.from(currentModifiedFiles),
    };

    const allSessions = [selfSession, ...otherSessions];
    const recapText = formatCrossSessionRecap(allSessions);

    if (!recapText) {
      ctx.ui.notify("No active or recent sessions found in this directory.", "info");
      return;
    }

    if (ctx.hasUI) {
      await ctx.ui.select(
        `Directory Sessions (${allSessions.length} total)\n\n${recapText}`,
        ["Close"]
      );
    } else {
      ctx.ui.notify(recapText, "info");
    }
  };

  pi.registerCommand("sessions", {
    description: "List active and recent Pi coding sessions in the current directory",
    handler: commandHandler,
  });

  pi.registerCommand("recap", {
    description: "Show cross-session recap of work in the current directory",
    handler: commandHandler,
  });

  pi.registerTool({
    name: "list_directory_sessions",
    label: "List Directory Sessions",
    description:
      "List other active or recent Pi coding sessions in the working directory, including their goals and status.",
    parameters: Type.Object({
      cwd: Type.Optional(
        Type.String({ description: "Target directory path (defaults to current working directory)" })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const targetCwd = params.cwd ? path.resolve(params.cwd) : ctx.cwd;
      const sessions = cleanAndListDirectorySessions(targetCwd, currentSessionId);
      const formatted = formatCrossSessionRecap(sessions);

      return {
        content: [
          {
            type: "text",
            text: formatted || "No other active or recent sessions found in this directory.",
          },
        ],
        details: {
          sessions,
          count: sessions.length,
          cwd: targetCwd,
        },
      };
    },
  });
}

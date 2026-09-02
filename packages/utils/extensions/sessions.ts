/**
 * pi-utils-fradser — cross-session awareness and directory recap extension.
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
import { keyHint, type ExtensionAPI, type ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { Container, Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleResultRenderer, detailField, eventToolLifecycle, formatAgentTaskName, notifyPi, safeDisplayText } from "@fradser/pi-kit";
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

/** Known session statuses; registry JSON is not type-checked at rest. */
const SESSION_STATUSES: readonly SessionInfo["status"][] = ["running", "idle", "settled", "exited"];

/**
 * Coerces an untrusted registry record into the SessionInfo contract: numeric
 * pid/timestamps, known status. Registry JSON is not type-checked at rest.
 */
function normalizeSessionRecord(raw: SessionInfo): SessionInfo {
  const pid = Math.trunc(Number(raw.pid));
  return {
    ...raw,
    sessionId: typeof raw.sessionId === "string" ? raw.sessionId : "",
    pid: Number.isFinite(pid) && pid > 0 ? pid : 0,
    cwd: typeof raw.cwd === "string" ? raw.cwd : "",
    startedAt: Number(raw.startedAt) || 0,
    updatedAt: Number(raw.updatedAt) || 0,
    status: SESSION_STATUSES.includes(raw.status) ? raw.status : "exited",
  };
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
      const info = normalizeSessionRecord(JSON.parse(raw));

      // Exclude self by id or by owning process (registry records from
      // multiple writers use different id conventions for the same session).
      if ((excludeSessionId && info.sessionId === excludeSessionId) || info.pid === process.pid) {
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

  // One logical session per owning process: registry records come from
  // multiple writers (extension state and glow state) with different ids.
  const merged = mergeSessionsByPid(sessions);
  merged.sort((a, b) => b.updatedAt - a.updatedAt);
  return merged;
}

/**
 * Collapses registry records that share an owning process into one record.
 * The newest record wins mutable scalars; optional detail fields are filled
 * from the other record when missing.
 */
function mergeSessionsByPid(sessions: SessionInfo[]): SessionInfo[] {
  const byPid = new Map<number, SessionInfo>();
  for (const session of sessions) {
    const existing = byPid.get(session.pid);
    byPid.set(session.pid, existing ? mergeSessionPair(existing, session) : session);
  }
  return Array.from(byPid.values());
}

function mergeSessionPair(a: SessionInfo, b: SessionInfo): SessionInfo {
  const [primary, secondary] = a.updatedAt >= b.updatedAt ? [a, b] : [b, a];
  return {
    ...primary,
    startedAt: primary.startedAt > 0 ? primary.startedAt : secondary.startedAt,
    sessionName: primary.sessionName ?? secondary.sessionName,
    latestGoal: primary.latestGoal ?? secondary.latestGoal,
    recap: primary.recap ?? secondary.recap,
    modifiedFiles: primary.modifiedFiles?.length ? primary.modifiedFiles : secondary.modifiedFiles,
  };
}

/**
 * Formats a relative age label like "5s ago", "5m ago", or "3h ago".
 */
export function formatSessionAge(updatedAt: number, now: number = Date.now()): string {
  const ageSec = Math.max(0, Math.round((now - updatedAt) / 1000));
  if (ageSec < 60) return `${ageSec}s ago`;
  const ageMin = Math.round(ageSec / 60);
  if (ageMin < 60) return `${ageMin}m ago`;
  return `${Math.round(ageMin / 60)}h ago`;
}

/**
 * Formats a list of sessions into a concise markdown recap for prompt injection or display.
 * All variable fields are sanitized — registry values are untrusted and this text reaches
 * both the terminal (/sessions) and the model system prompt.
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
    const timeAgo = formatSessionAge(s.updatedAt, now);

    const statusLabel = s.status.toUpperCase();
    lines.push(`- **${safeDisplayText(name)}** (PID ${s.pid}, status: ${statusLabel}, updated ${timeAgo}):`);
    if (s.latestGoal) {
      lines.push(`  - **Goal**: ${safeDisplayText(s.latestGoal)}`);
    }
    if (s.recap) {
      lines.push(`  - **Recap**: ${safeDisplayText(s.recap)}`);
    }
    if (s.modifiedFiles && s.modifiedFiles.length > 0) {
      lines.push(`  - **Recent files**: ${s.modifiedFiles.slice(0, 5).map((file) => safeDisplayText(file)).join(", ")}`);
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

  function setSessionToolActive(active: boolean): void {
    if (typeof pi.getActiveTools !== "function") return;
    const activeTools = pi.getActiveTools();
    const isActive = activeTools.includes("list_directory_sessions");
    if (isActive === active) return;
    pi.setActiveTools(
      active
        ? [...activeTools, "list_directory_sessions"]
        : activeTools.filter((tool) => tool !== "list_directory_sessions"),
    );
  }

  function syncSessionTool(ctxCwd: string): SessionInfo[] {
    const peers = cleanAndListDirectorySessions(ctxCwd, currentSessionId);
    setSessionToolActive(peers.length > 0);
    return peers;
  }

  pi.on("session_start", async (_event, ctx) => {
    const file = ctx.sessionManager?.getSessionFile();
    if (file) {
      currentSessionId = path.basename(file, ".jsonl");
    }
    updateSelf(ctx.cwd, "idle");
    syncSessionTool(ctx.cwd);
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

    const otherSessions = syncSessionTool(ctx.cwd);
    if (otherSessions.length > 0) {
      const recapText = formatCrossSessionRecap(otherSessions);
      return {
        systemPrompt: event.systemPrompt + "\n\n" + recapText,
      };
    }
  });

  pi.on("agent_settled", async (_event, ctx) => {
    updateSelf(ctx.cwd, "idle");
    syncSessionTool(ctx.cwd);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    removeSessionInfo(ctx.cwd, currentSessionId);
    setSessionToolActive(false);
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
      notifyPi(ctx.ui, "No active or recent sessions found in this directory.", "info");
      return;
    }

    if (ctx.hasUI) {
      await ctx.ui.select(
        `Directory Sessions (${allSessions.length} total)\n\n${recapText}`,
        ["Close"]
      );
    } else {
      notifyPi(ctx.ui, recapText, "info");
    }
  };

  pi.registerCommand("sessions", {
    description: "List active and recent Pi coding sessions in the current directory",
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
    renderShell: "self",
    renderCall: () => new Container(),
    // Pi passes only { content, details } here; liveness comes from context.isError.
    renderResult(result, options, theme, context) {
      const sessions = detailField<SessionInfo[]>(result.details, "sessions") ?? [];
      const summary = sessionListSummary(sessions, path.basename(safeDisplayText(detailField<string>(result.details, "cwd") ?? "")));
      const shown = sessions.slice(0, MAX_DISPLAY_SESSIONS);
      const hidden = sessions.length - shown.length;
      // One detail row per line so the shared band fits and truncates each
      // line at the actual width.
      const rows = [
        ...shown.flatMap((session) => buildSessionLines(session)),
        ...(hidden > 0 ? [`... +${hidden} more not shown`] : []),
      ];
      return createStaticToolLifecycleResultRenderer({
        createSpec: () => eventToolLifecycle("sessions", summary, { label: "listed", details: rows }),
        expandHint: keyHint("app.tools.expand", "to expand"),
        fit: truncateToWidth,
        visibleWidth,
        renderError: (line, currentTheme) => new Text(currentTheme.fg("error", line), 0, 0),
      })(result, options, theme, context);
    },
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

const MAX_DISPLAY_SESSIONS = 10;
const MAX_RECAP_LENGTH = 120;
const MAX_FILES_SHOWN = 4;

function firstLine(text: string): string {
  return text.split("\n", 1)[0]?.trim() ?? "";
}

function truncatePlain(text: string, maxLength: number): string {
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 3)}...`;
}

function sessionListSummary(sessions: SessionInfo[], dirName: string): string {
  const dir = truncatePlain(safeDisplayText(dirName), 40);
  if (sessions.length === 0) return `no other sessions in ${dir}`;
  const noun = sessions.length === 1 ? "other session" : "other sessions";
  return `${sessions.length} ${noun} in ${dir}`;
}

/**
 * Builds the bounded detail block shown for one session in the expanded view:
 * identity header plus Goal / Recap / Files lines when the data exists.
 * All fields are sanitized and truncated — registry values are untrusted.
 */
function buildSessionLines(session: SessionInfo): string[] {
  const rawName = session.sessionName ? `"${session.sessionName}"` : `Session [${session.sessionId.slice(0, 8)}]`;
  const name = truncatePlain(safeDisplayText(rawName), 60);
  const lines = [`  ${name} · ${session.status.toUpperCase()} · pid ${session.pid} · ${formatSessionAge(session.updatedAt)}`];
  if (session.latestGoal) {
    lines.push(`    Goal  ${truncateToWidth(formatAgentTaskName(safeDisplayText(firstLine(session.latestGoal)), ""), 80)}`);
  }
  if (session.recap) {
    lines.push(`    Recap ${truncatePlain(safeDisplayText(firstLine(session.recap)), MAX_RECAP_LENGTH)}`);
  }
  if (session.modifiedFiles?.length) {
    const shown = session.modifiedFiles
      .slice(0, MAX_FILES_SHOWN)
      .map((file) => truncatePlain(safeDisplayText(file), 80));
    const rest = session.modifiedFiles.length - shown.length;
    lines.push(`    Files ${shown.join(", ")}${rest > 0 ? ` (+${rest} more)` : ""}`);
  }
  return lines;
}

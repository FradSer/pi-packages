/**
 * @fradser/teammate — Pi extension for multi-agent teams.
 *
 * Provides a mailbox-based communication system, task management,
 * and team-leader orchestration for Pi agents.
 *
 * Tools registered:
 *   teammate_register      — Register a new teammate agent
 *   teammate_list          — List all registered teammates
 *   teammate_send          — Send a message to a teammate's mailbox
 *   teammate_read_mailbox  — Read messages from a teammate's mailbox
 *   teammate_assign_task   — Assign a task to a teammate (leader = main session)
 *   teammate_list_tasks    — List tasks by status/assignee
 *   teammate_update_task   — Update task status (start, complete, fail)
 *   teammate_broadcast     — Broadcast to all teammates (leader = main session)
 */

import { isKeyRelease, truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionUIContext, Theme, ThemeColor } from "@earendil-works/pi-coding-agent";
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import {
  EmptyParams,
  TeammateAssignTaskParams,
  TeammateBroadcastParams,
  TeammateCleanupParams,
  TeammateListTasksParams,
  TeammateReadMailboxParams,
  TeammateRegisterParams,
  TeammateRemoveParams,
  TeammateSendParams,
  TeammateSpawnParams,
  TeammateTaskDepsParams,
  TeammateUpdateModelParams,
  TeammateUpdateTaskParams,
  type Task,
  type TeammateRole,
} from "./types";
import {
  createTask,
  getTeammate,
  getTeammatesByRole,
  getUnreadCount,
  isTaskReady,
  listTasks,
  listTeammates,
  markTeammateIdle,
  markTeammateRunning,
  persistState,
  readMailbox,
  registerTeammate,
  sendMessage,
  setSpawnInfo,
  setTaskDeps,
  tryRestoreState,
  updateTaskStatus,
  getSummary,
  applyStateFile,
  getState,
  markTaskNotificationsRead,
  listAllMessages,
  pruneFinishedTasks,
  removeTask,
  removeTeammate,
  resetBoard,
  updateTeammateModel,
} from "./state";
import { buildAutonomousPrompt, killWorker, spawnPiWorker, spawnPiWorkerBlocking } from "./spawner";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree";
import {
  cleanupExpiredStateDirs,
  readStateFile,
  removeSessionStateDir,
  stateFilePath,
  writeStateFile,
} from "./statefile";
import type { WorkerUsage } from "./types";

/** Keep shared state dirs for at most 7 days after their last write. */
const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/** Truncate worker/task output to the built-in tool-output limits (50KB / 2000 lines). */
function cap(text: string | undefined, maxBytes = DEFAULT_MAX_BYTES): string {
  if (!text) return "";
  if (text.length <= maxBytes) return text;
  const t = truncateTail(text, { maxLines: DEFAULT_MAX_LINES, maxBytes });
  return `${t.content}\n…[truncated ${text.length - t.content.length} chars]`;
}

// ── Team UI: passive widget + full-screen console ──────────────────
// Design: the widget above the editor is DISPLAY-ONLY (no key interception —
// pi's model selector, history navigation and dialogs are never affected).
// ALL interaction happens in the full-screen Team Console (`/teammate`), which
// owns input explicitly via ctx.ui.custom, so ↑/↓/Enter are safe in there.

const TEAM_COLORS = ["accent", "success", "warning", "error", "toolTitle", "mdLink"] as const;
const PANEL_IDLE_COLLAPSE_MS = 30_000;

let panelRequestRender: (() => void) | undefined;
let panelLastActivity = 0;
let panelCollapseTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * Esc arrives as a bare `\x1b` in legacy terminals, or as CSI-u `\x1b[27u`
 * (with optional `:shifted`, `;mod`, `:event` segments) once the Kitty
 * protocol (flags=7, which pi negotiates) is active in Ghostty.
 */
function isEscapeKey(data: string): boolean {
  return data === "\u001b" || /^\u001b\[27(?:[:;\d]*)?u$/.test(data);
}

/** Display label for a role: a plain registered teammate shows as "teammate". */
function displayRole(role: string): string {
  return role === "worker" ? "teammate" : role;
}

/** Stable per-teammate color (independent of row order). */
function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return Math.abs(h);
}

interface PanelRow {
  kind: "inbox" | "teammate";
  name?: string;
}
/** Console/widget rows: the leader-inbox row (when teammates sent messages) + teammate rows. */
function buildPanelRows(): PanelRow[] {
  const rows: PanelRow[] = [];
  if (getUnreadCount("agent") > 0) rows.push({ kind: "inbox" });
  for (const t of listTeammates()) rows.push({ kind: "teammate", name: t.name });
  return rows;
}

function isPanelCollapsed(): boolean {
  const rows = buildPanelRows();
  if (rows.length === 0) return false;
  const hasInbox = rows.some((r) => r.kind === "inbox");
  const teammates = listTeammates();
  return (
    teammates.length > 0 &&
    !hasInbox &&
    teammates.every((t) => t.status === "idle") &&
    Date.now() - panelLastActivity > PANEL_IDLE_COLLAPSE_MS
  );
}

function scheduleIdleCollapse(): void {
  if (panelCollapseTimer) clearTimeout(panelCollapseTimer);
  panelCollapseTimer = undefined;
  const teammates = listTeammates();
  if (teammates.length === 0 || getUnreadCount("agent") > 0 || !teammates.every((t) => t.status === "idle")) return;
  panelCollapseTimer = setTimeout(() => {
    panelCollapseTimer = undefined;
    panelRequestRender?.();
  }, PANEL_IDLE_COLLAPSE_MS);
}

/** Refresh the passive widget after any state change. */
function refreshTeamUI(_ctx: { ui: ExtensionUIContext }): void {
  panelLastActivity = Date.now();
  scheduleIdleCollapse();
  ensureLivePoll();
  panelRequestRender?.();
}

// ── Live state merge while workers run ─────────────────────────────
// A worker writes progress into the shared state file (mailbox replies,
// task.result) as it goes. While ANY teammate is running, poll that file
// every few seconds and merge worker-written changes back into memory so the
// leader inbox alert / panel / detail pages show mid-run content live.
let liveStateFile: string | undefined;
let livePollTimer: ReturnType<typeof setInterval> | undefined;
const LIVE_POLL_MS = 5000;

function ensureLivePoll(): void {
  const running = listTeammates().some((t) => t.status === "running");
  if (running && !livePollTimer && liveStateFile) {
    livePollTimer = setInterval(() => {
      try {
        applyStateFile(liveStateFile!, readStateFile);
        panelRequestRender?.();
      } catch {
        // Never let a poll error break the extension.
      }
    }, LIVE_POLL_MS);
  } else if (!running && livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = undefined;
  }
}

/** Passive widget rows (display only — no selection, no key handling). */
function panelRows(theme: Theme, width?: number): string[] {
  const fg = (color: ThemeColor, s: string): string => theme.fg(color, s);
  const bold = (s: string): string => theme.bold(s);
  const fit = (line: string): string =>
    typeof width === "number" && width > 0 ? truncateToWidth(line, Math.max(10, width - 1)) : line;
  const rows = buildPanelRows();
  if (rows.length === 0) return [];

  if (isPanelCollapsed()) {
    return [fit(fg("dim", `Team idle — ${listTeammates().length} teammate(s) — /teammate to interact`))];
  }

  const lines: string[] = [];
  for (const row of rows) {
    if (row.kind === "inbox") {
      const n = getUnreadCount("agent");
      const preview = inboxPreview();
      lines.push(fit(fg("error", `${n} message(s) to you — ${preview}`)));
    } else {
      const t = getTeammate(row.name ?? "");
      if (!t) continue;
      const color = TEAM_COLORS[hashName(t.name) % TEAM_COLORS.length];
      const name = bold(fg(color, t.name));
      const role = fg("muted", `(${displayRole(t.role)})`);
      const status =
        t.status === "running"
          ? fg("warning", `● running${t.currentTaskId ? ` ${t.currentTaskId}` : ""}`)
          : fg("dim", "○ idle");
      lines.push(fit(`${name} ${role} ${status}`));
    }
  }
  lines.push(fit(fg("dim", "/teammate — open console")));
  return lines;
}

/** Full content of a task as shown on an agent's detail page: description,
 * dependencies, spawn lifecycle (pid/status/timing/exit/timeout/usage), the
 * worker's final report (stdout), stderr, result and error. The worker output
 * is the agent's actual "running content" — previously hidden behind a
 * one-line status. */
function buildTaskSection(t: Task): string[] {
  const lines: string[] = [`- [${t.id}] ${t.status}: ${t.title}`];
  if (t.description) lines.push(`  ${t.description}`);
  if (t.blockedBy.length > 0) lines.push(`  Blocked by: ${t.blockedBy.join(", ")}`);
  if (t.blocks.length > 0) lines.push(`  Blocks: ${t.blocks.join(", ")}`);

  const spawn = t.spawn;
  if (spawn) {
    const stateLabel = spawn.status === "running" ? `running (pid ${spawn.pid})` : spawn.status;
    lines.push(`  Spawn: ${stateLabel}`);
    if (spawn.startedAt) lines.push(`  Started: ${new Date(spawn.startedAt).toLocaleString()}`);
    if (spawn.finishedAt) lines.push(`  Finished: ${new Date(spawn.finishedAt).toLocaleString()}`);
    if (spawn.exitCode !== undefined) lines.push(`  Exit code: ${spawn.exitCode}`);
    if (spawn.timedOut) lines.push("  Timed out: yes");
    if (spawn.usage) {
      const u = spawn.usage;
      lines.push(`  Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
    }
    if (spawn.error) lines.push(`  Spawn error: ${spawn.error}`);
    if (spawn.stdout) {
      lines.push("  --- Worker output ---");
      lines.push(...spawn.stdout.split("\n"));
    }
    if (spawn.stderr) {
      lines.push("  --- Worker stderr ---");
      lines.push(...spawn.stderr.split("\n"));
    }
  }

  // Completed spawns already fold stdout into task.result (setSpawnInfo) — avoid
  // printing the same report twice. Standalone results (update_task_status or a
  // worker-written state file) are still shown here.
  if (t.result && t.result !== spawn?.stdout) lines.push(`  Result: ${t.result}`);
  if (t.errorMessage) lines.push(`  Error: ${t.errorMessage}`);
  return lines;
}

/** One-line preview of the newest unread leader-inbox message (from: subject — body first line). */
function inboxPreview(): string {
  const unread = readMailbox("agent", { unreadOnly: true, markRead: false });
  if (unread.length === 0) return "";
  const latest = unread[unread.length - 1];
  const firstBodyLine = latest.body.split("\n")[0].trim();
  const preview = firstBodyLine ? ` — ${firstBodyLine}` : "";
  return `${latest.from}: ${latest.subject}${preview}`;
}

/**
 * Write the leader's read flags back into the shared state file so the
 * SENDER (the worker) can see the read receipt: once the team leader has
 * read a message, the file copy shows read:true and the worker sees
 * "leader received ✓".
 */
function syncReadFlagsToFile(): void {
  if (!liveStateFile) return;
  try {
    const fresh = readStateFile(liveStateFile);
    if (!fresh) return;
    for (const [name, msgs] of Object.entries(fresh.mailboxes)) {
      const inMem = getState().mailboxes[name] ?? [];
      const byId = new Map(inMem.map((m) => [m.id, m]));
      for (const m of msgs) {
        const mem = byId.get(m.id);
        if (mem?.read) m.read = true;
      }
    }
    writeStateFile(liveStateFile, fresh);
  } catch {
    // Never break reading on a receipt-sync failure.
  }
}

/**
 * Publish the parent's current board to the shared state file so running
 * workers see leader-side changes (new messages, task status) — without this,
 * teammate_send/broadcast/assign only touched the parent's memory and the
 * worker's mailbox watch never saw the message.
 */
function publishToStateFile(): void {
  if (!liveStateFile) return;
  try {
    writeStateFile(liveStateFile, getState());
  } catch {
    // Best effort — the in-memory board is authoritative.
  }
}

/** Teammate detail: special sections (unread, tasks) + the FULL conversation —
 * every message the teammate received (←) and every message it sent (→),
 * merged and sorted by time. */
function buildTeammateDetail(name: string): string[] {
  const teammate = getTeammate(name);
  if (!teammate) return ["(removed)"];
  const incoming = readMailbox(name, { unreadOnly: false, markRead: false });
  const unread = incoming.filter((m) => !m.read);
  const outgoing = listAllMessages().filter((m) => m.from === name);
  const conversation = [...incoming, ...outgoing].sort((a, b) => a.timestamp - b.timestamp);
  const tasks = listTasks({ assignee: name });

  const lines: string[] = [
    `${teammate.name} (${displayRole(teammate.role)}) [${teammate.status}]`,
    teammate.description,
    teammate.model ? `Model: ${teammate.model}` : "",
    "",
    `== ${unread.length} unread message(s) ==`,
    ...(unread.length === 0 ? ["(none)"] : unread.map((m) => `[${m.id}] ${m.subject} — from ${m.from}`)),
    "",
    `== ${tasks.length} task(s) ==`,
    ...(tasks.length === 0 ? ["(none)"] : tasks.flatMap(buildTaskSection)),
    "",
    `== all conversations (${conversation.length}) ==`,
    ...(conversation.length === 0
      ? ["(no messages yet)"]
      : conversation.flatMap((m) => {
          const sent = m.from === name;
          const peer = sent ? m.to : m.from;
          const time = new Date(m.timestamp).toLocaleString();
          // Read status: outgoing → whether the leader received/read it (read
          // receipt); incoming → whether the teammate read it.
          const receipt = sent
            ? m.to === "agent"
              ? m.read
                ? "✓ leader received"
                : "○ leader pending"
              : ""
            : m.read
              ? "✓ read"
              : "● unread";
          return [
            `${sent ? "→" : "←"} [${m.id}] ${m.subject} — ${sent ? `to ${peer}` : `from ${peer}`} | ${time}${receipt ? ` | ${receipt}` : ""}`,
            m.taskId ? `  task ${m.taskId}` : "",
            m.body,
            "",
          ];
        })),
  ];
  return lines;
}

/** Leader inbox content; viewing consumes it (markRead) so the row disappears.
 * Each message carries a read/unread marker; after viewing, read flags are
 * synced back to the shared file as a read receipt for the sender. */
function buildInboxContent(): string[] {
  const messages = readMailbox("agent", { unreadOnly: false, markRead: true });
  syncReadFlagsToFile();
  return messages.length === 0
    ? ["(empty — teammates can message you via the agent mailbox)"]
    : messages.flatMap((m) => [
        `${m.read ? "✓" : "●"} [${m.id}] ${m.subject}`,
        `  ${m.read ? "received" : "unread"} | from ${m.from} | ${new Date(m.timestamp).toLocaleString()}${m.taskId ? ` | task ${m.taskId}` : ""}`,
        m.body,
        "",
      ]);
}

/**
 * Full-screen Team Console — owns input via ctx.ui.custom, so ↑/↓ and Enter are
 * safe in here and nothing is intercepted globally. Modes: list / detail / inbox.
 */
function openTeamConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
  return ctx.ui.custom<void>((_tui, theme, _keybindings, done) => {
    let mode: "list" | "detail" | "inbox" = "list";
    let selected = 0;
    let detailName = "";
    let replyMode = false;
    let replyBuffer = "";
    let offset = 0;
    const WINDOW = 20;
    const up = /^\u001b\[(?:[0-9;:]*)?A$|^\u001bOA$/;
    const down = /^\u001b\[(?:[0-9;:]*)?B$|^\u001bOB$/;

    // btw-style callbacks (same accent/muted/dim/border/success/error language as @fradser/pi-btw).
    const style = {
      accent: (s: string) => theme.fg("accent", s),
      muted: (s: string) => theme.fg("muted", s),
      dim: (s: string) => theme.fg("dim", s),
      border: (s: string) => theme.fg("border", s),
      success: (s: string) => theme.fg("success", s),
      error: (s: string) => theme.fg("error", s),
    };

    const windowLines = (full: string[], width: number): string[] => {
      const contentWidth = Math.max(20, width - 4);
      const maxOffset = Math.max(0, full.length - WINDOW);
      if (offset > maxOffset) offset = maxOffset;
      const wrapped: string[] = [];
      for (const line of full.slice(offset, offset + WINDOW)) {
        wrapped.push(...wrapTextWithAnsi(line, contentWidth));
      }
      if (full.length > WINDOW) {
        wrapped.push(style.dim(`… ${full.length - WINDOW} more lines — ↑/↓`));
      }
      return wrapped;
    };

    const renderList = (width: number): string[] => {
      const rows = buildPanelRows();
      if (selected >= rows.length) selected = Math.max(0, rows.length - 1);
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines: string[] = [
        border,
        style.accent(truncateToWidth(`teammate  ${listTeammates().length} teammate(s)`, width)),
        "",
      ];
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const marker = i === selected ? style.accent("❯ ") : "  ";
        if (row.kind === "inbox") {
          const n = getUnreadCount("agent");
          const preview = inboxPreview();
          lines.push(`${marker}${style.error(`${n} message(s) to you — ${preview}`)}`);
        } else {
          const t = getTeammate(row.name ?? "");
          if (!t) continue;
          const color = TEAM_COLORS[hashName(t.name) % TEAM_COLORS.length];
          const name = theme.bold(theme.fg(color, t.name));
          const role = style.muted(`(${displayRole(t.role)})`);
          const status =
            t.status === "running"
              ? theme.fg("warning", `● running${t.currentTaskId ? ` ${t.currentTaskId}` : ""}`)
              : style.dim("○ idle");
          lines.push(`${marker}${name} ${role} ${status}`);
        }
      }
      lines.push("", style.dim("↑↓ select · enter open · r reply · esc interrupt · x stop · q close"), border);
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    const renderDetail = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines = [
        border,
        style.accent(truncateToWidth(`teammate  ${detailName}`, width)),
        "",
        ...windowLines(buildTeammateDetail(detailName), width).map((l) => `  ${l}`),
        "",
        replyMode
          ? style.accent(`  Reply to ${detailName}: ${replyBuffer}_(enter send, esc cancel)`)
          : style.dim("  esc back · r reply · q close"),
        border,
      ];
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    const renderInbox = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines = [
        border,
        style.accent(truncateToWidth("teammate  inbox — messages to you", width)),
        "",
        ...windowLines(buildInboxContent(), width).map((l) => `  ${l}`),
        "",
        style.dim("  esc back · q close"),
        border,
      ];
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    return {
      render: (width) =>
        mode === "list" ? renderList(width) : mode === "detail" ? renderDetail(width) : renderInbox(width),
      invalidate: () => {},
      handleInput: (data: string) => {
        // Detail-mode inline reply input.
        if (mode === "detail" && replyMode) {
          if (isEscapeKey(data)) {
            replyMode = false;
            return;
          }
          if (data === "\r" || data === "\n") {
            if (replyBuffer.trim()) {
              sendMessage({ from: "agent", to: detailName, subject: "Direct message", body: replyBuffer.trim() });
              refreshTeamUI(ctx);
              ctx.ui.notify(`Message sent to ${detailName}.`, "info");
            }
            replyMode = false;
            replyBuffer = "";
            return;
          }
          if (data === "\x7f" || data === "\x08") {
            replyBuffer = replyBuffer.slice(0, -1);
            return;
          }
          if (data.length === 1 && data >= " " && data < "\x7f") replyBuffer += data;
          return;
        }

        // Detail / inbox modes: Esc returns to the list, q closes, r replies.
        if (mode !== "list") {
          if (isEscapeKey(data)) {
            mode = "list";
            offset = 0;
            return;
          }
          if (data === "q" || data === "Q") {
            done();
            return;
          }
          if (mode === "detail" && (data === "r" || data === "R")) {
            replyMode = true;
            return;
          }
          if (down.test(data)) offset++;
          if (up.test(data)) offset--;
          return;
        }

        // List mode — the console owns input, so ↑/↓/Enter are safe here.
        const rows = buildPanelRows();
        if (down.test(data)) selected = Math.min(selected + 1, rows.length - 1);
        if (up.test(data)) selected = Math.max(selected - 1, 0);
        if (data === "\r" || data === "\n") {
          const row = rows[Math.min(selected, rows.length - 1)];
          if (row.kind === "inbox") {
            mode = "inbox";
            offset = 0;
          } else if (row.name) {
            mode = "detail";
            detailName = row.name;
            offset = 0;
          }
          return;
        }
        if (isEscapeKey(data) || data === "q" || data === "Q") {
          done();
          return;
        }
        if (data === "x" || data === "X") {
          const row = rows[Math.min(selected, rows.length - 1)];
          if (row.kind === "teammate" && row.name) {
            const t = getTeammate(row.name);
            if (t?.status === "running" && killWorker(row.name, "SIGKILL")) {
              ctx.ui.notify(`Stopped ${row.name}'s worker.`, "info");
            }
          }
          return;
        }
      },
    };
  });
}

/** Wire the passive widget (display only). No input interception. */
function setupTeamWidget(ctx: { ui: ExtensionUIContext; mode: string }): void {
  if (ctx.mode !== "tui") return;
  ctx.ui.setWidget("teammate", (tui, theme) => {
    panelRequestRender = () => tui.requestRender();
    return {
      render: (width) => panelRows(theme, width),
      invalidate: () => {},
      dispose: () => {
        panelRequestRender = undefined;
      },
    };
  });
}

const TEAMMATE_GUIDANCE = `
## Teammate System

You have access to a teammate multi-agent system (mailbox, tasks, orchestration). You are the team leader (main session); teammates are workers/reviewers/specialists/observers.
Use it when:
- Delegating work to specialized sub-agents (register workers, assign tasks)
- Tracking progress across multiple parallel workstreams
- Sending async instructions or broadcast updates to team members
- Requesting review or handoff between agents

When you need to use it, consult /skill:using-teammate for the full tool reference.
`;

export default function (pi: ExtensionAPI) {
  // ── Session lifecycle ───────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    // Restore persisted state, then ALWAYS surface the footer status — including
    // the empty state. Gating it on a restored snapshot left fresh sessions with
    // no status until a teammate was registered (or state was restored).
    tryRestoreState(ctx.sessionManager);
    setupTeamWidget(ctx);
    liveStateFile = stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    // No footer status for the team — the panel widget owns the display.
    ctx.ui.setStatus("teammate", undefined);
    refreshTeamUI(ctx);
    // Sweep abandoned shared state dirs from older sessions.
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    persistState(pi);
    // The shared state file is a working medium for spawns; drop it when the
    // session ends so ~/.pi/agent/teammate/ never accumulates one dir per run.
    removeSessionStateDir(ctx.sessionManager.getSessionFile(), process.cwd());
  });

  pi.on("turn_end", async () => {
    persistState(pi);
  });

  // ── Inject teammate guidance into system prompt ─────────────────

  pi.on("before_agent_start", async (event) => {
    return {
      systemPrompt: event.systemPrompt + TEAMMATE_GUIDANCE,
    };
  });

  // ── Tools ───────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_register",
    promptSnippet: "Register a teammate agent (worker/reviewer/specialist/observer)",
    label: "Register Teammate",
    description: [
      "Register a new teammate agent with a name, role, and description.",
      "Roles: worker (default executor), reviewer (code review), specialist (domain expert), observer (read-only).",
      "The team leader is ALWAYS the current main session — do not register a 'team-leader' teammate.",
    ].join(" "),
    parameters: TeammateRegisterParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.role === "team-leader") {
        return {
          content: [
            {
              type: "text",
              text: [
                "The team leader is the current main session — you cannot register a 'team-leader' teammate.",
                "Register teammates with role worker / reviewer / specialist / observer instead.",
              ].join(" "),
            },
          ],
          details: {},
          isError: true,
        };
      }
      const result = registerTeammate({
        name: params.name,
        role: params.role as TeammateRole,
        description: params.description,
        model: params.model,
        tools: params.tools,
        registeredAt: Date.now(),
      });

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to register teammate." }],
          details: {},
          isError: true,
        };
      }

      persistState(pi);
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: [
              `Registered teammate "${params.name}" (${displayRole(params.role)}).`,
              `Registered teammates: ${listTeammates().map((t) => `${t.name} (${displayRole(t.role)})`).join(", ")}`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list",
    promptSnippet: "List all registered teammates",
    label: "List Teammates",
    description: "List all registered teammates with their roles and descriptions.",
    parameters: EmptyParams,

    async execute() {
      const teammates = listTeammates();
      if (teammates.length === 0) {
        return {
          content: [{ type: "text", text: "No teammates registered yet. Use teammate_register to add one." }],
          details: {},
        };
      }

      const lines: string[] = ["## Registered Teammates\n"];
      for (const t of teammates) {
        const unread = getUnreadCount(t.name);
        const liveness =
          t.status === "running"
            ? `\u25CF running${t.currentTaskId ? ` (task ${t.currentTaskId})` : ""}`
            : "idle";
        lines.push(`- **${t.name}** (${displayRole(t.role)}) [${liveness}]`);
        lines.push(`  ${t.description}`);
        if (unread > 0) lines.push(`  - ${unread} unread message(s)`);
        if (t.model) lines.push(`  Model: ${t.model}`);
        if (t.tools && t.tools.length > 0) lines.push(`  Tools: ${t.tools.join(", ")}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_send",
    promptSnippet: "Send a message to a teammate's mailbox",
    label: "Send Message",
    description: "Send a message to a teammate's mailbox. The recipient can read it with teammate_read_mailbox.",
    parameters: TeammateSendParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const recipient = getTeammate(params.to);
      if (!recipient) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${params.to}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const sender = "agent";

      const msg = sendMessage({
        from: sender,
        to: params.to,
        subject: params.subject,
        body: params.body,
        taskId: params.taskId,
      });

      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: `Message sent to "${params.to}".\nSubject: ${params.subject}\nMessage ID: ${msg.id}`,
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_read_mailbox",
    promptSnippet: "Read messages from a teammate's mailbox (or the leader inbox)",
    label: "Read Mailbox",
    description: [
      "Read messages from a teammate's mailbox (or the leader's own inbox with name=agent —",
      "teammates can send the leader messages via the shared state file).",
      "Optionally mark as read or filter to unread only.",
    ].join(" "),
    parameters: TeammateReadMailboxParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const name = params.name ?? "agent";
      // The leader inbox ("agent") always exists; only registered teammates are validated.
      if (name !== "agent") {
        const teammate = getTeammate(name);
        if (!teammate) {
          return {
            content: [
              {
                type: "text",
                text: `Teammate "${name}" not found. Register them first with teammate_register.`,
              },
            ],
            details: {},
            isError: true,
          };
        }
      }

      const messages = readMailbox(name, {
        unreadOnly: params.unreadOnly ?? true,
        markRead: params.markRead ?? true,
      });
      // Reading consumes the message — sync the read receipt to the shared file
      // so the sender (the worker) can see the leader received it.
      if (params.markRead !== false) syncReadFlagsToFile();

      if (messages.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: `No ${params.unreadOnly !== false ? "unread " : ""}messages in "${name}"'s mailbox.`,
            },
          ],
          details: {},
        };
      }

      const lines: string[] = [
        `## Mailbox: ${name} (${messages.length} message${messages.length > 1 ? "s" : ""})\n`,
      ];
      for (const msg of messages) {
        lines.push(`### [${msg.id}] ${msg.subject}`);
        lines.push(`From: ${msg.from} | ${new Date(msg.timestamp).toLocaleString()}`);
        if (msg.taskId) lines.push(`Task: ${msg.taskId}`);
        lines.push("");
        lines.push(cap(msg.body));
        lines.push("");
        lines.push("---");
        lines.push("");
      }

      persistState(pi);
      refreshTeamUI(ctx);

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_assign_task",
    promptSnippet: "Assign a task to a teammate",
    label: "Assign Task",
    description: [
      "Assign a task to a teammate. The team leader is the current main session,",
      "so this is always available.",
      "The assignee will see the task in their task list and receive a mailbox notification.",
    ].join(" "),
    parameters: TeammateAssignTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const assignee = getTeammate(params.assignee);
      if (!assignee) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${params.assignee}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const created = createTask(params.title, params.description, params.assignee, "agent");
      if (!created.ok || !created.task) {
        return {
          content: [{ type: "text", text: created.error ?? "Failed to create task." }],
          details: {},
          isError: true,
        };
      }
      const task = created.task;

      sendMessage({
        from: "agent",
        to: params.assignee,
        subject: `New task: ${params.title}`,
        body: `You have been assigned a new task.\n\nTitle: ${params.title}\nDescription: ${params.description}\n\nTask ID: ${task.id}`,
        taskId: task.id,
      });

      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: [
              `Task assigned to "${params.assignee}".`,
              `Task ID: ${task.id}`,
              `Title: ${params.title}`,
              `Status: assigned`,
              "",
              `${params.assignee} has been notified via mailbox.`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list_tasks",
    promptSnippet: "List tasks by status or assignee",
    label: "List Tasks",
    description: "List tasks, optionally filtered by status or assignee.",
    parameters: TeammateListTasksParams,

    async execute(_toolCallId, params) {
      const tasks = listTasks({
        status: params.status,
        assignee: params.assignee,
      });

      if (tasks.length === 0) {
        let msg = "No tasks found.";
        if (params.status) msg += ` Status: ${params.status}.`;
        if (params.assignee) msg += ` Assignee: ${params.assignee}.`;
        return { content: [{ type: "text", text: msg }], details: {} };
      }

      const lines: string[] = ["## Tasks\n"];
      for (const task of tasks) {
        const statusIcon =
          task.status === "completed"
            ? "\u2713"
            : task.status === "failed"
              ? "\u2717"
              : task.status === "in_progress"
                ? "\u22EF"
                : task.status === "cancelled"
                  ? "\u2212"
                  : "\u25CB";
        lines.push(`### ${statusIcon} [${task.id}] ${task.title}`);
        lines.push(`Assignee: ${task.assignee} | Status: ${task.status}`);
        if (task.spawn) {
          const spawn = task.spawn;
          const stateLabel = spawn.status === "running" ? "running (pid " + spawn.pid + ")" : spawn.status;
          lines.push(`Spawn: ${stateLabel}`);
          if (spawn.timedOut) lines.push(`Timed out: yes`);
          if (spawn.usage) {
            const u = spawn.usage;
            lines.push(`Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
          }
        }
        if (task.blockedBy.length > 0) lines.push(`Blocked by: ${task.blockedBy.join(", ")}`);
        if (task.blocks.length > 0) lines.push(`Blocks: ${task.blocks.join(", ")}`);
        lines.push(cap(task.description));
        if (task.result) lines.push(`Result: ${cap(task.result)}`);
        if (task.errorMessage) lines.push(`Error: ${cap(task.errorMessage)}`);
        lines.push(`Created: ${new Date(task.createdAt).toLocaleString()}`);
        if (task.completedAt) lines.push(`Completed: ${new Date(task.completedAt).toLocaleString()}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_update_task",
    promptSnippet: "Update a task's status (in_progress/completed/failed/cancelled)",
    label: "Update Task",
    description: "Update a task's status — mark as in_progress, completed, failed, or cancelled.",
    parameters: TeammateUpdateTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = updateTaskStatus(params.taskId, params.status, params.result, params.errorMessage);

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to update task." }],
          details: {},
          isError: true,
        };
      }

      // Starting a task consumes its assignment notification (B).
      if (params.status === "in_progress") markTaskNotificationsRead(params.taskId);
      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      const task = result.task!;
      return {
        content: [
          {
            type: "text",
            text: [
              `Task [${task.id}] "${task.title}" updated to status: ${task.status}.`,
              task.result ? `Result: ${cap(task.result)}` : "",
              task.errorMessage ? `Error: ${cap(task.errorMessage)}` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_broadcast",
    promptSnippet: "Broadcast a message to all teammates",
    label: "Broadcast",
    description: [
      "Broadcast a message to all teammates (or filter by role).",
      "The team leader is the current main session, so this is always available.",
    ].join(" "),
    parameters: TeammateBroadcastParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      let recipients = params.role
        ? getTeammatesByRole(params.role)
        : listTeammates();

      if (recipients.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: params.role
                ? `No teammates found with role "${params.role}".`
                : "No teammates registered to broadcast to.",
            },
          ],
          details: {},
          isError: true,
        };
      }

      for (const recipient of recipients) {
        sendMessage({
          from: "agent",
          to: recipient.name,
          subject: `Broadcast: ${params.subject}`,
          body: params.body,
        });
      }

      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: [
              `Broadcast sent to ${recipients.length} teammate(s).`,
              `Subject: ${params.subject}`,
              params.role ? `(filtered by role: ${params.role})` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_task_deps",
    promptSnippet: "Wire task dependencies (blockedBy/blocks)",
    label: "Set Task Dependencies",
    description: [
      "Wire task dependencies on the board: which tasks block this one (blockedBy)",
      "and which tasks this one blocks (blocks). A task cannot be spawned until",
      "every blockedBy task is completed or cancelled.",
    ].join(" "),
    parameters: TeammateTaskDepsParams,

    async execute(_toolCallId, params) {
      const result = setTaskDeps(params.taskId, {
        blocks: params.blocks,
        blockedBy: params.blockedBy,
      });
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to update task dependencies." }],
          details: {},
          isError: true,
        };
      }
      const task = listTasks().find((t) => t.id === params.taskId);
      const parts = [`Task [${params.taskId}] dependencies updated.`];
      if (task) {
        if (task.blockedBy.length > 0) parts.push(`Blocked by: ${task.blockedBy.join(", ")}`);
        if (task.blocks.length > 0) parts.push(`Blocks: ${task.blocks.join(", ")}`);
      }
      return { content: [{ type: "text", text: parts.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_spawn",
    promptSnippet: "Spawn an autonomous child Pi worker to execute a task",
    label: "Spawn Teammate",
    description: [
      "Spawn a real child Pi process as the teammate to execute a task — a FULLY AUTONOMOUS agent.",
      "The worker watches its mailbox via a shared state file, processes new messages on its own,",
      "and decides when to close. Default (background=false) BLOCKS until the worker closes itself",
      "and returns its final report — no polling needed. background=true fires it off and the worker",
      "keeps watching its mailbox until it decides to stop.",
      "The task must be ready: every blockedBy task must be completed or cancelled.",
    ].join(" "),
    parameters: TeammateSpawnParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const teammate = getTeammate(params.name);
      if (!teammate) {
        return {
          content: [{ type: "text", text: `Teammate "${params.name}" not found. Register them first with teammate_register.` }],
          details: {},
          isError: true,
        };
      }
      const task = listTasks().find((t) => t.id === params.taskId);
      if (!task) {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" not found.` }],
          details: {},
          isError: true,
        };
      }
      const readiness = isTaskReady(params.taskId);
      if (!readiness.ready) {
        return {
          content: [
            {
              type: "text",
              text: [
                `Task "${params.taskId}" is not ready: blocked by ${readiness.unmet.join(", ")}.`, 
                "Complete or cancel those tasks first, or rewire deps with teammate_task_deps.",
              ].join(" "),
            },
          ],
          details: {},
          isError: true,
        };
      }

      const sessionFile = ctx.sessionManager.getSessionFile();
      const cwd = ctx.cwd || process.cwd();
      const stateFile = stateFilePath(sessionFile, cwd);
      // Consume the assignment notification (B): the task is starting, so its
      // "you have a new task" message no longer needs to count as unread.
      markTaskNotificationsRead(params.taskId);
      // Publish the current board so the worker sees its mailbox + task.
      writeStateFile(stateFile, getState());

      // Optional git worktree isolation: run the worker on its own branch.
      let worktree: ReturnType<typeof createWorktree> | undefined;
      if (params.isolation === "worktree") {
        worktree = createWorktree(cwd, params.taskId);
        if ("error" in worktree) {
          return {
            content: [{ type: "text", text: `Cannot isolate worker: ${worktree.error}` }],
            details: {},
            isError: true,
          };
        }
      }

      markTeammateRunning(params.name, params.taskId);

      const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
      const timeoutMs = params.timeoutMs ?? DEFAULT_TIMEOUT_MS;
      const workerCwd = worktree && !("error" in worktree) ? worktree.cwd : cwd;

      const description = [
        buildAutonomousPrompt({
          name: teammate.name,
          role: teammate.role,
          taskId: task.id,
          taskTitle: task.title,
          stateFile,
          timeoutSec: Math.round(timeoutMs / 1000),
        }),
        "",
        "=== TASK ===",
        task.description,
      ].join("\n");

      const finish = (result: {
        pid: number;
        exitCode: number;
        stdout: string;
        stderr: string;
        usage?: WorkerUsage;
        timedOut: boolean;
      }) => {
        // Adopt whatever the worker wrote to the board while it was alive
        // (replies it posted, task status/result it set).
        applyStateFile(stateFile, readStateFile);
        // Write the merged memory state back to the shared file so the final
        // read receipts (leader read flags) persist once the worker is gone.
        try {
          writeStateFile(stateFile, getState());
        } catch {
          // Best-effort; the in-memory board is authoritative.
        }
        let patchText = "";
        if (worktree && !("error" in worktree)) {
          const diff = captureWorktreeDiff(worktree);
          if (diff.patch.trim()) {
            patchText = `\n\n=== Worktree changes ===\n${diff.diffStat}\n\n${diff.patch}`;
          }
          cleanupWorktree(worktree);
        }
        const ok = result.exitCode === 0 && !result.timedOut;
        setSpawnInfo(params.taskId, {
          pid: result.pid,
          status: ok ? "completed" : "failed",
          startedAt: task.spawn?.startedAt ?? Date.now(),
          finishedAt: Date.now(),
          exitCode: result.exitCode,
          stdout: ok ? result.stdout + patchText : undefined,
          stderr: ok ? undefined : result.stderr,
          usage: result.usage,
          timedOut: result.timedOut,
          error: ok
            ? undefined
            : result.timedOut
              ? `Worker timed out after ${Math.round(timeoutMs / 1000)}s.`
              : `Worker exited with code ${result.exitCode}.`,
        });
        markTeammateIdle(params.name);
        persistState(pi);
        refreshTeamUI(ctx);
      };

      const spawnFailure = (error: Error | string) => {
        setSpawnInfo(params.taskId, {
          pid: 0,
          status: "failed",
          startedAt: task.spawn?.startedAt ?? Date.now(),
          finishedAt: Date.now(),
          error: typeof error === "string" ? error : error.message,
        });
        markTeammateIdle(params.name);
        if (worktree && !("error" in worktree)) discardWorktree(worktree);
        persistState(pi);
        refreshTeamUI(ctx);
      };

      // ── Blocking mode (default): await the worker's OWN exit. No polling. ──
      if (!params.background) {
        const outcome = await spawnPiWorkerBlocking({
          workerName: teammate.name,
          description,
          model: teammate.model,
          tools: teammate.tools,
          cwd: workerCwd,
          signal: ctx.signal,
          timeoutMs,
        });

        if (!outcome.ok || !outcome.result) {
          spawnFailure(outcome.error ?? "Failed to spawn worker.");
          return {
            content: [{ type: "text", text: `Failed to spawn worker: ${outcome.error ?? "unknown"}` }],
            details: {},
            isError: true,
          };
        }

        finish(outcome.result);
        const updated = listTasks().find((t) => t.id === params.taskId);
        const replies = listTeammates().reduce(
          (sum, t) => sum + getUnreadCount(t.name),
          0,
        );
        const isolationNote =
          params.isolation === "worktree" && worktree && !("error" in worktree)
            ? `Isolation: worktree ${worktree.path} (branch ${worktree.branch})`
            : "Isolation: none";
        return {
          content: [
            {
              type: "text",
              text: [
                `Worker "${params.name}" closed itself (autonomous).`,
                `Task [${params.taskId}] status: ${updated?.status ?? "unknown"}${outcome.result.timedOut ? " (timed out)" : ""}`,
                `Usage: ${outcome.result.usage ? `${outcome.result.usage.totalTokens} tokens | cost $${outcome.result.usage.cost}` : "n/a"}`,
                isolationNote,
                "",
                "=== Worker final report ===",
                cap(outcome.result.stdout) || "(no report)",
                outcome.result.stderr ? `\n=== Worker stderr ===\n${cap(outcome.result.stderr)}` : "",
                updated?.result ? `\n=== Task result ===\n${cap(updated.result)}` : "",
                replies > 0 ? `\nUnread messages across the team: ${replies}` : "",
              ].join("\n"),
            },
          ],
          details: {},
        };
      }

      // ── Background mode: fire-and-forget; the worker keeps watching its mailbox. ──
      const started = spawnPiWorker({
        workerName: teammate.name,
        description,
        model: teammate.model,
        tools: teammate.tools,
        cwd: workerCwd,
        signal: ctx.signal,
        timeoutMs,
        onExit: (result) => finish(result),
        onError: (error) => spawnFailure(error),
      });

      if ("error" in started) {
        spawnFailure(started.error);
        return {
          content: [{ type: "text", text: `Failed to spawn worker: ${started.error}` }],
          details: {},
          isError: true,
        };
      }

      setSpawnInfo(params.taskId, {
        pid: started.pid,
        status: "running",
        startedAt: Date.now(),
      });
      task.status = "in_progress";
      persistState(pi);
      refreshTeamUI(ctx);

      const isolationNote =
        params.isolation === "worktree" && worktree && !("error" in worktree)
          ? `Isolation: worktree ${worktree.path} (branch ${worktree.branch})`
          : "Isolation: none";
      return {
        content: [
          {
            type: "text",
            text: [
              `Spawned "${params.name}" as a background worker for task [${params.taskId}] "${task.title}".`,
              `PID: ${started.pid} | Model: ${teammate.model ?? "default"} | Status: running (autonomous — watches its mailbox until it decides to close)`, 
              isolationNote,
              `The worker will mark the task completed/failed when it closes itself. Check teammate_list_tasks later for the outcome.`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ── Management tools: remove teammate, clean up tasks, reset board ──

  pi.registerTool({
    name: "teammate_remove",
    promptSnippet: "Unregister a teammate and delete its mailbox",
    label: "Remove Teammate",
    description: [
      "Unregister a teammate and delete its mailbox.",
      "Refuses while the teammate is running a worker unless force=true.",
    ].join(" "),
    parameters: TeammateRemoveParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = removeTeammate(params.name, params.force === true);
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to remove teammate." }],
          details: {},
          isError: true,
        };
      }
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [
          {
            type: "text",
            text: `Removed teammate "${params.name}".\nRemaining: ${listTeammates().length} teammate(s).`,
          },
        ],
        details: {},
      };
    },
  });

  pi.registerTool({
    name: "teammate_update_model",
    promptSnippet: "Change the model a teammate spawns with",
    label: "Update Teammate Model",
    description: [
      "Change the model a teammate is spawned with (applies to its next spawn;",
      "a running worker keeps the model it started with).",
    ].join(" "),
    parameters: TeammateUpdateModelParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = updateTeammateModel(params.name, params.model);
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to update model." }],
          details: {},
          isError: true,
        };
      }
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [
          {
            type: "text",
            text: `Teammate "${params.name}" model updated to: ${params.model} (next spawn).`,
          },
        ],
        details: {},
      };
    },
  });

  pi.registerTool({
    name: "teammate_cleanup",
    promptSnippet: "Prune finished tasks from the board",
    label: "Clean Up Tasks",
    description: [
      "Remove finished tasks (completed/failed/cancelled) from the board, or a single task via taskId.",
      "Keeps the footer task count from growing forever.",
    ].join(" "),
    parameters: TeammateCleanupParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.taskId) {
        const result = removeTask(params.taskId);
        if (!result.ok) {
          return {
            content: [{ type: "text", text: result.error ?? "Failed to remove task." }],
            details: {},
            isError: true,
          };
        }
        persistState(pi);
        refreshTeamUI(ctx);
        return {
          content: [
            {
              type: "text",
              text: `Removed task [${params.taskId}].\nTasks remaining: ${Object.keys(getState().tasks).length}`,
            },
          ],
          details: {},
        };
      }

      const removed = pruneFinishedTasks();
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [
          {
            type: "text",
            text: `Pruned ${removed} finished task(s).\nTasks remaining: ${Object.keys(getState().tasks).length}`,
          },
        ],
        details: {},
      };
    },
  });

  pi.registerTool({
    name: "teammate_reset",
    promptSnippet: "Wipe the whole team board",
    label: "Reset Board",
    description: [
      "Wipe the entire team: all teammates, mailboxes, and tasks.",
      "Refuses while any teammate is running a worker. Irreversible.",
    ].join(" "),
    parameters: EmptyParams,

    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      const result = resetBoard();
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to reset board." }],
          details: {},
          isError: true,
        };
      }
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [
          {
            type: "text",
            text: `Board reset: removed ${result.removedTeammates} teammate(s), ${result.removedTasks} task(s).`,
          },
        ],
        details: {},
      };
    },
  });

  // ── Team console (full-screen, owns input) ───────────────────────

  pi.registerCommand("teammate", {
    description: "Open the full-screen teammate team console: status, leader inbox, agent details, replies, interrupt/stop",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify(getSummary() ?? "No teammates registered.", "info");
        return;
      }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}
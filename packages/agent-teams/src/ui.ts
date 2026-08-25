/** Passive team widget and the /agent-teams management console
 * (session teammates + persistent agent roles + board). */

import { truncateToWidth, Key, matchesKey, fuzzyFilter } from "@earendil-works/pi-tui";
import {
  createPiThemeStyle,
  createSearchPicker,
  modelLabel,
  modelSearchText,
  PI_SPINNER_FRAMES,
  PI_SPINNER_INTERVAL_MS,
  sortModels,
  type SearchPicker,
} from "@fradser/pi-kit";
import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import {
  clampConsoleScroll, consoleScrollRange, maxConsoleBody, scrollConsoleDetail, wrapConsoleDetail,
} from "./console-viewport.ts";
import { fitTeammateRow, formatTeammateLabel, runningTeammateActivity } from "./activity.ts";
import { MODEL_INHERIT_ALIAS, discoverAgents, resolveAgent, type AgentDefinition } from "./agents.ts";
import { getState, getTeammate, getTeamDefaultModel, listTasks, listTeammates, livingTeammates, setTeamDefaultModel } from "./state.ts";
import {
  currentLeaderModelRef,
  ensureLivePoll,
  formatSilenceDuration,
  resolveSpawnModel,
  runtimeDirPath,
  shutdownTeammate,
  stallSilenceMs,
  stallThresholdMs,
} from "./team-machine.ts";
import type { Teammate } from "./types.ts";
import { mapPickerKey } from "./picker-keys.ts";
import { inboxPath } from "./statefile.ts";
import * as fs from "node:fs";
import * as path from "node:path";

const TEAM_COLORS = ["success", "warning", "error", "mdLink"] as const;
let spinnerTimer: ReturnType<typeof setInterval> | undefined;
let spinnerFrame = 0;

function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(0) + i * 7) | 0;
  return Math.abs(h);
}

function colorFor(name: string): (typeof TEAM_COLORS)[number] {
  return TEAM_COLORS[hashName(name) % TEAM_COLORS.length];
}

function ensureSpinner(): void {
  const working = livingTeammates().some(isWorking);
  if (working && !spinnerTimer) {
    spinnerTimer = setInterval(() => {
      spinnerFrame = (spinnerFrame + 1) % PI_SPINNER_FRAMES.length;
    }, PI_SPINNER_INTERVAL_MS);
    spinnerTimer.unref?.();
  } else if (!working && spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

export function stopUiTimers(): void {
  if (spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

export function ensureTeamWidget(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  if (!ctx?.ui?.setWidget) return;
  if (ctx.mode && ctx.mode !== "tui") return;

  if (livingTeammates().filter(isWorking).length === 0) {
    ctx.ui.setWidget("teammate", undefined);
    return;
  }

  ctx.ui.setWidget("teammate", (tui, theme) => {
    const timer = setInterval(() => tui.requestRender(), PI_SPINNER_INTERVAL_MS);
    timer.unref?.();
    const style = createPiThemeStyle(theme);
    return {
      placement: "belowEditor",
      render: (width: number) => {
        // Only WORKING teammates appear above the input box; idle and
        // stopped teammates stay in the /agent-teams console instead.
        const working = livingTeammates().filter(isWorking);
        if (working.length === 0) return [];
        const lines: string[] = [];
        for (const teammate of working) {
          lines.push(fitTeammateRow(
            PI_SPINNER_FRAMES[spinnerFrame],
            style.fg(colorFor(teammate.name), teammate.name),
            runningTeammateActivity(teammate) + stallSuffix(teammate),
            width,
            (activity) => theme.bold(style.fg("accent", activity)),
          ));
        }
        return lines;
      },
      invalidate: () => {},
      dispose: () => clearInterval(timer),
    };
  });
}

function isWorking(teammate: { status: string }): boolean {
  return teammate.status === "working" || teammate.status === "starting";
}

/** Silence marker appended once a working teammate passes its stall threshold. */
function stallSuffix(teammate: Teammate): string {
  if (!isWorking(teammate)) return "";
  const silence = stallSilenceMs(teammate);
  const threshold = stallThresholdMs(teammate);
  return silence !== undefined && threshold > 0 && silence >= threshold
    ? ` · stalled for ${formatSilenceDuration(silence)}`
    : "";
}

export function refreshTeamUI(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  ensureTeamWidget(ctx);
  ensureLivePoll();
  ensureSpinner();
}

function cap(text: string | undefined, maxBytes = 2000): string {
  if (!text) return "";
  return text.length <= maxBytes ? text : `${text.slice(0, maxBytes)}\n…[truncated ${text.length - maxBytes} chars]`;
}

// ── Detail builders ───────────────────────────────────────────────

interface PeerMailLine {
  direction: "sent" | "received";
  counterpart: string;
  subject: string;
  body: string;
  timestamp: number;
}

function readPeerMail(teammateName: string): PeerMailLine[] {
  const runtimeDir = runtimeDirPath();
  if (!runtimeDir) return [];
  const mailDirPath = path.dirname(inboxPath(path.join(runtimeDir, "state.json"), teammateName));
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(mailDirPath).filter((name) => name.startsWith("inbox-") && name.endsWith(".jsonl"));
  } catch {
    return [];
  }
  const lines: PeerMailLine[] = [];
  for (const entry of entries) {
    const recipient = decodeURIComponent(entry.slice("inbox-".length, -".jsonl".length));
    let raw = "";
    try {
      raw = fs.readFileSync(path.join(mailDirPath, entry), "utf-8");
    } catch {
      continue;
    }
    for (const line of raw.split("\n")) {
      if (!line.trim()) continue;
      try {
        const message = JSON.parse(line) as { id?: string; from?: string; subject?: string; body?: string; timestamp?: number };
        if (!message.id || !message.from || !message.subject) continue;
        if (message.from !== teammateName && recipient !== teammateName) continue;
        lines.push({
          direction: message.from === teammateName ? "sent" : "received",
          counterpart: message.from === teammateName ? recipient : message.from,
          subject: message.subject,
          body: message.body ?? "",
          timestamp: message.timestamp ?? 0,
        });
      } catch {
        continue;
      }
    }
  }
  return lines.sort((a, b) => a.timestamp - b.timestamp);
}

function indent(text: string): string[] {
  return text.split("\n").map((line) => `  ${line}`);
}

function displaySource(sourcePath: string | undefined): string {
  if (!sourcePath) return "(in-memory session role)";
  const relative = path.relative(process.cwd(), sourcePath);
  return relative.startsWith("..") ? sourcePath : `./${relative}`;
}

function buildTeammateDetail(name: string): string[] {
  const teammate = getTeammate(name);
  if (!teammate) return ["(teammate removed from the roster)"];
  const reports = getState().leaderMailbox.filter((message) => message.from === name);
  const lines: string[] = [
    `@${teammate.name} (${teammate.agent}) [${teammate.status}]`,
    "",
    "== teammate ==",
    `  Status: ${teammate.status}${teammate.currentTaskId ? ` | Task: ${teammate.currentTaskId}` : ""}`,
    `  Spawn: ${teammate.pid > 0 ? `pid ${teammate.pid}` : "pid unknown"} | Isolation: ${teammate.isolation}`,
    ...(teammate.model ? [`  Launch model: ${teammate.model}`] : []),
    ...(teammate.tools?.length ? [`  Tools: ${teammate.tools.join(", ")}`] : []),
    `  Created: ${new Date(teammate.createdAt).toLocaleString()}`,
  ];
  if (teammate.stoppedAt) lines.push(`  Stopped: ${new Date(teammate.stoppedAt).toLocaleString()}`);
  if (isWorking(teammate) && teammate.lastOutputAt !== undefined) {
    const silence = stallSilenceMs(teammate);
    if (silence !== undefined) {
      lines.push(`  Last output: ${new Date(teammate.lastOutputAt).toLocaleString()} (${formatSilenceDuration(silence)} ago${stallSuffix(teammate) ? " — stalled" : ""})`);
    }
  }
  if (teammate.usage) lines.push(`  Usage: ${teammate.usage.totalTokens} tokens | $${teammate.usage.cost.toFixed(4)}`);
  if (teammate.error) lines.push(`  Error: ${teammate.error}`);

  lines.push("", `== reports to leader (${reports.length}) ==`);
  if (reports.length === 0) lines.push("  (none)");
  for (const report of reports) {
    lines.push(`  -> [${report.subject}] ${new Date(report.timestamp).toLocaleString()}`, ...indent(cap(report.body)), "");
  }

  const peer = readPeerMail(name);
  lines.push(`== peer mail (${peer.length}) ==`);
  if (peer.length === 0) lines.push("  (none)");
  for (const mail of peer) {
    const arrow = mail.direction === "sent" ? `to @${mail.counterpart}` : `from @${mail.counterpart}`;
    lines.push(`  ${arrow} [${mail.subject}] ${new Date(mail.timestamp).toLocaleString()}`, ...indent(cap(mail.body)), "");
  }
  return lines;
}

function buildTaskDetail(taskId: string): string[] {
  const tasks = listTasks();
  const task = tasks.find((candidate) => candidate.id === taskId);
  if (!task) return ["(task not on the board)"];
  const byId = new Map(tasks.map((candidate) => [candidate.id, candidate]));
  return [
    `[${task.id}] ${task.subject}`,
    "",
    "== task ==",
    `  Status: ${task.status}${task.claimedBy ? ` (@${task.claimedBy})` : ""}`,
    ...(task.description ? [`  Description:`, ...indent(cap(task.description))] : []),
    ...(task.dependsOn.length > 0
      ? [`  Depends on: ${task.dependsOn.join(", ")} (${task.dependsOn.every((dep) => byId.get(dep)?.status === "completed") ? "met" : "unmet"})`]
      : []),
    `  Verify: ${task.verify ?? "(none)"}`,
    ...(task.result ? ["  Result:", ...indent(cap(task.result))] : []),
    ...(task.errorMessage ? ["  Error:", ...indent(cap(task.errorMessage))] : []),
    `  Created: ${new Date(task.createdAt).toLocaleString()}`,
    ...(task.completedAt ? [`  Completed: ${new Date(task.completedAt).toLocaleString()}`] : []),
  ];
}

function buildRoleDetail(name: string): string[] {
  const def = resolveAgent(name);
  if (!def) return ["(agent definition not found)"];
  return [
    `@${def.name} (${def.scope})${def.scope === "session" ? " [in-memory]" : def.gitManaged ? " [git-managed]" : " [local]"}`,
    "",
    "== role ==",
    `  Source: ${displaySource(def.source)}`,
    `  Description: ${def.description || "(none)"}`,
    `  Tools: ${def.tools.join(", ") || "(role defaults)"}`,
    `  Model: ${describeSpawnModel(def.model)}`,
    `  Verify: ${def.verify ?? "(none)"}`,
    `  Worktree: ${def.worktree ? "true" : "false"}`,
    `  Living instances: ${livingTeammates().filter((teammate) => teammate.agent === def.name).length}`,
    "",
    "== role prompt ==",
    ...indent(cap(def.prompt)),
  ];
}

/** Human-readable effective launch model for a role definition. */
function describeSpawnModel(pinned: string | undefined): string {
  const resolved = resolveSpawnModel(pinned, getTeamDefaultModel(), currentLeaderModelRef());
  if (pinned && pinned.trim().toLowerCase() !== MODEL_INHERIT_ALIAS) return pinned.trim();
  if (resolved.model) {
    const suffix = pinned ? "inherit -> " : "[team default] ";
    return `${suffix}${resolved.model}`;
  }
  return pinned ? "inherit -> (unavailable at spawn)" : "(Pi default)";
}

// ── Full-screen console ───────────────────────────────────────────

type ConsolePage = "roster" | "board";

interface RosterRow {
  key: string;
  kind: "teammate";
}
interface RoleRow {
  key: string;
  kind: "role";
}
interface BoardRow {
  key: string;
  kind: "task";
}
type ConsoleRow = RosterRow | RoleRow | BoardRow;

/** SGR mouse-wheel events carry a button code; return signed line delta. */
function wheelDelta(data: string): number | undefined {
  const match = /^\x1b\[<(\d+);\d+;\d+[Mm]$/.exec(data);
  if (!match) return undefined;
  const button = Number.parseInt(match[1], 10);
  if ((button & 64) === 0) return undefined;
  const direction = button & 3;
  if (direction === 0) return -1;
  if (direction === 1) return 1;
  return undefined;
}

/** Chrome lines around the list viewport: border, header, spacer, footer, border. */
const LIST_CHROME_LINES = 5;

/** Full-screen Team Console — owns input via ctx.ui.custom. Pages: roster /
 * board; each row opens a scrolling detail view; m opens the searchable
 * teammate-model picker. */
export function openTeamConsole(ctx: {
  ui: ExtensionUIContext;
  modelRegistry?: { getAvailable(): Array<{ provider: string; id: string; name?: string }> };
}): Promise<void> {
  return ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
    let page: ConsolePage = "roster";
    let mode: "list" | "detail" | "picker" = "list";
    let selectedRoster = 0;
    let selectedBoard = 0;
    let listOffset = 0;
    let detailKind: ConsoleRow["kind"] = "teammate";
    let detailKey = "";
    let offset = 0;
    let confirmName: string | undefined;
    let closed = false;
    let renderTimer: ReturnType<typeof setInterval> | undefined;

    // Definitions are reread lazily so mid-session role creation shows up,
    // but never once per animation frame.
    let rolesCache: AgentDefinition[] = [];
    let rolesCacheAt = 0;
    const ROLES_CACHE_TTL_MS = 2000;
    const getRoles = (): AgentDefinition[] => {
      const now = Date.now();
      if (now - rolesCacheAt > ROLES_CACHE_TTL_MS) {
        rolesCache = [...discoverAgents().values()].sort((a, b) => a.name.localeCompare(b.name));
        rolesCacheAt = now;
      }
      return rolesCache;
    };

    const requestRender = () => {
      if (!closed) tui.requestRender();
    };
    const startLiveRefresh = () => {
      if (renderTimer) return;
      renderTimer = setInterval(() => {
        // Redraw only while something can animate (spinner/activity/stall).
        if (livingTeammates().some(isWorking)) requestRender();
      }, PI_SPINNER_INTERVAL_MS);
      renderTimer.unref?.();
    };
    const stopLiveRefresh = () => {
      if (!renderTimer) return;
      clearInterval(renderTimer);
      renderTimer = undefined;
    };
    startLiveRefresh();

    const style = createPiThemeStyle(theme);

    // ── Teammate-model picker (type-to-filter) ──────────────────
    let picker: SearchPicker<{ provider: string; id: string; name?: string }> | undefined;
    let pickerOffset = 0;

    /** Pinned pseudo-entry so clearing never collides with typed search text. */
    const CLEAR_TEAM_MODEL_ENTRY: { provider: string; id: string; name?: string } = {
      provider: "",
      id: "__clear-team-default__",
      name: "Use Pi default",
    };
    const isClearEntry = (model: { id: string } | undefined): boolean =>
      model?.id === CLEAR_TEAM_MODEL_ENTRY.id;

    const openModelPicker = (): void => {
      const models = sortModels([...(ctx.modelRegistry?.getAvailable() ?? [])]);
      if (models.length === 0) return;
      picker = createSearchPicker([CLEAR_TEAM_MODEL_ENTRY, ...models], {
        filter: fuzzyFilter,
        getText: (model) => (isClearEntry(model) ? "clear team default use pi default" : modelSearchText(model)),
      });
      pickerOffset = 0;
      mode = "picker";
      requestRender();
    };

    const closeModelPicker = (): void => {
      picker = undefined;
      mode = "list";
      requestRender();
    };

    const PICKER_CHROME_LINES = 7;
    const pickerViewport = (): number => Math.max(1, tui.terminal.rows - PICKER_CHROME_LINES);

    const renderPicker = (width: number): string[] => {
      if (!picker) return [];
      const border = style.border("─".repeat(Math.max(1, width)));
      const results = picker.results();
      const selected = picker.selectedIndex();
      if (selected < pickerOffset) pickerOffset = selected;
      else if (selected >= pickerOffset + pickerViewport()) pickerOffset = selected - pickerViewport() + 1;
      pickerOffset = clampConsoleScroll(pickerOffset, results.length, pickerViewport());
      const leaderRef = currentLeaderModelRef();
      const teamDefault = getTeamDefaultModel();
      const rows = results.slice(pickerOffset, pickerOffset + pickerViewport()).map((model, index) => {
        const absolute = pickerOffset + index;
        const marker = absolute === selected ? style.accent("❯ ") : "  ";
        if (isClearEntry(model)) {
          return truncateToWidth(`${marker}${theme.fg("warning", "✕ clear team default")} ${style.dim("· use Pi default")}`, Math.max(10, width - 1));
        }
        const tags = [
          modelLabel(model) === leaderRef ? style.dim("(leader)") : "",
          modelLabel(model) === teamDefault ? style.success("(default)") : "",
        ].filter(Boolean).join(" ");
        const display = model.name && model.name !== model.id ? style.dim(model.name) : "";
        return truncateToWidth(`${marker}${theme.fg("customMessageText", modelLabel(model))} ${display} ${tags}`.replace(/\s+$/g, ""), Math.max(10, width - 1));
      });
      return [
        border,
        style.accent(truncateToWidth(`teammate model  ${teamDefault ?? "auto (Pi default)"}`, width)),
        "",
        truncateToWidth(`${style.accent("❯ ")}${picker.query()}▏  ${style.dim(`${results.length} models`)}`, Math.max(10, width - 1)),
        ...rows,
        "",
        truncateToWidth(style.dim("type to filter · ↑↓ select · enter set/clear · esc cancel"), Math.max(10, width - 1)),
        border,
      ];
    };

    function handlePickerInput(data: string): void {
      if (!picker) {
        mode = "list";
        return;
      }
      const action = mapPickerKey(data);
      if (!action) return;
      if (action.kind === "cancel") {
        closeModelPicker();
        return;
      }
      if (action.kind === "confirm") {
        const picked = picker.selected();
        // An empty filtered list must not clobber the current default.
        if (!picked) return;
        if (isClearEntry(picked)) {
          setTeamDefaultModel(undefined);
          ctx.ui.notify("Teammate model cleared — Pi picks its default", "info");
        } else {
          setTeamDefaultModel(modelLabel(picked));
          ctx.ui.notify(`Teammate model set to ${modelLabel(picked)} for this session`, "info");
        }
        closeModelPicker();
        return;
      }
      if (action.kind === "up") picker.up();
      else if (action.kind === "down") picker.down();
      else if (action.kind === "backspace") picker.backspace();
      else picker.type(action.text);
      requestRender();
    }

    const currentRows = (): ConsoleRow[] =>
      page === "roster"
        // The console is the management surface: idle and stopped stay
        // visible, and persistent agent roles are listed after the session.
        ? [
            ...listTeammates().map((t) => ({ key: t.name, kind: "teammate" as const })),
            ...getRoles().map((def) => ({ key: def.name, kind: "role" as const })),
          ]
        : listTasks().map((task) => ({ key: task.id, kind: "task" as const }));

    const windowLines = (full: string[], width: number): { lines: string[]; range: string } => {
      const wrapped = wrapConsoleDetail(full, width);
      const viewport = maxConsoleBody(tui.terminal.rows);
      offset = clampConsoleScroll(offset, wrapped.length, viewport);
      return {
        lines: wrapped.slice(offset, offset + viewport),
        range: consoleScrollRange(offset, wrapped.length, viewport),
      };
    };

    const headerLine = (): string => {
      const alive = livingTeammates();
      const tasks = listTasks();
      return `team  ${alive.length} alive · ${alive.filter(isWorking).length} working · ${getRoles().length} roles · board ${tasks.filter((task) => task.status === "pending").length}p/${tasks.filter((task) => task.status === "claimed").length}c/${tasks.filter((task) => task.status === "completed").length}d · model ${getTeamDefaultModel() ?? "auto"} · ${page}`;
    };

    interface ContentLine {
      text: string;
      /** Selectable row index, or -1 for section chrome. */
      select: number;
    }

    const teammateRowText = (key: string, selected: boolean): string => {
      const teammate = getTeammate(key)!;
      const marker = selected ? style.accent("❯ ") : "  ";
      const name = theme.bold(theme.fg(colorFor(teammate.name), `@${teammate.name}`));
      if (isWorking(teammate)) {
        const prefix = `${marker}${name} `;
        const width = tui.terminal.columns;
        const available = Math.max(0, width - prefix.length - PI_SPINNER_FRAMES[spinnerFrame].length - 2);
        const status = theme.fg("warning", formatTeammateLabel(PI_SPINNER_FRAMES[spinnerFrame], runningTeammateActivity(teammate) + stallSuffix(teammate), available));
        return `${prefix}${status}`;
      }
      if (teammate.status === "idle") {
        return `${marker}${name} ${style.dim(`○ idle${teammate.currentTaskId ? ` · ${teammate.currentTaskId}` : ""}`)}`;
      }
      return `${marker}${name} ${theme.fg("warning", "■ stopped")}`;
    };

    const roleRowText = (key: string, selected: boolean): string => {
      const def = getRoles().find((candidate) => candidate.name === key)!;
      const marker = selected ? style.accent("❯ ") : "  ";
      const name = theme.bold(theme.fg(colorFor(key), `@${key}`));
      const live = livingTeammates().filter((teammate) => teammate.agent === key && teammate.status !== "stopped").length;
      const liveTag = live > 0 ? style.success(`[${live} live]`) : style.dim("[0 live]");
      const provenance = def.scope === "session" ? "in-memory" : displaySource(def.source);
      return `${marker}${name} ${style.dim(def.scope)} ${style.dim(provenance)} ${liveTag}`;
    };

    const taskRowText = (key: string, selected: boolean): string => {
      const task = listTasks().find((candidate) => candidate.id === key)!;
      const marker = selected ? style.accent("❯ ") : "  ";
      const label = theme.fg(colorFor(key), `[${key}]`);
      const holder = task.claimedBy ? style.dim(` @${task.claimedBy}`) : "";
      const statusText = task.status === "completed"
        ? style.success("✓")
        : task.status === "claimed"
          ? theme.fg("warning", "◐ claimed")
          : style.dim("○ pending");
      return `${marker}${label} ${statusText} ${theme.fg("customMessageText", task.subject)}${holder}`;
    };

    const buildContent = (): ContentLine[] => {
      const rows = currentRows();
      const lines: ContentLine[] = [];
      if (page === "board") {
        if (rows.length === 0) {
          lines.push({ text: style.dim("The task board is empty. Create tasks with task_create."), select: -1 });
        }
        rows.forEach((row, index) => lines.push({ text: taskRowText(row.key, index === currentPageSelection(rows.length)), select: index }));
        return lines;
      }
      const teammates = rows.filter((row): row is RosterRow => row.kind === "teammate");
      const roles = rows.filter((row): row is RoleRow => row.kind === "role");
      const selection = currentPageSelection(rows.length);
      lines.push({ text: style.dim("== teammates (this session) =="), select: -1 });
      if (teammates.length === 0) {
        lines.push({ text: style.dim("No teammates this session. Ask the model to spawn one."), select: -1 });
      }
      teammates.forEach((row, index) => lines.push({ text: teammateRowText(row.key, index === selection), select: index }));
      lines.push({ text: "", select: -1 });
      lines.push({ text: style.dim("== agent roles (persistent and session definitions) =="), select: -1 });
      if (roles.length === 0) {
        lines.push({ text: style.dim("No agent definitions discovered."), select: -1 });
      }
      roles.forEach((row, index) => lines.push({ text: roleRowText(row.key, teammates.length + index === selection), select: teammates.length + index }));
      return lines;
    };

    const listViewport = (): number => Math.max(1, tui.terminal.rows - LIST_CHROME_LINES);

    const renderList = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const content = buildContent();
      const viewport = listViewport();
      const selection = currentPageSelection(currentRows().length);
      const selectedIndex = content.findIndex((line) => line.select === selection);
      if (selectedIndex >= 0) {
        if (selectedIndex < listOffset) listOffset = selectedIndex;
        else if (selectedIndex >= listOffset + viewport) listOffset = selectedIndex - viewport + 1;
      }
      listOffset = clampConsoleScroll(listOffset, content.length, viewport);
      const footer = confirmName
        ? theme.fg("warning", `Shut down @${confirmName}? Its claimed task returns to the board · y yes / n no`)
        : style.dim(page === "roster"
            ? "↑↓ select · enter open · tab board · x shutdown · m model · esc/q close"
            : "↑↓ select · enter open · tab roster · esc/q close");
      return [
        border,
        style.accent(truncateToWidth(headerLine(), width)),
        "",
        ...content.slice(listOffset, listOffset + viewport)
          .map((line) => truncateToWidth(line.text, Math.max(10, width - 1))),
        "",
        truncateToWidth(footer, Math.max(10, width - 1)),
        border,
      ];
    };

    const currentPageSelection = (rowCount: number): number => {
      const selection = page === "roster" ? selectedRoster : selectedBoard;
      return rowCount === 0 ? 0 : Math.min(selection, rowCount - 1);
    };

    const detailTitle = (): string =>
      detailKind === "task" ? `[${detailKey}]` : detailKind === "role" ? `@${detailKey} · role` : `@${detailKey}`;

    const renderDetail = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const source = detailSource();
      const detail = windowLines(source, width);
      const footer = style.dim(`  ${detail.range} · ↑↓ scroll · pgup/pgdn page · home/end jump · esc back · q close`);
      const lines = [
        border,
        style.accent(truncateToWidth(`agent-teams  ${detailTitle()}`, width)),
        "",
        ...detail.lines.map((line) => `  ${line}`),
        "",
        footer,
        border,
      ];
      return lines.map((line) => truncateToWidth(line, Math.max(10, width - 1)));
    };

    const detailSource = (): string[] => {
      if (detailKind === "task") return buildTaskDetail(detailKey);
      if (detailKind === "role") return buildRoleDetail(detailKey);
      return buildTeammateDetail(detailKey);
    };

    return {
      render: (width) => (mode === "picker" ? renderPicker(width) : mode === "detail" ? renderDetail(width) : renderList(width)),
      handleInput: (data: string) => {
        if (mode === "picker") {
          handlePickerInput(data);
          return;
        }
        if (mode !== "list") {
          handleDetailInput(data);
          return;
        }
        if (confirmName) {
          if (data === "y" || data === "Y") {
            const name = confirmName;
            confirmName = undefined;
            void shutdownFromConsole(ctx, name);
          } else if (data === "n" || data === "N" || matchesKey(data, Key.escape)) {
            confirmName = undefined;
          } else if (data === "q" || data === "Q") {
            closeConsole(done);
          }
          return;
        }
        const rows = currentRows();
        if (matchesKey(data, Key.tab)) {
          page = page === "roster" ? "board" : "roster";
          listOffset = 0;
          return;
        }
        if (matchesKey(data, Key.down)) bumpSelection(1, rows.length);
        if (matchesKey(data, Key.up)) bumpSelection(-1, rows.length);
        if (matchesKey(data, Key.enter)) {
          const selection = currentPageSelection(rows.length);
          const row = rows[selection];
          if (row) {
            mode = "detail";
            offset = 0;
            detailKind = row.kind;
            detailKey = row.key;
          }
          return;
        }
        if (data === "x" || data === "X") {
          const selection = currentPageSelection(rows.length);
          const row = rows[selection];
          if (page === "roster" && row?.kind === "teammate" && getTeammate(row.key)?.status !== "stopped") {
            confirmName = row.key;
          }
          return;
        }
        if (data === "m" || data === "M") {
          if (ctx.modelRegistry && ctx.modelRegistry.getAvailable().length > 0) {
            openModelPicker();
          } else {
            ctx.ui.notify("No models are available in the model registry.", "warning");
          }
          return;
        }
        const wheel = wheelDelta(data);
        if (wheel !== undefined) {
          scrollList(wheel * 3);
          return;
        }
        if (matchesKey(data, Key.pageUp)) scrollList(-listViewport());
        else if (matchesKey(data, Key.pageDown)) scrollList(listViewport());
        else if (matchesKey(data, Key.home)) listOffset = 0;
        else if (matchesKey(data, Key.end)) listOffset = clampConsoleScroll(Number.MAX_SAFE_INTEGER, buildContent().length, listViewport());
        else if (matchesKey(data, Key.escape) || data === "q" || data === "Q") closeConsole(done);
      },
      invalidate: () => requestRender(),
      dispose: () => {
        closed = true;
        stopLiveRefresh();
      },
    };

    function closeConsole(doneFn: () => void): void {
      closed = true;
      stopLiveRefresh();
      doneFn();
    }

    function bumpSelection(delta: number, rowCount: number): void {
      if (rowCount === 0) return;
      if (page === "roster") selectedRoster = clampIndex(selectedRoster + delta, rowCount);
      else selectedBoard = clampIndex(selectedBoard + delta, rowCount);
    }

    function scrollList(delta: number): void {
      listOffset = clampConsoleScroll(listOffset + delta, buildContent().length, listViewport());
    }

    function handleDetailInput(data: string): void {
      const source = detailSource();
      const viewport = maxConsoleBody(tui.terminal.rows);
      if (matchesKey(data, Key.escape)) {
        mode = "list";
        offset = 0;
        return;
      }
      if (data === "q" || data === "Q") {
        closeConsole(done);
        return;
      }
      const total = wrapConsoleDetail(source, tui.terminal.columns).length;
      const wheel = wheelDelta(data);
      if (wheel !== undefined) {
        offset = scrollConsoleDetail(offset, wheel * 3, total, viewport);
        return;
      }
      if (matchesKey(data, Key.up)) offset = scrollConsoleDetail(offset, -1, total, viewport);
      else if (matchesKey(data, Key.down)) offset = scrollConsoleDetail(offset, 1, total, viewport);
      else if (matchesKey(data, Key.pageUp)) offset = scrollConsoleDetail(offset, -Math.max(1, viewport - 1), total, viewport);
      else if (matchesKey(data, Key.pageDown)) offset = scrollConsoleDetail(offset, Math.max(1, viewport - 1), total, viewport);
      else if (matchesKey(data, Key.home)) offset = 0;
      else if (matchesKey(data, Key.end)) offset = clampConsoleScroll(Number.MAX_SAFE_INTEGER, total, viewport);
    }
  });
}

async function shutdownFromConsole(ctx: { ui: ExtensionUIContext }, name: string): Promise<void> {
  const result = await shutdownTeammate(name);
  if (result.ok) ctx.ui.notify(result.body, "info");
  else ctx.ui.notify(result.error, "error");
}

function clampIndex(index: number, rowCount: number): number {
  return Math.max(0, Math.min(rowCount - 1, index));
}

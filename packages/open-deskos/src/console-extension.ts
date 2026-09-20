import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Container, Input, Key, SelectList, Text, matchesKey, truncateToWidth, type Focusable, type SelectItem } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import { DeskConsoleClient, type ConsoleAttachment } from "./console-client.ts";
import type { DeskLinkSnapshot } from "./reporter.ts";
import type { DeskLinkConfig, HistoryPage, HostedPiSession, PositionedSessionEvent } from "./types.ts";
import type { ControlTransport } from "./control-transport.ts";

const CONSOLE_STATE_ENTRY = "open-deskos-console-state";
const CONSOLE_CONTEXT_MESSAGE = "open-deskos-hosted-pi";
const CONTEXT_EVENTS = 24;
const CONTEXT_BYTES = 24 * 1024;
const TOOL_OUTPUT_BYTES = 48 * 1024;

export interface ConsoleExtensionOptions {
  pi: ExtensionAPI;
  config: DeskLinkConfig | null;
  createControlTransport: (config: DeskLinkConfig) => ControlTransport;
  reporterSnapshot: () => DeskLinkSnapshot | null;
  configHint: string;
}

interface PersistedConsoleState {
  sessionId?: string;
  attachmentId?: string;
  lastApplied: number;
}

function textResult(text: string, details: unknown = {}): { content: Array<{ type: "text"; text: string }>; details: unknown } {
  return { content: [{ type: "text", text }], details };
}

function asState(data: unknown): PersistedConsoleState | null {
  if (typeof data !== "object" || data === null) return null;
  const value = data as { sessionId?: unknown; attachmentId?: unknown; lastApplied?: unknown };
  const lastApplied = Number.isSafeInteger(value.lastApplied) && Number(value.lastApplied) >= 0 ? Number(value.lastApplied) : 0;
  return {
    ...(typeof value.sessionId === "string" && value.sessionId.length > 0 ? { sessionId: value.sessionId } : {}),
    ...(typeof value.attachmentId === "string" && value.attachmentId.length > 0 ? { attachmentId: value.attachmentId } : {}),
    lastApplied,
  };
}

function restoreState(ctx: ExtensionContext): PersistedConsoleState {
  let restored: PersistedConsoleState = { lastApplied: 0 };
  for (const entry of ctx.sessionManager.getBranch()) {
    if (entry.type !== "custom" || entry.customType !== CONSOLE_STATE_ENTRY) continue;
    restored = asState(entry.data) ?? restored;
  }
  return restored;
}

function firstLine(value: string, max = 80): string {
  const line = value.split(/\r?\n/).find((candidate) => candidate.trim().length > 0)?.trim() ?? "";
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

function eventLine(entry: PositionedSessionEvent): string {
  const summary = entry.events.map((event) => {
    const label = event.toolName ? `${event.kind}:${event.toolName}` : event.kind;
    return `${label} · ${firstLine(event.text, 120)}`;
  }).join(" | ");
  return `${entry.position} ${summary}`;
}

function boundedContext(entries: readonly PositionedSessionEvent[]): PositionedSessionEvent[] {
  const retained: PositionedSessionEvent[] = [];
  let bytes = 0;
  for (let index = entries.length - 1; index >= 0 && retained.length < CONTEXT_EVENTS; index -= 1) {
    const entry = entries[index]!;
    const size = Buffer.byteLength(JSON.stringify(entry));
    if (bytes + size > CONTEXT_BYTES) break;
    retained.push(entry);
    bytes += size;
  }
  return retained.reverse();
}

function sessionLabel(session: HostedPiSession): string {
  const project = session.workspaceName ?? session.project ?? session.cwd ?? "unknown project";
  const goal = session.goal ?? session.latestGoal ?? session.activity ?? "no goal";
  const at = session.updatedAt ?? session.startedAt;
  const age = at === undefined ? "unknown age" : `${Math.max(0, Math.floor((Date.now() - at) / 60000))}m`;
  return `${session.status} · ${project} · ${age} · ${firstLine(goal, 70)}`;
}

export function formatHistory(page: HistoryPage): string {
  if (page.oversized) return "The next Hosted Pi log entry exceeds the bounded history response. Read the session log on the desk directly; retrying the same position will not make the entry fit.";
  const lines: string[] = [];
  let bytes = 0;
  let continuation = page.nextPosition;
  for (const entry of page.entries) {
    const batch = entry.events.map((event, index) => `${entry.position}${index === 0 ? "" : "."} ${event.kind}${event.toolName ? ` ${event.toolName}` : ""}\n${event.text}`).join("\n\n");
    const addition = `${lines.length ? "\n\n" : ""}${batch}`;
    if (bytes + Buffer.byteLength(addition, "utf8") > TOOL_OUTPUT_BYTES) {
      continuation = entry.position - 1;
      break;
    }
    lines.push(batch);
    bytes += Buffer.byteLength(addition, "utf8");
  }
  if (continuation !== null) lines.push(`[continue from position ${continuation}]`);
  return lines.join("\n\n") || "No history entries.";
}

export function registerConsoleExtension(options: ConsoleExtensionOptions): void {
  const { pi, config, createControlTransport, reporterSnapshot, configHint } = options;
  let currentConsoleSessionId = "";
  let state: PersistedConsoleState = { lastApplied: 0 };
  let client: DeskConsoleClient | null = null;
  let attachment: ConsoleAttachment | null = null;
  let tail: PositionedSessionEvent[] = [];
  const surfaceListeners = new Set<(entry: PositionedSessionEvent) => void>();

  const controlConfigured = (): boolean => config !== null && Boolean(config.controlToken);
  const unavailable = (): string => config !== null
    ? "set ODK_DESK_LINK_CONTROL_TOKEN to enable the Console"
    : `${configHint}; set ODK_DESK_LINK_CONTROL_TOKEN to enable the Console`;
  const requireClient = (): DeskConsoleClient => {
    if (!controlConfigured() || !client) throw new Error(unavailable());
    return client;
  };
  const persist = (): void => pi.appendEntry(CONSOLE_STATE_ENTRY, state);
  const injectContext = (terminal?: unknown): void => {
    if (tail.length === 0 && terminal === undefined) return;
    const content = [
      state.sessionId ? `Hosted Pi ${state.sessionId}` : "Hosted Pi",
      ...tail.map(eventLine),
      ...(terminal === undefined ? [] : [`terminal ${JSON.stringify(terminal)}`]),
      "Complete content remains available through desk_history.",
    ].join("\n");
    // Persist the bounded observation in context without autonomously starting
    // another model turn. The next user turn sees it, and a terminal result is
    // still visible immediately in the transcript.
    pi.sendMessage({ customType: CONSOLE_CONTEXT_MESSAGE, content, display: true, details: { sessionId: state.sessionId, lastApplied: state.lastApplied } }, { deliverAs: "followUp", triggerTurn: false });
    tail = [];
  };
  const applyEvent = (entry: PositionedSessionEvent): void => {
    tail = boundedContext([...tail, entry]);
    for (const listener of surfaceListeners) listener(entry);
  };
  const attach = async (sessionId: string, position = state.sessionId === sessionId ? state.lastApplied : undefined): Promise<ConsoleAttachment> => {
    attachment?.close();
    const next = await requireClient().attach({
      sessionId,
      ...(position === undefined ? {} : { position }),
      onEvent: applyEvent,
      onPosition(lastApplied) {
        state = { sessionId, ...(state.attachmentId ? { attachmentId: state.attachmentId } : {}), lastApplied };
        persist();
      },
      onTerminal(record) { injectContext(record); },
    });
    attachment = next;
    state = { sessionId, attachmentId: next.attachmentId, lastApplied: next.lastApplied() };
    persist();
    return next;
  };

  if (controlConfigured()) {
    pi.registerMessageRenderer(CONSOLE_CONTEXT_MESSAGE, (message, _renderOptions, theme) =>
      new Text(`${theme.fg("customMessageLabel", "[open-deskos] ")}${theme.fg("customMessageText", firstLine(typeof message.content === "string" ? message.content : "Hosted Pi update", 160))}`, 0, 0));

    pi.on("session_start", (_event, ctx) => {
    currentConsoleSessionId = ctx.sessionManager.getSessionId();
    state = restoreState(ctx);
    tail = [];
    attachment = null;
    client = controlConfigured() && config
      ? new DeskConsoleClient({ config, consoleSessionId: currentConsoleSessionId, createTransport: createControlTransport })
      : null;
  });
  pi.on("agent_settled", () => injectContext());
    pi.on("session_shutdown", () => {
      attachment?.close();
      attachment = null;
      client?.closeAttachment();
      client = null;
    });

    pi.registerTool({
    name: "desk_list",
    label: "Desk List",
    description: "List the Hosted Pi sessions on Open DeskOS, including state, project, goal, and age.",
    parameters: Type.Object({}),
    async execute() {
      const result = await requireClient().list();
      const text = result.sessions.length === 0 ? "No Hosted Pi sessions." : result.sessions.map((session) => `${session.sessionId} · ${sessionLabel(session)}`).join("\n");
      return textResult(text, result);
    },
  });
  pi.registerTool({
    name: "desk_start",
    label: "Desk Start",
    description: "Start a Hosted Pi on Open DeskOS with a project and prompt. Returns its durable identity immediately.",
    parameters: Type.Object({ project: Type.String(), prompt: Type.String(), session_id: Type.Optional(Type.String()), mutation_id: Type.Optional(Type.String()) }),
    async execute(_id, params) {
      const reply = await requireClient().launch({
        project: params.project,
        prompt: params.prompt,
        ...(params.session_id ? { sessionId: params.session_id } : {}),
        ...(params.mutation_id ? { mutationId: params.mutation_id } : {}),
      });
      return textResult(`Hosted Pi ${String(reply.sessionId ?? params.session_id ?? "started")}`, reply);
    },
  });
  pi.registerTool({
    name: "desk_attach",
    label: "Desk Attach",
    description: "Attach this Pi session to one Hosted Pi and follow it from the last applied log position.",
    parameters: Type.Object({ session_id: Type.String(), position: Type.Optional(Type.Integer({ minimum: 0 })) }),
    async execute(_id, params) {
      const joined = await attach(params.session_id, params.position ?? (state.sessionId === params.session_id ? state.lastApplied : undefined));
      return textResult(`Attached to ${joined.sessionId} from position ${joined.lastApplied()}.`, state);
    },
  });
  pi.registerTool({
    name: "desk_prompt",
    label: "Desk Prompt",
    description: "Send a further instruction to the attached Hosted Pi; while running this steers the current turn.",
    parameters: Type.Object({ prompt: Type.String(), mutation_id: Type.Optional(Type.String()) }),
    async execute(_id, params) {
      if (!attachment) throw new Error("attach to a Hosted Pi first");
      await attachment.prompt(params.prompt, params.mutation_id ? { mutationId: params.mutation_id } : {});
      return textResult(`Prompt delivered to ${attachment.sessionId}.`, state);
    },
  });
  pi.registerTool({
    name: "desk_cancel",
    label: "Desk Cancel",
    description: "Cancel the attached Hosted Pi's running turn without ending the session.",
    parameters: Type.Object({
      mutation_id: Type.Optional(Type.String()),
      turn_id: Type.Optional(Type.String()),
      precondition: Type.Optional(Type.String()),
    }),
    async execute(_id, params) {
      if (!attachment) throw new Error("attach to a Hosted Pi first");
      await attachment.cancel({
        ...(params.mutation_id ? { mutationId: params.mutation_id } : {}),
        ...(params.turn_id ? { turnId: params.turn_id } : {}),
        ...(params.precondition ? { precondition: params.precondition } : {}),
      });
      return textResult(`Cancelled the running turn on ${attachment.sessionId}.`, state);
    },
  });
  pi.registerTool({
    name: "desk_end",
    label: "Desk End",
    description: "End the attached Hosted Pi and release its host slot.",
    parameters: Type.Object({ mutation_id: Type.Optional(Type.String()) }),
    async execute(_id, params) {
      if (!attachment) throw new Error("attach to a Hosted Pi first");
      const ended = attachment.sessionId;
      await attachment.end(params.mutation_id ? { mutationId: params.mutation_id } : {});
      injectContext({ type: "ended", sessionId: ended });
      attachment.close();
      attachment = null;
      return textResult(`Ended Hosted Pi ${ended}.`, state);
    },
  });
    pi.registerTool({
      name: "desk_history",
      label: "Desk History",
      description: "Read a bounded page of complete Hosted Pi history from a session-log position.",
      parameters: Type.Object({ session_id: Type.String(), position: Type.Optional(Type.Integer({ minimum: 0 })) }),
      async execute(_id, params) {
        const page = await requireClient().history({ sessionId: params.session_id, position: params.position ?? 0 });
        return textResult(formatHistory(page), page);
      },
    });
  }

  const showStatus = (ctx: ExtensionContext): void => {
    const snapshot = reporterSnapshot();
    const endpoint = config !== null ? `${config.host}:${config.port}` : "not configured";
    const report = snapshot ? `${snapshot.link} · ${snapshot.sessions} session(s) · ${snapshot.events} event(s)` : "reporting inactive";
    const control = controlConfigured() ? `Console ready${state.sessionId ? ` · attached ${state.sessionId} @ ${state.lastApplied}` : ""}` : unavailable();
    ctx.ui.notify(`[open-deskos] ${snapshot?.link ?? "offline"} · ${config?.machine ?? "machine"} → ${endpoint} · ${report.replace(/^(offline|connecting|connected) · /, "")} · ${control}${snapshot?.lastError ? ` · ${snapshot.lastError}` : ""}`, snapshot?.link === "connected" ? "info" : "warning");
  };

  const chooseSession = async (ctx: ExtensionContext): Promise<string | undefined> => {
    const sessions = (await requireClient().list()).sessions;
    if (sessions.length === 0) {
      ctx.ui.notify("[open-deskos] no Hosted Pi sessions", "info");
      return undefined;
    }
    const labels = sessions.map((session) => `${session.sessionId} · ${sessionLabel(session)}`);
    const selected = await ctx.ui.select("Hosted Pi", labels);
    const index = selected === undefined ? -1 : labels.indexOf(selected);
    return index < 0 ? undefined : sessions[index]?.sessionId;
  };

  const launchInteractive = async (ctx: ExtensionContext): Promise<void> => {
    if (!ctx.hasUI) throw new Error("launch requires interactive UI or desk_start");
    const project = await ctx.ui.input("Hosted Pi project", ctx.cwd);
    if (!project) return;
    const prompt = await ctx.ui.editor("Hosted Pi prompt", "");
    if (!prompt?.trim()) return;
    const reply = await requireClient().launch({ project, prompt });
    ctx.ui.notify(`[open-deskos] started ${String(reply.sessionId ?? "Hosted Pi")}`, "info");
  };

  const openConsole = async (ctx: ExtensionContext): Promise<void> => {
    if (!controlConfigured()) {
      ctx.ui.notify(`[open-deskos] Console unavailable · ${unavailable()}`, "warning");
      return;
    }
    if (ctx.mode !== "tui") {
      const sessions = await requireClient().list();
      ctx.ui.notify(`[open-deskos] ${sessions.sessions.length} Hosted Pi session(s)`, "info");
      return;
    }
    const sessions = (await requireClient().list()).sessions;
    await ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
      let rows = sessions;
      let selected = 0;
      let log: PositionedSessionEvent[] = [];
      let historyText = "";
      const promptInput = new Input();
      let error = "";
      const receiveEvent = (entry: PositionedSessionEvent): void => {
        log = boundedContext([...log, entry]);
        tui.requestRender();
      };
      surfaceListeners.add(receiveEvent);
      const closeSurface = (): void => {
        surfaceListeners.delete(receiveEvent);
        done();
      };
      const render = (width: number): string[] => {
        const body = rows.map((session, index) => truncateToWidth(`${index === selected ? theme.fg("accent", "> ") : "  "}${session.sessionId} · ${sessionLabel(session)}`, width));
        const events = log.slice(-Math.max(3, Math.floor(tui.terminal.rows / 3))).map((entry) => truncateToWidth(`  ${eventLine(entry)}`, width));
        const historyLines = historyText ? historyText.split("\n").slice(-Math.max(3, Math.floor(tui.terminal.rows / 3))).map((line) => truncateToWidth(`  ${line}`, width)) : [];
        return [
          truncateToWidth(theme.fg("accent", theme.bold("Open DeskOS Console")), width),
          ...body,
          ...(attachment ? ["", truncateToWidth(theme.fg("success", `attached ${attachment.sessionId} @ ${attachment.lastApplied()}`), width), ...(historyLines.length ? [theme.fg("muted", "History"), ...historyLines] : events), ...promptInput.render(width)] : []),
          ...(error ? [truncateToWidth(theme.fg("error", error), width)] : []),
          truncateToWidth(theme.fg("dim", attachment ? "enter send · ctrl+h history · ctrl+x cancel · ctrl+e end · esc close" : "up/down select · enter attach · n launch · r refresh · esc close"), width),
        ];
      };
      const refresh = async (): Promise<void> => {
        try { rows = (await requireClient().list()).sessions; selected = Math.min(selected, Math.max(0, rows.length - 1)); error = ""; }
        catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
        tui.requestRender();
      };
      const handleInput = (data: string): void => {
        if (matchesKey(data, Key.escape)) { closeSurface(); return; }
        if (!attachment && matchesKey(data, Key.up)) { selected = Math.max(0, selected - 1); tui.requestRender(); return; }
        if (!attachment && matchesKey(data, Key.down)) { selected = Math.min(rows.length - 1, selected + 1); tui.requestRender(); return; }
        if (!attachment && data === "r") { void refresh(); return; }
        if (!attachment && data === "n") { closeSurface(); void launchInteractive(ctx); return; }
        if (attachment && matchesKey(data, Key.ctrl("h"))) {
          void attachment.history(Math.max(0, attachment.lastApplied() - 100)).then((page) => { historyText = formatHistory(page); error = ""; }).catch((cause) => { error = String(cause); }).finally(() => tui.requestRender());
          return;
        }
        if (attachment && matchesKey(data, Key.ctrl("x"))) { void attachment.cancel().catch((cause) => { error = String(cause); tui.requestRender(); }); return; }
        if (attachment && matchesKey(data, Key.ctrl("e"))) { void attachment.end().then(() => { attachment?.close(); attachment = null; }).catch((cause) => { error = String(cause); }).finally(() => tui.requestRender()); return; }
        if (matchesKey(data, Key.enter)) {
          const value = promptInput.getValue().trim();
          if (attachment && value) {
            historyText = "";
            promptInput.setValue("");
            void attachment.prompt(value).catch((cause) => { error = String(cause); }).finally(() => tui.requestRender());
          } else if (!attachment && rows[selected]) {
            log = [];
            void attach(rows[selected]!.sessionId).then(() => { error = ""; }).catch((cause) => { error = String(cause); }).finally(() => tui.requestRender());
          }
          return;
        }
        if (attachment) {
          promptInput.handleInput(data);
          tui.requestRender();
        }
      };
      const surface: Focusable & { render(width: number): string[]; handleInput(data: string): void; invalidate(): void } = {
        get focused() { return promptInput.focused; },
        set focused(value: boolean) { promptInput.focused = value; },
        render,
        handleInput,
        invalidate() { promptInput.invalidate(); },
      };
      return surface;
    });
  };

  pi.registerCommand("open-deskos", {
    description: "Open DeskOS menu or use console/status/attach/launch/cancel/history fast paths",
    handler: async (raw, ctx) => {
      const [action, ...rest] = raw.trim().split(/\s+/).filter(Boolean);
      if (action === "status") { showStatus(ctx); return; }
      if (action === "console") { await openConsole(ctx); return; }
      if (action === "attach") {
        const sessionId = rest[0] ?? await chooseSession(ctx);
        if (sessionId) await attach(sessionId);
        return;
      }
      if (action === "launch") { await launchInteractive(ctx); return; }
      if (action === "cancel") { if (!attachment) throw new Error("attach to a Hosted Pi first"); await attachment.cancel(); return; }
      if (action === "history") {
        const sessionId = rest[0] ?? state.sessionId ?? await chooseSession(ctx);
        if (!sessionId) return;
        const page = await requireClient().history({ sessionId, position: Number.parseInt(rest[1] ?? "0", 10) || 0 });
        ctx.ui.notify(`[open-deskos] ${formatHistory(page)}`, "info");
        return;
      }
      if (ctx.mode !== "tui") {
        showStatus(ctx);
        return;
      }
      const rows: SelectItem[] = [
        { value: "console", label: "Console", description: controlConfigured() ? "List, launch, attach, and drive Hosted Pi" : unavailable() },
        { value: "status", label: "Link status", description: config !== null ? `${config.machine} → ${config.host}:${config.port}` : configHint },
        { value: "attach", label: "Attach", description: controlConfigured() ? "Attach to a Hosted Pi" : unavailable() },
        { value: "launch", label: "Launch", description: controlConfigured() ? "Start a Hosted Pi" : unavailable() },
        { value: "cancel", label: "Cancel", description: attachment ? `Cancel ${attachment.sessionId}` : "Attach first" },
        { value: "history", label: "History", description: controlConfigured() ? "Read complete paged history" : unavailable() },
      ];
      const selected = await ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
        const container = new Container();
        container.addChild(new Text(theme.fg("accent", theme.bold("Open DeskOS")), 1, 0));
        const list = new SelectList(rows, rows.length, {
          selectedPrefix: (text) => theme.fg("accent", text),
          selectedText: (text) => theme.fg("accent", text),
          description: (text) => theme.fg("muted", text),
          scrollInfo: (text) => theme.fg("dim", text),
          noMatch: (text) => theme.fg("warning", text),
        });
        list.onSelect = (item) => done(item.value);
        list.onCancel = () => done(null);
        container.addChild(list);
        return { render: (width) => container.render(width), invalidate: () => container.invalidate(), handleInput: (data) => { list.handleInput(data); tui.requestRender(); } };
      });
      if (selected === "console") await openConsole(ctx);
      else if (selected === "status") showStatus(ctx);
      else if (selected === "attach") { const sessionId = await chooseSession(ctx); if (sessionId) await attach(sessionId); }
      else if (selected === "launch") await launchInteractive(ctx);
      else if (selected === "cancel" && attachment) await attachment.cancel();
      else if (selected === "history") { const sessionId = state.sessionId ?? await chooseSession(ctx); if (sessionId) ctx.ui.notify(formatHistory(await requireClient().history({ sessionId, position: 0 })), "info"); }
    },
  });
}

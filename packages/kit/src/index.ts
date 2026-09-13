/**
 * Shared runtime helpers for FradSer pi packages.
 *
 * Everything lives in this single file on purpose: a zero-internal-import
 * module resolves identically under Node's native type stripping, tsx, pi's
 * extension loader, and tsc with any moduleResolution — no extensionless
 * specifier or allowImportingTsExtensions edge cases.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { createHash } from "node:crypto";
import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { fileURLToPath } from "node:url";

// ── TUI ─────────────────────────────────────────────────────────────
// Spinner cadence matching pi's native " ⠋ Working..." loader and the
// accent/muted/dim style language used by overlay and console UIs
// (packages/btw is the canonical layout).

/** Braille spinner frames, identical to pi's native loader row. */
export const PI_SPINNER_FRAMES: string[] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/** Spinner frame interval matching pi's native loader cadence. */
export const PI_SPINNER_INTERVAL_MS = 120;

/** Minimal structural view of pi's TUI theme: only fg() is needed. */
export interface PiThemeLike {
  fg(color: string, text: string): string;
}

/** Normalize a task prompt into the compact name shown in the TUI. */
export function formatAgentTaskName(prompt: string, fallback: string): string {
  return prompt.replace(/\s+/g, " ").trim() || fallback;
}

/** Stable, bounded sub-agent identity derived from one tool execution id. */
export function subagentDisplayName(prefix: string, toolCallId: string): string {
  const normalized = prefix.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "") || "agent";
  const suffix = createHash("sha256").update(toolCallId).digest("hex").slice(0, 12);
  return `${normalized.slice(0, 51)}-${suffix}`;
}

export interface PackageAgentRunOptions {
  /** File URL for the package root directory, usually new URL("../", import.meta.url).href. */
  packageRootUrl: string;
  /** Package-relative resource path, for example agents/researcher.md. */
  resourcePath: string;
  namePrefix: string;
  toolCallId: string;
  request: string;
  requestLabel?: string;
}

export interface PackageAgentRun {
  name: string;
  displayPath: string;
  prompt: string;
}

/** Load a package-owned agent prompt and bind it to one stable tool execution. */
export function createPackageAgentRun(options: PackageAgentRunOptions): PackageAgentRun {
  if (/^[a-z][a-z0-9+.-]*:/i.test(options.resourcePath) || path.isAbsolute(options.resourcePath)) {
    throw new Error("Package agent resource path must be package-relative.");
  }
  const rootUrl = new URL(options.packageRootUrl);
  if (rootUrl.protocol !== "file:") throw new Error("Package agent roots must use file URLs.");
  const root = fs.realpathSync(fileURLToPath(rootUrl));
  const candidate = path.resolve(root, options.resourcePath);
  const relative = path.relative(root, candidate);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Package agent resource must stay inside its package root.");
  }
  const resource = fs.realpathSync(candidate);
  const canonicalRelative = path.relative(root, resource);
  if (canonicalRelative.startsWith("..") || path.isAbsolute(canonicalRelative)) {
    throw new Error("Package agent resource symlink escapes its package root.");
  }
  const agentPrompt = fs.readFileSync(resource, "utf8").trim();
  const displayPath = canonicalRelative.split(path.sep).join("/");
  if (!agentPrompt) throw new Error(`Package agent resource is empty: ${displayPath}`);
  const requestLabel = options.requestLabel?.trim() || "User request";
  return {
    name: subagentDisplayName(options.namePrefix, options.toolCallId),
    displayPath,
    prompt: `${agentPrompt}\n\n${requestLabel}:\n${options.request}`,
  };
}

/** Lifecycle row kind shared by background and coordination tools. */
export type ToolLifecycleKind = "started" | "event";

/** Shared lifecycle row specification. Consumers adapt it to Pi's TUI types. */
export interface ToolLifecycleSpec {
  kind: ToolLifecycleKind;
  tool: string;
  subject: string;
  /** Optional semantic verb such as `created`, `listed`, `gathered`, or `to @name`. */
  label?: string;
  /** Always-visible secondary lines, shown both collapsed and expanded. */
  summary?: readonly string[];
  details?: readonly string[];
  /** Default bounds expanded details to 50 lines; opt in only when every
   * line is required for a user-visible readback. */
  detailLimit?: number | "all";
}

/** Build the common one-line lifecycle title for a tool result.
 * A missing label omits the middle segment entirely: the generic kind word
 * ("event"/"started") is layout metadata, not prose worth showing. */
export function formatToolLifecycleTitle(spec: ToolLifecycleSpec): string {
  const tag = `[${safeDisplayText(spec.tool)}]`;
  if (spec.label === undefined) return `${tag} ${safeDisplayText(spec.subject)}`;
  return `${tag} ${safeDisplayText(spec.label)} · ${safeDisplayText(spec.subject)}`;
}

/** Build a started-row specification. */
export function startedToolLifecycle(
  tool: string,
  subject: string,
  options: { label?: string } = {},
): ToolLifecycleSpec {
  return { kind: "started", tool, subject, label: options.label };
}

/** Build an event-row specification with optional semantic verb and expandable details. */
export function eventToolLifecycle(
  tool: string,
  subject: string,
  options: { label?: string; summary?: readonly string[]; details?: readonly string[]; detailLimit?: number | "all" } = {},
): ToolLifecycleSpec {
  return {
    kind: "event",
    tool,
    subject,
    label: options.label,
    summary: options.summary,
    details: options.details,
    detailLimit: options.detailLimit,
  };
}

/** Return lifecycle details with a safe default bound. An explicit `all` is
 * reserved for user-requested readbacks that would otherwise lose data. */
export function formatToolLifecycleDetails(spec: ToolLifecycleSpec, maxLines = 50): string[] {
  const limit = spec.detailLimit === "all"
    ? undefined
    : Math.max(0, typeof spec.detailLimit === "number" ? spec.detailLimit : maxLines);
  const details = spec.details ?? [];
  return (limit === undefined ? details : details.slice(0, limit)).map((line) => safeDisplayText(line));
}

/** Return the first safe non-empty line from a failed tool result. */
export function formatToolErrorLine(value: unknown, fallback = "Tool failed."): string {
  const line = safeDisplayText(value).split("\n").find((entry) => entry.trim());
  return line?.trim() || fallback;
}

/** Minimal structural view of pi's TUI theme for lifecycle rendering. */
export interface ToolLifecycleTheme {
  fg(color: string, text: string): string;
  bg(color: string, text: string): string;
  bold(text: string): string;
}

/** Stable per-teammate accent palette for @name segments (report-row language). */
const AGENT_COLORS = ["success", "warning", "error", "mdLink"] as const;

/** Deterministic accent color key for a teammate name. */
export function agentColor(name: string): (typeof AGENT_COLORS)[number] {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

export interface ToolLifecycleRenderOptions {
  /** Full band width; content truncates to the inset width inside the band. */
  width: number;
  expanded?: boolean;
  /** Host-resolved expand-key text, e.g. keyHint("app.tools.expand", "to expand"). */
  expandHint?: string;
  /** Whether the row has expandable result metadata even when its body is empty. */
  expandable?: boolean;
  theme: ToolLifecycleTheme;
  /** ANSI-aware width fit, e.g. pi-tui's truncateToWidth. */
  fit: (text: string, width: number, ellipsis?: string, pad?: boolean) => string;
  /** Visible terminal width, e.g. pi-tui's visibleWidth. */
  visibleWidth: (text: string) => number;
  /** Optional ANSI-aware detail wrapper, e.g. pi-tui's wrapTextWithAnsi. */
  wrapDetail?: (text: string, width: number) => string[];
}

/** Shared band geometry: every lifecycle row block renders in this style. */
const BAND_PAD_X = 1;
const BAND_PAD_Y = 1;

/** pi's theme.bg emits `<bg-ansi><text>\x1b[49m`; recover the leading bg-ansi alone. */
function bandBgPrefix(theme: ToolLifecycleTheme): string {
  const painted = theme.bg("customMessageBg", "");
  return painted.slice(0, -"\x1b[49m".length);
}

function paintBand(
  rows: string[],
  options: Pick<ToolLifecycleRenderOptions, "width" | "theme" | "fit">,
): string[] {
  const bg = (line: string) => options.theme.bg("customMessageBg", line);
  const padRow = () => bg(options.fit("", options.width, "", true));
  const prefix = bandBgPrefix(options.theme);
  return [
    ...Array.from({ length: BAND_PAD_Y }, padRow),
    // Truncating styled rows can inject a full SGR reset (\x1b[0m) before the
    // ellipsis, which also clears the band background for everything after it.
    // Re-apply the background immediately after every reset so the whole row —
    // ellipsis and padding included — stays on the uniform band color.
    ...rows.map((row) =>
      bg(options.fit(`${" ".repeat(BAND_PAD_X)}${row}`, options.width, "", true).replaceAll("\x1b[0m", `\x1b[0m${prefix}`)),
    ),
    ...Array.from({ length: BAND_PAD_Y }, padRow),
  ];
}

/** Compose the report-row text language: label-colored prefix, colored @names, plain rest. */
function styleSubject(subject: string, options: ToolLifecycleRenderOptions): string {
  const { theme } = options;
  return subject.replace(/@[\w][\w.-]*/g, (token) => theme.fg(agentColor(token.slice(1)), token));
}

/**
 * Render one lifecycle row block: the started/event row and, when expanded,
 * its bounded detail lines, painted as a full-width customMessageBg band with
 * a blank band row above and below — the shared report-row visual language:
 * label-colored `[tool] label ·` prefix, per-teammate colored @names, plain
 * subject text, dim expand hint. pi-kit owns the styling so extensions cannot
 * drift.
 */
export function renderToolLifecycle(
  spec: ToolLifecycleSpec,
  options: ToolLifecycleRenderOptions,
): string[] {
  if (options.width <= 0) return [];
  const { theme, fit } = options;
  const contentWidth = Math.max(1, options.width - 2 * BAND_PAD_X);
  const tag = `[${safeDisplayText(spec.tool)}]`;
  const label = spec.label === undefined ? "" : ` ${safeDisplayText(spec.label)} ·`;
  const head = theme.fg("customMessageLabel", theme.bold(`${tag}${label}`));
  const subjectText = safeDisplayText(spec.subject);
  const summary = (spec.summary ?? []).map((line) => safeDisplayText(line));
  const details = formatToolLifecycleDetails(spec);
  // Structured metadata can make a result expandable even when its visible
  // content body is empty (for example teammate_spawn's { started }).
  const expandable = options.expandable ?? details.length > 0;
  // Any lifecycle row with details can expand. Started rows remain compact
  // until the host toggles them with its standard expand key.
  const hint = expandable && !options.expanded
    ? theme.fg("dim", ` · ${options.expandHint ?? "to expand"}`)
    : "";
  const title = `${head} ${styleSubject(subjectText, options)}`;
  const summaryRows = summary.map((line) => fit(theme.fg("customMessageText", line), contentWidth));
  const rows = options.expanded
    ? [
        fit(title, contentWidth),
        ...summaryRows,
        ...details.flatMap((detail) => {
          const wrapped = options.wrapDetail
            ? options.wrapDetail(detail, contentWidth)
            : [detail];
          return wrapped.map((line) => fit(theme.fg("customMessageText", line), contentWidth));
        }),
      ]
    : [
        hint
          ? options.visibleWidth(hint) >= contentWidth
            ? fit(hint, contentWidth)
            : `${fit(title, Math.max(0, contentWidth - options.visibleWidth(hint)))}${hint}`
          : fit(title, contentWidth),
        ...summaryRows,
      ];
  return paintBand(rows, options);
}

/** One collapsed teammate-message row inside the shared band. */
export interface AgentMessageRowSpec {
  direction: "from" | "to";
  teammate: string;
  count?: number;
}

export interface AgentMessageBandOptions {
  theme: ToolLifecycleTheme;
  /** ANSI-aware width fit, e.g. pi-tui's truncateToWidth. */
  fit: (text: string, width: number, ellipsis?: string, pad?: boolean) => string;
  /** Host-resolved expand-key text, e.g. keyHint("app.tools.expand", "to expand"). */
  expandHint?: string;
}

/**
 * Render collapsed teammate-message rows (`[message] from @name · ctrl+o to
 * expand`) in the same shared band as lifecycle tool rows. Returns a render
 * component because message renderers do not know the transcript width until
 * pi calls render().
 */
export function renderAgentMessageBand(
  rows: readonly AgentMessageRowSpec[],
  options: AgentMessageBandOptions,
): { render: (width: number) => string[]; invalidate: () => void } {
  return {
    render: (width) => {
      if (width <= 0) return [];
      const { theme, fit } = options;
      const contentWidth = Math.max(1, width - 2 * BAND_PAD_X);
      const hint = theme.fg("dim", ` · ${options.expandHint ?? "to expand"}`);
      const content = rows.map(({ direction, teammate, count }) => {
        const label = count === 1 || count === undefined ? "message" : `${count} messages`;
        const prefix = theme.fg("customMessageLabel", theme.bold(`[${label}] ${direction} `));
        const name = theme.fg(agentColor(teammate), `@${teammate}`);
        return fit(`${prefix}${name}${hint}`, contentWidth);
      });
      return paintBand(content, { ...options, width });
    },
    invalidate: () => {},
  };
}

/** A structural custom-message component accepted by Pi without importing Pi runtime types. */
export interface PiMessageComponent {
  render(width: number): string[];
  invalidate(): void;
  handleMouse?(event: unknown): unknown;
  setExpanded?(expanded: boolean): void;
}

/** Structural message input used by custom transcript renderers. */
export interface PiCustomMessageLike {
  content: unknown;
  details?: unknown;
}

/** Options for wrapping a lifecycle rendering callback in a host ToolExecutionComponent. */
export interface ToolExecutionWrapperOptions {
  hostComponent?: any;
  toolName?: string;
  toolCallId?: string;
  expanded?: boolean;
  ui?: any;
  cwd?: string;
  emptyCall?: () => any;
}

/**
 * Wrap a lifecycle component or render callback inside a host ToolExecutionComponent.
 * When hostComponent is supplied, this equips the custom message with native
 * mouse click toggling and self-render container layout.
 */
export function createToolExecutionWrapper<C extends PiMessageComponent>(
  render: (options: { expanded?: boolean }, theme?: ToolLifecycleTheme) => C,
  options: ToolExecutionWrapperOptions = {},
  theme?: ToolLifecycleTheme,
): C {
  const {
    hostComponent,
    toolName = "message",
    toolCallId = "lifecycle_message",
    expanded = false,
    ui = { requestRender: () => {} },
    cwd = process.cwd(),
  } = options;

  if (!hostComponent) {
    return render({ expanded }, theme);
  }

  class LifecycleToolExecutionWrapper extends (hostComponent as any) {
    constructor(...args: any[]) {
      super(...args);
    }
    render(width: number): string[] {
      const lines = super.render(width);
      return lines.length > 0 && lines[0] === "" ? lines.slice(1) : lines;
    }
    handleMouse(event: any): any {
      if (event.type === "click" && event.button === "left") {
        this.setExpanded(!this.expanded);
        if (typeof this.updateDisplay === "function") {
          this.updateDisplay();
        }
        if (this.ui?.requestRender) {
          this.ui.requestRender();
        }
        return { handled: true };
      }
      if (!this.hasRendererDefinition || !this.hasRendererDefinition() || this.getRenderShell?.() !== "self") {
        return super.handleMouse?.(event);
      }
      if (event.y < 0 || (this.selfRenderHeight !== undefined && event.y >= this.selfRenderHeight)) {
        return undefined;
      }
      return this.selfRenderContainer?.handleMouse
        ? this.selfRenderContainer.handleMouse({
            ...event,
            y: event.y,
            height: this.selfRenderHeight,
          })
        : super.handleMouse?.(event);
    }
  }

  const toolDefinition = {
    renderShell: "self",
    renderCall: options.emptyCall ?? (() => ({ render: () => [], invalidate: () => {} })),
    renderResult: (_result: unknown, opt: { expanded?: boolean }, toolTheme: ToolLifecycleTheme) =>
      render(opt, theme ?? toolTheme),
  };

  const comp = new LifecycleToolExecutionWrapper(toolName, toolCallId, {}, {}, toolDefinition, ui, cwd);
  comp.updateResult?.({ content: [{ type: "text", text: "details" }], isError: false });
  comp.setExpanded?.(expanded);
  return comp as unknown as C;
}

/** Shared host-independent renderer inputs for custom messages and native tools. */
export interface ToolLifecycleRendererOptions<T> {
  createSpec: (value: T, text: string, details: string[]) => ToolLifecycleSpec;
  expandHint?: string;
  fit: ToolLifecycleRenderOptions["fit"];
  visibleWidth: ToolLifecycleRenderOptions["visibleWidth"];
  wrapDetail?: ToolLifecycleRenderOptions["wrapDetail"];
  hostComponent?: any;
  emptyCall?: () => any;
  ui?: any;
  cwd?: string;
}

/**
 * Build a Pi custom-message renderer around the standard lifecycle band.
 * Pi supplies the width, expansion state, and theme at render time; keeping
 * those parameters structural lets extension packages retain their own Pi API
 * version while every row still follows pi-kit's contract.
 */
export function createToolLifecycleMessageRenderer(
  options: ToolLifecycleRendererOptions<PiCustomMessageLike>,
): (
  message: PiCustomMessageLike,
  state: { expanded?: boolean },
  theme: ToolLifecycleTheme,
) => PiMessageComponent {
  return (message, state, theme) => {
    const text = extractTextContent(message.content);
    const details = textLines(message.details === undefined ? text : message.details);
    const spec = options.createSpec(message, text, details);
    const renderContent = (contentState: { expanded?: boolean }, currentTheme: ToolLifecycleTheme = theme) =>
      lifecycleComponent(spec, {
        expanded: contentState.expanded,
        expandable: message.details !== undefined || details.length > 0,
        expandHint: options.expandHint,
        theme: currentTheme,
        fit: options.fit,
        visibleWidth: options.visibleWidth,
        wrapDetail: options.wrapDetail,
      });

    if (options.hostComponent) {
      return createToolExecutionWrapper(
        (opt, t) => renderContent(opt, t),
        {
          hostComponent: options.hostComponent,
          toolName: spec.tool,
          toolCallId: "msg_lifecycle",
          expanded: state.expanded,
          ui: options.ui,
          cwd: options.cwd,
          emptyCall: options.emptyCall,
        },
        theme,
      );
    }

    return renderContent(state, theme);
  };
}

/**
 * Build a native-tool result renderer. Hosts retain control of their native
 * error component while successful results always use the lifecycle band.
 */
export function createStaticToolLifecycleMessageRenderer<T extends PiCustomMessageLike>(
  options: Omit<ToolLifecycleRendererOptions<T>, "createSpec"> & {
    createSpec: (message: T) => ToolLifecycleSpec;
  },
): (
  message: T,
  state: { expanded?: boolean },
  theme: ToolLifecycleTheme,
) => PiMessageComponent {
  return (message, state, theme) => {
    const renderContent = (contentState: { expanded?: boolean }, currentTheme: ToolLifecycleTheme = theme) => ({
      render: (width: number) => renderToolLifecycle(options.createSpec(message), {
        expanded: contentState.expanded,
        expandHint: options.expandHint,
        theme: currentTheme,
        fit: options.fit,
        visibleWidth: options.visibleWidth,
        wrapDetail: options.wrapDetail,
        width,
      }),
      invalidate: () => {},
    });

    if (options.hostComponent) {
      return createToolExecutionWrapper(
        (opt, t) => renderContent(opt, t),
        {
          hostComponent: options.hostComponent,
          toolName: options.createSpec(message).tool,
          toolCallId: "msg_lifecycle",
          expanded: state.expanded,
          ui: options.ui,
          cwd: options.cwd,
          emptyCall: options.emptyCall,
        },
        theme,
      );
    }

    return renderContent(state, theme);
  };
}

export function createToolLifecycleResultRenderer<T extends PiCustomMessageLike, E>(
  options: ToolLifecycleRendererOptions<T> & {
    renderError: (line: string, theme: ToolLifecycleTheme) => E;
  },
): (
  result: T,
  state: { expanded?: boolean },
  theme: ToolLifecycleTheme,
  context: { isError?: boolean },
) => PiMessageComponent | E {
  return (result, state, theme, context) => {
    const text = extractTextContent(result.content);
    if (context.isError) return options.renderError(formatToolErrorLine(text), theme);
    const details = textLines(text);
    const spec = options.createSpec(result, text, details);
    return lifecycleComponent(spec, {
      expanded: state.expanded,
      expandable: result.details !== undefined || details.length > 0,
      expandHint: options.expandHint,
      theme,
      fit: options.fit,
      visibleWidth: options.visibleWidth,
      wrapDetail: options.wrapDetail,
    });
  };
}

export function createStaticToolLifecycleResultRenderer<T extends PiCustomMessageLike, E>(
  options: Omit<ToolLifecycleRendererOptions<T>, "createSpec"> & {
    createSpec: (result: T) => ToolLifecycleSpec;
    renderError: (line: string, theme: ToolLifecycleTheme) => E;
  },
): (
  result: T,
  state: { expanded?: boolean },
  theme: ToolLifecycleTheme,
  context: { isError?: boolean },
) => PiMessageComponent | E {
  return (result, state, theme, context) => {
    const text = extractTextContent(result.content);
    if (context.isError) return options.renderError(formatToolErrorLine(text), theme);
    return lifecycleComponent(options.createSpec(result), {
      expanded: state.expanded,
      expandHint: options.expandHint,
      theme,
      fit: options.fit,
      visibleWidth: options.visibleWidth,
      wrapDetail: options.wrapDetail,
    });
  };
}

function lifecycleComponent(
  spec: ToolLifecycleSpec,
  options: Omit<ToolLifecycleRenderOptions, "width">,
): PiMessageComponent {
  return {
    render: (width) => renderToolLifecycle(spec, { width, ...options }),
    invalidate: () => {},
  };
}

function textLines(value: unknown): string[] {
  return extractTextContent(value).split("\n").filter((line) => line.trim());
}

/** Minimal structural `ctx.ui` surface for notifications. */
export interface PiNotificationUi {
  notify(message: string, level?: "info" | "warning" | "error"): void;
}

/** Sanitize and forward a notification through Pi's native UI. */
export function notifyPi(
  ui: PiNotificationUi,
  message: unknown,
  level: "info" | "warning" | "error" = "info",
): void {
  ui.notify(safeDisplayText(message), level);
}

/** Minimal structural UI surface for transient extension status. */
export interface PiStatusUi {
  setStatus(key: string, value: string | undefined): void;
}

/** Sanitize and set one extension-owned transient status entry. */
export function setPiStatus(ui: PiStatusUi, key: unknown, value: unknown): void {
  ui.setStatus(safeDisplayText(key), safeDisplayText(value));
}

/** Clear one extension-owned transient status entry. */
export function clearPiStatus(ui: PiStatusUi, key: unknown): void {
  ui.setStatus(safeDisplayText(key), undefined);
}

/** Minimal structural UI surface for Pi's inline working indicator. */
export interface PiWorkingIndicatorUi {
  setWorkingIndicator(options?: { frames: string[]; intervalMs: number }): void;
}

/** Start Pi's inline working indicator with the shared native cadence. */
export function startPiWorkingIndicator(ui: PiWorkingIndicatorUi): void {
  ui.setWorkingIndicator({ frames: PI_SPINNER_FRAMES, intervalMs: PI_SPINNER_INTERVAL_MS });
}

/** Restore Pi's native inline working indicator. */
export function clearPiWorkingIndicator(ui: PiWorkingIndicatorUi): void {
  ui.setWorkingIndicator();
}

/**
 * Type-safe read of an optional field from a tool result's untrusted details
 * record. Returns undefined when details is missing or the key is absent.
 */
export function detailField<T>(details: unknown, key: string): T | undefined {
  if (!details || typeof details !== "object" || Array.isArray(details)) return undefined;
  const value = (details as Record<string, unknown>)[key];
  return value === undefined ? undefined : (value as T);
}

/**
 * Strips ANSI/OSC escape sequences and control characters from untrusted
 * display text (registry values, process output) so it cannot inject
 * terminal commands or corrupt TUI layout.
 */
export function safeDisplayText(value: unknown): string {
  return String(value)
    .replace(/\u001b(?:\[[0-?]*[ -/]*[@-~]|\][^\u0007]*(?:\u0007|\u001b\\)|[@-_])/g, "")
    .replace(/(?:\u009b[0-?]*[ -/]*[@-~]|\u009d[^\u0007]*(?:\u0007|\u009c)|\u0090[^\u0007]*(?:\u0007|\u009c)|\u0098[^\u0007]*(?:\u0007|\u009c)|\u009e[^\u0007]*(?:\u0007|\u009c)|\u009f[^\u0007]*(?:\u0007|\u009c))/g, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u0080-\u009f]/g, "");
}

/** Format the colored-prefix portion of an incoming or outgoing message label. */
export function formatAgentMessagePrefix(direction: "from" | "to", count = 1): string {
  const label = count === 1 ? "message" : `${count} messages`;
  return `[${label}] ${direction} `;
}

/** Style callbacks shared by overlay/console UIs (the btw style language). */
export interface PiThemeStyle {
  accent: (s: string) => string;
  muted: (s: string) => string;
  dim: (s: string) => string;
  border: (s: string) => string;
  success: (s: string) => string;
  error: (s: string) => string;
  fg: (color: string, text: string) => string;
}

/** Adapt a pi theme to the shared style-callback language. */
export function createPiThemeStyle(theme: PiThemeLike): PiThemeStyle {
  return {
    accent: (s) => theme.fg("accent", s),
    muted: (s) => theme.fg("muted", s),
    dim: (s) => theme.fg("dim", s),
    border: (s) => theme.fg("border", s),
    success: (s) => theme.fg("success", s),
    error: (s) => theme.fg("error", s),
    fg: (color, s) => theme.fg(color, s),
  };
}

/** The small style subset needed for the standard overlay/console frame. */
export interface PiPanelStyle {
  accent(text: string): string;
  dim(text: string): string;
  border(text: string): string;
}

/** Inputs for the standard bordered Pi overlay/console panel. */
export interface PiPanelOptions {
  width: number;
  style: PiPanelStyle;
  /** ANSI-aware width fit, e.g. pi-tui's truncateToWidth. */
  fit: (text: string, width: number, ellipsis?: string, pad?: boolean) => string;
  title: string;
  body: readonly string[];
  footer: string;
}

/**
 * Render Pi's shared panel language: border, accented header, two-space body
 * inset, dim footer, border. Interactive overlays own their input and scroll
 * state; this helper owns the stable geometry so they cannot drift.
 */
export function renderPiPanel(options: PiPanelOptions): string[] {
  if (options.width <= 0) return [];
  const { width, style, fit } = options;
  const row = (text: string) => fit(`  ${text}`, width, "", true);
  const border = style.border("─".repeat(Math.max(1, width)));
  return [
    border,
    row(style.accent(options.title)),
    ...options.body.map(row),
    row(style.dim(options.footer)),
    border,
  ];
}

/** Render a passive widget row aligned with Pi's native leading-space rows.
 * leadingSpaces defaults to one; pass zero for flush-left rows. */
export function renderPiWidgetRow(
  content: string,
  width: number,
  fit: (text: string, width: number, ellipsis?: string, pad?: boolean) => string,
  leadingSpaces = 1,
): string {
  return width <= 0 ? "" : fit(`${" ".repeat(Math.max(0, leadingSpaces))}${content}`, width, "", true);
}

// ── Overlay layout helpers ──────────────────────────────────────────
// Shared by btw, plan-mode, and other overlay UIs.

/**
 * Compute the maximum body height for an overlay panel.
 * Caps at the given fraction of terminal rows (default 40%).
 */
export function maxBodyHeight(rows: number, fraction = 0.4): number {
  return Math.max(3, Math.floor(rows * fraction));
}

/**
 * Build Markdown theme callbacks from the shared style language.
 * Returns an object matching pi-tui's MarkdownTheme shape.
 */
export function buildMarkdownThemeCallbacks(style: PiThemeStyle): {
  heading: (t: string) => string;
  link: (t: string) => string;
  linkUrl: (t: string) => string;
  code: (t: string) => string;
  codeBlock: (t: string) => string;
  codeBlockBorder: (t: string) => string;
  quote: (t: string) => string;
  quoteBorder: (t: string) => string;
  hr: () => string;
  listBullet: (t: string) => string;
  bold: (t: string) => string;
  italic: (t: string) => string;
  strikethrough: (t: string) => string;
  underline: (t: string) => string;
} {
  return {
    heading: (t) => style.accent(t),
    link: (t) => style.accent(t),
    linkUrl: (t) => style.dim(t),
    code: (t) => style.accent(t),
    codeBlock: (t) => t,
    codeBlockBorder: (t) => style.border(t),
    quote: (t) => style.muted(t),
    quoteBorder: (t) => style.border(t),
    hr: () => "__OVERLAY_SEPARATOR__",
    listBullet: (t) => style.accent(t),
    bold: (t) => style.accent(t),
    italic: (t) => style.muted(t),
    strikethrough: (t) => style.dim(t),
    underline: (t) => t,
  };
}

/**
 * Compute scroll window bounds for a scrollable panel.
 * Returns the slice of lines to display.
 */
export function computeScrollWindow(
  lines: string[],
  scroll: number,
  maxBody: number,
): { start: number; end: number; clampedScroll: number } {
  const viewport = Math.min(lines.length, maxBody);
  const max = Math.max(0, lines.length - viewport);
  const clampedScroll = Math.min(scroll, max);
  return { start: clampedScroll, end: clampedScroll + viewport, clampedScroll };
}

/** Resolve a directory to its filesystem identity. Existing paths use realpath;
 * missing paths retain their absolute spelling so callers can still derive a
 * stable identity before the directory is created. */
function canonicalDirectoryPath(candidate: string): string {
  const absolute = path.resolve(candidate);
  try {
    return fs.realpathSync(absolute);
  } catch (error) {
    if (error && typeof error === "object" && (error as NodeJS.ErrnoException).code === "ENOENT") {
      return absolute;
    }
    throw error;
  }
}

/** Hash a canonical directory path for use as a session identity. */
export function getDirectorySessionKey(cwd: string): string {
  return createHash("sha256").update(canonicalDirectoryPath(cwd)).digest("hex");
}

/** Compare directory identity after resolving existing symlinks. */
export function isSameDirectory(left: string, right: string): boolean {
  return canonicalDirectoryPath(left) === canonicalDirectoryPath(right);
}

// ── Worker process helpers ──────────────────────────────────────────
// Shared by plan-mode, agent-teams, and btw for spawning child Pi processes.

/** Result of resolving how to launch a Pi CLI process. */
export interface PiCliResolution {
  /** Command to execute — either a runtime (node/bun) or a `pi` binary. */
  command: string;
  /** Leading args: the CLI script path when running via a runtime, else empty. */
  args: string[];
}

/** Usage stats from a Pi worker run. */
export interface PiWorkerUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

/** Result of a Pi worker run. */
export interface PiWorkerResult {
  text: string;
  usage?: PiWorkerUsage;
  exitCode: number;
  stderr: string;
  /** True when the caller's signal was already or became aborted. */
  cancelled?: boolean;
}

/** Live state extracted from a spawned worker's JSON-mode output. */
export interface PiWorkerProgressUpdate {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  /** Authoritative latest worker activity across tools, thinking, and text. */
  activity?: string;
  turns: number;
}

/** Options for running a Pi worker. */
export interface RunPiWorkerOptions {
  /** Prompt to send to the worker. */
  prompt: string;
  /** Working directory for the child. */
  cwd: string;
  /** Tools to allow (comma-separated or array). */
  tools?: string | string[];
  /** Model to use (e.g. "anthropic/claude-3-5-sonnet"). */
  model?: string;
  /** Abort signal to cancel the worker. */
  signal?: AbortSignal;
  /** Additional environment variables. */
  env?: Record<string, string | undefined>;
  /** Disable extension, skill, prompt-template, context-file, and theme discovery. */
  minimal?: boolean;
  /** Additional CLI arguments. */
  extraArgs?: string[];
  /** Called when JSON-mode output reveals live worker activity. */
  onUpdate?: (update: PiWorkerProgressUpdate) => void;
}

/** Bounded grace period before a cancellation escalates from SIGTERM to SIGKILL. */
export const DEFAULT_TERMINATION_GRACE_MS = 5_000;

/** Maximum stdout bytes retained from one one-shot worker. */
export const PI_WORKER_STDOUT_LIMIT_BYTES = 16 * 1024 * 1024;

/** Maximum stderr bytes retained from one one-shot worker. */
export const PI_WORKER_STDERR_LIMIT_BYTES = 8 * 1024 * 1024;

/** Maximum bytes in one JSONL stream line from a one-shot worker. Eight MiB
 * leaves room for the coding agent's normal 4.5 MiB inline image payload plus
 * its JSON envelope. */
export const PI_WORKER_JSONL_LINE_LIMIT_BYTES = 8 * 1024 * 1024;

const processGroupChildren = new WeakSet<ChildProcess>();
const closedChildren = new WeakSet<ChildProcess>();

/** Spawn a Pi child in its own process group where the platform supports it. */
export function spawnPiChild(command: string, args: string[], options: SpawnOptions = {}): ChildProcess {
  const child = spawn(command, args, {
    ...options,
    detached: process.platform === "win32" ? false : true,
  });
  if (process.platform !== "win32") processGroupChildren.add(child);
  child.once("close", () => closedChildren.add(child));
  return child;
}

/**
 * Resolve how to launch a Pi CLI process.
 *
 * Resolution order:
 *   1. `process.argv[1]` — the current Pi process entry, verified against the
 *      exact coding-agent package manifest.
 *   2. The installed coding-agent package's `dist/cli.js`.
 *   3. A `pi` binary on PATH (best effort).
 */
export function resolvePiCli(): PiCliResolution {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }

  const installed = resolveInstalledPiCli();
  if (installed) return installed;

  return { command: "pi", args: [] };
}

function isPiPackageScript(filePath: string): boolean {
  try {
    const resolved = fs.realpathSync(filePath);
    if (!/\.(mjs|cjs|js)$/.test(resolved)) return false;
    let dir = path.dirname(resolved);
    while (dir !== path.dirname(dir)) {
      const pkgPath = path.join(dir, "package.json");
      if (fs.existsSync(pkgPath)) {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8")) as { name?: unknown };
        return pkg.name === "@earendil-works/pi-coding-agent";
      }
      dir = path.dirname(dir);
    }
  } catch {
    // Unreadable paths are simply not candidates.
  }
  return false;
}

function resolveInstalledPiCli(): PiCliResolution | undefined {
  try {
    const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
    const packageRoot = path.dirname(path.dirname(entry));
    const cliPath = path.join(packageRoot, "dist", "cli.js");
    if (fs.existsSync(cliPath)) return { command: process.execPath, args: [cliPath] };
  } catch {
    // Package resolution is best-effort; fall through to PATH.
  }
  return undefined;
}

/**
 * Run a Pi worker child process and return the result.
 *
 * Spawns `pi --print --mode json --no-session` with the given prompt and tools.
 * Parses the JSONL output to extract the final text and usage stats.
 */
export async function runPiWorker(options: RunPiWorkerOptions): Promise<PiWorkerResult> {
  const { prompt, cwd, tools, model, signal, env, minimal, extraArgs, onUpdate } = options;
  if (signal?.aborted) {
    return {
      text: "",
      exitCode: 1,
      stderr: "Pi worker cancelled before start.",
      cancelled: true,
    };
  }
  const cli = resolvePiCli();

  const args = [...cli.args, "--print", "--mode", "json", "--no-session"];
  if (minimal) args.push("-ne", "-ns", "-np", "-nc", "--no-themes");
  if (model) args.push("--model", model);
  if (tools) {
    const toolStr = Array.isArray(tools) ? tools.join(",") : tools;
    args.push("--tools", toolStr);
  }
  if (extraArgs) args.push(...extraArgs);
  args.push(prompt);

  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let stdoutBuffer = "";
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let failureReason: string | undefined;
    let cancelled = false;
    const progress = createPiWorkerProgress();
    const emitProgress = () => onUpdate?.({
      text: progress.text,
      activeTool: progress.activeTool,
      liveThinking: progress.thinking,
      activity: progress.activity,
      turns: progress.turns,
    });

    const child = spawnPiChild(cli.command, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...env },
    });

    let termination: Promise<boolean> | undefined;
    const failWorker = (reason: string) => {
      failureReason ??= reason;
      stdoutBuffer = "";
      termination ??= terminateChildProcess(child);
    };
    const abortHandler = () => {
      cancelled = true;
      failWorker("Pi worker cancelled.");
    };
    if (signal?.aborted) {
      abortHandler();
    } else {
      signal?.addEventListener("abort", abortHandler, { once: true });
    }

    const handleStdout = (chunk: Buffer) => {
      if (failureReason) return;
      const chunkBytes = chunk.byteLength;
      if (stdoutBytes + chunkBytes > PI_WORKER_STDOUT_LIMIT_BYTES) {
        failWorker(`Pi worker stdout exceeded ${PI_WORKER_STDOUT_LIMIT_BYTES} bytes.`);
        return;
      }
      stdoutBytes += chunkBytes;
      const text = chunk.toString();
      stdout += text;
      stdoutBuffer += text;
      const lines = stdoutBuffer.split("\n");
      stdoutBuffer = lines.pop() ?? "";
      let changed = false;
      for (const line of lines) {
        if (Buffer.byteLength(line, "utf8") > PI_WORKER_JSONL_LINE_LIMIT_BYTES) {
          failWorker(`Pi worker JSONL line exceeded ${PI_WORKER_JSONL_LINE_LIMIT_BYTES} bytes.`);
          return;
        }
        changed = applyPiWorkerProgress(progress, line) || changed;
      }
      if (Buffer.byteLength(stdoutBuffer, "utf8") > PI_WORKER_JSONL_LINE_LIMIT_BYTES) {
        failWorker(`Pi worker JSONL line exceeded ${PI_WORKER_JSONL_LINE_LIMIT_BYTES} bytes.`);
        return;
      }
      if (changed) emitProgress();
    };
    const handleStderr = (chunk: Buffer) => {
      if (failureReason) return;
      const chunkBytes = chunk.byteLength;
      if (stderrBytes + chunkBytes > PI_WORKER_STDERR_LIMIT_BYTES) {
        failWorker(`Pi worker stderr exceeded ${PI_WORKER_STDERR_LIMIT_BYTES} bytes.`);
        return;
      }
      stderrBytes += chunkBytes;
      stderr += chunk.toString();
    };

    child.stdout?.on("data", handleStdout);
    child.stderr?.on("data", handleStderr);

    child.on("close", (code) => {
      signal?.removeEventListener("abort", abortHandler);

      const failed = code !== 0 || cancelled || failureReason !== undefined;
      const { text, usage } = failed ? { text: "", usage: undefined } : parsePiWorkerOutput(stdout);
      const diagnostic = [failureReason, stderr.trim()].filter(Boolean).join("\n");
      resolve({
        text,
        usage,
        exitCode: code === 0 && failed ? 1 : code ?? 1,
        stderr: diagnostic,
        cancelled,
      });
    });

    child.on("error", (err) => {
      signal?.removeEventListener("abort", abortHandler);
      resolve({
        text: "",
        exitCode: 1,
        stderr: [failureReason, stderr.trim(), err.message].filter(Boolean).join("\n"),
        cancelled,
      });
    });
  });
}

/**
 * Parse the JSONL output of a `pi --print --mode json` worker run.
 * Returns the final assistant text and the last reported usage.
 */
export function parsePiWorkerOutput(stdout: string): { text: string; usage?: PiWorkerUsage } {
  let text = "";
  let usage: PiWorkerUsage | undefined;

  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue;
    let event: {
      type?: string;
      message?: {
        role?: string;
        content?: Array<{ type?: string; text?: string }>;
        usage?: {
          input?: number;
          output?: number;
          cacheRead?: number;
          cacheWrite?: number;
          totalTokens?: number;
          cost?: { total?: number };
        };
      };
    };
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
    const parts = (event.message.content ?? [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text as string);
    if (parts.length > 0) text = parts.join("\n");
    const u = event.message.usage;
    if (u) {
      usage = {
        input: u.input ?? 0,
        output: u.output ?? 0,
        cacheRead: u.cacheRead ?? 0,
        cacheWrite: u.cacheWrite ?? 0,
        totalTokens: u.totalTokens ?? 0,
        cost: u.cost?.total ?? 0,
      };
    }
  }
  return { text, usage };
}

/**
 * Terminate a child process gracefully, escalating to SIGKILL if needed.
 * Resolution is based on the child's close event, not only its exit code.
 */
export async function terminateChildProcess(
  child: ChildProcess,
  graceMs = DEFAULT_TERMINATION_GRACE_MS,
): Promise<boolean> {
  const closedAfterTerm = waitForClose(child, graceMs);
  if (!isChildRunning(child)) return closedAfterTerm;

  if (!signalChild(child, "SIGTERM")) return closedAfterTerm;
  if (await closedAfterTerm) return true;
  if (!isChildRunning(child)) return false;

  const closedAfterKill = waitForClose(child, graceMs);
  if (!signalChild(child, "SIGKILL")) return closedAfterKill;
  return closedAfterKill;
}

function isChildRunning(child: ChildProcess): boolean {
  return child.exitCode === null && child.signalCode === null;
}

function signalChild(child: ChildProcess, signal: NodeJS.Signals): boolean {
  if (process.platform !== "win32" && child.pid && processGroupChildren.has(child)) {
    try {
      process.kill(-child.pid, signal);
      return true;
    } catch {
      // Fall through to the direct child signal when the process group is gone.
    }
  }
  try {
    return child.kill(signal);
  } catch {
    return false;
  }
}

interface PiWorkerProgressState {
  text: string;
  thinking: string;
  toolcallArgs: string;
  activeTool?: string;
  activity?: string;
  activityKind?: "text" | "thinking" | "tool";
  turns: number;
}

function createPiWorkerProgress(): PiWorkerProgressState {
  return { text: "", thinking: "", toolcallArgs: "", turns: 0 };
}

function latestActivityLine(text: string): string | undefined {
  const lines = text.split("\n");
  for (let index = lines.length - 1; index >= 0; index--) {
    const line = lines[index].replace(/\s+/g, " ").trim();
    if (line) return line;
  }
  return undefined;
}

function applyPiWorkerProgress(state: PiWorkerProgressState, line: string): boolean {
  if (!line.trim()) return false;
  let event: {
    type?: string;
    toolCallId?: string;
    toolName?: string;
    args?: unknown;
    assistantMessageEvent?: { type?: string; delta?: string; toolCall?: { name?: string } };
    message?: { role?: string; content?: Array<{ type?: string; text?: string }> };
  };
  try {
    event = JSON.parse(line) as typeof event;
  } catch {
    return false;
  }
  if (event.type === "tool_execution_start") {
    const serialized = typeof event.args === "string" ? event.args : JSON.stringify(event.args ?? {});
    state.activeTool = toolcallLabel(serialized) ?? event.toolName ?? "tool";
    state.activity = state.activeTool;
    state.activityKind = "tool";
    return true;
  }
  if (event.type === "tool_execution_end") {
    state.activity = state.activeTool ?? state.activity;
    return true;
  }
  if (event.type === "message_end" && event.message?.role === "assistant") {
    state.turns++;
    const text = extractTextContent(event.message.content, "");
    if (text.trim()) {
      state.text = text;
      state.activity = latestActivityLine(text);
    }
    state.activityKind = undefined;
    return true;
  }
  if (event.type !== "message_update" || !event.assistantMessageEvent) return false;
  const update = event.assistantMessageEvent;
  switch (update.type) {
    case "text_delta":
      if (state.activityKind !== "text") state.text = "";
      state.activeTool = undefined;
      state.activityKind = "text";
      state.text += update.delta ?? "";
      state.activity = latestActivityLine(state.text) ?? state.activity;
      return true;
    case "thinking_delta":
      if (state.activityKind !== "thinking") state.thinking = "";
      state.activeTool = undefined;
      state.activityKind = "thinking";
      state.thinking += update.delta ?? "";
      state.activity = latestActivityLine(state.thinking) ?? state.activity;
      return true;
    case "toolcall_start":
      state.toolcallArgs = "";
      state.activeTool = undefined;
      return true;
    case "toolcall_delta":
      state.toolcallArgs += update.delta ?? "";
      state.activeTool = toolcallLabel(state.toolcallArgs) ?? state.activeTool;
      state.activity = state.activeTool ?? state.activity;
      if (state.activeTool) state.activityKind = "tool";
      return true;
    case "toolcall_end":
      state.activeTool = toolcallLabel(state.toolcallArgs)
        ?? update.toolCall?.name
        ?? state.activeTool;
      state.activity = state.activeTool ?? state.activity;
      if (state.activeTool) state.activityKind = "tool";
      state.toolcallArgs = "";
      return true;
    default:
      return false;
  }
}

function toolcallLabel(rawArgs: string): string | undefined {
  try {
    const args = JSON.parse(rawArgs) as Record<string, unknown>;
    if (typeof args.command === "string" && args.command.trim()) return `bash: ${truncateInline(args.command, 40)}`;
    if (typeof args.path === "string" && args.path.trim()) return `file: ${path.basename(args.path.trim())}`;
    if (typeof args.query === "string" && args.query.trim()) return `search: ${truncateInline(args.query, 40)}`;
  } catch {
    // Tool-call arguments are incomplete while they stream.
  }
  return undefined;
}

function truncateInline(text: string, cap: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length <= cap ? oneLine : `${oneLine.slice(0, cap).trimEnd()} ...`;
}

function waitForClose(child: ChildProcess, graceMs: number): Promise<boolean> {
  if (closedChildren.has(child)) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const onClose = () => {
      closedChildren.add(child);
      finish(true);
    };
    const timer = setTimeout(() => finish(false), graceMs);
    timer.unref?.();

    function finish(closed: boolean): void {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.off("close", onClose);
      resolve(closed);
    }

    child.once("close", onClose);
  });
}

// ── Messages ────────────────────────────────────────────────────────

/**
 * Extract plain text from a pi message content value (string or content-block
 * array). Non-text blocks (images, tool calls, thinking) contribute nothing.
 * Returns the joined text, possibly empty; callers own trim/empty semantics.
 */
export function extractTextContent(content: unknown, separator = "\n"): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const texts: string[] = [];
  for (const part of content) {
    if (typeof part !== "object" || part === null) continue;
    const block = part as { type?: unknown; text?: unknown };
    if (block.type === "text" && typeof block.text === "string") texts.push(block.text);
  }
  return texts.join(separator);
}

// ── Model selection ─────────────────────────────────────────────────
// Shared across memory, recap, and vision for selecting a model from the
// registry via the interactive TUI menu (ctx.ui.select/input).

/**
 * Return the trimmed string when it is non-empty, otherwise undefined.
 * Shared by readConfig functions across packages.
 */
export function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * Parse a "provider/model" reference string into its parts. Invalid formats
 * (no slash, leading/trailing slash, empty) return undefined.
 */
export function parseModelRef(
  value: string | undefined,
): { provider: string; model: string } | undefined {
  const ref = nonEmpty(value);
  if (!ref) return undefined;
  const separator = ref.indexOf("/");
  if (separator <= 0 || separator === ref.length - 1) return undefined;
  return { provider: ref.slice(0, separator), model: ref.slice(separator + 1) };
}

/**
 * Format a config's provider and model as "provider/model". Returns the bare
 * model when only the model is set, or undefined when neither is set.
 */
export function modelRef(config: { provider?: string; model?: string }): string | undefined {
  if (config.provider && config.model) return `${config.provider}/${config.model}`;
  return config.model;
}

/** Format a model as "provider/id". */
export function modelLabel(model: { provider: string; id: string }): string {
  return `${model.provider}/${model.id}`;
}

/** Sort models in-place by provider/id label. */
export function sortModels<T extends { provider: string; id: string }>(models: T[]): T[] {
  return models.sort((a, b) => modelLabel(a).localeCompare(modelLabel(b)));
}

/** Minimal UI surface for interactive model selection via ctx.ui.select. */
export interface MenuUi {
  select(label: string, options: string[]): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/** Minimal UI surface for interactive model entry via ctx.ui.input. */
export interface InputUi {
  input(label: string, defaultValue?: string): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/** Interactive picker options for searchModelFromPicker. */
export interface ModelPickerOptions {
  title?: string;
  maxVisible?: number;
  onSelectAsDefault?: (model: { provider: string; model: string }) => void;
}

/**
 * Interactive model search picker component using ctx.ui.custom.
 * Provides live type-to-filter search across all supplied models,
 * keyboard navigation, current model indicator, and optional default selection.
 */
export async function searchModelFromPicker(
  ui: {
    custom<T>(
      factory: (
        tui: any,
        theme: any,
        keybindings: any,
        done: (result: T) => void,
      ) => any,
      options?: { overlay?: boolean },
    ): Promise<T>;
    notify(msg: string, type?: "error" | "info" | "warning"): void;
  },
  models: { provider: string; id: string; name?: string }[],
  currentModel: string | undefined,
  options?: ModelPickerOptions,
): Promise<{ provider: string; model: string } | undefined> {
  if (models.length === 0) {
    ui.notify("No models are available in the model registry.", "warning");
    return undefined;
  }

  const defaultFilter = (
    items: { provider: string; id: string; name?: string }[],
    query: string,
    getText: (item: { provider: string; id: string; name?: string }) => string,
  ) => {
    const q = query.toLowerCase();
    return items.filter((item) => getText(item).toLowerCase().includes(q));
  };

  return ui.custom<{ provider: string; model: string } | undefined>((_tui, theme, kb, done) => {
    let filterFn = defaultFilter;
    try {
      // Dynamic import / global check if fuzzyFilter is available
      const tuiMod = (globalThis as any).__PI_TUI_MODULE__;
      if (tuiMod && typeof tuiMod.fuzzyFilter === "function") {
        filterFn = (items, q, gt) => tuiMod.fuzzyFilter(items, q, gt);
      }
    } catch {
      // Fall back to defaultFilter
    }

    const picker = createSearchPicker(models, {
      filter: filterFn,
      getText: modelSearchText,
    });

    const maxVisible = options?.maxVisible ?? 10;
    const title = options?.title ?? "Select a model";

    const render = (width: number): string[] => {
      const results = picker.results();
      const selectedIndex = picker.selectedIndex();
      const lines: string[] = [];

      // Top border & Title
      const border = "─".repeat(Math.max(1, width));
      lines.push(theme.fg("border", border));
      lines.push(theme.fg("accent", theme.bold(` ${title}`)));

      // Search input line
      const query = picker.query();
      const inputPrefix = theme.fg("muted", " Search: ");
      const inputCursor = theme.fg("accent", "▏");
      lines.push(`${inputPrefix}${query}${inputCursor}`);
      lines.push("");

      // Windowing slice
      const startIndex = Math.max(
        0,
        Math.min(selectedIndex - Math.floor(maxVisible / 2), results.length - maxVisible),
      );
      const endIndex = Math.min(startIndex + maxVisible, results.length);

      if (results.length === 0) {
        lines.push(theme.fg("muted", "  No matching models"));
      } else {
        for (let i = startIndex; i < endIndex; i++) {
          const item = results[i];
          const isSelected = i === selectedIndex;
          const label = modelLabel(item);
          const isCurrent = label === currentModel;

          const cursor = isSelected ? theme.fg("accent", "→ ") : "  ";
          const currentMarker = isCurrent ? theme.fg("accent", "✓ ") : "  ";
          const modelText = isSelected ? theme.fg("accent", item.id) : item.id;
          const providerBadge = theme.fg("muted", `[${item.provider}]`);
          const nameBadge = item.name && item.name !== item.id ? theme.fg("dim", ` · ${item.name}`) : "";

          lines.push(`${cursor}${currentMarker}${modelText} ${providerBadge}${nameBadge}`);
        }
      }

      // Scroll info
      if (results.length > 0 && (startIndex > 0 || endIndex < results.length)) {
        lines.push(theme.fg("muted", `  (${selectedIndex + 1}/${results.length})`));
      }

      lines.push("");
      // Key hints
      const confirmHint = "Enter to select";
      const cancelHint = "Esc to cancel";
      const navHint = "↑/↓ to navigate";
      lines.push(theme.fg("dim", `  ${navHint} · ${confirmHint} · ${cancelHint}`));
      lines.push(theme.fg("border", border));

      return lines;
    };

    const handleInput = (keyData: string): void => {
      if (kb && typeof kb.matches === "function") {
        if (kb.matches(keyData, "tui.select.up") || keyData === "\x1b[A" || keyData === "k") {
          picker.up();
          return;
        }
        if (kb.matches(keyData, "tui.select.down") || keyData === "\x1b[B" || keyData === "j") {
          picker.down();
          return;
        }
        if (kb.matches(keyData, "tui.select.confirm") || keyData === "\r" || keyData === "\n") {
          const sel = picker.selected();
          if (sel) {
            done({ provider: sel.provider, model: sel.id });
          }
          return;
        }
        if (kb.matches(keyData, "tui.select.cancel") || keyData === "\x1b" || keyData === "\x03") {
          done(undefined);
          return;
        }
      } else {
        // Fallback key handling when kb matcher is not provided
        if (keyData === "\x1b[A") {
          picker.up();
          return;
        }
        if (keyData === "\x1b[B") {
          picker.down();
          return;
        }
        if (keyData === "\r" || keyData === "\n") {
          const sel = picker.selected();
          if (sel) {
            done({ provider: sel.provider, model: sel.id });
          }
          return;
        }
        if (keyData === "\x1b" || keyData === "\x03") {
          done(undefined);
          return;
        }
      }

      // Backspace: \x7f (DEL) or \x08 (BS)
      if (keyData === "\x7f" || keyData === "\x08") {
        picker.backspace();
        return;
      }

      // Printable text (exclude escape sequences)
      if (keyData.length > 0 && !keyData.startsWith("\x1b") && keyData >= " ") {
        picker.type(keyData);
      }
    };

    return {
      render,
      handleInput,
    };
  }, { overlay: true });
}

/**
 * Interactive model selection via ctx.ui.select. Pass the available models
 * (already filtered and sorted by the caller), the current model reference
 * (for the "current" marker), and an optional title. Returns the selected
 * provider/model pair, or undefined when the dialog is cancelled or no models
 * are available.
 */
export async function selectModelFromMenu(
  ui: MenuUi,
  models: { provider: string; id: string; name: string }[],
  currentModel: string | undefined,
  title?: string,
): Promise<{ provider: string; model: string } | undefined> {
  if (models.length === 0) {
    ui.notify("No models are available in the model registry.", "warning");
    return undefined;
  }
  const options = models.map((model) => {
    const current = modelLabel(model) === currentModel ? " · current" : "";
    return `${modelLabel(model)} · ${model.name}${current}`;
  });
  const selected = await ui.select(title ?? "Select a model", options);
  if (!selected) return undefined;
  const model = models[options.indexOf(selected)];
  if (!model) return undefined;
  return { provider: model.provider, model: model.id };
}

// ── Model search ────────────────────────────────────────────────────

/**
 * Searchable text for one model: the provider-prefixed label first, then the
 * display name — mirroring pi's own /model selector ranking where exact
 * provider-prefixed queries rank ahead of bare model ids.
 */
export function modelSearchText(model: { provider: string; id: string; name?: string }): string {
  const label = modelLabel(model);
  return model.name && model.name !== model.id ? `${label} · ${model.name}` : label;
}

/** Pure type-to-filter controller shared by interactive model pickers. The
 * filter callback is injected by the host (typically @earendil-works/pi-tui's
 * fuzzyFilter), keeping this module free of UI dependencies. Typing refilters
 * from the full item list and resets the selection to the best match;
 * navigation clamps within the filtered results. */
export interface SearchPicker<T> {
  /** Current query text. */
  query(): string;
  /** Items matching the current query (the full list when the query is empty). */
  results(): T[];
  /** Selected item, or undefined when no results remain. */
  selected(): T | undefined;
  /** Index of the selection within results(). */
  selectedIndex(): number;
  /** Append typed text; refilters and moves the selection to the top result. */
  type(text: string): void;
  /** Remove the last query character; refilters. */
  backspace(): void;
  /** Clear the query entirely; restores the full list in original order. */
  clear(): void;
  /** Move the selection up; clamps at the first result. */
  up(): void;
  /** Move the selection down; clamps at the last result. */
  down(): void;
}

/** Create a search picker over a fixed item list with an injected filter. */
export function createSearchPicker<T>(
  items: readonly T[],
  options: {
    filter: (items: T[], query: string, getText: (item: T) => string) => T[];
    getText: (item: T) => string;
  },
): SearchPicker<T> {
  let query = "";
  let filtered = [...items];
  let index = 0;
  const refilter = () => {
    filtered = query ? options.filter([...items], query, options.getText) : [...items];
    index = 0;
  };
  return {
    query: () => query,
    results: () => filtered,
    selected: () => filtered[index],
    selectedIndex: () => index,
    type: (text) => {
      query += text;
      refilter();
    },
    backspace: () => {
      if (!query) return;
      query = query.slice(0, -1);
      refilter();
    },
    clear: () => {
      query = "";
      refilter();
    },
    up: () => {
      index = Math.max(0, index - 1);
    },
    down: () => {
      index = Math.max(0, Math.min(filtered.length - 1, index + 1));
    },
  };
}

/** Options for enterModelFromInput. */
export interface EnterModelOptions {
  /** Dialog label shown to the user. */
  label?: string;
  /** Called when the user submits empty input (not on cancel). Default: notify an error. */
  onEmpty?: () => void;
}

/**
 * Interactive model entry via ctx.ui.input. Validates the input as a
 * "provider/model" reference and checks that the model exists in the registry.
 * Returns the parsed provider/model pair, or undefined when the dialog is
 * cancelled, the input is empty, or validation fails. Empty input notifies an
 * error unless an onEmpty handler is provided.
 */
export async function enterModelFromInput(
  ui: InputUi,
  modelRegistry: { find(provider: string, model: string): unknown },
  currentModel: string | undefined,
  options?: EnterModelOptions,
): Promise<{ provider: string; model: string } | undefined> {
  const value = await ui.input(
    options?.label ?? "Model (provider/model format):",
    currentModel ?? "",
  );
  if (value === undefined) return undefined;
  const trimmed = value.trim();
  if (!trimmed) {
    if (options?.onEmpty) {
      options.onEmpty();
    } else {
      ui.notify(
        "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
        "error",
      );
    }
    return undefined;
  }
  const ref = parseModelRef(trimmed);
  if (!ref) {
    ui.notify(
      "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
      "error",
    );
    return undefined;
  }
  if (!modelRegistry.find(ref.provider, ref.model)) {
    ui.notify(
      `Model ${ref.provider}/${ref.model} was not found in the model registry`,
      "error",
    );
    return undefined;
  }
  return ref;
}

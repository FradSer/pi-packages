import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { type Component, Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import {
  createToolLifecycleResultRenderer,
  eventToolLifecycle,
  PI_SPINNER_FRAMES,
  PI_SPINNER_INTERVAL_MS,
  renderPiWidgetRow,
  runPiWorker,
  safeDisplayText,
  type PiWorkerProgressUpdate,
} from "@fradser/pi-kit";
import { Type } from "typebox";

const RESEARCH_TOOLS = ["read", "bash"];
const EXCLUDED_TOOLS = ["edit", "write"];

interface ToolTextResult {
  content: [{ type: "text"; text: string }];
  details: Record<string, unknown>;
}

interface ToolResultForRendering {
  content: unknown;
  details?: unknown;
}

interface ChildResult {
  text: string;
  stderr: string;
  exitCode: number;
  cancelled: boolean;
}

function textResult(text: string, details: Record<string, unknown> = {}): ToolTextResult {
  return { content: [{ type: "text", text }], details };
}

function renderContextCall(
  args: { query?: string },
  theme: { fg(color: string, text: string): string; bold(text: string): string },
): Component {
  return {
    render(width) {
      if (width <= 0) return [];
      const prefix = theme.fg("customMessageLabel", theme.bold("[context] started ·"));
      // Trailing blank line separates the started row from the next transcript
      // block; every other package renders an empty call, so context (the only
      // package with a visible call row) owns its spacing locally.
      return [
        ...new Text(`${prefix} ${normalizeSubject(args.query)}`, 0, 0).render(width)
          .map((line) => truncateToWidth(line, width, "")),
        "",
      ];
    },
    invalidate() {},
  };
}

function normalizeSubject(value: unknown): string {
  return safeDisplayText(String(value ?? "research").replace(/\s+/g, " ").trim());
}

function renderContextResult(
  result: ToolResultForRendering,
  options: { expanded?: boolean },
  theme: { fg(color: string, text: string): string; bg(color: string, text: string): string; bold(text: string): string },
  context: { isError?: boolean },
  subject: string,
) {
  return createToolLifecycleResultRenderer<ToolResultForRendering, Text>({
    createSpec: (_result, _text, details) => eventToolLifecycle("context", subject, {
      label: "researched",
      details,
      detailLimit: "all",
    }),
    expandHint: "ctrl+o to expand",
    fit: truncateToWidth,
    visibleWidth,
    renderError: (line, errorTheme) => new Text(errorTheme.fg("error", line), 0, 0),
  })(result, options, theme, context);
}

export function buildResearchPrompt(query: string): string {
  return [
    "Research the user's request independently and return a concise, evidence-based answer.",
    "You are in a child Pi process with read and bash available. Treat the caller's working directory as read-only: never edit or write files. The bash tool can technically write, so this boundary is enforced by the research instruction rather than an OS sandbox.",
    "For public repository line-level evidence, you may run git clone --depth=1 into a unique /tmp directory, inspect it, and remove it before answering.",
    "Never modify the caller's working directory. Do not use package managers, deployment commands, or interactive commands.",
    "Cite concrete source URLs, repository paths, or documentation names when available.",
    "Keep raw findings compact and synthesize the answer rather than dumping large payloads.",
    "",
    "User research request:",
    query,
  ].join("\n");
}

/** Minimal structural view of the tool-execution context: only what the research widget needs. */
export interface ResearchWidgetContext {
  mode?: string;
  ui?: {
    setWidget(
      key: string,
      factory:
        | undefined
        | ((
            tui: { requestRender(): void },
            theme: { fg(color: string, text: string): string; bold(text: string): string },
          ) => { render(width: number): string[]; invalidate(): void; dispose?(): void }),
      options?: { placement?: string },
    ): void;
  };
}

interface ActiveResearch {
  token: number;
  query: string;
  detail?: string;
}

let researchToken = 0;
let activeResearch: ActiveResearch | undefined;
let researchWidgetTui: { requestRender(): void } | undefined;
let researchSpinnerTimer: ReturnType<typeof setInterval> | undefined;
let researchSpinnerFrame = 0;

function firstProgressLine(text: string | undefined): string | undefined {
  return text?.split("\n").map((line) => line.trim()).find((line) => line.length > 0);
}

/** Show the running-research status above the editor; returns a token for updates/clear. */
export function startResearchWidget(ctx: ResearchWidgetContext | undefined, query: string): number {
  const token = ++researchToken;
  activeResearch = { token, query };
  if (typeof ctx?.ui?.setWidget !== "function" || (ctx.mode !== undefined && ctx.mode !== "tui")) return token;
  if (researchSpinnerTimer) clearInterval(researchSpinnerTimer);
  researchSpinnerFrame = 0;
  researchSpinnerTimer = setInterval(() => {
    researchSpinnerFrame = (researchSpinnerFrame + 1) % PI_SPINNER_FRAMES.length;
    researchWidgetTui?.requestRender();
  }, PI_SPINNER_INTERVAL_MS);
  researchSpinnerTimer.unref?.();
  ctx.ui.setWidget("context-research", (tui, theme) => {
    researchWidgetTui = tui;
    return {
      render: (width: number) => {
        const current = activeResearch;
        if (!current || current.token !== token) return [];
        const marker = theme.fg("warning", PI_SPINNER_FRAMES[researchSpinnerFrame]);
        const detail = current.detail ? ` · ${current.detail}` : "";
        return [renderPiWidgetRow(
          `${marker} ${theme.bold("[context] researching")} · ${normalizeSubject(current.query)}${detail}`,
          width,
          truncateToWidth,
        )];
      },
      invalidate: () => {},
      dispose: () => { if (researchWidgetTui === tui) researchWidgetTui = undefined; },
    };
  }, { placement: "aboveEditor" });
  return token;
}

/** Refresh the live activity line; stale tokens are ignored. */
export function updateResearchWidget(token: number, detail: string | undefined): void {
  if (activeResearch?.token !== token) return;
  if (detail) activeResearch.detail = detail;
  researchWidgetTui?.requestRender();
}

/** Remove the status widget; stale tokens are ignored. */
export function clearResearchWidget(ctx: ResearchWidgetContext | undefined, token: number): void {
  if (activeResearch?.token !== token) return;
  activeResearch = undefined;
  if (researchSpinnerTimer) {
    clearInterval(researchSpinnerTimer);
    researchSpinnerTimer = undefined;
  }
  researchWidgetTui = undefined;
  if (ctx?.mode === undefined || ctx.mode === "tui") ctx?.ui?.setWidget?.("context-research", undefined);
}

export function runResearchChild(
  query: string,
  signal?: AbortSignal,
  onUpdate?: (update: PiWorkerProgressUpdate) => void,
): Promise<ChildResult> {
  let cancelled = signal?.aborted ?? false;
  const onAbort = () => { cancelled = true; };
  if (!signal?.aborted) signal?.addEventListener("abort", onAbort, { once: true });
  return runPiWorker({
    prompt: buildResearchPrompt(query),
    cwd: process.cwd(),
    tools: RESEARCH_TOOLS,
    extraArgs: ["--no-extensions", "--exclude-tools", EXCLUDED_TOOLS.join(",")],
    signal,
    onUpdate,
  }).then((result) => {
    signal?.removeEventListener("abort", onAbort);
    return { text: result.text.trim(), stderr: result.stderr.trim(), exitCode: result.exitCode, cancelled };
  });
}

const ResearchParams = Type.Object({
  query: Type.String({ description: "Research request: repository, library, codebase question, or current technical topic." }),
});

export function registerContextTools(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "context_get",
    label: "Isolated Pi research",
    description: "Research a repository, library, codebase, or technical topic in an independent prompt-constrained Pi child process. The child has read and bash available and can inspect or temporarily clone public repositories under /tmp.",
    promptSnippet: "Research independently in a prompt-constrained Pi child process",
    promptGuidelines: [
      "Use context_get when the user needs external context for a repository, library, codebase, or current technical topic. It retrieves that context in an isolated Pi process with a read/bash allowlist and prompt-level no-modification guidance.",
    ],
    parameters: ResearchParams,
    executionMode: "sequential",
    renderShell: "self",
    renderCall(args, theme) {
      return renderContextCall(args as { query?: string }, theme);
    },
    renderResult(result, options, theme, context) {
      const params = context.args as { query?: string };
      return renderContextResult(result, options, theme, context, normalizeSubject(params.query));
    },
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const widget = startResearchWidget(ctx as ResearchWidgetContext | undefined, params.query);
      try {
        const child = await runResearchChild(params.query, signal, (progress) => {
          updateResearchWidget(widget, firstProgressLine(progress.activeTool)
            ?? firstProgressLine(progress.liveThinking)
            ?? firstProgressLine(progress.text));
        });
        if (child.cancelled) throw new Error("Isolated Pi research was cancelled");
        if (child.exitCode !== 0) {
          throw new Error(`Isolated Pi research failed (exit ${child.exitCode}): ${child.stderr.slice(0, 400)}`);
        }
        if (!child.text) {
          throw new Error("Isolated Pi research returned no answer");
        }
        return textResult(child.text, { exitCode: child.exitCode });
      } finally {
        clearResearchWidget(ctx as ResearchWidgetContext | undefined, widget);
      }
    },
  });
}

export default registerContextTools;

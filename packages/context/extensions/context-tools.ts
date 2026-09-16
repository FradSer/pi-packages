import { getMarkdownTheme, keyHint, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { type Component, Markdown, Text, truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  createLiveActivityWidget,
  createStaticToolLifecycleResultRenderer,
  eventToolLifecycle,
  runPiWorker,
  type PiLiveWidgetContext,
  type PiWorkerProgressUpdate,
} from "@fradser/pi-kit";
import { Type } from "typebox";
import { buildContextResearchPrompt } from "./context-prompt.ts";

const RESEARCH_TOOLS = ["read", "bash"];
const FINAL_ANSWER_RETRY_INSTRUCTION = `

Completion requirement: the previous attempt produced no textual final answer. Complete the original research request now without relying on hidden reasoning, transient tool output, or state from the prior attempt; repeat any inspection needed to support the answer. Your final assistant message must be a self-contained plain-text answer with the conclusion and concrete evidence. Do not finish immediately after a tool call.`;

interface ToolTextResult {
  content: [{ type: "text"; text: string }];
  details: Record<string, unknown>;
}

interface ChildResult {
  text: string;
  stderr: string;
  exitCode: number;
  cancelled: boolean;
}

interface ResearchAttemptResult extends ChildResult {
  retried: boolean;
}

type ResearchRunner = (
  query: string,
  signal: AbortSignal | undefined,
  onUpdate: ((update: PiWorkerProgressUpdate) => void) | undefined,
  finalAnswerRetry: boolean,
) => Promise<ChildResult>;

function textResult(text: string, details: Record<string, unknown> = {}): ToolTextResult {
  return { content: [{ type: "text", text }], details };
}

export function formatResearchSubject(query: unknown): string {
  if (typeof query !== "string") return "context request";
  return query.replace(/\s+/g, " ").trim() || "context request";
}

function renderContextCall(
  query: unknown,
  theme: { fg(color: string, text: string): string; bold(text: string): string },
): Component {
  return {
    render: (width) => {
      if (width <= 0) return [];
      const prefix = theme.fg("customMessageLabel", theme.bold("[context]"));
      const title = `research started · ${formatResearchSubject(query)}`;
      return new Text(`${prefix} ${title}`, 0, 0).render(width)
        .map((line) => truncateToWidth(line, width, ""));
    },
    invalidate: () => {},
  };
}

function resultText(result: ToolTextResult): string {
  return result.content.find((part) => part.type === "text")?.text ?? "";
}

export function buildResearchPrompt(query: string, finalAnswerRetry = false): string {
  const prompt = buildContextResearchPrompt({
    userResearchRequest: query,
    workingDirectory: process.cwd(),
  });
  return finalAnswerRetry ? `${prompt}${FINAL_ANSWER_RETRY_INSTRUCTION}` : prompt;
}

/** Minimal structural view of the tool-execution context: only what the research widget needs. */
export type ResearchWidgetContext = PiLiveWidgetContext;

interface ActiveResearch {
  token: number;
  ctx: ResearchWidgetContext | undefined;
  activity?: string;
}

let researchToken = 0;
let activeResearch: ActiveResearch | undefined;
const researchWidget = createLiveActivityWidget({
  key: "context-research",
  placement: "aboveEditor",
  fit: truncateToWidth,
  formatIdentity: (identity, theme) => theme.fg("success", theme.bold(identity)),
  formatActivity: (activity, theme) => new Markdown(
    activity, 0, 0, getMarkdownTheme(), { color: (text) => theme.fg("accent", text) },
  ).render(Math.max(1, visibleWidth(activity))).map((line) => line.trim()).filter(Boolean).join(" "),
});

/** Show the running-research status above the editor; returns a token for updates/clear. */
export function startResearchWidget(ctx: ResearchWidgetContext | undefined): number {
  const token = ++researchToken;
  activeResearch = { token, ctx };
  researchWidget.update(ctx, [{ id: String(token), identity: "research" }]);
  return token;
}

/** Refresh the live activity line; stale tokens are ignored. */
export function updateResearchWidget(token: number, activity: string | undefined): void {
  if (activeResearch?.token !== token) return;
  if (activity) activeResearch.activity = activity;
  researchWidget.update(activeResearch.ctx, [{
    id: String(token),
    identity: "research",
    activity: activeResearch.activity,
  }]);
}

/** Remove the status widget; stale tokens are ignored. */
export function clearResearchWidget(ctx: ResearchWidgetContext | undefined, token: number): void {
  if (activeResearch?.token !== token) return;
  activeResearch = undefined;
  researchWidget.clear(ctx);
}

export function runResearchChild(
  query: string,
  signal?: AbortSignal,
  onUpdate?: (update: PiWorkerProgressUpdate) => void,
  finalAnswerRetry = false,
): Promise<ChildResult> {
  let cancelled = signal?.aborted ?? false;
  const onAbort = () => { cancelled = true; };
  if (!signal?.aborted) signal?.addEventListener("abort", onAbort, { once: true });
  return runPiWorker({
    prompt: buildResearchPrompt(query, finalAnswerRetry),
    cwd: process.cwd(),
    tools: RESEARCH_TOOLS,
    minimal: true,
    signal,
    onUpdate,
  }).then((result) => {
    signal?.removeEventListener("abort", onAbort);
    return { text: result.text.trim(), stderr: result.stderr.trim(), exitCode: result.exitCode, cancelled };
  });
}

export async function runResearchWithFinalAnswerRetry(
  query: string,
  signal?: AbortSignal,
  onUpdate?: (update: PiWorkerProgressUpdate) => void,
  runner: ResearchRunner = runResearchChild,
): Promise<ResearchAttemptResult> {
  const first = await runner(query, signal, onUpdate, false);
  if (first.cancelled || first.exitCode !== 0 || first.text) return { ...first, retried: false };
  const retry = await runner(query, signal, onUpdate, true);
  return { ...retry, retried: true };
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
    renderCall(args, theme, _context) {
      return renderContextCall(args.query, theme);
    },
    renderResult(result, options, theme, context) {
      const query = (context.args as { query?: string })?.query;
      const subject = formatResearchSubject(query);
      const text = resultText(result as ToolTextResult);
      const details = text.split("\n").map((line) => line.trim()).filter(Boolean);
      // A still-running partial update is live progress, never a finished
      // research result: it renders as `[context] researching` on the pending
      // band and only the settled result becomes `[context] researched`.
      const spec = options.isPartial
        ? eventToolLifecycle("context", subject, { label: "researching" })
        : eventToolLifecycle("context", subject, {
            label: "researched",
            details,
            detailLimit: "all",
          });
      return createStaticToolLifecycleResultRenderer({
        createSpec: () => spec,
        expandHint: keyHint("app.tools.expand", "to expand"),
        fit: truncateToWidth,
        visibleWidth,
        wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
      })(result as ToolTextResult, options, theme, context);
    },
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const widget = startResearchWidget(ctx as ResearchWidgetContext | undefined);
      try {
        const child = await runResearchWithFinalAnswerRetry(params.query, signal, (progress) => {
          updateResearchWidget(widget, progress.activity);
          onUpdate?.(textResult(progress.activity ?? "Working...", {
            operation: "context-review",
          }));
        });
        if (child.cancelled) throw new Error("Isolated Pi research was cancelled");
        if (child.exitCode !== 0) {
          const phase = child.retried ? " retry" : "";
          throw new Error(`Isolated Pi research${phase} failed (exit ${child.exitCode}): ${child.stderr.slice(0, 400)}`);
        }
        if (!child.text) throw new Error("Isolated Pi research returned no answer after retry");
        return textResult(child.text, {
          exitCode: child.exitCode,
          operation: "context-review",
          ...(child.retried ? { retried: true } : {}),
        });
      } finally {
        clearResearchWidget(ctx as ResearchWidgetContext | undefined, widget);
      }
    },
  });
}

export default registerContextTools;

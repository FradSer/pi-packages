import type { ChildProcess } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DEFAULT_MAX_LINES, truncateHead, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import {
  createToolLifecycleResultRenderer,
  eventToolLifecycle,
  resolvePiCli,
  spawnPiChild,
  terminateChildProcess,
} from "@fradser/pi-kit";
import { Type } from "typebox";

const READ_ONLY_TOOLS = ["read", "bash"];
const EXCLUDED_TOOLS = ["edit", "write"];
const MAX_CHARS = 60_000;
const CHILD_TIMEOUT_MS = 180_000;

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
  timedOut: boolean;
}

function textResult(text: string, details: Record<string, unknown> = {}): ToolTextResult {
  return { content: [{ type: "text", text }], details };
}

function emptyToolCall(): Text {
  return new Text("", 0, 0);
}

function compactSubject(value: unknown): string {
  const normalized = String(value ?? "research").replace(/\s+/g, " ").trim();
  return normalized.length <= 120 ? normalized : `${normalized.slice(0, 117)}...`;
}

function truncate(text: string): string {
  if (text.length <= MAX_CHARS) return text;
  const result = truncateHead(text, { maxLines: DEFAULT_MAX_LINES, maxBytes: MAX_CHARS });
  return `${result.content}\n\n…[truncated ${text.length - MAX_CHARS} chars]`;
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
      detailLimit: 50,
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
    "You are in a child Pi process. Use only read and bash; never edit or write files.",
    "For public repository line-level evidence, you may run git clone --depth=1 into a unique /tmp directory, inspect it, and remove it before answering.",
    "Never modify the caller's working directory. Do not use package managers, deployment commands, or interactive commands.",
    "Cite concrete source URLs, repository paths, or documentation names when available.",
    "Keep raw findings compact and synthesize the answer rather than dumping large payloads.",
    "",
    "User research request:",
    query,
  ].join("\n");
}

function parseChildOutput(stdout: string): string {
  let text = "";
  for (const line of stdout.split("\n")) {
    try {
      const event = JSON.parse(line) as { type?: string; message?: { role?: string; content?: Array<{ type?: string; text?: string }> } };
      if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
      const candidate = (event.message.content ?? [])
        .filter((part) => part.type === "text" && typeof part.text === "string")
        .map((part) => part.text)
        .join("");
      if (candidate.trim()) text = candidate;
    } catch {
      // JSON mode may include non-event output; it is not part of the result.
    }
  }
  return text.trim();
}

function sandboxProfile(researchDirectory: string): string {
  const temporaryDirectory = researchDirectory.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return [
    "(version 1)",
    "(deny default)",
    "(allow process*)",
    "(allow sysctl-read)",
    "(allow file-read*)",
    `(allow file-write* (subpath \"${temporaryDirectory}\"))`,
    "(allow network*)",
  ].join("\n");
}

export function runResearchChild(query: string, signal?: AbortSignal): Promise<ChildResult> {
  const cli = resolvePiCli();
  const researchDirectory = realpathSync(mkdtempSync(join(tmpdir(), "pi-context-")));
  const piArgs = [
    ...cli.args,
    "--print",
    "--mode",
    "json",
    "--no-session",
    "--tools",
    READ_ONLY_TOOLS.join(","),
    "--exclude-tools",
    EXCLUDED_TOOLS.join(","),
    buildResearchPrompt(query),
  ];

  const sandboxed = process.platform === "darwin";
  const command = sandboxed ? "sandbox-exec" : cli.command;
  const args = sandboxed ? ["-p", sandboxProfile(researchDirectory), cli.command, ...piArgs] : piArgs;

  return new Promise((resolve, reject) => {
    let child: ChildProcess;
    let settled = false;
    try {
      child = spawnPiChild(command, args, { cwd: researchDirectory, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    } catch (error) {
      rmSync(researchDirectory, { recursive: true, force: true });
      reject(error);
      return;
    }

    let stdout = "";
    let stderr = "";
    let termination: Promise<boolean> | undefined;
    let timedOut = false;
    let cancelled = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      termination ??= terminateChildProcess(child);
    }, CHILD_TIMEOUT_MS);
    timeout.unref?.();
    const abort = () => {
      cancelled = true;
      termination ??= terminateChildProcess(child);
    };
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });

    child.stdout?.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    child.stderr?.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", abort);
      clearTimeout(timeout);
      rmSync(researchDirectory, { recursive: true, force: true });
      reject(error);
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", abort);
      clearTimeout(timeout);
      rmSync(researchDirectory, { recursive: true, force: true });
      resolve({ text: parseChildOutput(stdout), stderr: stderr.trim(), exitCode: code ?? 1, cancelled, timedOut });
    });
  });
}

const ResearchParams = Type.Object({
  query: Type.String({ description: "Research request: repository, library, codebase question, or current technical topic." }),
});

export function registerContextTools(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "context_get",
    label: "Isolated Pi research",
    description: "Research a repository, library, codebase, or technical topic in an independent read-only Pi child process. The child can inspect and temporarily clone public repositories under /tmp.",
    promptSnippet: "Research independently in a read-only child Pi process",
    promptGuidelines: [
      "Use context_get when the user needs external context for a repository, library, codebase, or current technical topic. It retrieves that context in an isolated read-only Pi process.",
    ],
    parameters: ResearchParams,
    executionMode: "sequential",
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const params = context.args as { query?: string };
      return renderContextResult(result, options, theme, context, compactSubject(params.query));
    },
    async execute(_toolCallId, params, signal) {
      const child = await runResearchChild(params.query, signal);
      if (child.cancelled) throw new Error("Isolated Pi research was cancelled");
      if (child.timedOut) throw new Error("Isolated Pi research timed out");
      if (child.exitCode !== 0) {
        throw new Error(`Isolated Pi research failed (exit ${child.exitCode}): ${child.stderr.slice(0, 400)}`);
      }
      if (!child.text) {
        throw new Error("Isolated Pi research returned no answer");
      }
      return textResult(truncate(child.text), { exitCode: child.exitCode });
    },
  });
}

export default registerContextTools;

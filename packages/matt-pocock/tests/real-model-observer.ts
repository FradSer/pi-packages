import { spawn } from "node:child_process";
import { appendFileSync, chmodSync, existsSync, realpathSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { Type, type Static } from "typebox";
import type {
  AgentEndEvent,
  AgentToolResult,
  ExtensionAPI,
  ExtensionContext,
  ToolCallEvent,
  ToolExecutionEndEvent,
  ToolExecutionStartEvent,
} from "@earendil-works/pi-coding-agent";

const FIXTURE_TOOL = "fixture_checks";
const BUILTIN_FILE_TOOLS = new Set(["read", "write", "edit", "grep", "find", "ls"]);
const MAX_TOOL_CALLS = 40;
export function realModelToolBudget(raw: string | undefined): number {
  const value = raw && /^\d+$/.test(raw) ? Number(raw) : NaN;
  return Number.isInteger(value) && value >= 1 && value <= 80 ? value : MAX_TOOL_CALLS;
}
const MAX_TEXT = 4_000;
const OBSERVER_PARAMETERS = Type.Object({});
type ObserverParameters = Static<typeof OBSERVER_PARAMETERS>;
type Evidence = Record<string, unknown>;
type AgentMessage = AgentEndEvent["messages"][number];

function projectRootFromEnv(): string | undefined {
  const value = process.env.MP_REAL_PROJECT;
  if (!value) return undefined;
  try {
    const root = realpathSync(value);
    return statSync(root).isDirectory() ? root : undefined;
  } catch {
    return undefined;
  }
}

function isWithin(root: string, candidate: string): boolean {
  const relativePath = relative(root, candidate);
  return relativePath === "" || (relativePath !== ".." && !relativePath.startsWith(`..${sep}`) && !isAbsolute(relativePath));
}

function nearestExisting(pathname: string): string {
  let current = pathname;
  while (!existsSync(current)) {
    const parent = dirname(current);
    if (parent === current) return current;
    current = parent;
  }
  return current;
}

/** Resolve existing symlinks and the nearest existing parent before allowing a project path. */
export function isProjectPathAllowed(root: string, value: string): boolean {
  try {
    const project = realpathSync(root);
    const candidate = isAbsolute(value) ? resolve(value) : resolve(project, value);
    const existing = nearestExisting(candidate);
    const resolvedParent = realpathSync(existing);
    if (!isWithin(project, resolvedParent)) return false;
    if (existsSync(candidate)) return isWithin(project, realpathSync(candidate));
    return true;
  } catch {
    return false;
  }
}

function toolPaths(toolName: string, input: unknown): string[] {
  if (!BUILTIN_FILE_TOOLS.has(toolName) || !input || typeof input !== "object") return [];
  const value = (input as { path?: unknown }).path;
  return typeof value === "string" ? [value] : [];
}

export function guardToolInput(root: string | undefined, toolName: string, input: unknown): { allowed: boolean; reason?: string } {
  if (!BUILTIN_FILE_TOOLS.has(toolName)) return { allowed: true };
  if (!root) return { allowed: false, reason: "project root is unavailable" };
  for (const value of toolPaths(toolName, input)) {
    if (!isProjectPathAllowed(root, value)) return { allowed: false, reason: "path is outside the real project" };
    if ((toolName === "write" || toolName === "edit") && isProtectedVerificationPath(root, value)) {
      return { allowed: false, reason: "fixed verification files and their parent directories are immutable" };
    }
  }
  return { allowed: true };
}

function isProtectedVerificationPath(root: string, value: string): boolean {
  try {
    const project = realpathSync(root);
    const candidate = isAbsolute(value) ? resolve(value) : resolve(project, value);
    const existing = nearestExisting(candidate);
    const resolvedParent = realpathSync(existing);
    const canonicalCandidate = existsSync(candidate)
      ? realpathSync(candidate)
      : resolve(resolvedParent, basename(candidate));
    const verifyPath = resolve(project, "tests/verify.test.mjs");
    const verify = existsSync(verifyPath) ? realpathSync(verifyPath) : verifyPath;
    return isWithin(canonicalCandidate, verify);
  } catch {
    return false;
  }
}

function redact(value: string): string {
  let result = value;
  for (const key of ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PI_REAL_MODEL_AUTH"]) {
    const secret = process.env[key];
    if (!secret) continue;
    result = result.replaceAll(secret, "[REDACTED]");
    // The bounded collector may end inside a secret. Remove its partial tail too.
    for (let size = Math.min(secret.length - 1, result.length); size > 0; size--) {
      if (result.endsWith(secret.slice(0, size))) {
        result = `${result.slice(0, -size)}[REDACTED]`;
        break;
      }
    }
  }
  return result.slice(0, MAX_TEXT);
}

function evidencePath(): string | undefined {
  const value = process.env.MP_REAL_EVIDENCE;
  return value && value.trim() ? value : undefined;
}

let evidenceWriteFailed = false;
let evidenceFailureReported = false;

function reportEvidenceFailure(): void {
  evidenceWriteFailed = true;
  if (evidenceFailureReported) return;
  evidenceFailureReported = true;
  process.stderr.write("real-model observer evidence write failed\n");
}

function record(value: Evidence): boolean {
  const target = evidencePath();
  if (!target) {
    reportEvidenceFailure();
    return false;
  }
  try {
    appendFileSync(target, `${JSON.stringify(value)}\n`, { encoding: "utf8", mode: 0o600 });
    chmodSync(target, 0o600);
    return true;
  } catch {
    reportEvidenceFailure();
    return false;
  }
}

function entryMetadata(entry: unknown): Evidence {
  if (!entry || typeof entry !== "object") return { type: "unknown" };
  const candidate = entry as { type?: unknown; customType?: unknown; data?: unknown };
  const result: Evidence = { type: typeof candidate.type === "string" ? candidate.type : "unknown" };
  if (typeof candidate.customType === "string") result.customType = candidate.customType;
  if (candidate.customType === "matt-pocock-workflow" && candidate.data && typeof candidate.data === "object") {
    const data = candidate.data as Record<string, unknown>;
    result.state = Object.fromEntries(["route", "procedure", "phase", "status", "workItemId"].flatMap((key) =>
      typeof data[key] === "string" ? [[key, data[key]]] : []));
  }
  return result;
}

function snapshot(ctx: ExtensionContext, pi: ExtensionAPI): Evidence {
  return {
    mode: ctx.mode,
    cwd: ctx.cwd,
    activeTools: pi.getActiveTools(),
    branch: ctx.sessionManager.getBranch().slice(-24).map(entryMetadata),
    model: ctx.model ? { provider: ctx.model.provider, id: ctx.model.id } : undefined,
  };
}

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.flatMap((part) => {
    if (part && typeof part === "object" && "text" in part && typeof part.text === "string") return [part.text];
    return [];
  }).join("\n");
}

function contextMetadata(messages: AgentMessage[]): Evidence {
  const sourceIds = new Set<string>();
  let textParts = 0;
  for (const message of messages) {
    const content = "content" in message ? textFromContent(message.content) : "";
    textParts += content ? 1 : 0;
    for (const match of content.matchAll(/<procedure-source\s+id="([^"]+)"/g)) sourceIds.add(match[1]);
  }
  return { messageCount: messages.length, textParts, sourceIds: [...sourceIds].sort() };
}

function assistantMetadata(event: AgentEndEvent): Evidence {
  const assistants = event.messages.filter((message) => message.role === "assistant") as Array<AgentMessage & {
    content?: unknown;
    stopReason?: unknown;
    usage?: unknown;
  }>;
  const final = assistants.at(-1);
  const usageTotals: Record<string, number> = {};
  for (const message of assistants) {
    if (!message.usage || typeof message.usage !== "object") continue;
    for (const [key, value] of Object.entries(message.usage)) {
      if (typeof value === "number" && Number.isFinite(value)) usageTotals[key] = (usageTotals[key] ?? 0) + value;
      if (key === "cost" && value && typeof value === "object") {
        for (const [costKey, costValue] of Object.entries(value)) {
          if (typeof costValue === "number" && Number.isFinite(costValue)) {
            const name = `cost_${costKey}`;
            usageTotals[name] = (usageTotals[name] ?? 0) + costValue;
          }
        }
      }
    }
  }
  const finalRecord = final as (typeof final & { errorMessage?: unknown }) | undefined;
  const errorMessage = typeof finalRecord?.errorMessage === "string" ? redact(finalRecord.errorMessage) : undefined;
  return {
    finalText: final ? redact(textFromContent(final.content)) : "",
    stopReason: typeof final?.stopReason === "string" ? final.stopReason : undefined,
    ...(errorMessage ? { errorMessage } : {}),
    usage: usageTotals,
    assistantCount: assistants.length,
  };
}

function workflowStateMetadata(value: unknown): Evidence | undefined {
  if (!value || typeof value !== "object") return undefined;
  const state = value as Record<string, unknown>;
  const selected = Object.fromEntries(["route", "procedure", "phase", "status", "workItemId"].flatMap((key) =>
    typeof state[key] === "string" ? [[key, state[key]]] : []));
  return Object.keys(selected).length > 0 ? selected : undefined;
}

function mattArguments(toolName: string, value: unknown): Evidence | undefined {
  if (!toolName.startsWith("matt_pocock") || !value || typeof value !== "object") return undefined;
  const args = value as Record<string, unknown>;
  const short = (item: unknown): string | null => typeof item === "string" ? redact(item).slice(0, 512) : null;
  const result: Evidence = Object.fromEntries(["mode", "capability", "route", "reference", "action", "target"].map((key) => [
    key,
    short(args[key]),
  ]));
  if (toolName === "matt_pocock_ask") {
    result.title = short(args.title);
    result.question = short(args.question);
    result.options = Array.isArray(args.options)
      ? args.options.filter((item): item is string => typeof item === "string").slice(0, 4).map((item) => short(item))
      : null;
    result.recommended = short(args.recommended);
    result.timeout_seconds = typeof args.timeout_seconds === "number" && Number.isFinite(args.timeout_seconds) ? args.timeout_seconds : null;
    result.allow_custom = typeof args.allow_custom === "boolean" ? args.allow_custom : null;
  }
  return result;
}

function toolMetadata(event: ToolExecutionStartEvent | ToolExecutionEndEvent, cachedArgs?: Evidence): Evidence {
  const metadata: Evidence = {
    toolCallId: event.toolCallId,
    toolName: event.toolName,
    parentToolCallId: event.parentToolCallId,
    ...("isError" in event ? { isError: event.isError } : {}),
    ...(event.toolName.startsWith("matt_pocock") ? { matt: true } : {}),
  };
  if ("args" in event) {
    const args = mattArguments(event.toolName, event.args);
    if (args) metadata.args = args;
  } else if (cachedArgs) {
    metadata.args = cachedArgs;
  }
  if ("result" in event && event.result && typeof event.result === "object") {
    const result = event.result as { content?: unknown; details?: unknown; structuredContent?: unknown };
    const details = result.details && typeof result.details === "object" ? result.details as Record<string, unknown> : undefined;
    const failed = "isError" in event && event.isError === true;
    const rawError = textFromContent(result.content)
      || (typeof details?.error === "string" ? details.error : typeof details?.message === "string" ? details.message : "");
    const errorText = failed ? redact(rawError).slice(0, 256) : undefined;
    metadata.result = {
      mode: typeof details?.mode === "string" ? details.mode : null,
      capability: typeof details?.capability === "string" ? details.capability : null,
      route: typeof details?.route === "string" ? details.route : null,
      reference: typeof details?.reference === "string" ? details.reference : null,
      passed: typeof details?.passed === "boolean" ? details.passed : null,
      available: typeof details?.available === "boolean" ? details.available : null,
      nodeCode: details?.node && typeof details.node === "object" && typeof (details.node as Record<string, unknown>).code === "number"
        ? (details.node as Record<string, unknown>).code
        : null,
      contentParts: Array.isArray(result.content) ? result.content.length : 0,
      textBytes: Array.isArray(result.content)
        ? result.content.reduce((total, part) => total + (part && typeof part === "object" && "text" in part && typeof part.text === "string" ? Buffer.byteLength(part.text, "utf8") : 0), 0)
        : 0,
      detailsKeys: result.details && typeof result.details === "object" ? Object.keys(result.details as object).sort() : [],
      structuredKeys: result.structuredContent && typeof result.structuredContent === "object" ? Object.keys(result.structuredContent as object).sort() : [],
      status: typeof details?.status === "string" ? details.status : null,
      action: typeof details?.action === "string" ? details.action : null,
      pending: typeof details?.pending === "boolean" ? details.pending : null,
      state: workflowStateMetadata(details?.state ?? details) ?? null,
      ...(failed ? { errorText: errorText || "tool execution failed" } : {}),
    };
  }
  return metadata;
}

type FixedCommandResult = { code: number; killed: boolean; aborted: boolean; elapsedMs: number; stdout: string; stderr: string; completed?: boolean };

const DIAGNOSTIC_LIMIT = 4_000;

function boundedAppend(current: string, chunk: Buffer | string): string {
  if (current.length >= DIAGNOSTIC_LIMIT) return current;
  return `${current}${chunk.toString()}`.slice(0, DIAGNOSTIC_LIMIT);
}

export function acceptanceCompletionTracker(marker: string): (chunk: string) => boolean {
  const expected = new RegExp(`^ok \\d+ - ${marker}\\r?$`);
  let line = "";
  let overflow = false;
  let completed = false;
  return (chunk) => {
    const parts = chunk.split("\n");
    for (let index = 0; index < parts.length; index++) {
      if (!overflow) {
        line += parts[index];
        if (line.length > 512) { line = ""; overflow = true; }
      }
      if (index < parts.length - 1) {
        completed ||= !overflow && expected.test(line);
        line = "";
        overflow = false;
      }
    }
    return completed;
  };
}

function runFixedCommand(command: string, args: string[], cwd: string, signal: AbortSignal | undefined, completionMarker?: string): Promise<FixedCommandResult> {
  const started = Date.now();
  const allowedEnv: NodeJS.ProcessEnv = {
    PATH: process.env.PATH ?? "/usr/bin:/bin",
    TMPDIR: join(cwd, ".tmp"),
    LANG: process.env.LANG ?? "C",
    LC_ALL: process.env.LC_ALL ?? "C",
    HOME: cwd,
  };
  if (signal?.aborted) return Promise.resolve({ code: 130, killed: false, aborted: true, elapsedMs: 0, stdout: "", stderr: "aborted before start" });
  return new Promise((resolveResult) => {
    const child = spawn(command, args, { cwd, env: allowedEnv, stdio: ["ignore", "pipe", "pipe"], detached: true });
    let killed = false;
    let aborted = false;
    let closed = false;
    let stdout = "";
    let stderr = "";
    let completed = false;
    const trackCompletion = completionMarker ? acceptanceCompletionTracker(completionMarker) : undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let escalation: ReturnType<typeof setTimeout> | undefined;
    const signalProcess = (name: NodeJS.Signals): void => {
      try {
        if (child.pid && process.platform !== "win32") process.kill(-child.pid, name);
        else child.kill(name);
      } catch {
        // The process may have exited between the close check and the signal.
      }
    };
    const stop = (wasAborted: boolean) => {
      if (closed) return;
      killed = true;
      aborted ||= wasAborted;
      signalProcess("SIGTERM");
      escalation ??= setTimeout(() => {
        if (!closed) signalProcess("SIGKILL");
      }, 500);
    };
    const timeout = () => stop(false);
    timer = setTimeout(timeout, 30_000);
    const abort = () => {
      stop(true);
    };
    signal?.addEventListener("abort", abort, { once: true });
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      if (escalation) clearTimeout(escalation);
      signal?.removeEventListener("abort", abort);
    };
    child.stdout?.on("data", (chunk: Buffer) => {
      if (trackCompletion) completed = trackCompletion(chunk.toString());
      stdout = boundedAppend(stdout, chunk);
    });
    child.stderr?.on("data", (chunk: Buffer) => { stderr = boundedAppend(stderr, chunk); });
    child.once("error", () => {
      closed = true;
      cleanup();
      resolveResult({ code: 127, killed, aborted, elapsedMs: Date.now() - started, stdout, stderr: "fixed fixture command could not start" });
    });
    child.once("close", (code) => {
      closed = true;
      cleanup();
      resolveResult({ code: code ?? 1, killed, aborted, elapsedMs: Date.now() - started, stdout, stderr, completed });
    });
  });
}

function sandboxProfile(root: string): string {
  const sandboxLiteral = (value: string) => value.replaceAll("\\", "\\\\").replaceAll('"', '\\\"');
  const runtimeRoots = [dirname(process.execPath), dirname(dirname(process.execPath)), "/usr/lib", "/usr/share", "/System", "/dev", "/bin"];
  const reads = [root, ...runtimeRoots].map((value) => `(subpath "${sandboxLiteral(value)}")`).join(" ");
  const ancestorPaths = (value: string): string[] => {
    const result: string[] = [];
    let current = dirname(resolve(value));
    while (current !== "/") {
      result.push(current);
      current = dirname(current);
    }
    return result;
  };
  const projectParents = ancestorPaths(root);
  const metadataParents = [...new Set([...projectParents, ...runtimeRoots.flatMap(ancestorPaths), "/private", "/System/Volumes/Data"])]
    .map((value) => `(literal "${sandboxLiteral(value)}")`)
    .join(" ");
  const projectParentReads = projectParents.map((value) => `(literal "${sandboxLiteral(value)}")`).join(" ");
  const tests = `(subpath "${sandboxLiteral(join(root, "tests"))}")`;
  // Start from a deny-all seatbelt profile. Node needs a small set of macOS
  // runtime primitives; all data reads/writes and executable launches remain
  // limited to the project, Node installation, system libraries, and bash.
  return [
    "(version 1)",
    "(deny default)",
    "(allow mach-bootstrap)",
    "(allow syscall*)",
    "(allow mach-register (local-name-prefix \"\"))",
    "(allow process*)",
    "(deny process-exec*)",
    `(allow process-exec (literal "${sandboxLiteral(process.execPath)}") (literal "/bin/bash"))`,
    "(allow sysctl-read)",
    "(allow syscall-mig (kernel-mig-routine mach_vm_reallocate vm_reallocate))",
    `(allow file-read* file-test-existence (literal "/") (literal "/etc") (literal "/tmp") (literal "/var") (literal "/private/etc/localtime") (literal "/dev/random") (literal "/dev/urandom") (literal "/dev/null") (literal "/dev/zero") ${projectParentReads} (subpath "/System") (subpath "/usr/lib") (subpath "/usr/share") ${reads})`,
    "(allow file-map-executable (subpath \"/System/Library/Frameworks\") (subpath \"/System/Library/PrivateFrameworks\") (subpath \"/System/Library/SubFrameworks\") (subpath \"/usr/lib\"))",
    `(allow file-read-metadata file-test-existence ${metadataParents})`,
    `(allow file-write* (subpath "${sandboxLiteral(root)}"))`,
    `(deny file-write* ${tests})`,
  ].join(" ");
}

function diagnostic(result: FixedCommandResult): { code: number; killed: boolean; aborted: boolean; elapsedMs: number; stdout: string; stderr: string } {
  return { code: result.code, killed: result.killed, aborted: result.aborted, elapsedMs: result.elapsedMs, stdout: redact(result.stdout), stderr: redact(result.stderr) };
}

function commandSummary(name: string, result: FixedCommandResult): string {
  const value = diagnostic(result);
  return `${name}: exit ${value.code}\nstdout:\n${value.stdout}\nstderr:\n${value.stderr}`;
}

async function runSandboxSelfChecks(root: string, sandbox: string, signal: AbortSignal | undefined): Promise<{ positive: FixedCommandResult; negative: FixedCommandResult }> {
  const profile = sandboxProfile(root);
  const rootLiteral = JSON.stringify(root);
  const positiveScript = `const fs=require('node:fs'); if(process.cwd()!==${rootLiteral}) process.exit(3); if(!fs.statSync('tests/verify.test.mjs').isFile()) process.exit(2); console.log('sandbox-positive-ok');`;
  const negativeScript = `const fs=require('node:fs'); const path=require('node:path'); const net=require('node:net'); if(process.cwd()!==${rootLiteral}) process.exit(3); let fileDenied=false; let externalDenied=false; let writeDenied=false; let networkDenied=false; try{fs.readFileSync('/etc/hosts')}catch(e){fileDenied=e&&['EACCES','EPERM'].includes(e.code)} try{fs.readFileSync(path.join(process.cwd(),'..',path.basename(process.cwd())+'-external-secret.txt'))}catch(e){externalDenied=e&&['EACCES','EPERM'].includes(e.code)} try{fs.writeFileSync('tests/verify.test.mjs','tamper')}catch(e){writeDenied=e&&['EACCES','EPERM'].includes(e.code)} const s=net.connect({host:'198.51.100.1',port:80}); s.on('error',e=>{networkDenied=e&&['EACCES','EPERM'].includes(e.code); process.exit(fileDenied&&externalDenied&&writeDenied&&networkDenied?0:1)}); setTimeout(()=>process.exit(1),1000);`;
  const positive = await runFixedCommand(sandbox, ["-p", profile, process.execPath, "-e", positiveScript], root, signal);
  const negative = await runFixedCommand(sandbox, ["-p", profile, process.execPath, "-e", negativeScript], root, signal);
  return { positive, negative };
}

export function isSandboxProjectRootAllowed(root: string): boolean {
  try {
    const project = realpathSync(root);
    if (!statSync(project).isDirectory() || !isWithin(project, realpathSync(nearestExisting(project)))) return false;
    return isProjectPathAllowed(project, "tests/verify.test.mjs");
  } catch {
    return false;
  }
}

export async function runFixtureChecks(root: string, signal: AbortSignal | undefined): Promise<AgentToolResult> {
  try {
    root = realpathSync(root);
  } catch {
    return { content: [{ type: "text", text: "fixture_checks unavailable: project root is invalid" }], details: { available: false } };
  }
  if (!isSandboxProjectRootAllowed(root)) {
    return { content: [{ type: "text", text: "fixture_checks unavailable: project root is invalid" }], details: { available: false } };
  }
  const verify = join(root, "tests", "verify.test.mjs");
  if (!existsSync(verify) || !isProjectPathAllowed(root, verify)) {
    return { content: [{ type: "text", text: "fixture_checks unavailable: fixed verification file is missing" }], details: { available: false } };
  }
  const sandbox = "/usr/bin/sandbox-exec";
  if (!existsSync(sandbox)) {
    return { content: [{ type: "text", text: "fixture_checks unavailable: macOS sandbox-exec is required" }], details: { available: false } };
  }
  let selfChecks: { positive: FixedCommandResult; negative: FixedCommandResult };
  try {
    selfChecks = await runSandboxSelfChecks(root, sandbox, signal);
  } catch {
    return { content: [{ type: "text", text: "fixture_checks unavailable: sandbox self-check could not start" }], details: { available: false } };
  }
  const sandboxPassed = selfChecks.positive.code === 0 && selfChecks.negative.code === 0;
  if (!sandboxPassed) {
    return {
      content: [{ type: "text", text: "fixture_checks failed: sandbox self-check" }],
      details: { available: true, passed: false, sandbox: { positive: diagnostic(selfChecks.positive), negative: diagnostic(selfChecks.negative) }, node: null, wizard: null },
    };
  }
  const profile = sandboxProfile(root);
  const completionMarker = readFileSync(verify, "utf8").match(/MP_ACCEPTANCE_COMPLETE_[a-f0-9]+/)?.[0];
  const node = await runFixedCommand(sandbox, ["-p", profile, process.execPath, "--test", "--test-reporter=tap", "tests/verify.test.mjs"], root, signal, completionMarker);
  const wizardCandidate = ["wizard.sh", "scripts/wizard.sh", "wizard"].find((name) => existsSync(join(root, name)));
  if (wizardCandidate && !isProjectPathAllowed(root, join(root, wizardCandidate))) {
    return {
      content: [{ type: "text", text: "fixture_checks failed" }],
      details: {
        available: true,
        passed: false,
        sandbox: { positive: diagnostic(selfChecks.positive), negative: diagnostic(selfChecks.negative) },
        node: diagnostic(node),
        wizard: { file: basename(wizardCandidate), code: 126, killed: false, aborted: false, elapsedMs: 0, stdout: "", stderr: "wizard path is outside the real project" },
      },
    };
  }
  const wizardName = wizardCandidate;
  const wizard = wizardName ? await runFixedCommand(sandbox, ["-p", profile, "/bin/bash", "-n", wizardName], root, signal) : undefined;
  const passed = node.code === 0 && (!completionMarker || node.completed === true) && (wizard === undefined || wizard.code === 0);
  return {
    content: [{ type: "text", text: [passed ? "fixture_checks passed" : "fixture_checks failed",
      commandSummary("node", node),
      ...(completionMarker && !node.completed ? ["acceptance did not complete"] : []),
      ...(wizard ? [commandSummary("wizard", wizard)] : []),
    ].join("\n") }],
    details: wizard
      ? { available: true, passed, sandbox: { positive: diagnostic(selfChecks.positive), negative: diagnostic(selfChecks.negative) }, node: diagnostic(node), wizard: { file: basename(wizardName!), ...diagnostic(wizard) } }
      : { available: true, passed, sandbox: { positive: diagnostic(selfChecks.positive), negative: diagnostic(selfChecks.negative) }, node: diagnostic(node), wizard: null },
  };
}

export function selfCheck(root: string | undefined): Evidence {
  return {
    allowedRead: Boolean(root && isProjectPathAllowed(root, "tests/verify.test.mjs")),
    allowedWrite: Boolean(root && isProjectPathAllowed(root, ".real-model-observer-selfcheck")),
    parentEscapeRejected: Boolean(root && !isProjectPathAllowed(root, "../outside")),
  };
}

export default function realModelObserver(pi: ExtensionAPI): void {
  const root = projectRootFromEnv();
  const toolBudget = realModelToolBudget(process.env.MP_REAL_TOOL_BUDGET);
  let toolCount = 0;
  let limitRecorded = false;
  const mattArgsByCall = new Map<string, Evidence>();

  pi.on("session_start", (_event, ctx) => {
    if (!evidencePath() || !record({ kind: "session_start", ...snapshot(ctx, pi), selfCheck: selfCheck(root) })) ctx.abort();
  });
  pi.on("context", (event, ctx) => {
    if (!record({ kind: "model_context", ...contextMetadata(event.messages), ...snapshot(ctx, pi) })) ctx.abort();
  });
  pi.on("context_with_system", (event, ctx) => {
    if (!record({ kind: "model_context", ...contextMetadata(event.messages), ...snapshot(ctx, pi) })) ctx.abort();
  });
  pi.on("tool_call", (event: ToolCallEvent) => {
    if (evidenceWriteFailed) return { block: true, terminate: true, reason: "real-model observer evidence is unavailable" };
    if (toolCount >= toolBudget) return { block: true, terminate: true, reason: "real-model observer tool budget is exhausted" };
    const input = "input" in event ? event.input : undefined;
    const guard = guardToolInput(root, event.toolName, input);
    if (!guard.allowed) {
      record({ kind: "tool_guard_block", toolName: event.toolName, reason: guard.reason });
      return { block: true, terminate: true, reason: "real-model observer blocked a path outside the project" };
    }
    return undefined;
  });
  pi.on("tool_execution_start", (event, ctx) => {
    toolCount += 1;
    const metadata = toolMetadata(event);
    if (metadata.args && event.toolName.startsWith("matt_pocock")) mattArgsByCall.set(event.toolCallId, metadata.args as Evidence);
    if (!record({ kind: "tool_execution_start", ...metadata, count: toolCount })) ctx.abort();
    if (toolCount >= toolBudget && !limitRecorded) {
      limitRecorded = true;
      record({ kind: "tool_limit", count: toolCount, budget: toolBudget });
      ctx.abort();
    }
  });
  pi.on("tool_execution_end", (event, ctx) => {
    if (!record({ kind: "tool_execution_end", ...toolMetadata(event, mattArgsByCall.get(event.toolCallId)) })) ctx.abort();
    mattArgsByCall.delete(event.toolCallId);
  });
  pi.on("agent_end", (event, ctx) => {
    if (!record({ kind: "agent_end", ...assistantMetadata(event), ...snapshot(ctx, pi) })) ctx.abort();
  });

  pi.registerTool({
    name: FIXTURE_TOOL,
    label: "Fixture checks",
    description: "Run the fixed project verification fixture in a restricted sandbox.",
    parameters: OBSERVER_PARAMETERS,
    async execute(_toolCallId, _params: ObserverParameters, signal, _onUpdate, ctx) {
      if (evidenceWriteFailed) return { content: [{ type: "text", text: "fixture_checks unavailable: evidence recording failed" }], details: { available: false, evidence: false } };
      const project = projectRootFromEnv();
      if (!project) return { content: [{ type: "text", text: "fixture_checks unavailable: project root is invalid" }], details: { available: false } };
      if (signal?.aborted || ctx.signal?.aborted) return { content: [{ type: "text", text: "fixture_checks aborted" }], details: { available: false, aborted: true } };
      return runFixtureChecks(project, signal ?? ctx.signal);
    },
  });
}

/**
 * pi-continual-learning — native Pi /memory command.
 *
 * Replaces the /skill:consolidate skill surface with a pi-native command menu:
 *
 *   /memory
 *     Auto-memory: on
 *     1. Select memory model
 *     2. Enter provider/model manually
 *     3. Consolidate memory now        (package prompt from prompts/memory-consolidator.md)
 *     4. Edit user instructions        (getAgentDir()/AGENTS.md)
 *     5. Edit project instructions     (./AGENTS.md or ./CLAUDE.md — whichever exists)
 *     6. Open memory folder
 *     7. Toggle auto-memory
 *
 * Auto-memory learns from settled user tasks through parent-validated plans.
 * Existing memory indexes are injected independently of the learning toggle.
 * Consolidation uses a separately selected Pi model when configured.
 */

import fs from "fs/promises";
import path from "path";
import { execFile } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { promisify } from "node:util";
import * as nodeFs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { keyHint, ToolExecutionComponent, type ExtensionAPI, type ExtensionCommandContext, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";

/** Geometry bound once: every learning row shares hint and wrapping. */
const learningRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});
import {
  bindLifecycleRenderers,
  createLiveActivityWidget,
  eventToolLifecycle,
  enterModelFromInput,
  notifyPi,
  modelRef,
  minimalPiWorkerArgs,
  parseModelRef,
  resolvePiCli,
  runPiWorker,
  searchModelFromPicker,
  sortModels,
  spawnPiChild,
} from "@fradser/pi-kit";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import {
  memoryConfigPath,
  readMemoryConfigState,
  writeMemoryConfig,
  type MemoryConfig,
} from "./config";
import { formatMemoriesBlock, loadAndDeduplicateMemories } from "./memory-files";
import { resolveMemoryPaths } from "./memory-paths";
import {
  buildIncrementalMemoryConsolidatorPrompt,
  buildMemoryConsolidatorPrompt,
  learningPlannerArgs,
} from "./planner-prompts";
import { registerAutomaticLearning } from "./automatic-learning";
import { buildLearningReceipt, formatLearningSummary, isLearningPipelineReceipt, learningSummaryDetails, learningSummarySubject, screenLearningEntries, shouldRetryPlanner, snapshotEntries, writeLearningReceipt, type LearningAttempt, type LearningMode, type LearningPipelineReceipt, type LearningScreen } from "./learning-efficiency";
import { currentTaskSlice, selectIncrementalLearning } from "./incremental-learning";
import { expandIncrementalMemoryPlan } from "./incremental-memory-plan";
import { automaticPhasePolicies, type PhasePolicies } from "./learning-controls";
import { checkPendingLearningMutations, memoryMutationFiles, normalizeTrackedMemory, recordLearningMutation, recordLearningProposal, recoverLearningUndo } from "./learning-history";
import { handleLearningManagement } from "./learning-management";
import {
  DEFAULT_AGENTS_MD_BUDGET_BYTES,
  MAX_AGENTS_MD_FILE_BYTES,
  MIN_BUDGET_BYTES,
  applyAgentsMdConsolidationPlan,
  planAgentsMdConsolidationPhase,
  recoverPendingAgentsMdConsolidations,
} from "./agents-md-consolidation";
import { applyHarnessConsolidationPlan, planHarnessConsolidationPhase, shouldRunHarnessPhase } from "./harness-consolidation";
import {
  acquireConsolidationLock,
  applyConsolidationPlan,
  containsSensitiveMemoryMaterial,
  sha256Digest,
  terminateConsolidationChild,
  createConsolidationReceipt,
  createPreApplyReceipt,
  createConsolidationRun,
  extractChildPlan,
  MAX_JSONL_LINE_BYTES,
  MAX_JSONL_LINES,
  MAX_PLAN_BYTES,
  MAX_NEW_MEMORY_PROPOSALS,
  MAX_STDOUT_BYTES,
  MAX_STDERR_BYTES,
  releaseConsolidationRun,
  resolveConsolidationRunPaths,
  writeConsolidationReceipt,
  writeFileAtomic,
  snapshotSessionContext,
  summarizeMemoryChanges,
  hashMemoryRoot,
  type ConsolidationRun,
} from "./consolidation-run";

export { formatMemoriesBlock, loadAndDeduplicateMemories, type MemoryEntry } from "./memory-files";
export { projectScopeKey, resolveMemoryPaths } from "./memory-paths";

// ── auto-memory settings (user-level, persisted) ───────────────────

interface MemorySettings {
  autoMemory: boolean;
  automaticPhases?: Partial<PhasePolicies>;
  /** AGENTS.md consolidation phase controls; absent means defaults (on). */
  agentsMd?: {
    disabled?: boolean;
    budgetBytes?: number;
  };
}

function safelyReadMemoryConfigState(): ReturnType<typeof readMemoryConfigState> {
  try {
    return readMemoryConfigState();
  } catch {
    return { config: {}, invalid: "memory.json could not be read safely", present: true };
  }
}

let memoryConfigState = safelyReadMemoryConfigState();
let memoryConfig: MemoryConfig = memoryConfigState.config;

function settingsFilePath(cwd = process.cwd()): string {
  return resolveMemoryPaths(cwd).settingsFile;
}

async function readSettings(cwd = process.cwd()): Promise<MemorySettings> {
  try {
    const raw = await fs.readFile(settingsFilePath(cwd), "utf-8");
    const parsed = JSON.parse(raw) as Partial<MemorySettings>;
    let agentsMd: MemorySettings["agentsMd"];
    if (parsed.agentsMd && typeof parsed.agentsMd === "object") {
      const budget = typeof parsed.agentsMd.budgetBytes === "number" && Number.isFinite(parsed.agentsMd.budgetBytes)
        ? Math.min(MAX_AGENTS_MD_FILE_BYTES, Math.max(MIN_BUDGET_BYTES, Math.round(parsed.agentsMd.budgetBytes)))
        : undefined;
      agentsMd = {
        ...(parsed.agentsMd.disabled === true ? { disabled: true } : {}),
        ...(budget !== undefined ? { budgetBytes: budget } : {}),
      };
    }
    return {
      autoMemory: parsed.autoMemory === false ? false : true,
      ...(parsed.automaticPhases !== undefined ? { automaticPhases: parsed.automaticPhases } : {}),
      ...(agentsMd !== undefined ? { agentsMd } : {}),
    };
  } catch {
    return { autoMemory: true };
  }
}

async function writeSettings(s: MemorySettings, cwd = process.cwd()): Promise<void> {
  const file = settingsFilePath(cwd);
  await writeFileAtomic(file, `${JSON.stringify(s, null, 2)}\n`, 0o600);
}

// ── auto-memory guidance (injected when enabled) ───────────────────

const AUTO_MEMORY_GUIDANCE = `

## Auto-memory

After this user task settles, a read-only learner extracts durable preferences,
decisions, and verified project facts from its context. The parent validates and
persists the plan. Do not write memory files or mirrors as part of ordinary task
execution. Never store credentials or tokens in memory.

Use relevant existing memories as reference; current explicit user instructions
take precedence. State the basis for project conclusions so future learning can
distinguish observed facts from assumptions. \`/memory\` manages automatic learning;
\`/consolidate\` runs it immediately.
`;

// ── locate this package (consolidate procedure doc) ────────────────

/**
 * Resolve the exact project instruction resource already selected by Pi. A
 * conventional AGENTS.md fallback is safe only when the context API is absent.
 */
export async function resolveProjectInstructionsFile(
  cwd: string,
  ctx?: ExtensionContext,
): Promise<{ path: string; display: string }> {
  const contextProvider = ctx as (ExtensionContext & {
    getSystemPromptOptions?: () => { contextFiles?: unknown };
  }) | undefined;
  const getOptions = contextProvider?.getSystemPromptOptions;
  let resources: unknown;
  let apiAvailable = typeof getOptions === "function";
  if (apiAvailable) {
    try {
      resources = getOptions?.().contextFiles;
    } catch {
      apiAvailable = false;
    }
  }
  const resolvedCwd = path.resolve(cwd);
  const candidates = Array.isArray(resources)
    ? resources.flatMap((resource, index) => {
        if (!resource || typeof resource !== "object") return [];
        const resourcePath = (resource as { path?: unknown }).path;
        if (typeof resourcePath !== "string") return [];
        const resolved = path.resolve(resolvedCwd, resourcePath);
        const basename = path.basename(resolved);
        if (!/^(?:AGENTS(?:\.override)?|CLAUDE)\.md$/i.test(basename)) return [];
        const relative = path.relative(path.dirname(resolved), resolvedCwd);
        if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) return [];
        const distance = relative === "" ? 0 : relative.split(path.sep).length;
        const priority = basename.toLowerCase() === "agents.override.md"
          ? 3
          : basename.toLowerCase() === "agents.md"
            ? 2
            : 1;
        return [{ path: resolved, index, distance, priority }];
      })
        .sort((left, right) => left.distance - right.distance || right.priority - left.priority || right.index - left.index)
    : [];
  const candidate = candidates[0];
  if (candidate) {
    return { path: candidate.path, display: path.relative(resolvedCwd, candidate.path) || path.basename(candidate.path) };
  }
  if (apiAvailable) {
    return { path: "", display: "Pi did not expose a project instruction file" };
  }
  const agents = path.join(resolvedCwd, "AGENTS.md");
  return { path: agents, display: "./AGENTS.md" };
}

/**
 * Resolve the shipped package root from this extension module. This works for
 * npm, git, and local installs without depending on Pi's settings format or
 * the active project's directory.
 */
function resolvePackageDir(): string {
  const extensionDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(extensionDir, "..");
}

// ── background consolidation ("dreaming") ─────────────────────────

interface LaterPlannerState {
  cancelled: boolean;
  generation: number;
  child?: ChildProcess;
}

interface DreamState {
  active: boolean;
  generation: number;
  cancelled: boolean;
  /** Terminal outcome of the last memory phase; gates the harness phase. */
  outcome?: "completed" | "unverified" | "failed";
  child?: ChildProcess;
  run?: ConsolidationRun;
  cleanup?: () => void;
  completion?: Promise<void>;
  /** Serializes the entire pipeline, including gaps between its phases. */
  pipeline?: Promise<void>;
  attempts?: LearningAttempt[];
  mode?: LearningMode;
  controller?: AbortController;
  laterStates?: LaterPlannerState[];
}

export async function cancelLaterPlannerChildren(states: readonly LaterPlannerState[]): Promise<void> {
  const children = new Set<ChildProcess>();
  for (const state of states) {
    state.cancelled = true;
    state.generation += 1;
    if (state.child) children.add(state.child);
  }
  await Promise.all([...children].map((child) => terminateConsolidationChild(child, 5_000)));
}

interface ChildJsonEvent {
  type?: string;
  toolCallId?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  isError?: boolean;
  error?: unknown;
  success?: boolean;
  finalError?: string;
  message?: {
    role?: string;
    content?: unknown;
    stopReason?: string;
    errorMessage?: string;
    usage?: { input?: number; output?: number; cacheRead?: number; cacheWrite?: number; totalTokens?: number; cost?: { total?: number } };
  };
  assistantMessageEvent?: {
    type?: string;
    delta?: string;
    content?: string;
  };
}

const MEMORY_FILENAME_RE = /^[A-Za-z0-9][A-Za-z0-9_-]*\.md$/;

/**
 * Normalize the child-facing selected scope using the same alias precedence as
 * the apply path. The parent receipt only ever receives this canonical list.
 */
export function normalizeSelectedScope(plan: unknown): string[] {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) {
    throw new Error("Consolidation plan must be an object");
  }
  const value = plan as Record<string, unknown>;
  if (!Array.isArray(value.selected)) {
    throw new Error("Consolidation plan must declare canonical selected scope");
  }
  const names = value.selected.map((entry, index) => {
    const name = typeof entry === "string"
      ? entry
      : entry && typeof entry === "object" && !Array.isArray(entry)
        ? (entry as { name?: unknown; file?: unknown; filename?: unknown }).name
          ?? (entry as { file?: unknown }).file
          ?? (entry as { filename?: unknown }).filename
        : undefined;
    if (typeof name !== "string" || !MEMORY_FILENAME_RE.test(name) || name.toLowerCase() === "memory.md") {
      throw new Error(`Consolidation plan selected[${index}] is not a canonical memory filename`);
    }
    return name;
  });
  const seen = new Set<string>();
  for (const name of names) {
    const key = name.toLowerCase();
    if (seen.has(key)) throw new Error(`Consolidation plan selects duplicate memory name: ${name}`);
    seen.add(key);
  }
  return names.sort();
}

const PER_ITEM_PLAN_SECTIONS = ["inventory", "staleness", "grounding", "report"] as const;

/**
 * Collapse byte-identical duplicate records for the same memory name inside
 * per-item plan sections. Models occasionally emit the same record twice; when
 * the duplicates are canonically equal the collapse is lossless. Conflicting
 * duplicates are left intact so validation rejects them and the retry path
 * handles genuine ambiguity.
 */
export function collapseDuplicatePlanRecords<T>(plan: T): T {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return plan;
  const value = plan as Record<string, unknown>;
  const next: Record<string, unknown> = { ...value };
  let collapsed = false;
  for (const section of PER_ITEM_PLAN_SECTIONS) {
    const records = value[section];
    if (!Array.isArray(records)) continue;
    const seen = new Set<string>();
    const kept: unknown[] = [];
    for (const record of records) {
      const name = record && typeof record === "object" && !Array.isArray(record)
        ? (record as { name?: unknown }).name
        : undefined;
      if (typeof name !== "string") {
        kept.push(record);
        continue;
      }
      const key = `${name.toLowerCase()}\u0000${JSON.stringify(record)}`;
      if (seen.has(key)) {
        collapsed = true;
        continue;
      }
      seen.add(key);
      kept.push(record);
    }
    if (collapsed && kept.length !== records.length) next[section] = kept;
  }
  return collapsed ? (next as T) : plan;
}

function parentSelectedScope(run: ConsolidationRun, noContext: boolean, selected?: readonly string[]): string[] {
  if (noContext) return [];
  if (selected) return [...selected].sort((left, right) => left.localeCompare(right));
  const names = new Map<string, string>();
  const sourceHashes = run.manifest.sourceHashes;
  for (const name of [...Object.keys(sourceHashes.harness), ...Object.keys(sourceHashes.public)].sort()) {
    if (!MEMORY_FILENAME_RE.test(name) || name.toLowerCase() === "memory.md") continue;
    names.set(name.toLowerCase(), names.get(name.toLowerCase()) ?? name);
  }
  return [...names.values()].sort();
}

async function ensureEmptyIncrementalIndexes(cwd: string, selected: readonly string[]): Promise<void> {
  if (selected.length > 0) return;
  const memory = resolveMemoryPaths(cwd);
  for (const root of [memory.harnessDir, ...(memory.publicDir ? [memory.publicDir] : [])]) {
    await fs.mkdir(root, { recursive: true, mode: 0o700 });
    const rootStat = await fs.lstat(root);
    if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) throw new Error(`Memory root is not a regular directory: ${root}`);
    const entries = await fs.readdir(root, { withFileTypes: true });
    const memoryEntries = entries.filter((entry) => entry.name.toLowerCase().endsWith(".md"));
    if (memoryEntries.length > 0) continue;
    const index = path.join(root, "MEMORY.md");
    let handle: fs.FileHandle | undefined;
    try {
      handle = await fs.open(index, nodeFs.constants.O_CREAT | nodeFs.constants.O_EXCL | nodeFs.constants.O_WRONLY | (nodeFs.constants.O_NOFOLLOW ?? 0), 0o600);
      await handle.writeFile("# Memory Index\n\n", "utf8");
      await handle.sync();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    } finally {
      await handle?.close().catch(() => {});
    }
  }
}

/**
 * Render the parent-owned selected scope for the child task. The child cannot
 * derive this list itself: the snapshot holds session entries, not memory
 * names, so the authoritative scope must be stated in the task header.
 */
export function formatSelectedScopeTaskLines(selectedScope: readonly string[], noContext = false): string[] {
  return [
    `- Selected memory scope (authoritative, complete, JSON): ${JSON.stringify(selectedScope)}`,
    "- Your plan's `selected` array MUST be exactly this list — same names, same casing, no additions or omissions.",
    noContext
      ? "- No-context mode: newMemories MUST be empty. No session knowledge may be created."
      : `- New context-derived files belong only in newMemories (at most ${MAX_NEW_MEMORY_PROPOSALS}), with snapshot evidence; do not add their names to selected or its per-item sections. An empty selected list does not prevent new memory creation.`,
    ...selectedScope.map((name) => `  - ${name}`),
  ];
}

function appendBoundedUtf8Text(current: string, text: string, maxBytes: number): string {
  if (!text) return current;
  const bytes = Buffer.concat([Buffer.from(current, "utf8"), Buffer.from(text, "utf8")]);
  if (bytes.byteLength <= maxBytes) return bytes.toString("utf8");
  return bytes.subarray(bytes.byteLength - maxBytes).toString("utf8");
}

function tailBoundedUtf8Text(text: string, maxBytes = MAX_STDOUT_BYTES): string {
  const bytes = Buffer.from(text, "utf8");
  return bytes.byteLength <= maxBytes ? text : bytes.subarray(bytes.byteLength - maxBytes).toString("utf8");
}

export function completeJsonlSuffix(text: string): string {
  if (!text) return text;
  const lines = text.split("\n");
  while (lines.length > 0 && lines[0].trim()) {
    try {
      JSON.parse(lines[0]);
      break;
    } catch {
      lines.shift();
    }
  }
  return lines.join("\n");
}

export interface ConsolidationEvidence {
  completedToolWork: boolean;
  parentReceiptVerified: boolean;
  planCount: number;
  lastJsonError: string;
  /** Latest planner model execution failure (quota, cooldown, provider error). */
  plannerModelError?: string;
  finalPlan?: unknown;
  attemptUsage?: { input: number; output: number; cacheRead: number; cacheWrite: number; totalTokens: number; cost: number };
}

/** Oversized message_update telemetry is diagnostic stream data, not a plan.
 * It is safe to ignore after JSON parsing; final plans remain subject to the
 * per-line bound in the shared extractor. */
export function isIgnorableOversizedJsonlEvent(line: string): boolean {
  try {
    const event = JSON.parse(line) as { type?: unknown; assistantMessageEvent?: unknown };
    return event?.type === "message_update" && event.assistantMessageEvent !== undefined;
  } catch {
    return false;
  }
}

export function createConsolidationEvidence(): ConsolidationEvidence {
  return { completedToolWork: false, parentReceiptVerified: false, planCount: 0, lastJsonError: "", attemptUsage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0 } };
}

function parseFinalPlan(event: ChildJsonEvent): unknown {
  const serialized = JSON.stringify(event);
  if (!serialized) return undefined;
  const result = extractChildPlan(`${serialized}\n`, {
    maxOutputBytes: MAX_STDOUT_BYTES,
    maxLines: 1,
    maxLineBytes: MAX_JSONL_LINE_BYTES,
    maxPlanBytes: MAX_PLAN_BYTES,
  });
  if (result.ok) return result.plan;
  if (event.type !== "message_end" || event.message?.role !== "assistant") return undefined;
  const content = event.message.content;
  const text = typeof content === "string"
    ? content
    : Array.isArray(content)
      ? content.map((part) => part && typeof part === "object" && !Array.isArray(part) && typeof (part as { text?: unknown }).text === "string" ? (part as { text: string }).text : "").join("")
      : "";
  try {
    const plan = JSON.parse(text) as unknown;
    return plan && typeof plan === "object" && !Array.isArray(plan) && (plan as { kind?: unknown }).kind === "incremental-memory-plan"
      ? plan
      : undefined;
  } catch {
    return undefined;
  }
}

export function recordConsolidationEvent(evidence: ConsolidationEvidence, event: ChildJsonEvent): void {
  if (typeof event.error === "string") evidence.lastJsonError = event.error.slice(-2_000);
  if (event.type === "message_end" && event.message?.role === "assistant") {
    const usage = event.message.usage;
    if (usage && evidence.attemptUsage) {
      evidence.attemptUsage.input += usage.input ?? 0;
      evidence.attemptUsage.output += usage.output ?? 0;
      evidence.attemptUsage.cacheRead += usage.cacheRead ?? 0;
      evidence.attemptUsage.cacheWrite += usage.cacheWrite ?? 0;
      evidence.attemptUsage.totalTokens += usage.totalTokens ?? 0;
      evidence.attemptUsage.cost += usage.cost?.total ?? 0;
    }
    if (event.message.stopReason === "error") {
      evidence.plannerModelError = (event.message.errorMessage || "planner model call failed").slice(-2_000);
    } else if (typeof event.message.stopReason === "string") {
      evidence.plannerModelError = undefined;
    }
  }
  if (event.type === "auto_retry_end") {
    if (event.success === false && typeof event.finalError === "string") {
      evidence.plannerModelError = event.finalError.slice(-2_000);
    } else if (event.success === true) {
      evidence.plannerModelError = undefined;
    }
  }
  if (event.type === "tool_execution_end" && event.isError) {
    evidence.lastJsonError = evidence.lastJsonError || "child tool execution failed";
  }
  const plan = parseFinalPlan(event);
  if (plan !== undefined) {
    evidence.plannerModelError = undefined;
    evidence.planCount += 1;
    evidence.finalPlan = plan;
  }
}

/**
 * Split plan-phase failures: a planner model execution error (quota, cooldown,
 * provider outage) is not a rejected plan — a fresh planner inherits the same
 * failing model, so the parent must label it and skip the retry. Child stderr
 * output indicates the worker itself misbehaved, which stays retryable.
 */
export function classifyPlanPhaseFailure(
  evidence: ConsolidationEvidence,
  stderr: string,
): { kind: "model-error"; detail: string } | { kind: "missing-plan"; detail: string } {
  const stderrDetail = stderr.trim();
  if (stderrDetail) return { kind: "missing-plan", detail: stderrDetail };
  if (evidence.plannerModelError) return { kind: "model-error", detail: evidence.plannerModelError };
  return { kind: "missing-plan", detail: evidence.lastJsonError };
}

/** Non-zero completion reason: a parent-timer termination is its own budget failure. */
export function plannerFailureReason(
  args: { timedOut: boolean; stderrDetail: string; lastJsonError: string; exitCode: number | null },
): string {
  if (args.timedOut) {
    const budget = `planner exceeded the dreaming budget (${Math.round(DREAM_TIMEOUT_MS / 60_000)} minutes) and was terminated`;
    return args.stderrDetail ? `${budget} (stderr: ${args.stderrDetail.slice(0, 200)})` : budget;
  }
  return args.stderrDetail || args.lastJsonError || `exit code ${args.exitCode}`;
}

/** Keep the causal head of a rejection reason; truncate for the notification budget. */
export function clipRejectionReason(reason: string, budget = 240): string {
  return reason.length <= budget ? reason : `${reason.slice(0, budget)}…`;
}

/** Feedback lines injected into the fresh planner's task header on retry attempts. */
export function buildTaskFeedbackLines(rejectionFeedback?: string): string[] {
  if (!rejectionFeedback) return [];
  return [`- Previous planning attempt was rejected: ${rejectionFeedback.slice(0, 800)} — produce a corrected plan that resolves every cited issue.`];
}

function finalAssistantText(stdout: string): string {
  let latest = "";
  for (const line of stdout.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const event = JSON.parse(line) as ChildJsonEvent;
      if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
      const content = event.message.content;
      latest = typeof content === "string"
        ? content
        : Array.isArray(content)
          ? content.map((part) => part && typeof part === "object" && !Array.isArray(part) && typeof (part as { text?: unknown }).text === "string" ? (part as { text: string }).text : "").join("")
          : "";
    } catch {
      // Only complete assistant message records are eligible repair input.
    }
  }
  return latest;
}

function parseIncrementalPlanText(text: string): unknown | undefined {
  const trimmed = text.trim();
  const candidates = [trimmed, /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(trimmed)?.[1]].filter((value): value is string => Boolean(value));
  for (const candidate of candidates) {
    try {
      const plan = JSON.parse(candidate) as unknown;
      if (plan && typeof plan === "object" && !Array.isArray(plan) && (plan as { kind?: unknown }).kind === "incremental-memory-plan") return plan;
    } catch {
      // The repair contract requires one exact JSON object.
    }
  }
  return undefined;
}

export interface IncrementalMemoryRepairInput {
  rejectedPlan: unknown;
  errors: readonly string[];
  selectedNames: readonly string[];
  identity: { runId: string; scopeKey: string; scopeDigest: string; artifactHash: string; snapshotDigest: string };
  model?: string;
  signal?: AbortSignal;
}

export async function repairIncrementalMemoryPlan(input: IncrementalMemoryRepairInput): Promise<{
  outcome: "repaired" | "failed" | "cancelled";
  durationMs: number;
  plan?: unknown;
  usage?: Awaited<ReturnType<typeof runPiWorker>>["usage"];
  error?: string;
}> {
  const startedAt = Date.now();
  const prompt = [
    "Task: repair one rejected incremental Memory delta plan.",
    "Return exactly one JSON object and no prose. Preserve the supplied identity and selected scope.",
    "Change only fields needed to resolve every bounded validation error.",
    "Use only the supplied JSON; do not request additional context or rerun planning.",
    JSON.stringify({
      identity: input.identity,
      selectedNames: [...input.selectedNames],
      errors: input.errors.map((error) => error.slice(0, 800)).slice(0, 16),
      rejectedPlan: input.rejectedPlan,
    }),
  ].join("\n");
  const result = await runPiWorker({
    prompt,
    cwd: os.tmpdir(),
    tools: [],
    model: input.model,
    signal: input.signal,
    minimal: true,
    extraArgs: learningPlannerArgs(),
  });
  const durationMs = Date.now() - startedAt;
  if (result.cancelled) return { outcome: "cancelled", durationMs, usage: result.usage, error: result.stderr };
  if (result.exitCode !== 0) return { outcome: "failed", durationMs, usage: result.usage, error: result.stderr };
  const plan = parseIncrementalPlanText(result.text);
  return plan
    ? { outcome: "repaired", durationMs, plan, usage: result.usage }
    : { outcome: "failed", durationMs, usage: result.usage, error: "repair returned no exact incremental-memory-plan object" };
}

export function missingConsolidationEvidence(evidence: ConsolidationEvidence): string[] {
  const missing: string[] = [];
  if (!evidence.completedToolWork) missing.push("completed tool work");
  if (evidence.planCount !== 1) missing.push("exactly one schema-valid consolidation plan");
  if (!evidence.parentReceiptVerified) missing.push("a parent-owned validation receipt");
  return missing;
}

// A full-scope run reads every selected memory file plus repository grounding;
// a measured 30-file pass took ~11 minutes, so keep headroom above that.
const DREAM_TIMEOUT_MS = 30 * 60 * 1000;
const runModeById = new Map<string, LearningMode>();

const dreamingWidget = createLiveActivityWidget({
  key: "memory-dreaming",
  placement: "aboveEditor",
  fit: truncateToWidth,
  leadingSpaces: 0,
});
let dreamingActivity = "";

function setDreamingActivity(activity: string): void {
  dreamingActivity = activity;
}

function setDreamingWidget(ctx: ExtensionContext, activity = "starting"): void {
  setDreamingActivity(activity);
  dreamingWidget.update(ctx, [{ id: "dreaming", identity: "Dreaming...", activity: dreamingActivity }]);
}

function availableMemoryModels(ctx: ExtensionContext) {
  const models =
    typeof ctx.modelRegistry.getAll === "function"
      ? ctx.modelRegistry.getAll()
      : ctx.scopedModels.length > 0
        ? ctx.scopedModels.map((scoped) => scoped.model)
        : ctx.modelRegistry.getAvailable();
  return sortModels(models);
}

function isAllowedMemoryModel(ctx: ExtensionContext, provider: string, model: string): boolean {
  return availableMemoryModels(ctx).some((candidate) => candidate.provider === provider && candidate.id === model);
}

function configuredMemoryModel(): string {
  return modelRef(memoryConfig) ?? "(not configured)";
}

function saveMemoryConfig(next: MemoryConfig): void {
  writeMemoryConfig(next);
  memoryConfig = next;
  memoryConfigState = { config: next, present: true };
}

async function chooseMemoryModel(ctx: ExtensionContext): Promise<void> {
  const result = await searchModelFromPicker(
    ctx.ui,
    availableMemoryModels(ctx),
    configuredMemoryModel(),
    { title: "Select a memory model" },
  );
  if (!result) return;
  saveMemoryConfig(result);
  notifyPi(ctx.ui, `Memory model set to ${result.provider}/${result.model}`, "info");
}

async function enterMemoryModel(ctx: ExtensionContext): Promise<void> {
  const result = await enterModelFromInput(ctx.ui, ctx.modelRegistry, modelRef(memoryConfig), { label: "Memory model" });
  if (!result) return;
  if (!isAllowedMemoryModel(ctx, result.provider, result.model)) {
    notifyPi(ctx.ui, `Model ${result.provider}/${result.model} is not allowed for memory workers`, "error");
    return;
  }
  saveMemoryConfig(result);
  notifyPi(ctx.ui, `Memory model set to ${result.provider}/${result.model}`, "info");
}

async function setMemoryModel(value: string, ctx: ExtensionContext): Promise<void> {
  const ref = parseModelRef(value);
  if (!ref) {
    notifyPi(ctx.ui, "Enter a model in provider/model format", "error");
    return;
  }
  if (!isAllowedMemoryModel(ctx, ref.provider, ref.model)) {
    notifyPi(ctx.ui, `Model ${ref.provider}/${ref.model} is not allowed for memory workers`, "error");
    return;
  }
  saveMemoryConfig(ref);
  notifyPi(ctx.ui, `Memory model set to ${ref.provider}/${ref.model}`, "info");
}

function clearDreamingWidget(ctx: ExtensionContext): void {
  dreamingActivity = "";
  dreamingWidget.clear(ctx);
}

const execFileAsync = promisify(execFile);

/** Python validator errors already embed their category in the message; keep one prefix. */
export function formatValidatorErrorEntry(e: { code?: string; message?: string }): string {
  const code = e.code ?? "error";
  const message = e.message ?? JSON.stringify(e);
  return message.startsWith(`${code}: `) ? message : `${code}: ${message}`;
}

async function runConsolidationValidator(
  pkgDir: string,
  run: ConsolidationRun,
  planPath: string,
  check: string,
  expectedSelected: readonly string[],
  receiptPath?: string,
  receiptAfterMs?: number,
): Promise<Record<string, unknown>> {
  const args = [
    path.join(pkgDir, "scripts", "validate-consolidate.py"),
    "--plan", planPath,
    "--snapshot", run.manifest.snapshotPath,
    "--repo-root", run.manifest.cwd,
    "--expected-run-id", run.manifest.runId,
    `--expected-scope-key=${run.manifest.scopeKey}`,
    "--expected-scope-digest", run.manifest.scopeDigest,
    "--expected-artifact-hash", run.manifest.snapshotDigest,
    "--mode", runModeById.get(run.manifest.runId) ?? "manual",
    "--expected-run-dir", run.manifest.runDir,
    "--expected-selected", JSON.stringify([...expectedSelected].sort()),
    "--check", check,
  ];
  if (receiptPath) {
    args.push("--receipt", receiptPath, "--harness", run.manifest.harnessDir, "--expected-receipt-phase", "post");
    if (run.manifest.publicDir) args.push("--public", run.manifest.publicDir);
    if (receiptAfterMs !== undefined) args.push("--expected-receipt-after", String(receiptAfterMs / 1000));
  }
  let rawStdout: string;
  try {
    const result = await execFileAsync("python3", args, { maxBuffer: 10 * 1024 * 1024 });
    rawStdout = result.stdout;
  } catch (err: unknown) {
    const maybe = err as { stdout?: string; stderr?: string; message?: string };
    rawStdout = typeof maybe.stdout === "string" ? maybe.stdout : "";
    if (!rawStdout.trim()) {
      throw new Error(`Consolidation validator failed: ${maybe.message ?? String(err)}${maybe.stderr ? ` — ${maybe.stderr.slice(0, 800)}` : ""}`);
    }
  }
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(rawStdout.trim()) as Record<string, unknown>;
  } catch {
    throw new Error(`Consolidation validator returned invalid JSON: ${rawStdout.trim().slice(0, 800)}`);
  }
  if (parsed.ok !== true) {
    const errs = Array.isArray((parsed as { errors?: unknown }).errors)
      ? (parsed.errors as Array<{ code?: string; message?: string }>).map(formatValidatorErrorEntry).join("; ")
      : rawStdout.trim().slice(0, 1200);
    throw new Error(`Consolidation validator rejected the plan: ${errs}`);
  }
  const binding = parsed.details && typeof parsed.details === "object" && !Array.isArray(parsed.details)
    ? (parsed.details as Record<string, unknown>).binding
    : undefined;
  if (!binding || typeof binding !== "object" || Array.isArray(binding)) {
    throw new Error("Consolidation validator omitted its structured parent binding");
  }
  const bindingRecord = binding as Record<string, unknown>;
  if (
    bindingRecord.runId !== run.manifest.runId ||
    bindingRecord.scopeDigest !== run.manifest.scopeDigest ||
    bindingRecord.artifactHash !== run.manifest.snapshotDigest ||
    bindingRecord.runDir !== path.resolve(run.manifest.runDir)
  ) {
    throw new Error("Consolidation validator returned an unrelated structured binding");
  }
  if (receiptPath && bindingRecord.receiptPath !== path.resolve(receiptPath)) {
    throw new Error("Consolidation validator receipt binding mismatch");
  }
  return parsed;
}

/**
 * Run the consolidation procedure in the background so the current session
 * stays responsive. The configured memory model is passed to the background
 * run when available. A "dreaming" widget shows progress until it exits.
 */
async function spawnAsyncConsolidation(
  ctx: ExtensionContext,
  state: DreamState,
  opts: {
    pkgDir: string;
    cwd: string;
    noContext?: boolean;
    reason: string;
    attempt?: number;
    rejectionFeedback?: string;
    mode?: LearningMode;
    selectedScope?: readonly string[];
    dossierPath?: string;
    dossierDigest?: string;
    selectedSourceDigest?: string;
    applyChanges?: boolean;
  },
): Promise<boolean> {
  const attempt = opts.attempt ?? 0;
  const incremental = opts.mode !== "full" && !opts.noContext;
  const attemptStartedAt = Date.now();
  if (state.active && attempt === 0) {
    notifyPi(ctx.ui, "Memory consolidation is already running in background.", "info");
    return false;
  }
  if (memoryConfigState.invalid) {
    notifyPi(ctx.ui, `Memory consolidation is blocked: ${memoryConfigState.invalid}`, "error");
    return false;
  }
  state.active = true;
  state.outcome = undefined;
  const generation = state.generation + 1;
  state.generation = generation;
  state.cancelled = false;
  const isGenerationCurrent = (): boolean => !state.cancelled && generation === state.generation;

  let run: ConsolidationRun;
  try {
    run = await createConsolidationRun(ctx, opts.cwd, opts.noContext, opts.applyChanges === false ? false : normalizeTrackedMemory);
  } catch (err: unknown) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      notifyPi(ctx.ui, `Memory consolidation setup failed: ${(err as Error).message}`, "error");
    }
    return false;
  }
  if (!isGenerationCurrent()) {
    await releaseConsolidationRun(run);
    return false;
  }
  try {
    if (incremental) {
      if (!opts.dossierPath || !opts.dossierDigest || !opts.selectedSourceDigest) {
        throw new Error("incremental Memory run is missing its bound dossier state");
      }
      const dossierBytes = await fs.readFile(opts.dossierPath);
      if (sha256Digest(dossierBytes) !== opts.dossierDigest) {
        throw new Error("incremental dossier changed after selection");
      }
      const currentSourceHashes = {
        harness: await hashMemoryRoot(run.manifest.harnessDir),
        public: run.manifest.publicDir ? await hashMemoryRoot(run.manifest.publicDir) : {},
      };
      if (sha256Digest(JSON.stringify(currentSourceHashes)) !== opts.selectedSourceDigest) {
        throw new Error("selected Memory changed after incremental selection");
      }
    }
  } catch (error) {
    await releaseConsolidationRun(run);
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
    }
    throw error;
  }
  state.run = run;
  runModeById.set(run.manifest.runId, opts.mode ?? "manual");
  const selectedScope = parentSelectedScope(run, Boolean(opts.noContext), opts.selectedScope);
  if (run.normalization.repaired.length > 0 || run.normalization.removed.length > 0) {
    notifyPi(ctx.ui,
      `Memory consolidation normalized mirrors before planning: ${run.normalization.repaired.length} repaired, ${run.normalization.removed.length} removed`,
      "info",
    );
  }

  let procedure: string;
  try {
    procedure = incremental
      ? buildIncrementalMemoryConsolidatorPrompt({
          runId: run.manifest.runId,
          scopeKey: run.manifest.scopeKey,
          scopeDigest: run.manifest.scopeDigest,
          artifactHash: run.manifest.snapshotDigest,
          snapshotDigest: run.manifest.snapshotDigest,
          dossierPath: opts.dossierPath ?? "",
        })
      : buildMemoryConsolidatorPrompt({
          pkgDir: opts.pkgDir,
          runId: run.manifest.runId,
          scopeDigest: run.manifest.scopeDigest,
          scopeKey: run.manifest.scopeKey,
          artifactHash: run.manifest.snapshotDigest,
          snapshotDigest: run.manifest.snapshotDigest,
          runDir: run.manifest.runDir,
          snapshotPath: run.manifest.snapshotPath,
          harnessDir: run.manifest.harnessDir,
          publicDir: run.manifest.publicDir ?? "(disabled for this non-project directory)",
          repoRoot: run.manifest.cwd,
        });
  } catch (err: unknown) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      notifyPi(ctx.ui, `Memory consolidation setup failed: ${(err as Error).message}`, "error");
    }
    await releaseConsolidationRun(run);
    return false;
  }

  const taskText = [
    `Task: produce a read-only structured consolidation plan for the project at ${opts.cwd}.`,
    `- Reason: ${opts.reason}`,
    ...buildTaskFeedbackLines(opts.rejectionFeedback),
    `- Context mode: ${opts.noContext ? "no-context (do not capture session context)" : "parent-provided immutable snapshot"}`,
    ...(incremental
      ? [
          `- Authoritative selected Memory names: ${JSON.stringify(selectedScope)}`,
        ]
      : [
          `- Pre-run mirror normalization: ${JSON.stringify({ repaired: run.normalization.repaired, removed: run.normalization.removed })}`,
          ...formatSelectedScopeTaskLines(selectedScope, Boolean(opts.noContext)),

        ]),
    "",
    procedure,
  ].join("\n");

  const cli = resolvePiCli();
  if (!cli) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      notifyPi(ctx.ui, "Memory consolidation: could not resolve the Pi CLI", "error");
    }
    await releaseConsolidationRun(run);
    return false;
  }

  let child: ChildProcess;
  try {
    const taskFile = path.join(run.manifest.runDir, "task.md");
    nodeFs.writeFileSync(taskFile, taskText, { mode: 0o600 });
    const modelArgs = memoryConfig.provider && memoryConfig.model
      ? ["--model", `${memoryConfig.provider}/${memoryConfig.model}`]
      : [];
    const workerEnv = Object.fromEntries(
      Object.entries({
        PATH: process.env.PATH,
        HOME: process.env.HOME,
        PI_CODING_AGENT_DIR: process.env.PI_CODING_AGENT_DIR,
        LANG: process.env.LANG,
        TERM: process.env.TERM,
      }).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
    );
    child = spawnPiChild(
      cli.command,
      [
        ...cli.args,
        ...minimalPiWorkerArgs(incremental ? ["read"] : ["read", "grep", "find", "ls"]),
        ...modelArgs,
        ...learningPlannerArgs(),
        `@${taskFile}`,
      ],
      { cwd: opts.cwd, env: workerEnv, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (err: unknown) {
    if (isGenerationCurrent()) state.outcome = "failed";
    state.active = false;
    await releaseConsolidationRun(run);
    if (isGenerationCurrent()) notifyPi(ctx.ui, `Memory consolidation spawn failed: ${(err as Error).message}`, "error");
    return false;
  }

  state.child = child;
  setDreamingActivity(incremental ? "memory delta" : "full memory");

  let stdoutBuffer = "";
  let stdoutCapture = "";
  let stdoutCaptureBytes = 0;
  let stdoutLineCount = 0;
  let stdoutCaptureOverflowed = false;
  let outputLimitReason = "";
  const activitySummary: string[] = [];
  const noteActivity = (entry: string): void => {
    activitySummary.push(entry);
    if (activitySummary.length > 200) activitySummary.shift();
  };
  const stdoutDecoder = new TextDecoder("utf-8");
  const stderrDecoder = new TextDecoder("utf-8");
  const evidence = createConsolidationEvidence();
  const stopForOutputLimit = (reason: string): void => {
    outputLimitReason = reason;
    if (stdoutCaptureOverflowed) return;
    stdoutCaptureOverflowed = true;
    stdoutBuffer = "";
    stdoutCapture = "";
    void terminateConsolidationChild(child, 5_000).catch(() => {});
  };
  const handleJsonLine = (line: string): void => {
    if (!line.trim()) return;
    try {
      const event = JSON.parse(line) as ChildJsonEvent;
      recordConsolidationEvent(evidence, event);
      if (event.type !== "tool_execution_start" || !event.toolName) return;

      const name = event.toolName;
      let detail = "";
      if (event.args) {
        if (typeof event.args.path === "string") {
          detail = path.basename(event.args.path);
        } else if (typeof event.args.command === "string") {
          const cmd = event.args.command.trim();
          if (cmd.includes("validate-consolidate")) {
            detail = "validate-consolidate.py";
          } else {
            const compact = cmd.replace(/\s+/g, " ");
            detail = compact.length > 32 ? `${compact.slice(0, 32)}…` : compact;
          }
        }
      }
      dreamingActivity = name === "bash" ? detail : detail ? `${name} ${detail}` : name;
      noteActivity(`tool ${name}${detail ? ` ${detail}` : ""}`);
    } catch {
      // ignore non-JSON output
    }
  };
  const handleJsonLineWithinBounds = (line: string): void => {
    if (!line.trim()) return;
    stdoutLineCount += 1;
    if (stdoutLineCount > MAX_JSONL_LINES) {
      stopForOutputLimit(`child JSONL exceeded ${MAX_JSONL_LINES} records`);
      return;
    }
    if (Buffer.byteLength(line, "utf8") > MAX_JSONL_LINE_BYTES) {
      if (isIgnorableOversizedJsonlEvent(line)) return;
      stopForOutputLimit(`child JSONL line exceeded ${MAX_JSONL_LINE_BYTES} bytes`);
      return;
    }
    handleJsonLine(line);
  };
  const consumeStdoutText = (text: string): void => {
    if (stdoutCaptureOverflowed) return; // child output limit exceeded
    if (!text) return;
    stdoutBuffer += text;
    let newline = stdoutBuffer.indexOf("\n");
    while (newline >= 0) {
      const line = stdoutBuffer.slice(0, newline);
      stdoutBuffer = stdoutBuffer.slice(newline + 1);
      handleJsonLineWithinBounds(line);
      if (stdoutCaptureOverflowed) return;
      newline = stdoutBuffer.indexOf("\n");
    }
    // Do not reject an unterminated telemetry line before it reaches the
    // parser. The total stdout bound above remains the memory safety circuit;
    // complete lines are checked by handleJsonLineWithinBounds.
  };
  child.stdout?.on("data", (chunk: Buffer) => {
    if (stdoutCaptureOverflowed) return; // child output limit exceeded
    stdoutCaptureBytes += chunk.byteLength;
    if (stdoutCaptureBytes > MAX_STDOUT_BYTES) {
      stopForOutputLimit(`child stdout exceeded ${MAX_STDOUT_BYTES} bytes`);
      return;
    }
    const text = stdoutDecoder.decode(chunk, { stream: true });
    stdoutCapture += text;
    if (Buffer.byteLength(stdoutCapture, "utf8") > MAX_STDOUT_BYTES) {
      stopForOutputLimit(`child stdout exceeded ${MAX_STDOUT_BYTES} bytes`);
      return;
    }
    consumeStdoutText(text);
  });

  let stderr = "";
  child.stderr?.on("data", (chunk: Buffer) => {
    const text = stderrDecoder.decode(chunk, { stream: true });
    stderr = appendBoundedUtf8Text(stderr, text, MAX_STDERR_BYTES);
  });

  const timer = setTimeout(() => {
    timedOut = true;
    void terminateConsolidationChild(child, 5_000);
  }, DREAM_TIMEOUT_MS);
  timer.unref?.();

  let resolveCompletion!: () => void;
  const completion = new Promise<void>((resolve) => { resolveCompletion = resolve; });
  state.completion = completion;
  let finished = false;
  let failureRecorded = false;
  let mutatedMemory = false;
  let appliedOperationCount = 0;
  let proposed = false;
  let timedOut = false;
  let repairAttempt: LearningAttempt | undefined;
  /** Full maintenance retains the existing fresh-planner retry. Incremental
   * runs never replay the dossier or selected Memory bodies. */
  const retryPlanPhase = async (reason: string, failure: "syntax" | "validation" | "model" | "timeout" | "cancelled" | "output-limit" | "stale" | "other" = "validation"): Promise<void> => {
    if (opts.mode !== "full" || !shouldRetryPlanner({ mode: "full", phase: "memory", attempt, failure, mutated: mutatedMemory })) {
      notifyPi(ctx.ui, `Memory dreaming failed: ${clipRejectionReason(reason)}`, "error");
      return;
    }
    await releaseConsolidationRun(run, { keepArtifacts: true });
    state.run = undefined;
    await spawnAsyncConsolidation(ctx, state, { ...opts, attempt: attempt + 1, rejectionFeedback: reason });
  };
  const failWithPlannerModelError = (detail: string): void => {
    state.outcome = "failed";
    notifyPi(ctx.ui,
      `Memory dreaming failed: planner model error: ${clipRejectionReason(detail)}; the fresh-planner retry is skipped because it inherits the same failing model`,
      "error",
    );
  };
  const persistRunDiagnostics = async (): Promise<void> => {
    failureRecorded = true;
    try {
      const marker = outputLimitReason ? `\n[truncated: ${outputLimitReason}]\n` : "";
      const boundedStdout = tailBoundedUtf8Text(`${stdoutCapture}${marker}`);
      await writeFileAtomic(run.paths.stdoutFile, completeJsonlSuffix(boundedStdout));
      await writeFileAtomic(run.paths.stderrFile, tailBoundedUtf8Text(stderr));
      await writeFileAtomic(run.paths.activitySummaryFile, `${JSON.stringify(activitySummary, null, 1)}\n`);
    } catch {
      // Diagnostics are best-effort; never mask the original failure.
    }
  };
  const finish = async (code: number | null, error?: Error): Promise<void> => {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    const ownsCurrentRun = (): boolean => !state.cancelled && generation === state.generation && state.run === run;
    if (ownsCurrentRun()) {
      const stdoutTail = stdoutDecoder.decode();
      if (stdoutTail) {
        stdoutCapture += stdoutTail;
        consumeStdoutText(stdoutTail);
      }
      if (!stdoutCaptureOverflowed && stdoutBuffer) {
        handleJsonLineWithinBounds(stdoutBuffer);
        stdoutBuffer = "";
      }
    }
    stderr = appendBoundedUtf8Text(stderr, stderrDecoder.decode(), MAX_STDERR_BYTES);
    if (ownsCurrentRun()) {
      if (state.child === child) state.child = undefined;
      state.active = false;
    }
    try {
      if (!ownsCurrentRun()) return;
      if (error) {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        state.outcome = "failed";
        notifyPi(ctx.ui, `Memory dreaming failed to start: ${error.message}`, "error");
      } else if (code === 0) {
        const extracted = stdoutCaptureOverflowed
          ? { ok: false as const, error: `child stdout exceeded ${MAX_STDOUT_BYTES} bytes` }
          : extractChildPlan(stdoutCapture, {
              expectedIdentity: {
                runId: run.manifest.runId,
                scopeDigest: run.manifest.scopeDigest,
                artifactHash: run.manifest.snapshotDigest,
              },
              maxOutputBytes: MAX_STDOUT_BYTES,
              maxLines: MAX_JSONL_LINES,
              maxLineBytes: MAX_JSONL_LINE_BYTES,
              maxPlanBytes: MAX_PLAN_BYTES,
            });
        if (!extracted.ok) {
          evidence.finalPlan = undefined;
          evidence.planCount = 0;
          evidence.lastJsonError = extracted.error;
        } else {
          evidence.finalPlan = extracted.plan;
          evidence.planCount = 1;
        }
        if (!ownsCurrentRun()) return;
        const assistantText = finalAssistantText(stdoutCapture);
        let rawPlan: unknown = evidence.finalPlan ? collapseDuplicatePlanRecords(evidence.finalPlan) : undefined;
        if (!rawPlan && incremental) rawPlan = parseIncrementalPlanText(assistantText);
        let rejectedPlan: unknown = rawPlan;
        let plan: unknown;
        let incrementalError: string | undefined;
        if (rawPlan && incremental) {
          try {
            plan = await expandIncrementalMemoryPlan(run, selectedScope, rawPlan);
          } catch (error) {
            incrementalError = (error as Error).message;
          }
        } else {
          plan = rawPlan;
        }
        if (incremental && rejectedPlan && !plan && incrementalError) {
          const repair = await repairIncrementalMemoryPlan({
            rejectedPlan,
            errors: [incrementalError],
            selectedNames: selectedScope,
            identity: {
              runId: run.manifest.runId,
              scopeKey: run.manifest.scopeKey,
              scopeDigest: run.manifest.scopeDigest,
              artifactHash: run.manifest.snapshotDigest,
              snapshotDigest: run.manifest.snapshotDigest,
            },
            model: memoryConfig.provider && memoryConfig.model ? `${memoryConfig.provider}/${memoryConfig.model}` : undefined,
            signal: state.controller?.signal,
          });
          repairAttempt = {
            phase: "memory",
            attempt: 1,
            outcome: repair.outcome === "repaired" ? "noop" : repair.outcome,
            durationMs: repair.durationMs,
            operations: 0,
            usage: repair.usage,
          };
          if (repair.outcome === "repaired" && repair.plan) {
            try {
              rawPlan = repair.plan;
              plan = await expandIncrementalMemoryPlan(run, selectedScope, repair.plan);
              evidence.finalPlan = repair.plan;
              evidence.planCount = 1;
            } catch (error) {
              incrementalError = (error as Error).message;
              repairAttempt.outcome = "rejected";
            }
          } else {
            incrementalError = repair.error || incrementalError;
          }
        }
        if (!plan || (evidence.planCount !== 1 && !incremental)) {
          await persistRunDiagnostics();
          if (!ownsCurrentRun()) return;
          const failure = classifyPlanPhaseFailure(evidence, stderr);
          if (failure.kind === "model-error" && !timedOut) {
            failWithPlannerModelError(failure.detail);
            return;
          }
          const detail = incrementalError || failure.detail || evidence.lastJsonError;
          if (attempt === 0 && opts.mode === "full") {
            await retryPlanPhase(`missing exactly one schema-valid consolidation plan${detail ? ` (${clipRejectionReason(detail, 300)})` : ""}`, "syntax");
            return;
          }
          notifyPi(ctx.ui,
            `Memory dreaming finished without verified consolidation: missing exactly one schema-valid consolidation plan${detail ? ` (${clipRejectionReason(detail, 300)})` : ""}`,
            "warning",
          );
          state.outcome = "unverified";
        } else {
          const planPath = path.join(run.manifest.runDir, "plan.json");
          const planText = `${JSON.stringify(plan, null, 2)}\n`;
          const planDigest = sha256Digest(planText);
          const preSelected = normalizeSelectedScope(plan);
          const expectedSelected = parentSelectedScope(run, Boolean(opts.noContext), opts.selectedScope);
          if (JSON.stringify(preSelected) !== JSON.stringify(expectedSelected)) {
            throw new Error("Consolidation plan selected scope does not match the parent snapshot scope");
          }
          await fs.writeFile(planPath, planText, { encoding: "utf8", mode: 0o600 });
          if (!ownsCurrentRun()) return;
          await runConsolidationValidator(opts.pkgDir, run, planPath, "plan", expectedSelected);
          if (!ownsCurrentRun()) return;
          if (opts.applyChanges === false) {
            const candidate = plan as { operations?: unknown[]; newMemories?: unknown[] };
            proposed = (candidate.operations?.length ?? 0) + (candidate.newMemories?.length ?? 0) > 0;
            if (proposed) await recordLearningProposal(opts.cwd, "memory", plan);
            state.outcome = "completed";
            return;
          }
          const preReceipt = createPreApplyReceipt({
            runId: run.manifest.runId,
            scopeDigest: run.manifest.scopeDigest,
            artifactHash: run.manifest.snapshotDigest,
            selected: preSelected,
            sourceHashes: run.manifest.sourceHashes,
            planDigest,
          });
          if (!ownsCurrentRun()) return;
          await writeConsolidationReceipt(run, preReceipt, "pre");
          if (!ownsCurrentRun()) return;
          const mutationStartedAt = Date.now();
          const memoryPlan = plan as { operations?: Array<{ name: string }>; newMemories?: Array<{ name: string }> };
          const mutationFiles = memoryMutationFiles(opts.cwd, [...(memoryPlan.operations ?? []), ...(memoryPlan.newMemories ?? [])].map(operation => operation.name));
          const applied = await recordLearningMutation(opts.cwd, "memory", mutationFiles, () => applyConsolidationPlan(run, plan, ownsCurrentRun), plan);
          mutatedMemory = true;
          const existingOperations = Array.isArray((plan as { operations?: unknown }).operations)
            ? (plan as { operations: unknown[] }).operations.length
            : 0;
          appliedOperationCount = existingOperations + applied.created.length;
          if (!ownsCurrentRun()) return;
          const receipt = createConsolidationReceipt(run.manifest, applied.selected, applied.finalState, planDigest, applied.created, summarizeMemoryChanges(plan));
          const receiptPath = await writeConsolidationReceipt(run, receipt);
          if (!ownsCurrentRun()) return;
          await runConsolidationValidator(opts.pkgDir, run, planPath, "plan,receipt,privacy", preSelected, receiptPath, mutationStartedAt);
          if (!ownsCurrentRun()) return;
          evidence.completedToolWork = true;
          evidence.parentReceiptVerified = true;
          const missing = missingConsolidationEvidence(evidence);
          if (missing.length === 0) {
            state.outcome = "completed";
          } else {
            state.outcome = "unverified";
            notifyPi(ctx.ui, `Memory dreaming finished without verified consolidation: missing ${missing.join(", ")}`, "warning");
          }
        }
      } else {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        const failure = classifyPlanPhaseFailure(evidence, stderr);
        if (failure.kind === "model-error" && !timedOut) {
          failWithPlannerModelError(failure.detail);
          return;
        }
        const errReason = plannerFailureReason({
          timedOut,
          stderrDetail: stderr.trim(),
          lastJsonError: evidence.lastJsonError,
          exitCode: code,
        });
        if (attempt === 0 && opts.mode === "full") {
          await retryPlanPhase(errReason, timedOut ? "timeout" : outputLimitReason ? "output-limit" : "other");
          return;
        }
        state.outcome = "failed";
        notifyPi(ctx.ui, `Memory dreaming failed: ${clipRejectionReason(errReason)}`, "error");
      }
    } catch (finishError: unknown) {
      if (ownsCurrentRun()) {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        const message = (finishError as Error).message;
        if (!mutatedMemory && attempt === 0 && opts.mode === "full") {
          await retryPlanPhase(message, /sources changed|snapshot/i.test(message) ? "stale" : "validation");
          return;
        }
        state.outcome = "failed";
        notifyPi(ctx.ui, `Memory consolidation verification failed: ${message}`, "error");
      }
    } finally {
      try {
        // Ownership must be captured before state.run is cleared: the retention
        // decision may not depend on a check that just became false.
        const ownedNow = generation === state.generation && !state.cancelled && state.run === run;
        if (ownedNow) state.run = undefined;
        await releaseConsolidationRun(run, { keepArtifacts: failureRecorded && ownedNow });
        runModeById.delete(run.manifest.runId);
      } finally {
        state.attempts?.push({
          phase: "memory",
          attempt,
          outcome: repairAttempt
            ? state.cancelled ? "cancelled" : "rejected"
            : state.cancelled ? "cancelled" : state.outcome === "completed" ? proposed ? "proposed" : appliedOperationCount > 0 ? "applied" : "noop" : state.outcome === "unverified" ? "rejected" : "failed",
          durationMs: Date.now() - attemptStartedAt,
          operations: repairAttempt ? 0 : appliedOperationCount,
          usage: evidence.attemptUsage,
        });
        if (repairAttempt) {
          repairAttempt.outcome = state.cancelled
            ? "cancelled"
            : state.outcome === "completed"
              ? proposed ? "proposed" : appliedOperationCount > 0 ? "applied" : "noop"
              : state.outcome === "unverified" ? "rejected" : "failed";
          repairAttempt.operations = state.outcome === "completed" ? appliedOperationCount : 0;
          state.attempts?.push(repairAttempt);
        }
        resolveCompletion();
        if (state.completion === completion) state.completion = undefined;
      }
    }
  };

  child.on("error", (err) => { void finish(null, err); });
  child.on("close", (code) => { void finish(code); });
  // Keep the worker referenced until close: its pipes can end before its exit,
  // and headless callers must remain alive for parent validation and receipts.
  return true;
}

/**
 * Full consolidation pipeline: the memory phase first; only a verified,
 * context-captured memory phase unlocks the harness phase, which in turn
 * hands off to the AGENTS.md phase against the same snapshot. Later phases
 * own their own single-flight guard, so their failures never invalidate
 * applied earlier-phase results, and session shutdown cancels any phase.
 */
async function startConsolidationPipeline(
  ctx: ExtensionContext,
  state: DreamState,
  opts: { pkgDir: string; cwd: string; noContext?: boolean; reason: string; availableSkills: readonly string[]; mode: LearningMode; reportResult?: boolean; reportReceipt?: (receipt: LearningPipelineReceipt) => void },
): Promise<void> {
  if (state.pipeline) return state.pipeline;
  let pipelineScreen: LearningScreen | undefined;
  let selectorRun: ConsolidationRun | undefined;
  let acquiredLaterRun: ConsolidationRun | undefined;
  setDreamingWidget(ctx, opts.mode === "full" || opts.noContext ? "preparing full maintenance" : "selecting current task");
  state.cleanup = () => clearDreamingWidget(ctx);
  const pipeline = (async () => {
    const recoveryLock = await acquireConsolidationLock(resolveConsolidationRunPaths(opts.cwd));
    try { await recoverPendingAgentsMdConsolidations(opts.cwd); }
    finally { await recoveryLock.release(); }
    await recoverLearningUndo(opts.cwd);
    await checkPendingLearningMutations(opts.cwd);
    const policies = automaticPhasePolicies(await readSettings(opts.cwd), opts.mode);
    const fullMode = opts.mode === "full" || Boolean(opts.noContext);
    const completeEntries = snapshotEntries(ctx);
    const taskSlice = currentTaskSlice(completeEntries);
    const taskContext = snapshotSessionContext(ctx, fullMode ? undefined : taskSlice.entries);
    const frozenContext = opts.noContext ? ctx : taskContext;
    const screen: LearningScreen = opts.noContext
      ? { memory: true, harness: false, agents: false, reasons: ["no-context"] }
      : screenLearningEntries(taskSlice.entries, opts.mode);
    pipelineScreen = screen;
    for (const phase of ["memory", "harness", "agents"] as const) if (policies[phase] === "off") screen[phase] = false;
    if (!screen.memory && !screen.harness && !screen.agents) {
      const receipt = buildLearningReceipt(opts.mode, screen, []);
      await writeLearningReceipt(resolveMemoryPaths(opts.cwd).runsDir, receipt);
      if (opts.reportResult) opts.reportReceipt?.(receipt);
      return;
    }
    state.attempts = [];
    state.mode = opts.mode;
    state.cancelled = false;
    state.controller = new AbortController();
    const reportReceipt = (receipt: LearningPipelineReceipt): void => {
      if (opts.reportResult) opts.reportReceipt?.(receipt);
    };
    const writeCurrentReceipt = async (directory = resolveMemoryPaths(opts.cwd).runsDir): Promise<void> => {
      const receipt = buildLearningReceipt(opts.mode, screen, state.attempts ?? []);
      await writeLearningReceipt(directory, receipt);
      reportReceipt(receipt);
    };
    let incrementalSelection: Awaited<ReturnType<typeof selectIncrementalLearning>> | undefined;
    let selectedSourceDigest: string | undefined;
    let appliedMemoryChanges = 0;
    if (!fullMode) {
      setDreamingActivity("selecting related memory");
      selectorRun = await createConsolidationRun(frozenContext, opts.cwd, false, policies.memory === "apply" ? normalizeTrackedMemory : false);
      selectedSourceDigest = sha256Digest(JSON.stringify(selectorRun.manifest.sourceHashes));
      const selectorReceiptDirectory = resolveMemoryPaths(opts.cwd).runsDir;
      try {
        incrementalSelection = await selectIncrementalLearning({
          cwd: opts.cwd,
          taskSlice,
          contextDigest: selectorRun.manifest.snapshotDigest,
          outputDir: selectorRun.manifest.runDir,
          model: memoryConfig.provider && memoryConfig.model ? `${memoryConfig.provider}/${memoryConfig.model}` : undefined,
          signal: state.controller.signal,
          registeredSkills: opts.availableSkills,
        });
        state.attempts.push({
          phase: "selector",
          attempt: 0,
          outcome: incrementalSelection.outcome === "selected" ? "applied" : incrementalSelection.outcome,
          durationMs: incrementalSelection.durationMs,
          operations: 0,
          usage: incrementalSelection.usage,
        });
        if (incrementalSelection.outcome !== "selected" || !incrementalSelection.selection) {
          if (!state.cancelled) notifyPi(ctx.ui, `Learning selector failed: ${incrementalSelection.error ?? "invalid selection"}`, "warning");
          await writeCurrentReceipt(selectorReceiptDirectory);
          return;
        }
        // The deterministic parent screen is authoritative for durable task
        // evidence; the selector may add phases but cannot suppress one the
        // parent already found.
        if (opts.mode === "manual") {
          // An explicit request always reaches selection, but does not force
          // three planners when neither task evidence nor the selector needs them.
          Object.assign(screen, screenLearningEntries(taskSlice.entries, "automatic"));
          screen.reasons.unshift("manual-incremental");
        }
        screen.memory = screen.memory || incrementalSelection.selection.memory;
        screen.harness = screen.harness || incrementalSelection.selection.harness;
        screen.agents = screen.agents || incrementalSelection.selection.agents;
        for (const phase of ["memory", "harness", "agents"] as const) if (policies[phase] === "off") screen[phase] = false;
        if (screen.memory) {
          if (policies.memory === "apply") {
            const selected = incrementalSelection.selection.selected;
            await recordLearningMutation(opts.cwd, "memory", memoryMutationFiles(opts.cwd, []), () => ensureEmptyIncrementalIndexes(opts.cwd, selected));
          }
          const memoryPaths = resolveMemoryPaths(opts.cwd);
          const currentSourceHashes = {
            harness: await hashMemoryRoot(memoryPaths.harnessDir),
            public: memoryPaths.publicDir ? await hashMemoryRoot(memoryPaths.publicDir) : {},
          };
          selectedSourceDigest = sha256Digest(JSON.stringify(currentSourceHashes));
        }
      } catch (error) {
        await releaseConsolidationRun(selectorRun, { keepArtifacts: Boolean(incrementalSelection?.dossierPath) });
        selectorRun = undefined;
        throw error;
      }
    }
    if (screen.memory) {
      setDreamingActivity(fullMode ? "full memory" : "memory delta");
      const memoryStartedAt = Date.now();
      if (selectorRun) {
        await releaseConsolidationRun(selectorRun, { keepArtifacts: true });
        selectorRun = undefined;
      }
      const started = await spawnAsyncConsolidation(frozenContext, state, {
        ...opts,
        selectedScope: incrementalSelection?.selection?.selected,
        dossierPath: incrementalSelection?.dossierPath,
        dossierDigest: incrementalSelection?.dossierDigest,
        selectedSourceDigest,
        applyChanges: policies.memory === "apply",
      });
      if (!started) {
        if (!state.cancelled) {
          state.attempts.push({ phase: "memory", attempt: 0, outcome: "failed", durationMs: Date.now() - memoryStartedAt, operations: 0 });
          await writeCurrentReceipt();
        }
        return;
      }
      // A retry replaces completion; wait for each attempt and its lock release.
      while (state.completion) await state.completion;
      if (state.cancelled) return;
      appliedMemoryChanges = (state.attempts ?? [])
        .filter((attempt) => attempt.phase === "memory")
        .reduce((total, attempt) => total + attempt.operations, 0);
    } else {
      // Later phases may have grounded evidence even when no Memory candidate
      // exists. Satisfy the ordering gate without spawning or mutating Memory.
      state.active = false;
      state.outcome = "completed";
    }
    const gate = shouldRunHarnessPhase(state, opts.noContext);
    if (gate !== "run" && gate !== "skip-no-context") {
      await writeCurrentReceipt();
      return;
    }
    if (opts.noContext) {
      await writeCurrentReceipt();
      return;
    }
    if (!screen.harness && !screen.agents) {
      await writeCurrentReceipt();
      return;
    }
    if (selectorRun) {
      if (!incrementalSelection?.dossierPath || !incrementalSelection.dossierDigest) throw new Error("incremental dossier is missing before later planning");
      const dossierBytes = await fs.readFile(incrementalSelection.dossierPath);
      if (sha256Digest(dossierBytes) !== incrementalSelection.dossierDigest) throw new Error("incremental dossier changed after selection");
      await releaseConsolidationRun(selectorRun, { keepArtifacts: true });
      selectorRun = undefined;
    }
    const laterRun = await createConsolidationRun(frozenContext, opts.cwd, false, policies.memory === "apply" ? normalizeTrackedMemory : false);
    acquiredLaterRun = laterRun;
    if (incrementalSelection?.dossierPath && incrementalSelection.dossierDigest) {
      const dossierBytes = await fs.readFile(incrementalSelection.dossierPath);
      if (sha256Digest(dossierBytes) !== incrementalSelection.dossierDigest) throw new Error("incremental dossier changed before later planning");
      if (selectedSourceDigest && appliedMemoryChanges === 0) {
        const currentSourceHashes = {
          harness: await hashMemoryRoot(laterRun.manifest.harnessDir),
          public: laterRun.manifest.publicDir ? await hashMemoryRoot(laterRun.manifest.publicDir) : {},
        };
        if (sha256Digest(JSON.stringify(currentSourceHashes)) !== selectedSourceDigest) {
          throw new Error("selected Memory changed before later planning");
        }
      }
    }
    const attempts = state.attempts ?? [];
    const laterGeneration = state.generation + 1;
    const harnessState = { cancelled: false, generation: laterGeneration, child: undefined as ChildProcess | undefined };
    const agentsState = { active: true, cancelled: false, generation: laterGeneration, child: undefined as ChildProcess | undefined };
    state.laterStates = [harnessState, agentsState];
    try {
      const exploration = incrementalSelection?.dossierPath
        ? { explorationPath: incrementalSelection.dossierPath, explorationDigest: incrementalSelection.dossierDigest }
        : {};
      const settings = await readSettings(opts.cwd);
      if (screen.harness && screen.agents) setDreamingActivity("harness and AGENTS.md");
      else if (screen.harness) setDreamingActivity("harness delta");
      else if (screen.agents) setDreamingActivity("AGENTS.md delta");
      const harnessPromise = screen.harness
        ? planHarnessConsolidationPhase(frozenContext, { pkgDir: opts.pkgDir, cwd: opts.cwd, reason: opts.reason, availableSkills: opts.availableSkills, run: laterRun, ...exploration }, {
            current: () => !state.cancelled && !harnessState.cancelled,
            onChild: (child) => { harnessState.child = child; },
          })
        : Promise.resolve(undefined);
      const agentsPromise = screen.agents && settings.agentsMd?.disabled !== true
        ? planAgentsMdConsolidationPhase(frozenContext, agentsState, {
            pkgDir: opts.pkgDir, cwd: opts.cwd, reason: opts.reason, availableSkills: opts.availableSkills,
            budgetBytes: settings.agentsMd?.budgetBytes ?? DEFAULT_AGENTS_MD_BUDGET_BYTES, disabled: false, ...exploration,
          }, laterRun, laterGeneration)
        : Promise.resolve(undefined);
      const [harnessPlan, agentsPlan] = await Promise.all([harnessPromise, agentsPromise]);
      if (harnessPlan) {
        attempts.push({ phase: "harness", attempt: 0, outcome: harnessPlan.ok ? "noop" : "failed", durationMs: harnessPlan.ok ? harnessPlan.value.durationMs : harnessPlan.durationMs, operations: harnessPlan.ok && Array.isArray(harnessPlan.value.plan.operations) ? harnessPlan.value.plan.operations.length : 0, usage: harnessPlan.ok ? harnessPlan.value.usage : harnessPlan.usage });
        if (!harnessPlan.ok && !state.cancelled) notifyPi(ctx.ui, `Harness learning failed: ${harnessPlan.detail.slice(-300)}`, "warning");
        if (harnessPlan.ok) {
          if (policies.harness === "propose") {
            const hasChanges = Array.isArray(harnessPlan.value.plan.operations) && harnessPlan.value.plan.operations.length > 0;
            if (hasChanges) await recordLearningProposal(opts.cwd, "harness", harnessPlan.value.plan);
            attempts[attempts.length - 1].outcome = hasChanges ? "proposed" : "noop";
            attempts[attempts.length - 1].operations = 0;
          } else {
            const applied = await applyHarnessConsolidationPlan(harnessPlan.value, () => !state.cancelled);
            attempts[attempts.length - 1].outcome = applied.outcome;
            attempts[attempts.length - 1].operations = applied.outcome === "applied" ? applied.applied.length : 0;
            if (applied.outcome === "rejected" && !state.cancelled) {
              const detail = containsSensitiveMemoryMaterial(applied.error) ? "Sensitive diagnostic omitted" : applied.error.slice(0, 2000);
              await writeFileAtomic(path.join(laterRun.manifest.runDir, "harness-error.txt"), detail);
              notifyPi(ctx.ui, `Harness learning rejected: ${detail}`, "warning");
            }
          }
        }
      }
      if (agentsPlan) {
        const attempt: LearningAttempt = {
          phase: "agents",
          attempt: 0,
          outcome: agentsPlan.outcome === "planned" ? "noop" : agentsPlan.outcome,
          durationMs: agentsPlan.durationMs,
          operations: 0,
          usage: agentsPlan.usage,
        };
        attempts.push(attempt);
        if ((agentsPlan.outcome === "failed" || agentsPlan.outcome === "rejected") && !state.cancelled) {
          notifyPi(ctx.ui, `AGENTS.md learning ${agentsPlan.outcome}: ${agentsPlan.detail ?? "no validated plan"}`, "warning");
        }
        if (agentsPlan.outcome === "planned") {
          const operations = agentsPlan.planning.operations;
          const memoryNames = operations.flatMap(operation => operation.extraction?.target === "memory" ? [operation.extraction.memoryName] : []);
          const hasSkillExtraction = operations.some(operation => operation.extraction?.target === "skillRule");
          const propose = policies.agents === "propose" || (memoryNames.length > 0 && policies.memory !== "apply") || (hasSkillExtraction && policies.harness !== "apply");
          if (propose) {
            await recordLearningProposal(opts.cwd, "agents", { ...agentsPlan.planning.rawPlan as object, operations });
            attempt.outcome = "proposed";
          } else {
            const files = [agentsPlan.planning.targetPath, ...(memoryNames.length ? memoryMutationFiles(opts.cwd, memoryNames) : []), ...(hasSkillExtraction ? [path.join(opts.cwd, ".pi", "harness.json")] : [])];
            const applied = await recordLearningMutation(opts.cwd, "agents", files, () => applyAgentsMdConsolidationPlan(frozenContext, agentsState, {
              pkgDir: opts.pkgDir, cwd: opts.cwd, reason: opts.reason, availableSkills: opts.availableSkills,
              budgetBytes: settings.agentsMd?.budgetBytes ?? DEFAULT_AGENTS_MD_BUDGET_BYTES, disabled: false, ...exploration,
            }, agentsPlan.planning, laterGeneration, () => !state.cancelled), agentsPlan.planning.rawPlan);
            attempt.outcome = applied.outcome;
            attempt.operations = applied.applied;
          }
        }
      }
      await writeCurrentReceipt(laterRun.manifest.runDir);
    } finally {
      state.laterStates = undefined;
      await releaseConsolidationRun(laterRun, { keepArtifacts: true });
    }
  })().finally(async () => {
    // Runs belong to the pipeline, including early selector returns and later
    // preflight failures before a phase's own try/finally. Release is idempotent.
    try {
      if (selectorRun) await releaseConsolidationRun(selectorRun, { keepArtifacts: true });
    } finally {
      if (acquiredLaterRun) await releaseConsolidationRun(acquiredLaterRun, { keepArtifacts: true });
    }
  }).catch(async (error: unknown) => {
    state.outcome = "failed";
    if (!state.cancelled && pipelineScreen && (state.attempts?.length ?? 0) > 0) {
      const receipt = buildLearningReceipt(opts.mode, pipelineScreen, state.attempts ?? []);
      await writeLearningReceipt(resolveMemoryPaths(opts.cwd).runsDir, receipt).catch(() => undefined);
    }
    if (!state.cancelled) notifyPi(ctx.ui, `Learning pipeline failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }).finally(() => {
    const cleanup = state.cleanup;
    state.cleanup = undefined;
    cleanup?.();
    if (state.pipeline === pipeline) state.pipeline = undefined;
  });
  state.pipeline = pipeline;
  return pipeline;
}

async function editInstructions(ctx: ExtensionCommandContext, filePath: string): Promise<void> {
  let current = "";
  try {
    current = await fs.readFile(filePath, "utf-8");
  } catch {
    // new file — start empty
  }

  if (typeof ctx.ui.editor !== "function") {
    notifyPi(ctx.ui, `Instructions file: ${filePath}`, "info");
    return;
  }

  const edited = await ctx.ui.editor(`Edit ${filePath}:`, current);
  if (edited === undefined) return; // cancelled

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, edited, "utf-8");
  notifyPi(ctx.ui, `Saved ${filePath}`, "info");
}

// ── extension ──────────────────────────────────────────────────────

const LEARNING_RESULT_MESSAGE = "continual-learning-result";

export default function (pi: ExtensionAPI) {
  const dreamState: DreamState = { active: false, generation: 0, cancelled: false };
  const reportLearningReceipt = (receipt: LearningPipelineReceipt): void => {
    pi.sendMessage(
      { customType: LEARNING_RESULT_MESSAGE, content: formatLearningSummary(receipt), display: true, details: receipt },
      { deliverAs: "followUp", triggerTurn: false },
    );
  };
  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(LEARNING_RESULT_MESSAGE, (message, { expanded }, theme) => {
      const receipt = isLearningPipelineReceipt(message.details) ? message.details : undefined;
      const subject = receipt ? learningSummarySubject(receipt) : "learning result";
      return learningRows.message(() => eventToolLifecycle("learning", subject, {
        label: "event",
        details: receipt ? learningSummaryDetails(receipt) : undefined,
      }))(message, { expanded }, theme);
    });
  }
  let sessionGeneration = 0;

  registerAutomaticLearning(pi, {
    enabled: async (ctx) => (await readSettings(ctx.cwd)).autoMemory,
    snapshot: snapshotSessionContext,
    run: async (ctx) => {
      const generation = sessionGeneration;
      if (dreamState.pipeline) await dreamState.pipeline;
      if (generation !== sessionGeneration) return;
      await startConsolidationPipeline(ctx, dreamState, {
        pkgDir: resolvePackageDir(),
        cwd: ctx.cwd,
        availableSkills: pi.getCommands().filter(command => command.source === "skill").map(command => command.name.replace(/^skill:/, "")),
        reason: "Learn durable memory and verifiable constraints from the completed user task.",
        mode: "automatic",
        reportResult: false,
        reportReceipt: reportLearningReceipt,
      });
    },
    reportError: (error, ctx) => notifyPi(ctx.ui, `Automatic learning failed: ${error instanceof Error ? error.message : String(error)}`, "error"),
  });

  const stopPipeline = async (): Promise<void> => {
    sessionGeneration += 1;
    dreamState.cancelled = true;
    dreamState.controller?.abort();
    const laterStates = dreamState.laterStates ?? [];
    dreamState.generation += 1;
    dreamState.active = false;
    const cleanup = dreamState.cleanup;
    dreamState.cleanup = undefined;
    cleanup?.();
    const child = dreamState.child;
    await Promise.all([
      ...(child ? [terminateConsolidationChild(child, 5_000)] : []),
      cancelLaterPlannerChildren(laterStates),
    ]);
    const completion = dreamState.completion;
    if (completion) await completion;
    if (dreamState.pipeline) await dreamState.pipeline;
    const run = dreamState.run;
    dreamState.run = undefined;
    if (run) await releaseConsolidationRun(run);
    dreamState.completion = undefined;
    dreamState.controller = undefined;
    dreamState.laterStates = undefined;
  };

  pi.on("session_start", async (_event, ctx) => {
    await stopPipeline();
    try {
      const recoveryLock = await acquireConsolidationLock(resolveConsolidationRunPaths(ctx.cwd || process.cwd()));
      try { await recoverPendingAgentsMdConsolidations(ctx.cwd || process.cwd()); }
      finally { await recoveryLock.release(); }
      await recoverLearningUndo(ctx.cwd || process.cwd());
      await checkPendingLearningMutations(ctx.cwd || process.cwd());
    } catch (error) {
      notifyPi(ctx.ui, `Learning recovery failed: ${error instanceof Error ? error.message : String(error)}`, "error");
    }
    memoryConfigState = safelyReadMemoryConfigState();
    memoryConfig = memoryConfigState.config;
  });
  pi.on("session_shutdown", stopPipeline);

  pi.on("before_agent_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const memories = await loadAndDeduplicateMemories(cwd);
    const settings = await readSettings(cwd);

    if (memories.totalEntries === 0 && !settings.autoMemory) return;

    let systemPrompt = event.systemPrompt || "";
    if (memories.totalEntries > 0) {
      systemPrompt = systemPrompt
        ? systemPrompt + "\n\n" + formatMemoriesBlock(memories)
        : formatMemoriesBlock(memories);
    }
    if (settings.autoMemory) {
      systemPrompt = systemPrompt + AUTO_MEMORY_GUIDANCE;
    }
    return { systemPrompt };
  });

  // /memory command with the management menu
  pi.registerCommand("memory", {
    description: "Manage project memory: model, instructions, memory folder, consolidation",
    handler: async (args, ctx) => {
      const command = args.trim();
      if (await handleLearningManagement(command, ctx, { readSettings, writeSettings, busy: () => Boolean(dreamState.pipeline || dreamState.active) })) return;
      if (command === "model") {
        await chooseMemoryModel(ctx);
        return;
      }
      if (command.startsWith("model ")) {
        await setMemoryModel(command.slice("model ".length).trim(), ctx);
        return;
      }
      if (command === "show" || command === "status") {
        notifyPi(ctx.ui, `Memory model: ${configuredMemoryModel()}\nConfig file: ${memoryConfigPath()}`, "info");
        return;
      }

      const cwd = ctx.cwd || process.cwd();
      const settings = await readSettings(cwd);
      const status = settings.autoMemory ? "on" : "off";
      const memoryPaths = resolveMemoryPaths(cwd);
      const harnessDir = memoryPaths.harnessDir;
      const home = getAgentDir();
      const pkgDir = resolvePackageDir();
      const procedureFile = path.join(pkgDir, "prompts", "incremental-memory-consolidator.md");
      const projectInstructions = await resolveProjectInstructionsFile(cwd, ctx);

      const options = [
        `Select memory model (current: ${configuredMemoryModel()})`,
        "Enter provider/model manually",
        "Consolidate memory now",
        "Show automatic phase policies",
        "Show learning history",
        `Edit user instructions (${path.join(home, "AGENTS.md")})`,
        `Edit project instructions (${projectInstructions.display})`,
        "Open memory folder",
        `Toggle auto-memory (currently ${status})`,
      ];

      if (!ctx.hasUI) {
        notifyPi(ctx.ui,
          [
            `Auto-memory: ${status}`,
            `Memory model: ${configuredMemoryModel()}`,
            `Harness memory: ${harnessDir}`,
            `Public memory: ${memoryPaths.publicDir ?? "disabled for this non-project directory"}`,
            `Consolidate procedure: ${procedureFile}`,
          ].join("\n"),
          "info",
        );
        return;
      }

      const choice = await ctx.ui.select(`Auto-memory: ${status}\n\nMemory management:`, options);
      if (!choice) return; // cancelled

      if (choice.startsWith("Select memory model")) {
        await chooseMemoryModel(ctx);
      } else if (choice === "Enter provider/model manually") {
        await enterMemoryModel(ctx);
      } else if (choice.startsWith("Consolidate memory now")) {
        if (dreamState.pipeline || dreamState.active) {
          notifyPi(ctx.ui, "Memory consolidation is already running in background.", "info");
          return;
        }
        void startConsolidationPipeline(ctx, dreamState, {
          pkgDir,
          cwd,
          noContext: false,
          availableSkills: pi.getCommands().filter(command => command.source === 'skill').map(command => command.name.replace(/^skill:/, '')),
          reason: "Consolidate the project memory now (user-invoked via /memory menu).",
          mode: "manual",
          reportResult: true,
          reportReceipt: reportLearningReceipt,
        });
      } else if (choice === "Show automatic phase policies" || choice === "Show learning history") {
        await handleLearningManagement(choice === "Show learning history" ? "history" : "policy", ctx, { readSettings, writeSettings, busy: () => Boolean(dreamState.pipeline || dreamState.active) });
      } else if (choice.startsWith("Edit user instructions")) {
        await editInstructions(ctx, path.join(home, "AGENTS.md"));
      } else if (choice.startsWith("Edit project instructions")) {
        if (!projectInstructions.path) {
          notifyPi(ctx.ui, "Pi did not expose a project instruction file", "warning");
        } else {
          await editInstructions(ctx, projectInstructions.path);
        }
      } else if (choice.startsWith("Open memory folder")) {
        await fs.mkdir(harnessDir, { recursive: true });
        if (ctx.mode === "tui" && process.platform === "darwin") {
          await pi.exec("open", [harnessDir]);
          notifyPi(ctx.ui, `Opened ${harnessDir}`, "info");
        } else {
          notifyPi(ctx.ui, `Memory folder: ${harnessDir}`, "info");
        }
      } else if (choice.startsWith("Toggle auto-memory")) {
        const next = { ...settings, autoMemory: !settings.autoMemory };
        await writeSettings(next, cwd);
        notifyPi(ctx.ui, `Auto-memory: ${next.autoMemory ? "on" : "off"}`, "info");
      }
    },
  });

  // /consolidate — dedicated one-shot consolidation trigger, sibling of
  // /memory (no menu). Kept separate from /memory so the management menu
  // stays focused on instructions + settings. Consolidation runs in the
  // background, so the active session remains responsive.
  pi.registerCommand("consolidate", {
    description: "Consolidate project memory and harness now",
    handler: async (rawArgs, ctx) => {
      const args = rawArgs.trim();
      if (args !== "" && args !== "full" && args !== "no-context") {
        notifyPi(ctx.ui, "Usage: /consolidate [full|no-context]", "error");
        return;
      }
      const cwd = ctx.cwd || process.cwd();
      const pkgDir = resolvePackageDir();

      if (dreamState.pipeline || dreamState.active) {
        notifyPi(ctx.ui, "Memory consolidation is already running.", "info");
        return;
      }

      const completion = startConsolidationPipeline(ctx, dreamState, {
        pkgDir,
        cwd,
        noContext: args === "no-context",
        availableSkills: pi.getCommands().filter(command => command.source === 'skill').map(command => command.name.replace(/^skill:/, '')),
        reason: args === "full"
          ? "Run explicit full-corpus Memory, Harness, and AGENTS.md maintenance."
          : "Consolidate the current task context incrementally (user-invoked via /consolidate command).",
        mode: args === "full" || args === "no-context" ? "full" : "manual",
        reportResult: true,
        reportReceipt: reportLearningReceipt,
      });
      if (!ctx.hasUI) await completion;
    },
  });
}

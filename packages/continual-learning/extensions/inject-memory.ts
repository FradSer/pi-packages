/**
 * pi-memory-fradser — native pi /memory command.
 *
 * Replaces the /skill:consolidate skill surface with a pi-native command menu:
 *
 *   /memory
 *     Auto-memory: on
 *     1. Select memory model
 *     2. Enter provider/model manually
 *     3. Consolidate memory now        (inline procedure from procedures/consolidate.md)
 *     4. Edit user instructions        (getAgentDir()/AGENTS.md)
 *     5. Edit project instructions     (./AGENTS.md or ./CLAUDE.md — whichever exists)
 *     6. Open memory folder
 *     7. Toggle auto-memory
 *
 * Auto-memory on → `before_agent_start` injects prompt guidance that tells the
 * LLM to actively capture durable decisions/preferences into memory when needed.
 * Existing memories are always injected into the system prompt; the toggle only
 * controls the auto-write guidance. Consolidation uses a separately selected
 * Pi model when configured.
 */

import fs from "fs/promises";
import path from "path";
import { execFile } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { promisify } from "node:util";
import * as nodeFs from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  enterModelFromInput,
  modelRef,
  parseModelRef,
  PI_SPINNER_FRAMES,
  PI_SPINNER_INTERVAL_MS,
  resolvePiCli,
  selectModelFromMenu,
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
  DEFAULT_AGENTS_MD_BUDGET_BYTES,
  MAX_AGENTS_MD_FILE_BYTES,
  MIN_BUDGET_BYTES,
  runAgentsMdConsolidationPhase,
} from "./agents-md-consolidation";
import { runHarnessConsolidationPhase, shouldRunHarnessPhase } from "./harness-consolidation";
import {
  applyConsolidationPlan,
  sha256Digest,
  terminateConsolidationChild,
  createConsolidationReceipt,
  createPreApplyReceipt,
  createConsolidationRun,
  extractChildPlan,
  MAX_JSONL_LINE_BYTES,
  MAX_JSONL_LINES,
  MAX_PLAN_BYTES,
  MAX_STDOUT_BYTES,
  MAX_STDERR_BYTES,
  releaseConsolidationRun,
  writeConsolidationReceipt,
  writeFileAtomic,
  type ConsolidationRun,
} from "./consolidation-run";

export { formatMemoriesBlock, loadAndDeduplicateMemories, type MemoryEntry } from "./memory-files";
export { projectScopeKey, resolveMemoryPaths } from "./memory-paths";

// ── auto-memory settings (user-level, persisted) ───────────────────

interface MemorySettings {
  autoMemory: boolean;
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

You maintain a durable project memory. When you encounter a decision, user
preference, lesson, gotcha, or non-obvious project fact during this session,
**write it down immediately** — do not wait for a memory command:

- Search existing memory files first; if one covers the topic, edit it instead of creating a near-duplicate.
- One decision per file. Format: frontmatter (name, description, type) + **Why** + **How to apply** + **Related** [[links]].
- Mirror safe technical content to the project's \`.memory/\`; keep private content (credentials, personal preferences) harness-only.
- Do not log pure operations or timelines — those belong in git history.

Run \`/memory\` to review, edit, or consolidate memory at any time.
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
}

interface ChildJsonEvent {
  type?: string;
  toolCallId?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  isError?: boolean;
  error?: unknown;
  message?: {
    role?: string;
    content?: unknown;
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

function parentSelectedScope(run: ConsolidationRun, noContext: boolean): string[] {
  if (noContext) return [];
  const names = new Map<string, string>();
  const sourceHashes = run.manifest.sourceHashes;
  for (const name of [...Object.keys(sourceHashes.harness), ...Object.keys(sourceHashes.public)].sort()) {
    if (!MEMORY_FILENAME_RE.test(name) || name.toLowerCase() === "memory.md") continue;
    names.set(name.toLowerCase(), names.get(name.toLowerCase()) ?? name);
  }
  return [...names.values()].sort();
}

/**
 * Render the parent-owned selected scope for the child task. The child cannot
 * derive this list itself: the snapshot holds session entries, not memory
 * names, so the authoritative scope must be stated in the task header.
 */
export function formatSelectedScopeTaskLines(selectedScope: readonly string[]): string[] {
  if (selectedScope.length === 0) {
    return [
      "- Selected memory scope (authoritative, complete): [] — verified no-op; every plan section must be empty",
    ];
  }
  return [
    `- Selected memory scope (authoritative, complete, JSON): ${JSON.stringify(selectedScope)}`,
    "- Your plan's `selected` array MUST be exactly this list — same names, same casing, no additions or omissions.",
    ...selectedScope.map((name) => `  - ${name}`),
  ];
}

function appendBoundedUtf8Text(current: string, text: string, maxBytes: number): string {
  if (!text) return current;
  const bytes = Buffer.concat([Buffer.from(current, "utf8"), Buffer.from(text, "utf8")]);
  if (bytes.byteLength <= maxBytes) return bytes.toString("utf8");
  return bytes.subarray(bytes.byteLength - maxBytes).toString("utf8");
}

function tailBoundedUtf8Text(text: string, maxBytes = 256 * 1024): string {
  const bytes = Buffer.from(text, "utf8");
  return bytes.byteLength <= maxBytes ? text : bytes.subarray(bytes.byteLength - maxBytes).toString("utf8");
}

export interface ConsolidationEvidence {
  completedToolWork: boolean;
  parentReceiptVerified: boolean;
  planCount: number;
  lastJsonError: string;
  finalPlan?: unknown;
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
  return { completedToolWork: false, parentReceiptVerified: false, planCount: 0, lastJsonError: "" };
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
  return result.ok ? result.plan : undefined;
}

export function recordConsolidationEvent(evidence: ConsolidationEvidence, event: ChildJsonEvent): void {
  if (typeof event.error === "string") evidence.lastJsonError = event.error.slice(-2_000);
  if (event.type === "tool_execution_end" && event.isError) {
    evidence.lastJsonError = evidence.lastJsonError || "child tool execution failed";
  }
  const plan = parseFinalPlan(event);
  if (plan !== undefined) {
    evidence.planCount += 1;
    evidence.finalPlan = plan;
  }
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

let dreamingTimer: NodeJS.Timeout | undefined;
let dreamingActivity = "";

function setDreamingWidget(ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;

  if (dreamingTimer) {
    clearInterval(dreamingTimer);
    dreamingTimer = undefined;
  }

  ctx.ui.setWidget("memory-dreaming", (tui, theme) => {
    let frameIndex = 0;
    dreamingTimer = setInterval(() => {
      frameIndex++;
      tui.requestRender();
    }, PI_SPINNER_INTERVAL_MS);
    dreamingTimer.unref?.();

    return {
      render: (_width: number) => {
        const frame = PI_SPINNER_FRAMES[frameIndex % PI_SPINNER_FRAMES.length];
        const icon = theme?.fg ? theme.fg("accent", frame) : frame;
        const text = theme?.fg ? theme.fg("accent", "Dreaming...") : "Dreaming...";
        const detail = dreamingActivity
          ? theme?.fg
            ? theme.fg("muted", ` · ${dreamingActivity}`)
            : ` · ${dreamingActivity}`
          : "";
        // Leading space aligns the spinner with the native " ⠋ Working...\" row.
        return [` ${icon} ${text}${detail}`];
      },
      invalidate: () => {},
      dispose: () => {
        if (dreamingTimer) {
          clearInterval(dreamingTimer);
          dreamingTimer = undefined;
        }
      },
    };
  });
}

function availableMemoryModels(ctx: ExtensionContext) {
  const models = ctx.scopedModels.length > 0
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
  const result = await selectModelFromMenu(
    ctx.ui,
    availableMemoryModels(ctx),
    configuredMemoryModel(),
    "Select a memory model",
  );
  if (!result) return;
  saveMemoryConfig(result);
  ctx.ui.notify(`Memory model set to ${result.provider}/${result.model}`, "info");
}

async function enterMemoryModel(ctx: ExtensionContext): Promise<void> {
  const result = await enterModelFromInput(ctx.ui, ctx.modelRegistry, modelRef(memoryConfig), { label: "Memory model" });
  if (!result) return;
  if (!isAllowedMemoryModel(ctx, result.provider, result.model)) {
    ctx.ui.notify(`Model ${result.provider}/${result.model} is not allowed for memory workers`, "error");
    return;
  }
  saveMemoryConfig(result);
  ctx.ui.notify(`Memory model set to ${result.provider}/${result.model}`, "info");
}

async function setMemoryModel(value: string, ctx: ExtensionContext): Promise<void> {
  const ref = parseModelRef(value);
  if (!ref) {
    ctx.ui.notify("Enter a model in provider/model format", "error");
    return;
  }
  if (!isAllowedMemoryModel(ctx, ref.provider, ref.model)) {
    ctx.ui.notify(`Model ${ref.provider}/${ref.model} is not allowed for memory workers`, "error");
    return;
  }
  saveMemoryConfig(ref);
  ctx.ui.notify(`Memory model set to ${ref.provider}/${ref.model}`, "info");
}

function clearDreamingWidget(ctx: ExtensionContext): void {
  dreamingActivity = "";
  if (ctx.mode === "tui") ctx.ui.setWidget("memory-dreaming", undefined);
}

const execFileAsync = promisify(execFile);

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
    "--repo-root", run.manifest.cwd,
    "--expected-run-id", run.manifest.runId,
    "--expected-scope-key", run.manifest.scopeKey,
    "--expected-scope-digest", run.manifest.scopeDigest,
    "--expected-artifact-hash", run.manifest.snapshotDigest,
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
      ? (parsed.errors as Array<{ code?: string; message?: string }>).map((e) => `${e.code ?? "error"}: ${e.message ?? JSON.stringify(e)}`).join("; ")
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
  opts: { pkgDir: string; cwd: string; noContext?: boolean; reason: string; attempt?: number },
): Promise<boolean> {
  const attempt = opts.attempt ?? 0;
  if (state.active && attempt === 0) {
    ctx.ui.notify("Memory consolidation is already running in background.", "info");
    return false;
  }
  if (memoryConfigState.invalid) {
    ctx.ui.notify(`Memory consolidation is blocked: ${memoryConfigState.invalid}`, "error");
    return false;
  }
  state.active = true;
  state.outcome = undefined;
  const generation = state.generation + 1;
  state.generation = generation;
  state.cancelled = false;
  const isGenerationCurrent = (): boolean => !state.cancelled && generation === state.generation;

  let procedure: string;
  try {
    procedure = (
      await fs.readFile(path.join(opts.pkgDir, "procedures", "consolidate.md"), "utf-8")
    ).replaceAll("{{PKG_DIR}}", opts.pkgDir);
  } catch (err: unknown) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      ctx.ui.notify(`Memory consolidation setup failed: ${(err as Error).message}`, "error");
    }
    return false;
  }
  const memoryPaths = resolveMemoryPaths(opts.cwd);
  const harnessDir = memoryPaths.harnessDir;
  let run: ConsolidationRun;
  try {
    run = await createConsolidationRun(ctx, opts.cwd, opts.noContext);
  } catch (err: unknown) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      ctx.ui.notify(`Memory consolidation setup failed: ${(err as Error).message}`, "error");
    }
    return false;
  }
  if (!isGenerationCurrent()) {
    await releaseConsolidationRun(run);
    return false;
  }
  state.run = run;
  const selectedScope = parentSelectedScope(run, Boolean(opts.noContext));
  if (run.normalization.repaired.length > 0 || run.normalization.removed.length > 0) {
    ctx.ui.notify(
      `Memory consolidation normalized mirrors before planning: ${run.normalization.repaired.length} repaired, ${run.normalization.removed.length} removed`,
      "info",
    );
  }

  procedure = procedure
    .replaceAll("{{RUN_ID}}", run.manifest.runId)
    .replaceAll("{{SCOPE_DIGEST}}", run.manifest.scopeDigest)
    .replaceAll("{{SCOPE_KEY}}", run.manifest.scopeKey)
    .replaceAll("{{ARTIFACT_HASH}}", run.manifest.snapshotDigest)
    .replaceAll("{{SNAPSHOT_DIGEST}}", run.manifest.snapshotDigest)
    .replaceAll("{{RUN_DIR}}", run.manifest.runDir)
    .replaceAll("{{SNAPSHOT_PATH}}", run.manifest.snapshotPath)
    .replaceAll("{{HARNESS_DIR}}", run.manifest.harnessDir)
    .replaceAll("{{PUBLIC_DIR}}", run.manifest.publicDir ?? "(disabled for this non-project directory)")
    .replaceAll("{{REPO_ROOT}}", run.manifest.cwd);

  const taskText = [
    `Task: produce a read-only structured consolidation plan for the project at ${opts.cwd}.`,
    `- Reason: ${opts.reason}`,
    `- Run ID: ${run.manifest.runId}`,
    `- Scope key: ${run.manifest.scopeKey}`,
    `- Scope digest: ${run.manifest.scopeDigest}`,
    `- Artifact/snapshot digest: ${run.manifest.snapshotDigest}`,
    `- Run directory: ${run.manifest.runDir}`,
    `- Context mode: ${opts.noContext ? "no-context (do not capture session context)" : "parent-provided immutable snapshot"}`,
    `- Pre-run mirror normalization: ${JSON.stringify({ repaired: run.normalization.repaired, removed: run.normalization.removed })}`,
    ...formatSelectedScopeTaskLines(selectedScope),
    `- Immutable manifest: ${path.join(run.manifest.runDir, "manifest.json")}`,
    `- Immutable context snapshot: ${run.manifest.snapshotPath}`,
    `- Harness memory dir: ${harnessDir}`,
    `- Public memory dir: ${run.manifest.publicDir ?? "disabled for this non-project directory"}`,
    "- Do not write to either memory directory.",
    "- Your final assistant message must be one JSON object containing schemaVersion, runId, scopeKey, snapshotDigest, selected, and operations.",
    "",
    procedure,
  ].join("\n");

  const cli = resolvePiCli();
  if (!cli) {
    if (isGenerationCurrent()) {
      state.active = false;
      state.outcome = "failed";
      ctx.ui.notify("Memory consolidation: could not resolve the Pi CLI", "error");
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
        "--print",
        "--mode",
        "json",
        "--no-session",
        "--no-extensions",
        "--tools",
        "read,grep,find,ls",
        ...modelArgs,
        `@${taskFile}`,
      ],
      { cwd: opts.cwd, env: workerEnv, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (err: unknown) {
    if (isGenerationCurrent()) state.outcome = "failed";
    state.active = false;
    await releaseConsolidationRun(run);
    if (isGenerationCurrent()) ctx.ui.notify(`Memory consolidation spawn failed: ${(err as Error).message}`, "error");
    return false;
  }

  state.child = child;
  setDreamingWidget(ctx);
  state.cleanup = () => clearDreamingWidget(ctx);

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
    void terminateConsolidationChild(child, 5_000);
  }, DREAM_TIMEOUT_MS);
  timer.unref?.();

  let resolveCompletion!: () => void;
  const completion = new Promise<void>((resolve) => { resolveCompletion = resolve; });
  state.completion = completion;
  let finished = false;
  let failureRecorded = false;
  let mutatedMemory = false;
  /**
   * One parent-owned retry for failures before any memory mutation: a fresh
   * child re-plans from the same immutable run inputs. Every retry attempt is
   * validated identically, so this never weakens the fail-closed gates.
   */
  const retryPlanPhase = async (reason: string): Promise<void> => {
    if (attempt > 0) {
      ctx.ui.notify(`Memory dreaming failed: ${reason.slice(-300)}`, "error");
      return;
    }
    ctx.ui.notify(`Memory consolidation plan was rejected (${reason.slice(-160)}); retrying once with a fresh planner…`, "info");
    await releaseConsolidationRun(run, { keepArtifacts: true });
    state.run = undefined;
    await spawnAsyncConsolidation(ctx, state, { ...opts, attempt: attempt + 1 });
  };
  const persistRunDiagnostics = async (): Promise<void> => {
    failureRecorded = true;
    try {
      const marker = outputLimitReason ? `\n[truncated: ${outputLimitReason}]\n` : "";
      await writeFileAtomic(run.paths.stdoutFile, tailBoundedUtf8Text(`${stdoutCapture}${marker}`));
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
    const cleanup = state.cleanup;
    if (ownsCurrentRun()) {
      if (state.child === child) state.child = undefined;
      state.active = false;
      state.cleanup = undefined;
      cleanup?.();
    }
    try {
      if (!ownsCurrentRun()) return;
      if (error) {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        state.outcome = "failed";
        ctx.ui.notify(`Memory dreaming failed to start: ${error.message}`, "error");
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
        const plan = evidence.finalPlan ? collapseDuplicatePlanRecords(evidence.finalPlan) : undefined;
        if (!plan || evidence.planCount !== 1) {
          await persistRunDiagnostics();
          if (!ownsCurrentRun()) return;
          const detail = stderr.trim() || evidence.lastJsonError;
          if (attempt === 0) {
            await retryPlanPhase(`missing exactly one schema-valid consolidation plan${detail ? ` (${detail.slice(-300)})` : ""}`);
            return;
          }
          ctx.ui.notify(
            `Memory dreaming finished without verified consolidation: missing exactly one schema-valid consolidation plan${detail ? ` (${detail.slice(-300)})` : ""}`,
            "warning",
          );
          state.outcome = "unverified";
        } else {
          const planPath = path.join(run.manifest.runDir, "plan.json");
          const planText = `${JSON.stringify(plan, null, 2)}\n`;
          const planDigest = sha256Digest(planText);
          const preSelected = normalizeSelectedScope(plan);
          const expectedSelected = parentSelectedScope(run, Boolean(opts.noContext));
          if (JSON.stringify(preSelected) !== JSON.stringify(expectedSelected)) {
            throw new Error("Consolidation plan selected scope does not match the parent snapshot scope");
          }
          await fs.writeFile(planPath, planText, { encoding: "utf8", mode: 0o600 });
          if (!ownsCurrentRun()) return;
          await runConsolidationValidator(opts.pkgDir, run, planPath, "plan", expectedSelected);
          if (!ownsCurrentRun()) return;
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
          const applied = await applyConsolidationPlan(run, plan, ownsCurrentRun);
          mutatedMemory = true;
          if (!ownsCurrentRun()) return;
          const receipt = createConsolidationReceipt(run.manifest, applied.selected, applied.finalState, planDigest);
          const receiptPath = await writeConsolidationReceipt(run, receipt);
          if (!ownsCurrentRun()) return;
          await runConsolidationValidator(opts.pkgDir, run, planPath, "plan,receipt,privacy", preSelected, receiptPath, mutationStartedAt);
          if (!ownsCurrentRun()) return;
          evidence.completedToolWork = true;
          evidence.parentReceiptVerified = true;
          const missing = missingConsolidationEvidence(evidence);
          if (missing.length === 0) {
            state.outcome = "completed";
            ctx.ui.notify("Memory dreaming complete — memory consolidated.", "info");
          } else {
            state.outcome = "unverified";
            ctx.ui.notify(`Memory dreaming finished without verified consolidation: missing ${missing.join(", ")}`, "warning");
          }
        }
      } else {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        const errReason = stderr.trim() || evidence.lastJsonError || `exit code ${code}`;
        if (attempt === 0) {
          await retryPlanPhase(errReason);
          return;
        }
        state.outcome = "failed";
        ctx.ui.notify(`Memory dreaming failed: ${errReason.slice(-300)}`, "error");
      }
    } catch (finishError: unknown) {
      if (ownsCurrentRun()) {
        await persistRunDiagnostics();
        if (!ownsCurrentRun()) return;
        const message = (finishError as Error).message;
        if (!mutatedMemory && attempt === 0) {
          await retryPlanPhase(message);
          return;
        }
        state.outcome = "failed";
        ctx.ui.notify(`Memory consolidation verification failed: ${message}`, "error");
      }
    } finally {
      try {
        // Ownership must be captured before state.run is cleared: the retention
        // decision may not depend on a check that just became false.
        const ownedNow = generation === state.generation && !state.cancelled && state.run === run;
        if (ownedNow) state.run = undefined;
        await releaseConsolidationRun(run, { keepArtifacts: failureRecorded && ownedNow });
      } finally {
        resolveCompletion();
        if (state.completion === completion) state.completion = undefined;
      }
    }
  };

  child.on("error", (err) => { void finish(null, err); });
  child.on("close", (code) => { void finish(code); });
  child.unref();
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
  opts: { pkgDir: string; cwd: string; noContext?: boolean; reason: string },
): Promise<void> {
  const started = await spawnAsyncConsolidation(ctx, state, opts);
  if (!started) return; // racing invocation: never wait on or unlock another run's phases
  void (async () => {
    // Wait for the memory phase's terminal outcome (retries included): the
    // last attempt sets `outcome` and its finally clears `active`.
    for (let i = 0; i < 9000 && !(state.outcome !== undefined && !state.active); i++) {
      if (state.cancelled) return;
      await new Promise((r) => setTimeout(r, 200));
    }
    const gate = shouldRunHarnessPhase(state, opts.noContext);
    if (gate !== "run" && gate !== "skip-no-context") return;
    if (opts.noContext) {
      ctx.ui.notify("Harness and AGENTS.md consolidation need captured context; skipped (no-context run).", "info");
      return;
    }
    await runHarnessConsolidationPhase(ctx, state, {
      pkgDir: opts.pkgDir,
      cwd: opts.cwd,
      reason: opts.reason,
    });
    if (state.cancelled) return;
    const settings = await readSettings(opts.cwd);
    await runAgentsMdConsolidationPhase(ctx, state, {
      pkgDir: opts.pkgDir,
      cwd: opts.cwd,
      reason: opts.reason,
      budgetBytes: settings.agentsMd?.budgetBytes ?? DEFAULT_AGENTS_MD_BUDGET_BYTES,
      disabled: settings.agentsMd?.disabled === true,
    });
  })();
}

async function editInstructions(ctx: ExtensionCommandContext, filePath: string): Promise<void> {
  let current = "";
  try {
    current = await fs.readFile(filePath, "utf-8");
  } catch {
    // new file — start empty
  }

  if (typeof ctx.ui.editor !== "function") {
    ctx.ui.notify(`Instructions file: ${filePath}`, "info");
    return;
  }

  const edited = await ctx.ui.editor(`Edit ${filePath}:`, current);
  if (edited === undefined) return; // cancelled

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, edited, "utf-8");
  ctx.ui.notify(`Saved ${filePath}`, "info");
}

// ── extension ──────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  const dreamState: DreamState = { active: false, generation: 0, cancelled: false };

  // Inject existing memories + auto-memory guidance before every turn
  pi.on("session_start", () => {
    memoryConfigState = safelyReadMemoryConfigState();
    memoryConfig = memoryConfigState.config;
  });

  pi.on("session_shutdown", async () => {
    dreamState.cancelled = true;
    dreamState.generation += 1;
    dreamState.active = false;
    const cleanup = dreamState.cleanup;
    dreamState.cleanup = undefined;
    cleanup?.();
    const child = dreamState.child;
    if (child) await terminateConsolidationChild(child, 5_000);
    const completion = dreamState.completion;
    if (completion) await completion;
    const run = dreamState.run;
    dreamState.run = undefined;
    if (run) await releaseConsolidationRun(run);
    dreamState.completion = undefined;
  });

  pi.on("before_agent_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const memories = await loadAndDeduplicateMemories(cwd);
    const settings = await readSettings(cwd);

    if (memories.length === 0 && !settings.autoMemory) return;

    let systemPrompt = event.systemPrompt || "";
    if (memories.length > 0) {
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
      if (command === "model") {
        await chooseMemoryModel(ctx);
        return;
      }
      if (command.startsWith("model ")) {
        await setMemoryModel(command.slice("model ".length).trim(), ctx);
        return;
      }
      if (command === "show" || command === "status") {
        ctx.ui.notify(`Memory model: ${configuredMemoryModel()}\nConfig file: ${memoryConfigPath()}`, "info");
        return;
      }

      const cwd = ctx.cwd || process.cwd();
      const settings = await readSettings(cwd);
      const status = settings.autoMemory ? "on" : "off";
      const memoryPaths = resolveMemoryPaths(cwd);
      const harnessDir = memoryPaths.harnessDir;
      const home = getAgentDir();
      const pkgDir = await resolvePackageDir();
      const procedureFile = path.join(pkgDir, "procedures", "consolidate.md");
      const projectInstructions = await resolveProjectInstructionsFile(cwd, ctx);

      const options = [
        `Select memory model (current: ${configuredMemoryModel()})`,
        "Enter provider/model manually",
        "Consolidate memory now",
        `Edit user instructions (${path.join(home, "AGENTS.md")})`,
        `Edit project instructions (${projectInstructions.display})`,
        "Open memory folder",
        `Toggle auto-memory (currently ${status})`,
      ];

      if (!ctx.hasUI) {
        ctx.ui.notify(
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
        if (dreamState.active) {
          ctx.ui.notify("Memory consolidation is already running in background.", "info");
          return;
        }
        ctx.ui.notify("Starting memory consolidation in the background…", "info");
        await startConsolidationPipeline(ctx, dreamState, {
          pkgDir,
          cwd,
          noContext: false,
          reason: "Consolidate the project memory now (user-invoked via /memory menu).",
        });
      } else if (choice.startsWith("Edit user instructions")) {
        await editInstructions(ctx, path.join(home, "AGENTS.md"));
      } else if (choice.startsWith("Edit project instructions")) {
        if (!projectInstructions.path) {
          ctx.ui.notify("Pi did not expose a project instruction file", "warning");
        } else {
          await editInstructions(ctx, projectInstructions.path);
        }
      } else if (choice.startsWith("Open memory folder")) {
        await fs.mkdir(harnessDir, { recursive: true });
        if (ctx.mode === "tui" && process.platform === "darwin") {
          await pi.exec("open", [harnessDir]);
          ctx.ui.notify(`Opened ${harnessDir}`, "info");
        } else {
          ctx.ui.notify(`Memory folder: ${harnessDir}`, "info");
        }
      } else if (choice.startsWith("Toggle auto-memory")) {
        const next = { ...settings, autoMemory: !settings.autoMemory };
        await writeSettings(next, cwd);
        ctx.ui.notify(`Auto-memory: ${next.autoMemory ? "on" : "off"}`, "info");
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
      if (args !== "" && args !== "no-context") {
        ctx.ui.notify("Usage: /consolidate [no-context]", "error");
        return;
      }
      const cwd = ctx.cwd || process.cwd();
      const pkgDir = await resolvePackageDir();
      const procedureFile = path.join(pkgDir, "procedures", "consolidate.md");

      if (!ctx.hasUI) {
        ctx.ui.notify(`Consolidate procedure: ${procedureFile}`, "info");
        return;
      }

      if (dreamState.active) {
        ctx.ui.notify("Memory consolidation is already running.", "info");
        return;
      }

      ctx.ui.notify("Starting memory consolidation in the background…", "info");
      await startConsolidationPipeline(ctx, dreamState, {
        pkgDir,
        cwd,
        noContext: args === "no-context",
        reason: "Consolidate the project memory and harness now (user-invoked via /consolidate command).",
      });
    },
  });
}

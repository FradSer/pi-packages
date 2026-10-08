import { jevCounterLocationText, type JevTelemetry } from "./jev-learning";
import fs from "node:fs/promises";
import path from "node:path";
import { fieldLine, type PiWorkerUsage } from "@fradser/pi-kit";
import { HARNESS_BASH_NOTE_PREFIX, HARNESS_CONFIG_NOTE_PREFIX } from "./harness-guidance-planner.ts";

export type LearningMode = "automatic" | "manual" | "full";
export type LearningPhase = "selector" | "memory" | "harness" | "agents";
export type LearningOutcome = "screened" | "skipped" | "noop" | "applied" | "proposed" | "rejected" | "failed" | "cancelled";

export interface LearningScreen {
  memory: boolean;
  harness: boolean;
  agents: boolean;
  reasons: string[];
}

export interface LearningAttempt {
  phase: LearningPhase;
  attempt: number;
  outcome: LearningOutcome;
  durationMs: number;
  operations: number;
  /** Pending original records preserved separately from applied operations. */
  pendingOperations?: number;
  usage?: PiWorkerUsage;
  costAvailable?: boolean;
  /** Controlled parent diagnostic; never raw worker stderr or model output. */
  diagnostic?: string;
  jev?: JevTelemetry;
  selectedMemory?: string[];
}

/**
 * A screen signal is an opportunity, not a learning decision. Keep it narrow
 * enough to avoid spending a model call on questions such as "Should I run
 * this?", while recognizing explicit knowledge and feedback that a planner
 * can later classify as a preference, project fact, or durable rule.
 */
const DURABLE_USER_PATTERN = /\b(?:prefer|always|never|must|require|decision|remember|durable|future tasks?|from now on|for future|should\s+(?:always|never|be|remain|use|not))\b|偏好|以后|始终|永远|必须|不要|记住|约束|决定|规则|持久/iu;
const KNOWLEDGE_USER_PATTERN = /\b(?:the project|this project|this repository|this repo)\s+(?:uses?|requires?|means?|defines?|treats?)\b|\b(?:is|are)\s+the\s+(?:source of truth|canonical reference)\b|\b(?:means?|defined as|source of truth|canonical reference)\b|事实|定义|真相来源|规范来源/iu;
const CONSTRAINT_USER_PATTERN = /\b(?:never|do not|don['’]t|must not|should not|prohibit(?:ed|s|ing)?|always\s+block)\b|不要|禁止|不得|严禁|切勿/iu;
const VALIDATION_USER_PATTERN = /\b(?:add|write|create|require|verify|check|assert|test|keep)\b[^\n]{0,100}\b(?:test|check|assert|guard|validation|invariant|regression)\b|增加[^\n]{0,40}(?:测试|检查|断言|验证|回归)|验证[^\n]{0,40}(?:必须|不应|不能|禁止)/iu;
const CORRECTION_PATTERN = /\b(wrong|instead|confirmed|retry)\b|不对|改成|而不是|确认|重试|纠正/iu;
const AGENTS_PATTERN = /AGENTS\.md|instruction|workflow|process|convention|architecture|指令|流程|规范|架构/iu;
const TOOL_FAILURE_PATTERN = /(?:^|\n)\s*(?:error|fatal)\s*:|\b(?:build|compilation|tests?|checks?)\b[^\n]{0,80}\bfailed\b|(?:构建|编译|测试|检查)失败/iu;
const VERIFICATION_SUCCESS_PATTERN = /\b(?:build|compilation|tests?|checks?)\b[^\n]{0,80}\b(?:passed|succeeded|successful)\b|(?:^|\n)\s*\d+ passed\b|(?:构建|编译|测试|检查)(?:成功|通过)/iu;
/** The Harness surface owns the `harness-` custom-type namespace and the notes
 * it attaches to tool results. Repository text that merely mentions policies,
 * harness files, or guarded words is not Harness activity. */
const HARNESS_OWNED_CUSTOM_PREFIX = "harness-";
const HARNESS_TOOL_MARKERS = [HARNESS_BASH_NOTE_PREFIX, HARNESS_CONFIG_NOTE_PREFIX];
const HARNESS_SCOPED_GUIDANCE_PATTERN = /\[harness:[^\]\r\n]+\]/u;

export function snapshotEntries(ctx: { sessionManager?: { buildContextEntries?: () => readonly unknown[]; getBranch?: () => readonly unknown[] } }): readonly unknown[] {
  const manager = ctx.sessionManager;
  if (!manager) return [];
  try {
    const context = manager.buildContextEntries?.();
    if (Array.isArray(context)) return context;
  } catch {
    // Fall back to the branch snapshot.
  }
  try {
    const branch = manager.getBranch?.();
    return Array.isArray(branch) ? branch : [];
  } catch {
    return [];
  }
}

function entryRole(entry: unknown): string {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return "";
  const value = entry as Record<string, unknown>;
  const message = value.message;
  if (message && typeof message === "object" && !Array.isArray(message)) {
    const role = (message as Record<string, unknown>).role;
    if (typeof role === "string") return role;
  }
  return typeof value.role === "string" ? value.role : "";
}

function collectText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(collectText).join("\n");
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return [record.text, record.content, record.message, record.reason, record.error].map(collectText).join("\n");
}

function entryCustomType(entry: unknown): string {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return "";
  const record = entry as Record<string, unknown>;
  const message = record.message && typeof record.message === "object" && !Array.isArray(record.message) ? record.message as Record<string, unknown> : undefined;
  const customType = record.customType ?? message?.customType;
  return typeof customType === "string" ? customType : "";
}

/** Harness transcript evidence: its own entry/message type, an attached tool
 * note, or the scoped-guidance prefix it delivers. */
function harnessOwnedActivity(entry: unknown): boolean {
  if (entryCustomType(entry).startsWith(HARNESS_OWNED_CUSTOM_PREFIX)) return true;
  const text = collectText(entry);
  return HARNESS_TOOL_MARKERS.some((marker) => text.includes(marker)) || HARNESS_SCOPED_GUIDANCE_PATTERN.test(text);
}

const MAX_HARNESS_EVENT_CHARS = 1_000;
/** Decision fields first, then the prose the Harness surface recorded. */
const HARNESS_EVENT_DATA_FIELDS = ["outcome", "tool", "policy", "ruleId", "prompt", "reason", "message", "detail"];
const HARNESS_EVENT_NOTE_LINES = 12;

function entryData(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const data = (value as Record<string, unknown>).data;
  return data && typeof data === "object" && !Array.isArray(data) ? data as Record<string, unknown> : {};
}

/** The marker line and the guidance block it introduces, never the surrounding
 * command output the note was attached to. */
function harnessOwnedNoteText(text: string): string[] {
  const lines = text.split(/\r?\n/u);
  const notes: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!HARNESS_TOOL_MARKERS.some((marker) => line.includes(marker)) && !HARNESS_SCOPED_GUIDANCE_PATTERN.test(line)) continue;
    const block: string[] = [];
    for (let cursor = index; cursor < lines.length && block.length < HARNESS_EVENT_NOTE_LINES; cursor += 1) {
      if (cursor > index && !lines[cursor].trim()) break;
      block.push(lines[cursor].trim());
    }
    notes.push(block.join("\n"));
    index += block.length - 1;
  }
  return notes;
}

/** One bounded line for a harness-owned activity, in the order a planner reads
 * it: what the Harness surface decided, and the prose it recorded. Dossiers
 * carry this instead of repository text that merely names the harness. */
export function harnessOwnedEventSummary(entry: unknown): string | undefined {
  if (!harnessOwnedActivity(entry)) return undefined;
  const data = entryData(entry);
  const fields = HARNESS_EVENT_DATA_FIELDS
    .map((field) => typeof data[field] === "string" ? (data[field] as string).replace(/\s+/gu, " ").trim() : "")
    .filter(Boolean);
  const prose = harnessOwnedNoteText(collectText(entry));
  const summary = [...new Set([...fields, ...prose])].join(" · ").slice(0, MAX_HARNESS_EVENT_CHARS).trim();
  return summary || undefined;
}

/** A recovery is a candidate for review, not proof of a durable lesson. */
function hasVerifiedToolRecovery(entries: readonly unknown[]): boolean {
  let failure: { toolName: unknown } | undefined;
  let recovered = false;
  for (const entry of entries) {
    if (entryRole(entry) !== "toolResult") continue;
    const record = entry as Record<string, unknown>;
    const message = record.message && typeof record.message === "object" && !Array.isArray(record.message)
      ? record.message as Record<string, unknown> : record;
    const details = message.details && typeof message.details === "object"
      ? message.details as Record<string, unknown> : undefined;
    const text = collectText(message.content);
    if (message.isError === true || (typeof details?.exitCode === "number" && details.exitCode !== 0) || TOOL_FAILURE_PATTERN.test(text)) {
      failure = { toolName: message.toolName };
      recovered = false;
    } else if (failure && (!failure.toolName || !message.toolName || failure.toolName === message.toolName) && VERIFICATION_SUCCESS_PATTERN.test(text)) {
      recovered = true;
    }
  }
  return recovered;
}

/** Evidence the parent screen can derive from one Task Slice without a model. */
export interface LearningSignals {
  /** User text states a preference, decision, or constraint. */
  durableUser: boolean;
  /** User text prohibits or requires something. */
  constraint: boolean;
  /** User text corrects an earlier answer or instruction. */
  correction: boolean;
  /** User text corrects project instructions named by AGENTS_PATTERN. */
  instructions: boolean;
  /** A failed tool call was followed by a verified success. */
  recovery: boolean;
  /** The Harness surface acted in this task. */
  harnessActivity: boolean;
}

type ScreenLearningSignals = LearningSignals & {
  knowledge: boolean;
  validation: boolean;
};

function deriveLearningSignals(entries: readonly unknown[]): ScreenLearningSignals {
  const userTexts = entries.filter((entry) => entryRole(entry) === "user").map(collectText).filter(Boolean);
  const constraint = userTexts.some((text) => CONSTRAINT_USER_PATTERN.test(text));
  const correction = userTexts.some((text) => CORRECTION_PATTERN.test(text));
  const knowledge = userTexts.some((text) => DURABLE_USER_PATTERN.test(text) || KNOWLEDGE_USER_PATTERN.test(text));
  const validation = userTexts.some((text) => VALIDATION_USER_PATTERN.test(text));
  return {
    durableUser: constraint || knowledge,
    constraint,
    correction,
    instructions: userTexts.some((text) => CORRECTION_PATTERN.test(text) && AGENTS_PATTERN.test(text)),
    recovery: hasVerifiedToolRecovery(entries),
    harnessActivity: entries.some(harnessOwnedActivity),
    knowledge,
    validation,
  };
}

/** Preserve the compact public signal shape; routing-only detail stays private. */
export function learningSignals(entries: readonly unknown[]): LearningSignals {
  const signals = deriveLearningSignals(entries);
  return {
    durableUser: signals.durableUser,
    constraint: signals.constraint,
    correction: signals.correction,
    instructions: signals.instructions,
    recovery: signals.recovery,
    harnessActivity: signals.harnessActivity,
  };
}

/** Every phase the deterministic screen can back with evidence. */
function evidenceSignals(signals: ScreenLearningSignals): { memory: boolean; harness: boolean; agents: boolean } {
  return {
    memory: signals.durableUser || signals.recovery,
    harness: signals.constraint || signals.correction || signals.validation || signals.harnessActivity,
    agents: signals.instructions,
  };
}

export function screenLearningEntries(entries: readonly unknown[], mode: LearningMode): LearningScreen {
  if (mode === "full") return { memory: true, harness: true, agents: true, reasons: ["manual-full"] };
  if (mode === "manual") return { memory: true, harness: true, agents: true, reasons: ["manual-incremental"] };
  const signals = deriveLearningSignals(entries);
  const evidence = evidenceSignals(signals);
  return {
    ...evidence,
    reasons: [
      signals.durableUser ? "durable-user-evidence" : signals.recovery ? "verified-tool-recovery" : "no-durable-memory-evidence",
      signals.constraint || signals.correction ? "constraint-evidence" : signals.validation ? "validation-evidence" : signals.harnessActivity ? "verified-harness-event" : "no-harness-evidence",
      signals.instructions ? "instruction-evidence" : "no-agents-evidence",
    ],
  };
}

/** Settings and extension status rows are not knowledge to learn from. */
export function hasLearningInput(entries: readonly unknown[]): boolean {
  return entries.some(entry => {
    if (entryRole(entry) !== "user" && entryRole(entry) !== "toolResult") return false;
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return false;
    const record = entry as Record<string, unknown>;
    const message = record.message && typeof record.message === "object"
      ? record.message as Record<string, unknown> : record;
    return collectText(message.content).trim().length > 0;
  });
}

/**
 * An explicit consolidation still honors the selector's reviewed verdict. Only
 * user-stated evidence (or Harness activity in this task) floors it: a verified
 * tool recovery is a review candidate, not durable evidence, so it must not
 * start a planner the selector declined after reading this same slice.
 */
export function manualIncrementalScreen(entries: readonly unknown[], selection: { memory: boolean; harness: boolean; agents: boolean }): LearningScreen {
  const signals = deriveLearningSignals(entries);
  const authoritative = { memory: signals.durableUser, harness: signals.constraint || signals.correction || signals.validation || signals.harnessActivity, agents: signals.instructions };
  const evidence = evidenceSignals(signals);
  const memory = selection.memory || authoritative.memory;
  const harness = selection.harness || authoritative.harness;
  const agents = selection.agents || authoritative.agents;
  return {
    memory,
    harness,
    agents,
    reasons: [
      "manual-incremental",
      memory
        ? authoritative.memory ? "durable-user-evidence" : "selector-selected-memory"
        : evidence.memory ? "selector-declined-memory" : "no-durable-memory-evidence",
      harness
        ? authoritative.harness ? (signals.constraint || signals.correction ? "constraint-evidence" : signals.validation ? "validation-evidence" : "verified-harness-event") : "selector-selected-harness"
        : authoritative.harness ? "selector-declined-harness" : "no-harness-evidence",
      agents
        ? authoritative.agents ? "instruction-evidence" : "selector-selected-agents"
        : authoritative.agents ? "selector-declined-agents" : "no-agents-evidence",
    ],
  };
}

export type PlannerFailure = "syntax" | "validation" | "model" | "timeout" | "cancelled" | "output-limit" | "stale" | "other";
export type PlannerRetry = "none" | "incremental-memory-repair" | "full-planner-retry";

export interface PlannerRetryInput {
  mode: LearningMode;
  phase: Exclude<LearningPhase, "selector">;
  attempt: number;
  failure: PlannerFailure;
  mutated: boolean;
}

export function classifyPlannerRetry(input: PlannerRetryInput): PlannerRetry {
  if (input.attempt > 0 || input.mutated) return "none";
  if (input.failure !== "syntax" && input.failure !== "validation") return "none";
  if (input.mode === "full") return "full-planner-retry";
  return input.phase === "memory" ? "incremental-memory-repair" : "none";
}

export function shouldRetryPlanner(input: PlannerRetryInput): boolean {
  return classifyPlannerRetry(input) !== "none";
}

export interface LearningPipelineReceipt {
  kind: "learning-pipeline-receipt";
  version: 1;
  mode: LearningMode;
  screen: LearningScreen;
  attempts: LearningAttempt[];
  totals: PiWorkerUsage;
  /** False when totals contain only the known subtotal of attempted calls. */
  usageAvailable?: boolean;
  costAvailable: boolean;
  operations: number;
  retries: number;
  input?: LearningInputSource;
}

export interface LearningInputSource {
  source: "current-session" | "recent-project-session" | "existing-memory" | "none";
  entryCount: number;
  omittedEntries?: number;
  sessionId?: string;
  sourceDigest?: string;
}

function allLearningUsageAvailable(attempts: readonly LearningAttempt[]): boolean {
  return attempts.every(attempt => attempt.usage !== undefined || attempt.outcome === "skipped" || attempt.outcome === "screened");
}

export function buildLearningReceipt(mode: LearningMode, screen: LearningScreen, attempts: LearningAttempt[], input?: LearningInputSource): LearningPipelineReceipt {
  return {
    kind: "learning-pipeline-receipt",
    version: 1,
    mode,
    screen,
    attempts,
    totals: totalLearningUsage(attempts),
    usageAvailable: allLearningUsageAvailable(attempts),
    costAvailable: attempts.every((attempt) => {
      if (!attempt.usage) return (attempt.outcome === "skipped" || attempt.outcome === "screened") && attempt.costAvailable !== false;
      const hasUsage = attempt.usage.input > 0 || attempt.usage.output > 0 || attempt.usage.cacheRead > 0 || attempt.usage.cacheWrite > 0 || attempt.usage.totalTokens > 0;
      return attempt.costAvailable ?? !(hasUsage && attempt.usage.cost === 0);
    }),
    operations: attempts.reduce((total, attempt) => total + attempt.operations, 0),
    retries: attempts.filter((attempt) => attempt.attempt > 0).length,
    ...(input ? { input } : {}),
  };
}

export async function writeLearningReceipt(directory: string, receipt: LearningPipelineReceipt): Promise<string> {
  await fs.mkdir(directory, { recursive: true });
  const target = path.join(directory, "learning-pipeline-receipt.json");
  const temporary = `${target}.${process.pid}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(temporary, target);
  return target;
}

export function formatLearningUsage(usage: PiWorkerUsage): string {
  return `input ${usage.input} · output ${usage.output} · cacheRead ${usage.cacheRead} · cacheWrite ${usage.cacheWrite} · total ${usage.totalTokens}`;
}

export function formatLearningCost(usage: PiWorkerUsage, costAvailable = true): string {
  const hasUsage = usage.input > 0 || usage.output > 0 || usage.cacheRead > 0 || usage.cacheWrite > 0 || usage.totalTokens > 0;
  if (!costAvailable || (usage.cost === 0 && hasUsage)) return "cost unavailable";
  return `$${usage.cost.toFixed(4)}`;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function validUsage(value: unknown): value is PiWorkerUsage {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const usage = value as Partial<PiWorkerUsage>;
  return [usage.input, usage.output, usage.cacheRead, usage.cacheWrite, usage.totalTokens, usage.cost].every(finiteNumber);
}

export function isLearningPipelineReceipt(value: unknown): value is LearningPipelineReceipt {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const receipt = value as Partial<LearningPipelineReceipt>;
  const modes: LearningMode[] = ["automatic", "manual", "full"];
  const phases: LearningPhase[] = ["selector", "memory", "harness", "agents"];
  const outcomes: LearningOutcome[] = ["screened", "skipped", "noop", "applied", "proposed", "rejected", "failed", "cancelled"];
  const screen = receipt.screen as Partial<LearningScreen> | undefined;
  const input = receipt.input;
  const validInput = input === undefined || Boolean(input && typeof input === "object"
    && ["current-session", "recent-project-session", "existing-memory", "none"].includes(input.source)
    && Number.isSafeInteger(input.entryCount) && input.entryCount >= 0
    && (input.omittedEntries === undefined || Number.isSafeInteger(input.omittedEntries) && input.omittedEntries >= 0)
    && (input.sessionId === undefined || (typeof input.sessionId === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(input.sessionId)))
    && (input.sourceDigest === undefined || (typeof input.sourceDigest === "string" && /^[a-f0-9]{64}$/.test(input.sourceDigest))));
  return validInput && receipt.kind === "learning-pipeline-receipt" && receipt.version === 1 &&
    typeof receipt.mode === "string" && modes.includes(receipt.mode as LearningMode) &&
    Boolean(screen && typeof screen.memory === "boolean" && typeof screen.harness === "boolean" && typeof screen.agents === "boolean" && Array.isArray(screen.reasons) && screen.reasons.every((reason) => typeof reason === "string")) &&
    Array.isArray(receipt.attempts) && receipt.attempts.every((attempt) =>
      Boolean(attempt && phases.includes(attempt.phase) && outcomes.includes(attempt.outcome) && Number.isSafeInteger(attempt.attempt) && attempt.attempt >= 0 && finiteNumber(attempt.durationMs) && finiteNumber(attempt.operations) && (attempt.pendingOperations === undefined || Number.isSafeInteger(attempt.pendingOperations) && attempt.pendingOperations >= 0) && (attempt.usage === undefined || validUsage(attempt.usage)))) &&
    (receipt.usageAvailable === undefined || typeof receipt.usageAvailable === "boolean") &&
    validUsage(receipt.totals) && finiteNumber(receipt.operations) && typeof receipt.retries === "number" && Number.isSafeInteger(receipt.retries) && receipt.retries >= 0 && typeof receipt.costAvailable === "boolean";
}

function surfaceCount(receipt: LearningPipelineReceipt, phase: "memory" | "harness" | "agents"): number {
  return receipt.attempts
    .filter((attempt) => attempt.phase === phase && attempt.outcome === "applied")
    .reduce((total, attempt) => total + attempt.operations, 0);
}

function surfaceLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function learningSummarySubject(receipt: LearningPipelineReceipt): string {
  const memory = surfaceCount(receipt, "memory");
  const harness = surfaceCount(receipt, "harness");
  const agents = surfaceCount(receipt, "agents");
  const surfaces = [
    ...(memory > 0 ? [surfaceLabel(memory, "memory", "memories")] : []),
    ...(harness > 0 ? [surfaceLabel(harness, "harness change", "harness changes")] : []),
    ...(agents > 0 ? [surfaceLabel(agents, "AGENTS.md change", "AGENTS.md changes")] : []),
  ];
  const pending = receipt.attempts.reduce((sum, attempt) => sum + (attempt.pendingOperations ?? 0), 0);
  if (surfaces.length > 0) return `${surfaces.join(" and ")} applied${pending ? `; ${pending} pending review` : ""}`;
  if (receipt.attempts.some(attempt => attempt.outcome === "proposed")) return "proposals saved for review";
  if (receipt.attempts.some((attempt) => attempt.outcome === "failed" || attempt.outcome === "rejected")) return "finished with issues";
  if (receipt.attempts.some(attempt => attempt.outcome === "cancelled")) return "cancelled";
  if (receipt.attempts.length === 0 && receipt.screen.reasons.includes("no-learning-inputs")) return "no learning input";
  return "no durable changes";
}

function receiptUsageAvailable(receipt: LearningPipelineReceipt): boolean {
  return receipt.usageAvailable !== false && allLearningUsageAvailable(receipt.attempts);
}

function receiptUsageText(receipt: LearningPipelineReceipt): string {
  if (receiptUsageAvailable(receipt)) return formatLearningUsage(receipt.totals);
  return receipt.totals.totalTokens > 0 ? `${formatLearningUsage(receipt.totals)} · known subtotal; total unavailable` : "usage unavailable";
}

function receiptCostText(receipt: LearningPipelineReceipt): string {
  if (receiptUsageAvailable(receipt)) return formatLearningCost(receipt.totals, receipt.costAvailable);
  return receipt.totals.cost > 0 ? `cost unavailable · known subtotal ${formatLearningCost(receipt.totals)}` : "cost unavailable";
}

export function learningSummaryDetails(receipt: LearningPipelineReceipt): string[] {
  const phaseLines = receipt.attempts.map((attempt) => `${attempt.phase}: ${attempt.outcome} · ${attempt.operations} change(s) · ${attempt.durationMs} ms`);
  return [
    fieldLine("mode", receipt.mode),
    ...(receipt.input ? [fieldLine("source", `${receipt.input.source} · ${receipt.input.entryCount} entries${receipt.input.omittedEntries ? ` · ${receipt.input.omittedEntries} omitted; proposals only` : ""}${receipt.input.sessionId ? ` · ${receipt.input.sessionId}` : ""}`)] : []),
    ...(receipt.screen.reasons.includes("no-learning-inputs") ? ["No session evidence or existing Memory. Resume a task session or use /memory <request>."] : []),
    fieldLine("operations", receipt.operations),
    fieldLine("calls", receipt.attempts.length),
    fieldLine("usage", receiptUsageText(receipt)),
    fieldLine("cost", receiptCostText(receipt)),
    fieldLine("directions", [receipt.screen.memory ? "memory" : "", receipt.screen.harness ? "harness" : "", receipt.screen.agents ? "agents" : ""].filter(Boolean).join(", ") || "none"),
    ...receipt.attempts.flatMap(attempt => [
      ...(attempt.selectedMemory ? [fieldLine("selected Memory", attempt.selectedMemory.join(", ") || "none")] : []),
      ...(attempt.diagnostic ? [fieldLine(`${attempt.phase} reason`, attempt.diagnostic)] : []),
      ...(attempt.jev ? [fieldLine(`Jev ${attempt.jev.stage}`, `${attempt.jev.status}: ${attempt.jev.reason}${typeof attempt.jev.httpStatus === "number" && Number.isSafeInteger(attempt.jev.httpStatus) && attempt.jev.httpStatus >= 400 && attempt.jev.httpStatus <= 599 ? ` · HTTP ${attempt.jev.httpStatus}` : ""}${attempt.jev.candidateIndex !== undefined && attempt.jev.dimension ? ` · candidate ${attempt.jev.candidateIndex} ${attempt.jev.dimension}${attempt.jev.field === "description" ? ".description" : ""}` : ""}${jevCounterLocationText(attempt.jev) ? ` · ${jevCounterLocationText(attempt.jev)}` : ""}${attempt.jev.strategy === "cited-support-full-review" ? ` · full review ${attempt.jev.coveredEntries}/${attempt.jev.evidenceEntries} entries (${attempt.jev.completedWindows}/${attempt.jev.evidenceWindows} windows)` : attempt.jev.strategy === "same-batch-relations" ? " · same-batch relations" : attempt.jev.strategy === "standalone-memory" ? " · standalone meaning" : ""} · ${attempt.jev.model ?? "no model response"} · ${attempt.jev.durationMs} ms · input ${attempt.jev.inputTokens ?? (attempt.jev.knownInputTokens !== undefined ? `unknown (at least ${attempt.jev.knownInputTokens})` : "unknown")} · output ${attempt.jev.outputTokens ?? "unknown"} · estimated cost ${attempt.jev.estimatedCostUsd === undefined ? (attempt.jev.knownEstimatedCostUsd !== undefined ? `unknown (at least $${attempt.jev.knownEstimatedCostUsd.toFixed(8)})` : "unavailable") : `$${attempt.jev.estimatedCostUsd.toFixed(8)}`}`)] : []),
    ]),
    ...phaseLines,
  ];
}

export function formatLearningSummary(receipt: LearningPipelineReceipt): string {
  return `Learning ${learningSummarySubject(receipt)} · ${receiptUsageText(receipt)} · ${receiptCostText(receipt)}`;
}

export function totalLearningUsage(attempts: readonly LearningAttempt[]): PiWorkerUsage {
  return attempts.reduce<PiWorkerUsage>((total, attempt) => {
    const usage = attempt.usage;
    if (!usage) return total;
    return {
      input: total.input + usage.input,
      output: total.output + usage.output,
      cacheRead: total.cacheRead + usage.cacheRead,
      cacheWrite: total.cacheWrite + usage.cacheWrite,
      totalTokens: total.totalTokens + usage.totalTokens,
      cost: total.cost + usage.cost,
    };
  }, { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0 });
}

export function shouldReportLearningReceipt(receipt: LearningPipelineReceipt, requested: boolean): boolean {
  return requested || (receipt.mode === "automatic" && receipt.attempts.some(attempt =>
    ["proposed", "failed", "rejected", "cancelled"].includes(attempt.outcome) || (attempt.phase !== "selector" && attempt.outcome === "applied")));
}

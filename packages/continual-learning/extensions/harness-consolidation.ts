/**
 * Harness consolidation phase — the second half of the /consolidate pipeline.
 *
 * Runs after a verified memory consolidation against the SAME immutable
 * session snapshot: a read-only planner child mines tool-call guardrail
 * evidence (blocked calls and reasons, confirmation outcomes, user
 * corrections) and returns one bounded `harness-consolidation-plan`. The
 * parent alone applies it, merging atomically into the personal project-local
 * layer (<cwd>/.pi/harness.local.json). Shared layers are never written, and
 * any failure here never touches already-applied memory results.
 */

import fs from "node:fs/promises";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  createPackageAgentRun,
  minimalPiWorkerArgs,
  notifyPi,
  parsePiWorkerOutput,
  resolvePiCli,
  spawnPiChild,
  type PiWorkerUsage,
} from "@fradser/pi-kit";
import {
  createConsolidationRun,
  extractChildPlan,
  releaseConsolidationRun,
  sha256Digest,
  terminateConsolidationChild,
  writeFileAtomic,
  MAX_JSONL_LINE_BYTES,
  MAX_JSONL_LINES,
  MAX_PLAN_BYTES,
  MAX_STDOUT_BYTES,
  type ConsolidationRun,
} from "./consolidation-run";
import { DEFAULT_POLICIES, evaluate, evaluatePhase, mergeLayers, validatePolicyDeclaration, validateSkillPromptDeclaration } from "./guardrail-engine";
import { configPaths, loadLayers } from "./guardrail-config";
import type { PolicyLayer, PolicyPhase } from "./guardrail-types";
import type { ToolCallInput } from "./guardrail-engine";

export const HARNESS_PLAN_KIND = "harness-consolidation-plan";
export const MAX_HARNESS_OPS = 12;
export const MAX_HARNESS_REPORTS = 12;
export const MAX_POLICY_BYTES = 8_192;
export const MAX_SKILL_PROMPT_CHARS = 2_000;
export const MAX_EVIDENCE_QUOTE_CHARS = 2_000;
export const MAX_POLICY_CASES = 12;
export const MAX_POLICY_CASE_ARG_BYTES = 8_192;
export const MAX_POLICY_CASE_TEXT_CHARS = 8_192;
const HARNESS_PHASE_TIMEOUT_MS = 15 * 60 * 1000;
const HARNESS_OP_KINDS = ["addPolicy", "updatePolicy", "disablePolicy", "addSkillPrompt", "removeSkillPrompt"] as const;
export type HarnessOpKind = (typeof HARNESS_OP_KINDS)[number];

/** Terminal gate for the second pipeline phase, shared by callers and tests:
 * only a finished, verified, context-captured memory phase unlocks it. */
export type PipelineGateState = { outcome?: string; active: boolean; cancelled: boolean };
export function shouldRunHarnessPhase(state: PipelineGateState, noContext?: boolean): "run" | "skip-no-context" | "wait" | "skip" {
  if (noContext) return "skip-no-context";
  if (state.cancelled || state.outcome === undefined || state.active) return "wait";
  return state.outcome === "completed" ? "run" : "skip";
}

export interface HarnessOp {
  op: HarnessOpKind;
  name?: string;
  policy?: Record<string, unknown>;
  prompt?: string;
  target?: string;
  userMessagePattern?: string;
  /** Executable transfer tests required for learned policy add/update ops. */
  cases?: unknown;
}

export type HarnessEvidenceSource = "user" | "tool";

export interface HarnessEvidence {
  index: number;
  quote: string;
  source: HarnessEvidenceSource;
  observation?: string;
  count: number;
  eventIndex?: number;
}

export interface HarnessPolicyCase {
  /** Required in automatic plans so each transfer test names its evaluator. */
  phase?: PolicyPhase;
  toolName?: string;
  args?: Record<string, unknown>;
  /** Output/artifact cases are evaluated against this bounded text fixture. */
  text?: string;
  expected?: "match" | "no-match" | "block" | "confirm" | "observe";
  action?: "block" | "confirm" | "observe";
}

export interface HarnessPolicyCases {
  positive: HarnessPolicyCase[];
  negative: HarnessPolicyCase[];
}

/** Inputs needed for the autonomous parent-side gates. `snapshot` may be the
 * parsed snapshot object or its `entries` array. `snapshotText` is retained so
 * quote checks use the exact immutable bytes the child was given. */
export interface HarnessPlanValidationOptions {
  availableSkills?: ReadonlySet<string> | readonly string[];
  snapshot?: unknown;
  snapshotText?: string;
  layers?: readonly PolicyLayer[];
  learnedPolicyNames?: ReadonlySet<string> | readonly string[];
  /** Evidence is supplied separately when validating ops before apply. */
  evidence?: unknown;
  /** Automatic consolidation owns only rules marked by this metadata. */
  automatic?: boolean;
  /** Internal apply path: skip the already-checked top-level evidence array. */
  requireEvidence?: boolean;
  requireCases?: boolean;
}

export interface HarnessConsolidationPlan {
  kind: typeof HARNESS_PLAN_KIND;
  version?: number;
  schemaVersion?: number;
  runId?: string;
  scopeDigest?: string;
  artifactHash?: string;
  operations?: unknown;
  evidence?: unknown;
  report?: unknown;
}

/** Structural subset of the shared dream state both phases coordinate on. */
export interface ConsolidationPhaseState {
  active: boolean;
  generation: number;
  cancelled: boolean;
}

function policyNameValid(name: unknown): name is string {
  return typeof name === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name);
}

function boundedString(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function asStringSet(value: unknown): ReadonlySet<string> | undefined {
  if (value instanceof Set) return value;
  if (Array.isArray(value) && value.every((entry) => typeof entry === "string")) return new Set(value);
  if (isRecord(value) && typeof value.has === "function") return value as unknown as ReadonlySet<string>;
  return undefined;
}

function availableSkills(options: HarnessPlanValidationOptions): ReadonlySet<string> | undefined {
  return asStringSet(options.availableSkills);
}

interface SnapshotEvidenceSource {
  text: string;
  entries: unknown[];
}

function snapshotEvidenceSource(options: HarnessPlanValidationOptions): SnapshotEvidenceSource | undefined {
  let snapshot = options.snapshot;
  let text = options.snapshotText;
  if (typeof snapshot === "string") {
    text ??= snapshot;
    try { snapshot = JSON.parse(snapshot) as unknown; } catch { snapshot = undefined; }
  }
  if (snapshot === undefined && text !== undefined) {
    try { snapshot = JSON.parse(text) as unknown; } catch { snapshot = undefined; }
  }
  if (text === undefined && snapshot !== undefined) {
    try { text = JSON.stringify(snapshot); } catch { text = undefined; }
  }
  if (!text || snapshot === undefined) return undefined;
  const entries = Array.isArray(snapshot)
    ? snapshot
    : isRecord(snapshot) && Array.isArray(snapshot.entries)
      ? snapshot.entries
      : [];
  return { text, entries };
}

function quoteVariants(quote: string): string[] {
  const values = [quote];
  try {
    const encoded = JSON.stringify(quote);
    if (typeof encoded === "string") values.push(encoded.slice(1, -1));
  } catch {
    // The bounded string was already checked; this is only a defensive guard
    // for callers that pass a hostile object through the public API.
  }
  return [...new Set(values.filter(Boolean))];
}

function countOccurrences(quote: string, text: string): number {
  const haystack = text;
  return Math.max(...quoteVariants(quote).map((needle) => {
    if (!needle) return 0;
    let count = 0;
    let offset = 0;
    while ((offset = haystack.indexOf(needle, offset)) >= 0) {
      count += 1;
      offset += needle.length;
    }
    return count;
  }));
}

/** A quote is admissible only when it occurs in the exact snapshot bytes (or
 * in their JSON string encoding) and in an allowed content leaf. */
export function quoteInHarnessSnapshot(quote: string, snapshotText: string): boolean {
  if (!quote.trim()) return false;
  return countOccurrences(quote, snapshotText) > 0;
}

function isToolResultRole(role: string): boolean {
  return role === "tool" || role === "toolresult" || role === "tool-result" || role === "tool_result";
}

function evidenceSourceOfSnapshotEntry(entry: unknown): HarnessEvidenceSource | "model" | undefined {
  if (!isRecord(entry)) return undefined;
  const explicit = entry.actor ?? entry.author ?? entry.source;
  if (explicit === "user" || explicit === "user-requirement" || explicit === "user-correction") return "user";
  if (explicit === "tool" || explicit === "tool-outcome" || explicit === "tool-call") return "tool";
  const type = typeof entry.type === "string" ? entry.type.toLowerCase() : "";
  const message = isRecord(entry.message) ? entry.message : undefined;
  const role = message && typeof message.role === "string" ? message.role.toLowerCase() : typeof entry.role === "string" ? entry.role.toLowerCase() : "";
  if (/(tool|policy|execution|result|call)/.test(type) || "toolName" in entry || "toolCall" in entry) return "tool";
  if (role === "user") return "user";
  if (role === "assistant" || role === "system") return "model";
  if (isToolResultRole(role)) return "tool";
  return undefined;
}

function contentTextLeaves(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(contentTextLeaves);
  if (isRecord(value)) {
    if (typeof value.text === "string") return [value.text];
    const nested = ["content", "output", "stdout", "stderr", "message", "error", "result"]
      .map((field) => value[field])
      .filter((field) => field !== undefined);
    return nested.flatMap(contentTextLeaves);
  }
  return [];
}

/** Return only conversational content or tool-result fields. Event metadata
 * such as a policy name, path, or tool name is deliberately excluded so an
 * evidence quote cannot be manufactured from the snapshot envelope. */
function evidenceTextOfSnapshotEntry(entry: unknown, source: HarnessEvidenceSource): string {
  if (!isRecord(entry)) return "";
  const message = isRecord(entry.message) ? entry.message : undefined;
  const role = message && typeof message.role === "string" ? message.role.toLowerCase() : typeof entry.role === "string" ? entry.role.toLowerCase() : "";
  if (source === "user") {
    const content = message?.content ?? (role === "user" ? entry.content : undefined);
    return contentTextLeaves(content).join("\n");
  }
  if (isToolResultRole(role)) return contentTextLeaves(message?.content ?? entry.content).join("\n");
  const resultFields = ["result", "output", "error"];
  return resultFields.flatMap((field) => contentTextLeaves(entry[field])).join("\n");
}

function sourceFromEvidence(raw: unknown): HarnessEvidenceSource | undefined {
  if (!isRecord(raw)) return undefined;
  const source = raw.source;
  if (source === "user") return "user";
  if (source === "tool") return "tool";
  return undefined;
}

function evidenceForOperation(
  p: HarnessConsolidationPlan,
  options: HarnessPlanValidationOptions,
  opsLength: number,
  strict: boolean,
  requireEvidence: boolean,
  errors: string[],
): void {
  const rawEvidence = options.evidence ?? p.evidence;
  if (opsLength === 0) return;
  if (!Array.isArray(rawEvidence)) {
    if (requireEvidence) errors.push("evidence must be an array citing every operation index");
    return;
  }
  const snapshot = strict ? snapshotEvidenceSource(options) : undefined;
  if (strict && !snapshot) errors.push("snapshot is required to verify harness evidence");
  const cited = new Set<number>();
  rawEvidence.forEach((raw, i) => {
    const label = `evidence[${i}]`;
    if (!isRecord(raw)) {
      errors.push(`${label} is not an object`);
      return;
    }
    const idx = typeof raw.index === "number" && Number.isInteger(raw.index) ? raw.index : -1;
    if (idx < 0 || idx >= opsLength) {
      errors.push(`${label}.index out of range`);
      return;
    }
    cited.add(idx);
    const quote = raw.quote;
    if (strict && !boundedString(quote, MAX_EVIDENCE_QUOTE_CHARS)) {
      errors.push(`${label}.quote must be 1..${MAX_EVIDENCE_QUOTE_CHARS} chars`);
    }
    if (!strict && raw.quote !== undefined && !boundedString(raw.quote, MAX_EVIDENCE_QUOTE_CHARS)) {
      errors.push(`${label}.quote must be 1..${MAX_EVIDENCE_QUOTE_CHARS} chars`);
    }
    if (!strict && !boundedString(raw.observation, 600)) errors.push(`${label}.observation must be 1..600 chars`);
    if (raw.observation !== undefined && !boundedString(raw.observation, 600)) errors.push(`${label}.observation must be 1..600 chars`);
    const count = raw.count;
    if (typeof count !== "number" || !Number.isInteger(count) || count < 1) {
      errors.push(`${label}.count must be a positive integer`);
    }
    const source = sourceFromEvidence(raw);
    if (strict && !source) errors.push(`${label}.source must identify an observed actor: "user" or "tool"`);
    const eventIndexValue = raw.eventIndex;
    const eventIndex = eventIndexValue === undefined ? undefined : typeof eventIndexValue === "number" && Number.isInteger(eventIndexValue) ? eventIndexValue : -1;
    if (eventIndex !== undefined && (eventIndex < 0 || !snapshot || eventIndex >= snapshot.entries.length)) {
      errors.push(`${label}.eventIndex is outside the snapshot entries`);
    }
    if (!boundedString(quote, MAX_EVIDENCE_QUOTE_CHARS) || !source || typeof count !== "number" || !Number.isInteger(count) || count < 1) return;
    if (strict && snapshot) {
      const candidateEntries = eventIndex === undefined ? snapshot.entries.map((entry, entryIndex) => ({ entry, entryIndex })) : [{ entry: snapshot.entries[eventIndex], entryIndex: eventIndex }];
      const matches = candidateEntries.filter(({ entry }) => evidenceSourceOfSnapshotEntry(entry) === source && countOccurrences(quote, evidenceTextOfSnapshotEntry(entry, source)) > 0);
      if (!quoteInHarnessSnapshot(quote, snapshot.text)) errors.push(`${label}.quote does not occur verbatim in the immutable snapshot`);
      if (!matches.length) errors.push(`${label}.quote is not grounded in a ${source} snapshot event`);
      // `count` is a count of distinct matching user/tool events. Counting
      // repeated substrings inside one event would let one envelope inflate
      // confidence without adding independent evidence.
      const observed = matches.length;
      if (matches.length > 0 && count > observed) errors.push(`${label}.count exceeds occurrences observed for the quoted ${source} evidence`);
    }
  });
  if (requireEvidence) {
    for (let i = 0; i < opsLength; i += 1) {
      if (!cited.has(i)) errors.push(`operations[${i}] has no evidence entry`);
    }
  }
}

function parsePolicyCase(
  raw: unknown,
  label: string,
  errors: string[],
  positive: boolean,
  defaultPhase: PolicyPhase,
  requirePhase: boolean,
): HarnessPolicyCase | undefined {
  if (!isRecord(raw)) {
    errors.push(`${label} is not an object`);
    return undefined;
  }
  if (requirePhase && raw.phase === undefined) {
    errors.push(`${label}.phase is required for an automatic policy case`);
    return undefined;
  }
  const phase = raw.phase === undefined ? defaultPhase : raw.phase;
  if (phase !== "tool-call" && phase !== "output" && phase !== "artifact") {
    errors.push(`${label}.phase must be tool-call, output, or artifact`);
    return undefined;
  }
  const toolName = raw.toolName;
  if (toolName !== undefined && !boundedString(toolName, 128)) {
    errors.push(`${label}.toolName must be 1..128 chars when supplied`);
    return undefined;
  }
  const args = raw.args;
  if (phase === "tool-call" && !isRecord(args)) {
    errors.push(`${label}.args must be an object for a tool-call case`);
    return undefined;
  }
  if (phase === "tool-call" && !boundedString(toolName, 128)) {
    errors.push(`${label}.toolName must be 1..128 chars for a tool-call case`);
    return undefined;
  }
  const text = raw.text;
  if (phase !== "tool-call" && !boundedString(text, MAX_POLICY_CASE_TEXT_CHARS)) {
    errors.push(`${label}.text must be 1..${MAX_POLICY_CASE_TEXT_CHARS} chars for an output or artifact case`);
    return undefined;
  }
  if (phase !== "tool-call" && args !== undefined) {
    errors.push(`${label}.args is only supported for tool-call cases`);
    return undefined;
  }
  const expected = raw.expected === undefined ? (positive ? "match" : "no-match") : raw.expected;
  const validExpected = ["match", "no-match", "block", "confirm", "observe"];
  if (!validExpected.includes(expected as string)) {
    errors.push(`${label}.expected must be match, no-match, block, confirm, or observe`);
    return undefined;
  }
  if (positive && expected === "no-match") errors.push(`${label} positive case must expect a policy match`);
  if (!positive && expected !== "no-match") errors.push(`${label} negative case must expect no policy match`);
  const action = raw.action;
  if (action !== undefined && action !== "block" && action !== "confirm" && action !== "observe") {
    errors.push(`${label}.action must be block, confirm, or observe`);
    return undefined;
  }
  let argsBytes = 0;
  if (args !== undefined) {
    try { argsBytes = Buffer.byteLength(JSON.stringify(args), "utf8"); } catch { argsBytes = MAX_POLICY_CASE_ARG_BYTES + 1; }
    if (argsBytes > MAX_POLICY_CASE_ARG_BYTES) errors.push(`${label}.args exceeds ${MAX_POLICY_CASE_ARG_BYTES} bytes`);
  }
  return {
    phase,
    ...(toolName !== undefined ? { toolName } : {}),
    ...(isRecord(args) ? { args } : {}),
    ...(typeof text === "string" ? { text } : {}),
    expected: expected as HarnessPolicyCase["expected"],
    ...(action !== undefined ? { action: action as HarnessPolicyCase["action"] } : {}),
  };
}

function parsePolicyCases(
  raw: HarnessOp,
  label: string,
  errors: string[],
  required: boolean,
  defaultPhase: PolicyPhase,
): HarnessPolicyCases | undefined {
  const direct = raw.cases;
  const container = direct;
  if (container === undefined) {
    if (required) errors.push(`${label} must include positive and negative policy cases`);
    return undefined;
  }
  if (!isRecord(container)) {
    errors.push(`${label}.cases must be an object`);
    return undefined;
  }
  const positiveRaw = container.positive;
  const negativeRaw = container.negative;
  if (!Array.isArray(positiveRaw) || !Array.isArray(negativeRaw)) {
    errors.push(`${label}.cases must include positive and negative arrays`);
    return undefined;
  }
  if (positiveRaw.length > MAX_POLICY_CASES || negativeRaw.length > MAX_POLICY_CASES) {
    errors.push(`${label}.cases exceed the maximum of ${MAX_POLICY_CASES} per side`);
    return undefined;
  }
  if (required && positiveRaw.length === 0) errors.push(`${label}.cases.positive must contain at least one case`);
  if (required && negativeRaw.length === 0) errors.push(`${label}.cases.negative must contain at least one case`);
  const positive = positiveRaw.flatMap((entry, index) => {
    const parsed = parsePolicyCase(entry, `${label}.cases.positive[${index}]`, errors, true, defaultPhase, required);
    return parsed ? [parsed] : [];
  });
  const negative = negativeRaw.flatMap((entry, index) => {
    const parsed = parsePolicyCase(entry, `${label}.cases.negative[${index}]`, errors, false, defaultPhase, required);
    return parsed ? [parsed] : [];
  });
  return { positive, negative };
}

function validatePolicyCases(policy: Record<string, unknown>, cases: HarnessPolicyCases, label: string, errors: string[]): void {
  const candidate = mergeLayers([{ source: "candidate policy", policies: [policy] }]);
  const policyPhase: PolicyPhase = policy.phase === "output" || policy.phase === "artifact" ? policy.phase : "tool-call";
  const evaluateCase = (testCase: HarnessPolicyCase) => {
    if (testCase.phase !== policyPhase) {
      errors.push(`${label}.cases phase ${testCase.phase} does not match proposed policy phase ${policyPhase}`);
      return null;
    }
    if (testCase.phase === "tool-call") {
      if (!testCase.toolName || !testCase.args) return null;
      return evaluate(candidate, { toolName: testCase.toolName, args: testCase.args } satisfies ToolCallInput);
    }
    if (!testCase.text) return null;
    return evaluatePhase(candidate, {
      phase: testCase.phase,
      text: testCase.text,
      ...(testCase.toolName ? { toolName: testCase.toolName } : {}),
      policyName: policy.name as string,
    });
  };
  for (const [index, testCase] of cases.positive.entries()) {
    const decision = evaluateCase(testCase);
    if (!decision) {
      errors.push(`${label}.cases.positive[${index}] did not match the proposed policy`);
      continue;
    }
    const expectedAction = testCase.action ?? (testCase.expected === "block" || testCase.expected === "confirm" || testCase.expected === "observe" ? testCase.expected : undefined);
    if (expectedAction && decision.action !== expectedAction) errors.push(`${label}.cases.positive[${index}] expected action ${expectedAction} but evaluator returned ${decision.action}`);
  }
  for (const [index, testCase] of cases.negative.entries()) {
    const decision = evaluateCase(testCase);
    if (decision) errors.push(`${label}.cases.negative[${index}] matched policy "${decision.policyName}" but must remain unmatched`);
  }
}

function actionRank(action: unknown): number {
  return action === "confirm" ? 2 : action === "observe" ? 1 : 3;
}

function policyWeakens(existing: Record<string, unknown>, proposed: Record<string, unknown>): boolean {
  const existingPhase = existing.phase ?? "tool-call";
  const proposedPhase = proposed.phase ?? "tool-call";
  if (existingPhase !== proposedPhase) return true;
  if (actionRank(proposed.action) < actionRank(existing.action)) return true;
  // Matcher containment is not decidable from declarations alone. Keep every
  // scope and expression byte-equivalent; only a stronger action or a reason
  // update is an automatic revision that can be trusted without a new owner
  // approval route.
  for (const field of ["tools", "paths", "artifactPaths", "pattern", "patterns", "require"] as const) {
    if (JSON.stringify(existing[field] ?? null) !== JSON.stringify(proposed[field] ?? null)) return true;
  }
  return false;
}

function layerPolicyOwnership(options: HarnessPlanValidationOptions): Map<string, { source: string; policy: Record<string, unknown> }> {
  const ownership = new Map<string, { source: string; policy: Record<string, unknown> }>();
  const layers: PolicyLayer[] = [builtInDefaultsLayer(), ...(options.layers ?? [])];
  for (const layer of layers) {
    for (const raw of layer.policies ?? []) {
      if (!isRecord(raw) || typeof raw.name !== "string") continue;
      ownership.set(raw.name, { source: layer.source, policy: raw });
    }
  }
  return ownership;
}

function learnedNames(options: HarnessPlanValidationOptions): ReadonlySet<string> {
  return asStringSet(options.learnedPolicyNames) ?? new Set();
}

function validateAutomaticOwnership(
  ops: readonly unknown[],
  options: HarnessPlanValidationOptions,
  errors: string[],
): void {
  if (!options.automatic) return;
  const ownership = layerPolicyOwnership(options);
  const skillPromptOwnership = new Map<string, string>();
  for (const layer of options.layers ?? []) {
    for (const name of Object.keys(layer.skillPrompts ?? {})) skillPromptOwnership.set(name, layer.source);
  }
  const learned = learnedNames(options);
  const plannedAdds = new Set<string>();
  const plannedSkillPromptAdds = new Set<string>();
  ops.forEach((raw, index) => {
    if (!isRecord(raw) || typeof raw.op !== "string") return;
    const op = raw as unknown as HarnessOp;
    const label = `operations[${index}]`;
    if (op.op === "addSkillPrompt") {
      const existingSource = skillPromptOwnership.get(op.name ?? "");
      if (existingSource) {
        errors.push(`${label}: skill prompt "${op.name}" already belongs to ${existingSource} and cannot be overwritten by automatic learning`);
      }
      if (plannedSkillPromptAdds.has(op.name ?? "")) {
        errors.push(`${label}: skill prompt "${op.name}" is proposed more than once in one automatic plan`);
      }
      plannedSkillPromptAdds.add(op.name ?? "");
      return;
    }
    if (op.op === "addPolicy") {
      const owner = ownership.get(op.name ?? "");
      if (owner) errors.push(`${label}: policy "${op.name}" already belongs to ${owner.source} and cannot be overridden by automatic learning`);
      plannedAdds.add(op.name ?? "");
      return;
    }
    if (op.op === "updatePolicy") {
      const owner = ownership.get(op.name ?? "");
      if (!owner) return;
      if (owner.source !== "project.local") {
        errors.push(`${label}: policy "${op.name}" is protected because it belongs to ${owner.source}`);
        return;
      }
      if (!learned.has(op.name ?? "") && !plannedAdds.has(op.name ?? "")) {
        errors.push(`${label}: policy "${op.name}" is an unmarked manually authored project-local rule`);
        return;
      }
      const proposed = isRecord(op.policy) ? { ...op.policy, name: op.name } : {};
      if (policyWeakens(owner.policy, proposed)) errors.push(`${label}: automatic learning cannot weaken an existing learned policy; use the explicit /harness command`);
      return;
    }
    if (op.op === "disablePolicy") {
      errors.push(`${label}: automatic learning cannot disable policy "${op.name}"; use the explicit /harness command`);
      return;
    }
    if (op.op === "removeSkillPrompt") {
      errors.push(`${label}: automatic learning cannot remove skill guidance; use the explicit /harness command`);
    }
  });
}

/** Validate shape and bounds in legacy callers. Autonomous callers pass a
 * snapshot-aware options object, which additionally verifies actor-bound
 * evidence, evaluator cases, and policy ownership before applying anything. */
export function validateHarnessPlan(plan: unknown, options: HarnessPlanValidationOptions = {}): string[] {
  const p = plan as HarnessConsolidationPlan;
  const strict = options.snapshot !== undefined || options.snapshotText !== undefined || options.automatic === true;
  const validationOptions = { ...options, automatic: options.automatic ?? strict };
  const requireEvidence = options.requireEvidence ?? true;
  const requireCases = options.requireCases ?? strict;
  const errors: string[] = [];
  if (!p || typeof p !== "object" || Array.isArray(p)) return ["plan is not an object"];
  if (p.kind !== HARNESS_PLAN_KIND) errors.push(`kind must be "${HARNESS_PLAN_KIND}"`);
  if (p.version !== undefined && p.version !== 1) errors.push("version must be 1");
  if (p.schemaVersion !== undefined && p.schemaVersion !== 1) errors.push("schemaVersion must be 1");
  const ops = Array.isArray(p.operations) ? p.operations : p.operations === undefined ? [] : null;
  if (ops === null) {
    errors.push("operations must be an array");
    return errors;
  }
  if (ops.length > MAX_HARNESS_OPS) {
    errors.push(`operations exceed the maximum of ${MAX_HARNESS_OPS}`);
    return errors;
  }
  const parsedCases = new Map<number, HarnessPolicyCases>();
  ops.forEach((raw, i) => {
    const op = raw as HarnessOp;
    const label = `operations[${i}]`;
    if (!op || typeof op !== "object") {
      errors.push(`${label} is not an object`);
      return;
    }
    if (!HARNESS_OP_KINDS.includes(op.op)) {
      errors.push(`${label}.op must be one of ${HARNESS_OP_KINDS.join(", ")}`);
      return;
    }
    if (op.op === "addSkillPrompt" || op.op === "removeSkillPrompt") {
      if (!policyNameValid(op.name)) errors.push(`${label}.name is invalid`);
      if (op.op === "addSkillPrompt") {
        const knownSkills = availableSkills(validationOptions) ?? (strict ? new Set<string>() : undefined);
        errors.push(...validateSkillPromptDeclaration(op.name, { prompt: op.prompt, target: op.target }, knownSkills).map((error) => `${label}: ${error}`));
        if (!boundedString(op.prompt, MAX_SKILL_PROMPT_CHARS)) errors.push(`${label}.prompt must be 1..${MAX_SKILL_PROMPT_CHARS} chars`);
        if (op.target !== "system" && op.target !== "user") errors.push(`${label}.target must be "system" or "user"`);
        if (op.userMessagePattern !== undefined) {
          if (!boundedString(op.userMessagePattern, 500)) errors.push(`${label}.userMessagePattern must be 1..500 chars`);
          else {
            try {
              new RegExp(op.userMessagePattern);
            } catch {
              errors.push(`${label}.userMessagePattern must be a valid regular expression`);
            }
          }
        }
      }
      return;
    }
    if (!boundedString(op.name, 64) || !policyNameValid(op.name)) {
      errors.push(`${label}.name is invalid`);
      return;
    }
    if (op.op === "disablePolicy") return;
    if (!op.policy || typeof op.policy !== "object" || Array.isArray(op.policy)) {
      errors.push(`${label}.policy must be an object`);
      return;
    }
    const policy = { ...op.policy, name: op.name };
    const policyBytes = Buffer.byteLength(JSON.stringify(policy), "utf8");
    if (policyBytes > MAX_POLICY_BYTES) {
      errors.push(`${label}.policy exceeds ${MAX_POLICY_BYTES} bytes`);
      return;
    }
    for (const policyError of validatePolicyDeclaration(policy)) errors.push(`${label}.policy ${policyError}`);
    const declaredPhase = (policy as { phase?: unknown }).phase;
    const defaultPhase: PolicyPhase = declaredPhase === "output" || declaredPhase === "artifact" ? declaredPhase : "tool-call";
    const cases = parsePolicyCases(op, label, errors, requireCases, defaultPhase);
    if (cases) parsedCases.set(i, cases);
  });

  evidenceForOperation(p, validationOptions, ops.length, strict, requireEvidence, errors);
  if (requireCases) {
    for (const [index, cases] of parsedCases) {
      const op = ops[index] as HarnessOp;
      if (op.policy && typeof op.policy === "object" && !Array.isArray(op.policy)) {
        validatePolicyCases({ ...op.policy, name: op.name }, cases, `operations[${index}]`, errors);
      }
    }
  }
  validateAutomaticOwnership(ops, validationOptions, errors);
  if (p.report !== undefined) {
    if (!Array.isArray(p.report)) errors.push("report must be an array");
    else {
      if (p.report.length > MAX_HARNESS_REPORTS) errors.push(`report exceeds the maximum of ${MAX_HARNESS_REPORTS} entries`);
      p.report.forEach((raw, i) => {
        const r = raw as { summary?: unknown };
        if (!r || typeof r !== "object" || typeof r.summary !== "string" || r.summary.length === 0 || r.summary.length > 400) {
          errors.push(`report[${i}] must carry a 1..400 char summary`);
        }
      });
    }
  }
  return errors;
}

/** Receipt builder shared by the phase flow and tests. Digests are hex
 * SHA-256 over exact file bytes so integrity stays verifiable later. */
export function buildHarnessReceipt(input: {
  phase: "pre" | "post";
  runId: string;
  scopeDigest: string;
  snapshotDigest: string;
  targetFile: string;
  digestBefore: string | null;
  digestAfter?: string | null;
  applied?: string[];
  planDigest: string;
}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    kind: "harness-consolidation-receipt",
    phase: input.phase,
    runId: input.runId,
    scopeDigest: input.scopeDigest,
    snapshotDigest: input.snapshotDigest,
    targetFile: input.targetFile,
    digestBefore: input.digestBefore,
    planDigest: input.planDigest,
  };
  if (input.phase === "post") {
    base.digestAfter = input.digestAfter ?? null;
    base.applied = input.applied ?? [];
  }
  return base;
}

async function readLayerFileBytes(filePath: string): Promise<Buffer | null> {
  try {
    const st = await fs.stat(filePath);
    if (!st.isFile()) return null;
    return await fs.readFile(filePath);
  } catch {
    return null;
  }
}

/** Read provenance written by autonomous consolidation. A project-local rule
 * without this marker is treated as manually authored and is immutable to the
 * learner. The metadata is intentionally top-level and ignored by the runtime
 * policy loader. */
export function learnedPolicyNamesFromConfig(config: unknown): Set<string> {
  if (!isRecord(config)) return new Set();
  const raw = config.learnedPolicies;
  if (Array.isArray(raw)) return new Set(raw.filter((name): name is string => typeof name === "string" && policyNameValid(name)));
  if (!isRecord(raw)) return new Set();
  return new Set(Object.entries(raw).filter(([name, marker]) => {
    if (!policyNameValid(name)) return false;
    if (marker === true) return true;
    return isRecord(marker) && (marker.origin === "consolidation" || marker.source === "consolidation");
  }).map(([name]) => name));
}

type HarnessApplyArgument = ReadonlySet<string> | HarnessPlanValidationOptions | undefined;

function applyValidationOptions(argument: HarnessApplyArgument): HarnessPlanValidationOptions {
  if (argument instanceof Set) return { availableSkills: argument, requireEvidence: false, requireCases: false };
  // Applying without a parent-supplied registry must fail closed for skill
  // guidance; callers that know the registry pass it explicitly (the AGENTS
  // and automatic phase paths do so).
  if (!argument) return { availableSkills: new Set<string>(), requireEvidence: false, requireCases: false };
  const options = argument as HarnessPlanValidationOptions;
  return {
    ...options,
    availableSkills: options.availableSkills ?? new Set<string>(),
    requireEvidence: options.requireEvidence ?? false,
  };
}

/** Apply harness ops by merging the project-local layer in ONE atomic write.
 * Semantic conflicts (e.g. addPolicy for an existing name) reject the whole
 * plan before anything is written, so no partial application is possible. */
export async function applyHarnessOps(
  projectLocalPath: string,
  ops: readonly HarnessOp[],
  argument?: HarnessApplyArgument,
): Promise<{ ok: true; applied: string[] } | { ok: false; error: string }> {
  const applied: string[] = [];
  let base: Record<string, unknown> = {};
  const prior = await readLayerFileBytes(projectLocalPath);
  if (prior) {
    try {
      const parsed = JSON.parse(prior.toString("utf8")) as Record<string, unknown>;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) base = parsed;
    } catch {
      return { ok: false, error: `existing ${projectLocalPath} is not valid JSON` };
    }
  }
  const requestedOptions = applyValidationOptions(argument);
  const localLayer: PolicyLayer = { source: "project.local", policies: Array.isArray(base.policies) ? base.policies as Array<Record<string, unknown>> : [] };
  const effectiveOptions: HarnessPlanValidationOptions = {
    ...requestedOptions,
    layers: [...(requestedOptions.layers ?? []).filter((layer) => layer.source !== "project.local"), localLayer],
    learnedPolicyNames: new Set([
      ...learnedPolicyNamesFromConfig(base),
      ...(asStringSet(requestedOptions.learnedPolicyNames) ?? []),
    ]),
  };
  const validationErrors = validateHarnessPlan(
    { kind: HARNESS_PLAN_KIND, operations: ops, ...(requestedOptions.evidence !== undefined ? { evidence: requestedOptions.evidence } : {}) },
    effectiveOptions,
  );
  if (validationErrors.length) return { ok: false, error: validationErrors.join("; ") };
  const policies = Array.isArray(base.policies) ? [...(base.policies as Array<Record<string, unknown>>)] : [];
  const disabled = Array.isArray(base.disabled) ? [...(base.disabled as string[])] : [];
  const skillPrompts = base.skillPrompts && typeof base.skillPrompts === "object" && !Array.isArray(base.skillPrompts)
    ? { ...(base.skillPrompts as Record<string, unknown>) }
    : {};
  const learnedPolicies = learnedPolicyNamesFromConfig(base);
  const learnedMetadata = isRecord(base.learnedPolicies) && !Array.isArray(base.learnedPolicies)
    ? { ...(base.learnedPolicies as Record<string, unknown>) }
    : {};
  if (effectiveOptions.automatic) {
    for (const name of learnedPolicies) {
      if (learnedMetadata[name] === undefined) learnedMetadata[name] = { origin: "consolidation" };
    }
  }
  for (const [i, op] of ops.entries()) {
    const label = `operations[${i}]`;
    if (op.op === "addPolicy") {
      const policy = { ...(op.policy as Record<string, unknown>), name: op.name };
      const name = policy.name as string;
      if (policies.some((x) => x.name === name)) return { ok: false, error: `${label}: policy "${name}" already exists in the project-local layer` };
      policies.push(policy);
      if (effectiveOptions.automatic) {
        learnedPolicies.add(name);
        learnedMetadata[name] = { origin: "consolidation", learnedAt: new Date().toISOString() };
      }
      applied.push(`addPolicy:${name}`);
    } else if (op.op === "updatePolicy") {
      const idx = policies.findIndex((x) => x.name === op.name);
      const policy = { ...(op.policy as Record<string, unknown>), name: op.name };
      if (idx >= 0) policies[idx] = policy;
      else policies.push(policy);
      if (effectiveOptions.automatic && idx < 0) {
        learnedPolicies.add(op.name as string);
        learnedMetadata[op.name as string] = { origin: "consolidation", learnedAt: new Date().toISOString() };
      }
      applied.push(`updatePolicy:${op.name}${idx >= 0 ? "" : " (added)"}`);
    } else if (op.op === "disablePolicy") {
      if (!disabled.includes(op.name as string)) disabled.push(op.name as string);
      applied.push(`disablePolicy:${op.name}`);
    } else if (op.op === "addSkillPrompt") {
      skillPrompts[op.name as string] = {
        prompt: op.prompt,
        target: op.target,
        ...(op.userMessagePattern !== undefined ? { userMessagePattern: op.userMessagePattern } : {}),
      };
      applied.push(`addSkillPrompt:${op.name}`);
    } else if (op.op === "removeSkillPrompt") {
      delete skillPrompts[op.name as string];
      applied.push(`removeSkillPrompt:${op.name}`);
    }
  }
  const next = {
    ...base,
    policies,
    disabled,
    skillPrompts,
    ...(effectiveOptions.automatic ? { learnedPolicies: learnedMetadata } : {}),
  };
  await writeFileAtomic(projectLocalPath, `${JSON.stringify(next, null, 2)}\n`, 0o600);
  return { ok: true, applied };
}

function builtInDefaultsLayer(): { source: string; policies: Array<Record<string, unknown>> } {
  return { source: "built-in defaults", policies: DEFAULT_POLICIES as unknown as Array<Record<string, unknown>> };
}

/** Current resolved harness surface handed to the planner as context. */
export async function harnessSurfaceSummary(cwd: string, agentDir?: string): Promise<string> {
  const paths = configPaths(cwd, agentDir);
  const config = mergeLayers([builtInDefaultsLayer(), ...loadLayers(cwd, agentDir)]);
  let localConfig: unknown;
  const localBytes = await readLayerFileBytes(paths.projectLocal);
  if (localBytes) {
    try { localConfig = JSON.parse(localBytes.toString("utf8")) as unknown; } catch { localConfig = undefined; }
  }
  const summary = {
    layers: Object.entries(paths).map(([k, v]) => ({ layer: k, file: v })),
    activePolicies: config.policies.map((p) => ({ name: p.name, action: (p as { action?: string }).action })),
    learnedPolicies: [...learnedPolicyNamesFromConfig(localConfig)].sort(),
    skillPrompts: Object.keys(config.skillPrompts),
    errors: config.errors,
    note: "the planner targets ONLY the project.local layer file",
  };
  return JSON.stringify(summary, null, 1);
}

export interface HarnessConsolidationPhaseOptions {
  pkgDir: string;
  cwd: string;
  reason: string;
  /** Test seams: inject a CLI resolver or an explicit absolute target path. */
  resolveCli?: () => { command: string; args: string[] } | null;
  targetPath?: string;
  availableSkills?: readonly string[];
  skipPlanner?: boolean;
  run?: ConsolidationRun;
  explorationPath?: string;
  explorationDigest?: string;
  /** Test seam for the bounded planner deadline; production defaults to 15 minutes. */
  timeoutMs?: number;
}

export interface HarnessConsolidationPlanningResult {
  run: ConsolidationRun;
  plan: HarnessConsolidationPlan;
  validationOptions: HarnessPlanValidationOptions;
  target: string;
  durationMs: number;
  usage?: PiWorkerUsage;
}

export type HarnessConsolidationPlanResult =
  | { ok: true; value: HarnessConsolidationPlanningResult }
  | { ok: false; detail: string; durationMs: number; usage?: PiWorkerUsage; run?: ConsolidationRun };

export type HarnessConsolidationApplyResult =
  | { outcome: "noop"; operations: number }
  | { outcome: "applied"; operations: number; applied: string[] }
  | { outcome: "rejected"; operations: number; error: string }
  | { outcome: "cancelled"; operations: number };

/** Run the read-only child planner and validate its output. This function never
 * mutates the harness target; its result retains the run and validation inputs
 * required for a later, separately scheduled apply. */
export async function planHarnessConsolidationPhase(
  ctx: ExtensionContext,
  opts: HarnessConsolidationPhaseOptions,
  hooks: { current?: () => boolean; onChild?: (child: ChildProcess) => void } = {},
): Promise<HarnessConsolidationPlanResult> {
  const startedAt = Date.now();
  const current = hooks.current ?? (() => true);
  let run: ConsolidationRun | undefined = opts.run;
  let usage: PiWorkerUsage | undefined;
  const fail = (detail: string): HarnessConsolidationPlanResult => ({
    ok: false,
    detail,
    durationMs: Date.now() - startedAt,
    ...(usage ? { usage } : {}),
    ...(run ? { run } : {}),
  });

  try {
    run ??= await createConsolidationRun(ctx, opts.cwd, false);
    if (!current()) return fail("harness planner cancelled");

    const cli = (opts.resolveCli ?? resolvePiCli)();
    if (!cli) return fail("could not resolve the Pi CLI");
    const procedure = createPackageAgentRun({
      packageRootUrl: new URL("../", import.meta.url).href,
      resourcePath: "agents/harness-consolidator.md",
      namePrefix: "harness-consolidator",
      toolCallId: `harness:${run.manifest.runId}`,
      request: "Follow the parent-provided task below.",
    }).prompt
      .replaceAll("{{PKG_DIR}}", opts.pkgDir)
      .replaceAll("{{RUN_ID}}", run.manifest.runId)
      .replaceAll("{{SCOPE_DIGEST}}", run.manifest.scopeDigest)
      .replaceAll("{{ARTIFACT_HASH}}", run.manifest.snapshotDigest)
      .replaceAll("{{SNAPSHOT_PATH}}", run.manifest.snapshotPath)
      .replaceAll("{{DOSSIER_PATH}}", opts.explorationPath ?? "")
      .replaceAll("{{REPO_ROOT}}", run.manifest.cwd);
    const surface = await harnessSurfaceSummary(opts.cwd);
    if (!current()) return fail("harness planner cancelled");
    const taskText = [
      `Task: produce a read-only structured harness consolidation plan for the project at ${opts.cwd}.`,
      `- Reason: ${opts.reason}`,
      `- Run ID: ${run.manifest.runId}`,
      `- Scope digest: ${run.manifest.scopeDigest}`,
      `- Artifact/snapshot digest: ${run.manifest.snapshotDigest}`,
      `- Immutable task-slice snapshot: ${run.manifest.snapshotPath}`,
      ...(opts.explorationPath ? [
        `- Authoritative Learning Dossier: ${opts.explorationPath}`,
        `- Dossier digest: ${opts.explorationDigest}`,
        "- Use the dossier and task-slice snapshot; do not perform independent repository-wide exploration.",
      ] : []),
      "- Current harness surface summary:",
      surface,
      "- Target layer for every change: <project>/.pi/harness.local.json only.",
      "- Your final assistant message must be exactly one JSON object with kind \"harness-consolidation-plan\".",
      "",
      procedure,
    ].join("\n");
    const taskFile = path.join(run.manifest.runDir, "harness-task.md");
    await fs.writeFile(taskFile, taskText, { mode: 0o600 });
    const child = spawnPiChild(cli.command, [
      ...cli.args,
      ...minimalPiWorkerArgs(["read", "grep", "find", "ls"]),
      `@${taskFile}`,
    ], { cwd: opts.cwd, stdio: ["ignore", "pipe", "pipe"] });
    hooks.onChild?.(child);
    if (!current()) {
      await terminateConsolidationChild(child, 5_000);
      return fail("harness planner cancelled");
    }

    const configuredTimeout = opts.timeoutMs ?? HARNESS_PHASE_TIMEOUT_MS;
    const timeoutMs = Number.isFinite(configuredTimeout)
      ? Math.min(HARNESS_PHASE_TIMEOUT_MS, Math.max(1, configuredTimeout))
      : HARNESS_PHASE_TIMEOUT_MS;
    const childResult = await new Promise<{ ok: true; stdout: string } | { ok: false; detail: string }>((resolve) => {
      let stdout = "";
      let stderr = "";
      let done = false;
      const finish = (value: { ok: true; stdout: string } | { ok: false; detail: string }) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(value);
      };
      const terminateAndFinish = async (detail: string): Promise<void> => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        await terminateConsolidationChild(child, 5_000).catch(() => false);
        resolve({ ok: false, detail });
      };
      const timer = setTimeout(() => {
        void terminateAndFinish("harness planner timed out");
      }, timeoutMs);
      timer.unref?.();
      child.stdout?.on("data", (chunk: Buffer) => {
        if (done) return;
        stdout += chunk.toString("utf8");
        if (Buffer.byteLength(stdout, "utf8") > MAX_STDOUT_BYTES) {
          void terminateAndFinish(`child stdout exceeded ${MAX_STDOUT_BYTES} bytes`);
        }
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        if (!done) stderr = (stderr + chunk.toString("utf8")).slice(-64_000);
      });
      child.on("error", (error) => finish({ ok: false, detail: error.message }));
      child.on("close", (code) => {
        if (done) return;
        usage = parsePiWorkerOutput(stdout).usage;
        if (stdout.split("\n").filter((line) => line.trim()).length > MAX_JSONL_LINES) {
          finish({ ok: false, detail: `child JSONL exceeded ${MAX_JSONL_LINES} records` });
        } else if (code !== 0) {
          finish({ ok: false, detail: stderr.trim() || `exit code ${code}` });
        } else {
          finish({ ok: true, stdout });
        }
      });
    });
    if (!childResult.ok) return fail(childResult.detail);
    if (!current()) return fail("harness planner cancelled");

    const extracted = extractChildPlan<HarnessConsolidationPlan>(childResult.stdout, {
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
    if (!extracted.ok) return fail(extracted.error);
    const snapshotBytes = await readLayerFileBytes(run.manifest.snapshotPath);
    if (!snapshotBytes) return fail("immutable harness evidence snapshot is missing");
    if (sha256Digest(snapshotBytes) !== run.manifest.snapshotDigest) return fail("immutable harness evidence snapshot changed after capture");
    let snapshot: unknown;
    try { snapshot = JSON.parse(snapshotBytes.toString("utf8")) as unknown; }
    catch { return fail("immutable harness evidence snapshot is not valid JSON"); }
    if (isRecord(snapshot) && snapshot.runId !== undefined && snapshot.runId !== run.manifest.runId) {
      return fail("immutable harness evidence snapshot run id mismatch");
    }
    const target = opts.targetPath ?? configPaths(opts.cwd).projectLocal;
    let localConfig: unknown;
    const localBytes = await readLayerFileBytes(target);
    if (localBytes) {
      try { localConfig = JSON.parse(localBytes.toString("utf8")) as unknown; } catch { localConfig = undefined; }
    }
    const validationOptions: HarnessPlanValidationOptions = {
      availableSkills: opts.availableSkills,
      snapshot,
      snapshotText: snapshotBytes.toString("utf8"),
      layers: [builtInDefaultsLayer(), ...loadLayers(opts.cwd)],
      learnedPolicyNames: learnedPolicyNamesFromConfig(localConfig),
      automatic: true,
    };
    const errors = validateHarnessPlan(extracted.plan, validationOptions);
    if (errors.length) return fail(errors.join("; ").slice(-600));
    return {
      ok: true,
      value: {
        run,
        plan: extracted.plan,
        validationOptions,
        target,
        durationMs: Date.now() - startedAt,
        ...(usage ? { usage } : {}),
      },
    };
  } catch (error) {
    return fail((error as Error).message);
  }
}

/** Revalidate and atomically apply a previously produced planning result. */
export async function applyHarnessConsolidationPlan(
  planning: HarnessConsolidationPlanningResult,
  current: () => boolean = () => true,
): Promise<HarnessConsolidationApplyResult> {
  const { run, plan, validationOptions, target } = planning;
  const ops = Array.isArray(plan.operations) ? plan.operations as HarnessOp[] : [];
  const runDir = run.manifest.runDir;
  if (ops.length === 0) {
    await writeFileAtomic(path.join(runDir, "harness-noop.txt"), "verified no-op\n").catch(() => {});
    return { outcome: "noop", operations: 0 };
  }
  const errors = validateHarnessPlan(plan, validationOptions);
  if (errors.length) return { outcome: "rejected", operations: ops.length, error: errors.join("; ") };
  const planDigest = sha256Digest(JSON.stringify(plan));
  const beforeBytes = await readLayerFileBytes(target);
  const digestBefore = beforeBytes ? sha256Digest(beforeBytes) : null;
  const preReceipt = buildHarnessReceipt({
    phase: "pre",
    runId: run.manifest.runId,
    scopeDigest: run.manifest.scopeDigest,
    snapshotDigest: run.manifest.snapshotDigest,
    targetFile: target,
    digestBefore,
    planDigest,
  });
  await writeFileAtomic(path.join(runDir, "harness-pre-receipt.json"), `${JSON.stringify(preReceipt, null, 2)}\n`);
  const applied = await applyHarnessOps(target, ops, {
    ...validationOptions,
    evidence: plan.evidence,
    requireEvidence: false,
    automatic: true,
  });
  if (!applied.ok) return { outcome: "rejected", operations: ops.length, error: applied.error };
  const postBytes = await readLayerFileBytes(target);
  if (!current()) {
    const nowBytes = await readLayerFileBytes(target);
    if (postBytes && nowBytes && postBytes.equals(nowBytes)) {
      if (!beforeBytes) await fs.rm(target, { force: true }).catch(() => {});
      else await writeFileAtomic(target, beforeBytes, 0o600).catch(() => {});
    }
    return { outcome: "cancelled", operations: ops.length };
  }
  const receipt = buildHarnessReceipt({
    phase: "post",
    runId: run.manifest.runId,
    scopeDigest: run.manifest.scopeDigest,
    snapshotDigest: run.manifest.snapshotDigest,
    targetFile: target,
    digestBefore,
    digestAfter: postBytes ? sha256Digest(postBytes) : null,
    applied: applied.applied,
    planDigest,
  });
  await writeFileAtomic(path.join(runDir, "harness-post-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`);
  return { outcome: "applied", operations: ops.length, applied: applied.applied };
}

/** Preserve the original sequential phase behavior while exposing planning and
 * mutation separately for callers that schedule phases themselves. */
export async function runHarnessConsolidationPhase(
  ctx: ExtensionContext,
  state: ConsolidationPhaseState & { child?: ChildProcess },
  opts: HarnessConsolidationPhaseOptions,
): Promise<void> {
  if (opts.skipPlanner) return;
  const resolveCli = opts.resolveCli ?? resolvePiCli;
  if (!resolveCli()) {
    notifyPi(ctx.ui, "Harness consolidation skipped: could not resolve the Pi CLI", "warning");
    return;
  }
  if (state.active) return;
  state.active = true;
  const generation = state.generation + 1;
  state.generation = generation;
  state.cancelled = false;
  const current = () => !state.cancelled && generation === state.generation;
  let run: ConsolidationRun | undefined;
  try {
    const planned = await planHarnessConsolidationPhase(ctx, opts, {
      current,
      onChild: (child) => { state.child = child; },
    });
    run = planned.ok ? planned.value.run : planned.run;
    if (!current()) return;
    if (!planned.ok) {
      if (run) await writeFileAtomic(path.join(run.manifest.runDir, "harness-error.txt"), planned.detail.slice(-8_000)).catch(() => {});
      notifyPi(ctx.ui, `Harness consolidation finished without applying changes: ${planned.detail.slice(-300)}`, "warning");
      return;
    }
    const result = await applyHarnessConsolidationPlan(planned.value, current);
    if (!current() || result.outcome === "cancelled") return;
    if (result.outcome === "noop") {
      notifyPi(ctx.ui, "Harness consolidation: verified no-op — no guardrail evidence worth encoding.", "info");
    } else if (result.outcome === "rejected") {
      notifyPi(ctx.ui, `Harness consolidation rejected: ${result.error.slice(-300)}`, "warning");
    } else {
      notifyPi(ctx.ui, `Harness consolidated: ${result.applied.length} change(s) applied to ${path.basename(planned.value.target)} (${result.operations} proposed).`, "info");
    }
  } catch (error) {
    if (current()) notifyPi(ctx.ui, `Harness consolidation failed: ${(error as Error).message.slice(-300)}`, "warning");
  } finally {
    const owned = current();
    try {
      if (owned && state.child) {
        const child = state.child;
        state.child = undefined;
        if (!child.killed) void terminateConsolidationChild(child, 5_000).catch(() => {});
      }
    } finally {
      if (run) await releaseConsolidationRun(run, { keepArtifacts: owned }).catch(() => {});
      if (owned) state.active = false;
    }
  }
}

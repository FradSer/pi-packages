import { plannerReadArgs } from "./planner-read-scope";
/**
 * Harness consolidation phase — the second half of the /consolidate pipeline.
 *
 * Runs after a verified memory consolidation against the SAME immutable
 * session snapshot: a read-only planner child mines tool-call guardrail
 * evidence (blocked calls and reasons, confirmation outcomes, user
 * corrections) and returns one bounded `harness-consolidation-plan`. The
 * parent alone applies it, merging atomically into the project
 * layer (<cwd>/.pi/harness.json). Other layers are never written, and
 * any failure here never touches already-applied memory results.
 */

import { completeLiteralRuleMessage, jevRepairFailureHints, type BoundScopeContext } from "./jev-learning";
import fs from "node:fs/promises";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import { withFileMutationQueue, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { recordLearningMutation, recordLearningProposal } from "./learning-history";
import {
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
  MAX_SNAPSHOT_BYTES,
  type ConsolidationRun,
} from "./consolidation-run";
import { DEFAULT_RULES, evaluateBash, evaluateSkill, evaluateText, mergeLayers, ruleRevision, validateRuleDeclaration } from "./guardrail-engine";
import { assertHarnessTargetContained } from "./guardrails";
import { assertHarnessConfigContainers, compareHarnessLayers, configPaths, loadLayers } from "./guardrail-config";
import type { RuleLayer } from "./guardrail-types";
import { legacyReservedNames } from "./legacy-harness";
import { buildHarnessConsolidatorPrompt, learningPlannerArgs } from "./planner-prompts";
import type { LearningAttempt, LearningOutcome } from "./learning-efficiency";

export const HARNESS_PLAN_KIND = "harness-consolidation-plan";
export const MAX_HARNESS_OPS = 12;
export const MAX_HARNESS_REPORTS = 12;
export const MAX_RULE_BYTES = 8_192;
export const MAX_GUIDANCE_CHARS = 2_000;
export const MAX_EVIDENCE_QUOTE_CHARS = 2_000;
export const MAX_RULE_CASES = 12;
export const MAX_RULE_CASE_BYTES = 8_192;
export const MAX_RULE_CASE_TEXT_CHARS = 8_192;
const HARNESS_PHASE_TIMEOUT_MS = 15 * 60 * 1000;
const MISSING_PLAN_ERROR = "child output did not contain a structured consolidation plan";
const HARNESS_OP_KINDS = ["addRule", "updateRule"] as const;
export type HarnessOpKind = (typeof HARNESS_OP_KINDS)[number];

function addPiWorkerUsage(previous: PiWorkerUsage | undefined, next: PiWorkerUsage | undefined): PiWorkerUsage | undefined {
  if (!next) return previous;
  if (!previous) return { ...next };
  return {
    input: previous.input + next.input,
    output: previous.output + next.output,
    cacheRead: previous.cacheRead + next.cacheRead,
    cacheWrite: previous.cacheWrite + next.cacheWrite,
    totalTokens: previous.totalTokens + next.totalTokens,
    cost: previous.cost + next.cost,
  };
}

/** Terminal gate for the second pipeline phase, shared by callers and tests:
 * only a finished, verified, context-captured memory phase unlocks it. */
export type PipelineGateState = { outcome?: string; active: boolean; cancelled: boolean };
export function shouldRunHarnessPhase(state: PipelineGateState): "run" | "wait" | "skip" {
  if (state.cancelled || state.outcome === undefined || state.active) return "wait";
  return state.outcome === "completed" ? "run" : "skip";
}

export interface HarnessOp {
  op: HarnessOpKind;
  rule: Record<string, unknown>;
  /** Bounded selector fixtures evaluated without executing commands. */
  cases?: unknown;
  correction?: { eventIndex: number; quote: string; priorRevision: string };
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

export interface HarnessRuleCase {
  bash?: string;
  skill?: string;
  text?: string[];
  expected?: "match" | "no-match" | "execute" | "confirm" | "block";
}

export interface HarnessRuleCases { positive: HarnessRuleCase[]; negative: HarnessRuleCase[] }

/** Inputs needed for the autonomous parent-side gates. `snapshot` may be the
 * parsed snapshot object or its `entries` array. `snapshotText` is retained so
 * quote checks use the exact immutable bytes the child was given. */
export interface HarnessPlanValidationOptions {
  availableSkills?: ReadonlySet<string> | readonly string[];
  targetSource?: "project" | "project.local";
  snapshot?: unknown;
  snapshotText?: string;
  layers?: readonly RuleLayer[];
  learnedRules?: Readonly<Record<string, string>>;
  /** Evidence is supplied separately when validating ops before apply. */
  evidence?: unknown;
  /** Automatic consolidation owns only rules marked by this metadata. */
  automatic?: boolean;
  /** Direct non-automatic callers may omit evidence explicitly. */
  requireEvidence?: boolean;
  requireCases?: boolean;
  /** Planning may inspect a correction; application always requires its exact review. */
  proposingCorrections?: boolean;
  reviewedCorrections?: Readonly<Record<string, string>>;
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

/** Caller must first validate all citations against the immutable snapshot.
 * The exact prefix extension changes no matcher, action, case or citation. */
export function completeHarnessLiteralMessages(plan: HarnessConsolidationPlan): HarnessConsolidationPlan {
  if (!Array.isArray(plan.operations) || !Array.isArray(plan.evidence)) return plan;
  const evidence = plan.evidence;
  let changed = false;
  const operations = plan.operations.map((operation, index) => {
    const citations = evidence.filter(item => isRecord(item) && item.index === index);
    const citation = citations[0];
    if (citations.length !== 1 || !isRecord(citation) || citation.source !== "user" || typeof citation.quote !== "string") return operation;
    const completed = completeLiteralRuleMessage(operation, citation.quote);
    if (!completed) return operation;
    changed = true;
    return completed;
  });
  return changed ? { ...plan, operations } : plan;
}

/** Structural subset of the shared dream state both phases coordinate on. */
export interface ConsolidationPhaseState {
  active: boolean;
  generation: number;
  cancelled: boolean;
}

function ruleIdValid(id: unknown): id is string {
  return typeof id === "string" && !!id.trim() && id.length <= 128;
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
/**
 * Accept a coverage-repaired Harness plan only when it passes validation and
 * carries at least one rule. An empty or invalid repair keeps the previous plan,
 * so a failed coverage repair can never make today's behaviour worse.
 */
export function coverageRepairAccepted(validationErrors: readonly string[], operationCount: number): boolean {
  return validationErrors.length === 0 && operationCount > 0;
}

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

function parseRuleCases(raw: unknown, label: string, errors: string[], required: boolean): HarnessRuleCases | undefined {
  if (raw === undefined && !required) return undefined;
  if (!isRecord(raw) || !Array.isArray(raw.positive) || !Array.isArray(raw.negative)) {
    errors.push(`${label} must include positive and negative rule cases`);
    return undefined;
  }
  const result: HarnessRuleCases = { positive: [], negative: [] };
  if (Object.keys(raw).some(key => key !== "positive" && key !== "negative")) errors.push(`${label}.cases has unsupported fields`);
  for (const side of ["positive", "negative"] as const) {
    const entries = raw[side] as unknown[];
    if (!entries.length || entries.length > MAX_RULE_CASES) {
      errors.push(`${label}.cases.${side} must contain 1..${MAX_RULE_CASES} cases`);
      continue;
    }
    entries.forEach((entry, index) => {
      const name = `${label}.cases.${side}[${index}]`;
      if (!isRecord(entry)) { errors.push(`${name} must be an object`); return; }
      if (Buffer.byteLength(JSON.stringify(entry), "utf8") > MAX_RULE_CASE_BYTES) { errors.push(`${name} exceeds ${MAX_RULE_CASE_BYTES} bytes`); return; }
      const selectors = ["bash", "skill", "text"].filter(key => entry[key] !== undefined);
      if (selectors.length !== 1 || Object.keys(entry).some(key => !["bash", "skill", "text", "expected"].includes(key))) {
        errors.push(`${name} requires exactly one supported selector fixture`); return;
      }
      const selector = selectors[0];
      if (selector === "text") {
        if (!Array.isArray(entry.text) || !entry.text.length || entry.text.length > 64 || entry.text.some(text => !boundedString(text, MAX_RULE_CASE_TEXT_CHARS))) {
          errors.push(`${name}.text must be a bounded non-empty array of text segments`); return;
        }
      } else if (!boundedString(entry[selector], MAX_RULE_CASE_TEXT_CHARS)) {
        errors.push(`${name}.${selector} must be a bounded non-empty string`); return;
      }
      const expected = entry.expected ?? (side === "positive" ? "match" : "no-match");
      if (!(side === "positive" ? ["match", "execute", "confirm", "block"] : ["no-match"]).includes(expected as string)) {
        errors.push(`${name} ${side} case has invalid expected result`); return;
      }
      result[side].push({ ...entry, expected } as HarnessRuleCase);
    });
  }
  return result;
}

function validateRuleCases(rule: Record<string, unknown>, cases: HarnessRuleCases, label: string, errors: string[], skills?: ReadonlySet<string>): void {
  const config = mergeLayers([{ source: "candidate", rules: [rule] }], skills);
  const matchingConfig = rule.enabled === false ? mergeLayers([{source:"retired predecessor selector", rules:[{...rule, enabled:true}]}], skills) : config;
  const selector = ["bash", "skill", "text"].find(key => rule[key] !== undefined);
  for (const side of ["positive", "negative"] as const) for (const [index, fixture] of cases[side].entries()) {
    const name = `${label}.cases.${side}[${index}]`;
    if (!selector || fixture[selector as keyof HarnessRuleCase] === undefined) { errors.push(`${name} selector does not match proposed rule`); continue; }
    let matched = false;
    let decision: string | undefined;
    if (selector === "bash") {
      const evaluation = evaluateBash(config, fixture.bash!);
      matched = evaluateBash(matchingConfig, fixture.bash!).matchedRules.some(match => match.id === rule.id);
      decision = evaluation.decision;
    } else if (selector === "skill") matched = evaluateSkill(matchingConfig, fixture.skill!).some(match => match.id === rule.id);
    else {
      const evaluation = evaluateText(matchingConfig, fixture.text!);
      if (evaluation.incomplete) errors.push(`${name} evaluator incomplete`);
      matched = evaluation.matches.some(match => match.id === rule.id);
    }
    if (side === "positive" && !matched) errors.push(`${name} did not match proposed rule`);
    if (side === "negative" && matched) errors.push(`${name} matched but must remain unmatched`);
    if (side === "positive" && fixture.expected !== "match" && fixture.expected !== decision) errors.push(`${name} expected ${fixture.expected}, evaluator returned ${decision ?? "guidance"}`);
  }
}

function ruleWeakens(existing: Record<string, unknown>, proposed: Record<string, unknown>): boolean {
  if (existing.enabled === false || proposed.enabled === false) return true;
  for (const field of ["skill", "bash", "text"] as const) if (existing[field] !== proposed[field]) return true;
  const rank = (action: unknown) => action === "block" ? 2 : action === "confirm" ? 1 : 0;
  return rank(proposed.action) < rank(existing.action);
}

export function correctionDigest(operation: unknown): string {
  return sha256Digest(JSON.stringify(operation));
}

function validCorrection(raw: Record<string, unknown>, existing: Record<string, unknown>, options: HarnessPlanValidationOptions): boolean {
  if (!isRecord(raw.correction) || Object.keys(raw.correction).some(key => !["eventIndex", "quote", "priorRevision"].includes(key))) return false;
  const { eventIndex, quote, priorRevision } = raw.correction;
  if (!Number.isSafeInteger(eventIndex) || Number(eventIndex) < 0 || !boundedString(quote, MAX_EVIDENCE_QUOTE_CHARS) || priorRevision !== ruleRevision(existing)) return false;
  const snapshot = snapshotEvidenceSource(options);
  const entry = snapshot?.entries[Number(eventIndex)];
  if (!entry || evidenceSourceOfSnapshotEntry(entry) !== "user" || !evidenceTextOfSnapshotEntry(entry, "user").includes(quote)) return false;
  return options.proposingCorrections === true || options.reviewedCorrections?.[String(existing.id)] === correctionDigest(raw);
}

function validateAutomaticOwnership(ops: readonly unknown[], options: HarnessPlanValidationOptions, errors: string[]): void {
  if (!options.automatic) return;
  if (options.targetSource === "project.local") errors.push("automatic learning targets only the project shared layer");
  const ownership = new Map<string, Array<{ source: string; rule: Record<string, unknown> }>>();
  for (const layer of [builtInDefaultsLayer(), ...(options.layers ?? [])]) {
    for (const id of legacyReservedNames(layer)) {
      const entries = ownership.get(id) ?? [];
      entries.push({ source: `legacy ${layer.source}`, rule: { id } });
      ownership.set(id, entries);
    }
    for (const raw of layer.rules ?? []) {
      if (!isRecord(raw) || typeof raw.id !== "string") continue;
      const entries = ownership.get(raw.id) ?? [];
      if (!entries.some(entry => entry.source === layer.source && entry.rule === raw)) entries.push({ source: layer.source, rule: raw });
      ownership.set(raw.id, entries);
    }
  }
  for (const [index, raw] of ops.entries()) {
    if (!isRecord(raw) || !isRecord(raw.rule) || typeof raw.rule.id !== "string") continue;
    const id = raw.rule.id;
    const entries = ownership.get(id) ?? [];
    const label = `operations[${index}]`;
    if (raw.op === "addRule") {
      if (entries.length) errors.push(`${label}: rule "${id}" already belongs to ${entries.map(entry => entry.source).join(", ")}; identity conflict, including disabled or invalid declarations`);
    } else if (raw.op === "updateRule") {
      if (entries.length !== 1 || entries[0]?.source !== (options.targetSource ?? "project")) {
        errors.push(`${label}: rule "${id}" is missing or protected by another layer`); continue;
      }
      const existing = entries[0].rule;
      if (options.learnedRules?.[id] !== ruleRevision(existing)) errors.push(`${label}: rule "${id}" is manually authored or its learned revision no longer matches`);
      if (ruleWeakens(existing, raw.rule) && !validCorrection(raw, existing, options)) errors.push(`${label}: automatic learning cannot weaken, change selectors, disable, or re-enable an existing rule without an exact reviewed user correction`);
      if (raw.correction !== undefined && !validCorrection(raw, existing, options)) errors.push(`${label}: correction lacks current user evidence, exact predecessor revision or semantic approval`);
    }
  }
}

/** All automatic writes require grounded evidence, executed fixtures and exact
 * revision ownership. Direct callers can skip evidence only explicitly. */
export function validateHarnessPlan(plan: unknown, options: HarnessPlanValidationOptions = {}): string[] {
  if (!isRecord(plan)) return ["plan is not an object"];
  const p = plan as unknown as HarnessConsolidationPlan;
  const strict = options.snapshot !== undefined || options.snapshotText !== undefined || options.automatic === true;
  const validationOptions = { ...options, automatic: options.automatic ?? strict };
  const errors: string[] = [];
  if (p.kind !== HARNESS_PLAN_KIND) errors.push(`kind must be "${HARNESS_PLAN_KIND}"`);
  if (p.version !== undefined && p.version !== 1) errors.push("version must be 1");
  if (p.schemaVersion !== undefined && p.schemaVersion !== 1) errors.push("schemaVersion must be 1");
  const ops = p.operations === undefined ? [] : p.operations;
  if (!Array.isArray(ops)) return [...errors, "operations must be an array"];
  if (ops.length > MAX_HARNESS_OPS) return [...errors, `operations exceed the maximum of ${MAX_HARNESS_OPS}`];
  const skills = availableSkills(options) ?? new Set<string>();
  const identities = new Set<string>();
  ops.forEach((raw, index) => {
    const label = `operations[${index}]`;
    if (!isRecord(raw)) { errors.push(`${label} is not an object`); return; }
    if (!HARNESS_OP_KINDS.includes(raw.op as HarnessOpKind)) { errors.push(`${label}.op must be one of ${HARNESS_OP_KINDS.join(", ")}`); return; }
    if (Object.keys(raw).some(key => !["op", "rule", "cases", "correction"].includes(key))) errors.push(`${label} has unsupported operation fields`);
    if (raw.correction !== undefined && raw.op !== "updateRule") errors.push(`${label}: corrections only update owned learned rules`);
    if (!isRecord(raw.rule)) { errors.push(`${label}.rule must be an object`); return; }
    const rule = raw.rule;
    if (!ruleIdValid(rule.id)) errors.push(`${label}.rule.id must be a non-empty string up to 128 chars`);
    else {
      if (identities.has(rule.id)) errors.push(`${label}: rule "${rule.id}" is proposed more than once`);
      identities.add(rule.id);
    }
    if (Buffer.byteLength(JSON.stringify(rule), "utf8") > MAX_RULE_BYTES) { errors.push(`${label}.rule exceeds ${MAX_RULE_BYTES} bytes`); return; }
    const declarationErrors = validateRuleDeclaration(rule, skills);
    errors.push(...declarationErrors.map(error => `${label}.rule ${error}`));
    if (rule.instructions !== undefined && !boundedString(rule.instructions, MAX_GUIDANCE_CHARS)) errors.push(`${label}.rule.instructions must be 1..${MAX_GUIDANCE_CHARS} chars`);
    if (validationOptions.automatic && rule.enabled === false && !(raw.op === "updateRule" && isRecord(raw.correction))) errors.push(`${label}: automatic learning cannot disable rules without a reviewed correction`);
    const fixtures = parseRuleCases(raw.cases, label, errors, strict || options.requireCases === true);
    if (fixtures && !declarationErrors.length) validateRuleCases(rule, fixtures, label, errors, skills);
    // A registry entry alone proves availability, not an evidence-backed scope.
    if (strict && raw.correction === undefined && (rule.skill !== undefined || rule.text !== undefined) && !declarationErrors.length) {
      const evidence = options.evidence ?? p.evidence;
      const quotes = Array.isArray(evidence) ? evidence.filter(item => isRecord(item) && item.index === index && typeof item.quote === "string").map(item => (item as HarnessEvidence).quote) : [];
      const config = mergeLayers([{ source: "candidate", rules: [{...rule, enabled:true}] }], skills);
      const groundedScope = typeof rule.skill === "string"
        ? quotes.some(quote => quote.includes(rule.skill as string))
        : evaluateText(config, quotes).matches.length > 0;
      if (!groundedScope) errors.push(`${label}: guidance requires narrow quoted evidence identifying its actual skill or matching text scope`);
    }
  });
  evidenceForOperation(p, validationOptions, ops.length, strict, strict || options.requireEvidence !== false, errors);
  if (validationOptions.automatic && ops.length) {
    const merged = mergeLayers([builtInDefaultsLayer(), ...(options.layers ?? [])], skills);
    errors.push(...merged.errors.map(error => `existing harness configuration: ${error}`));
  }
  validateAutomaticOwnership(ops, validationOptions, errors);
  if (p.report !== undefined) {
    if (!Array.isArray(p.report)) errors.push("report must be an array");
    else {
      if (p.report.length > MAX_HARNESS_REPORTS) errors.push(`report exceeds the maximum of ${MAX_HARNESS_REPORTS} entries`);
      p.report.forEach((raw, index) => { if (!isRecord(raw) || !boundedString(raw.summary, 400)) errors.push(`report[${index}] must carry a 1..400 char summary`); });
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

async function readLayerFileBytes(filePath: string, maxBytes = 1_000_000): Promise<Buffer | null> {
  try {
    const stat = await fs.lstat(filePath);
    if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Harness input is not a regular file: ${filePath}`);
    if (stat.size > maxBytes) throw new Error(`Harness input exceeds ${maxBytes} bytes: ${filePath}`);
    return await fs.readFile(filePath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

/** Marker-only names are not ownership: the exact current declaration must
 * still match the parent-written revision before automatic updating is safe. */
export function learnedRuleRevisionsFromConfig(config: unknown): Record<string, string> {
  if (!isRecord(config) || !isRecord(config.learnedRules) || !Array.isArray(config.rules)) return {};
  const revisions: Record<string, string> = Object.create(null);
  for (const rule of config.rules) {
    if (!isRecord(rule) || !ruleIdValid(rule.id)) continue;
    const marker = config.learnedRules[rule.id];
    if (isRecord(marker) && marker.origin === "consolidation" && marker.revision === ruleRevision(rule)) revisions[rule.id] = marker.revision as string;
  }
  return revisions;
}

type HarnessApplyArgument = ReadonlySet<string> | HarnessPlanValidationOptions | undefined;
function applyValidationOptions(argument: HarnessApplyArgument): HarnessPlanValidationOptions {
  if (argument instanceof Set) return { availableSkills: argument, requireEvidence: false, requireCases: false };
  if (!argument) return { availableSkills: new Set<string>(), requireEvidence: false, requireCases: false };
  return { ...argument, availableSkills: (argument as HarnessPlanValidationOptions).availableSkills ?? new Set<string>(), requireEvidence: (argument as HarnessPlanValidationOptions).requireEvidence ?? false };
}

function builtInDefaultsLayer(): RuleLayer {
  return { source: "built-in defaults", rules: DEFAULT_RULES as unknown as Array<Record<string, unknown>> };
}

async function prepareHarnessOps(target: string, ops: readonly HarnessOp[], requested: HarnessPlanValidationOptions): Promise<{ before: Buffer | null; next: string; applied: string[] }> {
  const workspace = path.basename(path.dirname(target)) === ".pi" ? path.dirname(path.dirname(target)) : undefined;
  await assertHarnessTargetContained(target, workspace);
  const before = await readLayerFileBytes(target);
  let base: Record<string, unknown> = { rules: [] };
  if (before) {
    try { const parsed: unknown = JSON.parse(before.toString("utf8")); assertHarnessConfigContainers(parsed); base = parsed; }
    catch (error) { throw new Error(`existing ${target} ${error instanceof SyntaxError ? "is not valid JSON" : "is invalid"}: ${(error as Error).message}`); }
  }
  const skills = availableSkills(requested) ?? new Set<string>();
  const rootErrors = mergeLayers([{ ...base, source: "target" } as RuleLayer], skills).errors;
  if (rootErrors.length) throw new Error(`existing ${target} is invalid: ${rootErrors.join("; ")}`);
  const source = path.basename(target) === "harness.local.json" ? "project.local" : "project";
  const local: RuleLayer = { ...base, source, rules: (base.rules ?? []) as Array<Record<string, unknown>> };
  const observedLayers = requested.automatic && workspace ? loadLayers(workspace) : requested.layers ?? [];
  const layers = observedLayers.filter(layer => layer.source !== source && layer.source !== "built-in defaults");
  layers.push(local);
  layers.sort(compareHarnessLayers);
  const options = { ...requested, proposingCorrections: false, targetSource: source as "project" | "project.local", layers, learnedRules: learnedRuleRevisionsFromConfig(base) };
  const validation = validateHarnessPlan({ kind: HARNESS_PLAN_KIND, operations: ops, evidence: options.evidence }, options);
  if (validation.length) throw new Error(validation.join("; "));
  const rules = [...local.rules!];
  const learnedRules: Record<string, unknown> = { ...(isRecord(base.learnedRules) ? base.learnedRules : {}) };
  const applied: string[] = [];
  for (const op of ops) {
    const id = op.rule.id as string;
    const index = rules.findIndex(rule => rule.id === id);
    if (op.op === "addRule" && index >= 0) throw new Error(`rule "${id}" already exists in the project layer`);
    if (op.op === "updateRule" && index < 0) throw new Error(`rule "${id}" does not exist in the project layer`);
    if (index < 0) rules.push({ ...op.rule }); else rules[index] = { ...op.rule };
    if (options.automatic) learnedRules[id] = { origin: "consolidation", revision: ruleRevision(op.rule) };
    applied.push(`${op.op}:${id}`);
  }
  const effective = mergeLayers([builtInDefaultsLayer(), ...layers.map(layer => layer.source === source ? { ...layer, rules } : layer)], skills);
  if (effective.errors.length) throw new Error(`invalid effective harness configuration: ${effective.errors.join("; ")}`);
  const next = JSON.stringify({ ...base, rules, ...(options.automatic ? { learnedRules } : {}) }, null, 2) + "\n";
  if (Buffer.byteLength(next, "utf8") > 1_000_000) throw new Error("candidate harness configuration exceeds 1000000 bytes");
  return { before, next, applied };
}

/** Called under the target mutation queue. Only byte-identifiable candidate
 * content belongs to this transaction; a newer external edit is never restored
 * over. Unreadable content is not proof of ownership and must fail explicitly. */
async function rollbackPreparedHarness(target: string, prepared: { before: Buffer | null; next: string }): Promise<void> {
  await assertHarnessTargetContained(target);
  const now = await readLayerFileBytes(target);
  if (now?.equals(Buffer.from(prepared.next))) {
    if (prepared.before) await writeFileAtomic(target, prepared.before, 0o600);
    else await fs.rm(target, { force: true });
  }
}

async function writePreparedHarness(target: string, prepared: { before: Buffer | null; next: string }): Promise<void> {
  await assertHarnessTargetContained(target);
  const current = await readLayerFileBytes(target);
  if (current?.toString("base64") !== prepared.before?.toString("base64")) throw new Error("Harness target changed before atomic application");
  // The boundary begins before replacement, not after readback: an atomic write
  // can succeed and still throw while verifying or finalizing its result.
  try {
    await writeFileAtomic(target, prepared.next, 0o600);
    const verified = await readLayerFileBytes(target);
    if (!verified?.equals(Buffer.from(prepared.next))) throw new Error("Harness readback does not match the complete candidate");
  } catch (error) {
    try { await rollbackPreparedHarness(target, prepared); }
    catch (rollbackError) {
      throw new Error(`${(error as Error).message}; rollback could not verify or restore the target: ${(rollbackError as Error).message}`, { cause: error });
    }
    throw error;
  }
}

export async function applyHarnessOps(target: string, ops: readonly HarnessOp[], argument?: HarnessApplyArgument): Promise<{ ok: true; applied: string[] } | { ok: false; error: string }> {
  try {
    return await withFileMutationQueue(path.resolve(target), async () => {
      const prepared = await prepareHarnessOps(target, ops, applyValidationOptions(argument));
      if (ops.length) await writePreparedHarness(target, prepared);
      return { ok: true as const, applied: prepared.applied };
    });
  } catch (error) { return { ok: false, error: (error as Error).message }; }
}

export async function harnessSurfaceSummary(cwd: string, agentDir?: string, availableSkills: ReadonlySet<string> = new Set()): Promise<string> {
  const paths = configPaths(cwd, agentDir);
  const config = mergeLayers([builtInDefaultsLayer(), ...loadLayers(cwd, agentDir)], availableSkills);
  let local: unknown;
  const bytes = await readLayerFileBytes(paths.project);
  if (bytes) try { local = JSON.parse(bytes.toString("utf8")); } catch { /* diagnostics come from shared loader */ }
  return JSON.stringify({
    layers: Object.entries(paths).map(([layer, file]) => ({ layer, file })),
    rules: config.rules.map(({ source, ...rule }) => ({ ...rule, regexp: undefined, source })),
    invalidRules: config.invalidRules,
    learnedRules: learnedRuleRevisionsFromConfig(local),
    availableSkills: [...availableSkills].sort(),
    errors: config.errors,
    notices: config.notices,
    reservedLegacyNames: [...new Set(loadLayers(cwd, agentDir).flatMap(legacyReservedNames))],
    note: "the planner targets ONLY project harness.json flat rules; existing legacy containers and provenance stay unchanged",
  }, null, 1);
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
  /** Parent semantic gate; no candidate may grant its own authority. */
  validateSemantics?: (snapshot: unknown, operations: readonly unknown[], citations?: unknown, parentScope?: BoundScopeContext) => Promise<{ decision: "allow" | "propose"; telemetry: NonNullable<LearningAttempt["jev"]> }>;
  /** Shares the single existing repair slot with structural recovery. */
  semanticRepair?: boolean;
  /** Parent-side coverage repair: a screened constraint with no rule is re-asked
   *  once. An adopted plan must still pass validation and carry at least one rule,
   *  so a failed coverage repair can never make today's behaviour worse. */
  coverageRepair?: boolean;
  run?: ConsolidationRun;
  explorationPath?: string;
  explorationDigest?: string;
  /** Test seam for the bounded planner deadline; production defaults to 15 minutes. */
  timeoutMs?: number;
  /** The configured consolidation model, as `provider/model`. The package header
   *  promises consolidation runs on the separately selected model; without this
   *  the Harness phase silently inherited the session default instead. */
  model?: string;
}

export interface HarnessConsolidationPlanningResult {
  run: ConsolidationRun;
  plan: HarnessConsolidationPlan;
  validationOptions: HarnessPlanValidationOptions;
  semanticDecision?: "allow" | "propose";
  /** Omitted semantic candidates saved separately for review, never applied. */
  deferredPlan?: HarnessConsolidationPlan;
  target: string;
  durationMs: number;
  usage?: PiWorkerUsage;
  /** One receipt row per bounded planner child, including a repair child. */
  attempts?: LearningAttempt[];
}

export type HarnessConsolidationPlanResult =
  | { ok: true; value: HarnessConsolidationPlanningResult }
  | { ok: false; detail: string; durationMs: number; usage?: PiWorkerUsage; run?: ConsolidationRun; attempts?: LearningAttempt[] };

export type HarnessConsolidationApplyResult =
  | { outcome: "noop"; operations: number }
  | { outcome: "applied"; operations: number; applied: string[] }
  | { outcome: "rejected"; operations: number; error: string }
  | { outcome: "cancelled"; operations: number };

/** Parent-validated plans only. A semantic repair may omit, not replace, rules.
 * Reindex exact original evidence; a missing opportunity stays in review. */
function semanticRepairRemainder(original: HarnessConsolidationPlan, repaired: HarnessConsolidationPlan): HarnessConsolidationPlan | "structure-mismatch" | "identity-mismatch" | "citation-mismatch" | undefined {
  if (!Array.isArray(original.operations) || !Array.isArray(repaired.operations)) return "structure-mismatch";
  const identity = (operation: unknown): string | undefined => isRecord(operation) && typeof operation.op === "string"
    && isRecord(operation.rule) && ruleIdValid(operation.rule.id) ? `${operation.op}:${operation.rule.id}` : undefined;
  const originalIds = new Set(original.operations.map(identity));
  const keptIds = new Set(repaired.operations.map(identity));
  if (originalIds.has(undefined) || keptIds.has(undefined) || [...keptIds].some(id => !originalIds.has(id))) return "identity-mismatch";
  // Semantic repair starts with valid citations; it may reindex, never replace them.
  const citationsAt = (values: unknown, index: number): string => JSON.stringify(
    (Array.isArray(values) ? values : []).filter(value => isRecord(value) && value.index === index)
      .map(value => JSON.stringify(Object.entries(value).filter(([key]) => key !== "index")
        .sort(([left], [right]) => left.localeCompare(right)))).sort(),
  );
  for (const [index, operation] of repaired.operations.entries()) {
    const previous = original.operations.findIndex(value => identity(value) === identity(operation));
    if (citationsAt(original.evidence, previous) !== citationsAt(repaired.evidence, index)) return "citation-mismatch";
  }
  const omitted = original.operations.map((operation, index) => ({ operation, index }))
    .filter(({ operation }) => !keptIds.has(identity(operation)));
  if (!omitted.length) return undefined;
  const indexes = new Map(omitted.map(({ index }, next) => [index, next]));
  const reindex = (values: unknown): unknown[] => Array.isArray(values) ? values.flatMap(value => {
    if (!isRecord(value) || typeof value.index !== "number" || !indexes.has(value.index)) return [];
    return [{ ...value, index: indexes.get(value.index)! }];
  }) : [];
  return structuredClone({ ...original, operations: omitted.map(({ operation }) => operation),
    evidence: reindex(original.evidence), ...(original.report === undefined ? {} : { report: reindex(original.report) }) });
}

/** Run the read-only child planner and validate its output. This function never
 * mutates the harness target; its result retains the run and validation inputs
 * required for a later, separately scheduled apply. */
/**
 * One read-only harness planner child, shared by the initial plan and its repair
 * so the two cannot drift on tools, timeout, or output bounds.
 */
async function runHarnessPlannerChild(
  cli: { command: string; args: readonly string[] },
  taskFile: string,
  cwd: string,
  options: {
    timeoutMs: number;
    files: string[];
    current: () => boolean;
    model?: string;
    onChild?: (child: ChildProcess) => void;
    onUsage?: (usage: PiWorkerUsage | undefined) => void;
  },
): Promise<{ ok: true; stdout: string } | { ok: false; detail: string }> {
  const child = spawnPiChild(cli.command, [
    ...cli.args,
    ...minimalPiWorkerArgs(["learning_read"]),
    ...await plannerReadArgs(path.dirname(taskFile), { cwd, files: options.files, roots: [cwd] }),
    ...learningPlannerArgs(),
    ...(options.model ? ["--model", options.model] : []),
    `@${taskFile}`,
  ], { cwd, stdio: ["ignore", "pipe", "pipe"] });
  options.onChild?.(child);
  if (!options.current()) {
    await terminateConsolidationChild(child, 5_000);
    return { ok: false, detail: "harness planner cancelled" };
  }
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let done = false;
    let usageReported = false;
    const reportUsage = (): void => {
      if (usageReported) return;
      usageReported = true;
      // A limit breach may leave one oversized chunk in memory. Parse only the
      // safely captured prefix so a complete usage event before the breach is
      // retained without accepting unbounded child output.
      const bounded = Buffer.from(stdout, "utf8").subarray(0, MAX_STDOUT_BYTES).toString("utf8");
      options.onUsage?.(parsePiWorkerOutput(bounded).usage);
    };
    const finish = (value: { ok: true; stdout: string } | { ok: false; detail: string }) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      reportUsage();
      resolve(value);
    };
    const terminateAndFinish = async (detail: string): Promise<void> => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      await terminateConsolidationChild(child, 5_000).catch(() => false);
      reportUsage();
      resolve({ ok: false, detail });
    };
    const timer = setTimeout(() => {
      void terminateAndFinish("harness planner timed out");
    }, options.timeoutMs);
    timer.unref?.();
    child.stdout?.on("data", (chunk: Buffer) => {
      if (done) return;
      stdout += chunk.toString("utf8");
      if (Buffer.byteLength(stdout, "utf8") > MAX_STDOUT_BYTES) {
        void terminateAndFinish(`child stdout exceeded ${MAX_STDOUT_BYTES} bytes`);
      }
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      if (done) return;
      stderr = (stderr + chunk.toString("utf8")).slice(-64_000);
    });
    child.on("error", (error) => finish({ ok: false, detail: error.message }));
    child.on("close", (code) => {
      if (done) return;
      if (!options.current()) {
        finish({ ok: false, detail: "harness planner cancelled" });
        return;
      }
      if (stdout.split("\n").filter((line) => line.trim()).length > MAX_JSONL_LINES) {
        finish({ ok: false, detail: `child JSONL exceeded ${MAX_JSONL_LINES} records` });
      } else if (code !== 0) {
        finish({ ok: false, detail: stderr.trim() || `exit code ${code}` });
      } else {
        finish({ ok: true, stdout });
      }
    });
  });
}

/**
 * One bounded repair of a rejected Harness plan.
 *
 * The repair child gets the same read-only tools, the same protocol, the same
 * frozen evidence — and the exact validation errors. It is not asked to plan
 * again: re-planning would let it drift onto different evidence, which is
 * exactly what a repair must not do.
 */
async function repairHarnessPlan(input: {
  cli: { command: string; args: readonly string[] };
  cwd: string;
  run: ConsolidationRun;
  rejected?: unknown;
  missingOutput?: boolean;
  allowOmissions?: boolean;
  errors: readonly string[];
  taskText: string;
  timeoutMs: number;
  current: () => boolean;
  model?: string;
  onChild?: (child: ChildProcess) => void;
  onUsage?: (usage: PiWorkerUsage | undefined) => void;
  onAttempt?: (attempt: Omit<LearningAttempt, "phase" | "attempt">) => void;
}): Promise<{ ok: true; plan: HarnessConsolidationPlan } | { ok: false; detail: string }> {
  const taskFile = path.join(input.run.manifest.runDir, "harness-repair.md");
  const missingOutput = input.missingOutput === true;
  const rejected = isRecord(input.rejected) ? input.rejected : undefined;
  const originalEvidence = rejected && Array.isArray(rejected.evidence) ? rejected.evidence : [];
  const taskText = [
    input.taskText,
    "",
    missingOutput ? "Task: recover ONE missing harness consolidation plan." : "Task: repair ONE rejected harness consolidation plan.",
    input.allowOmissions
      ? "Return exactly one JSON object and no prose. Preserve the supplied identity, retained rule identities and their exact evidence quotes. Omit an unsupported operation rather than invent lasting authorization; reindex retained evidence/report. The parent retains omissions for review. Do not add a new rule identity."
      : "Return exactly one JSON object and no prose. Preserve the supplied identity and every cited evidence quote.",
    ...(input.allowOmissions ? [
      "Copy each retained operation's op and rule.id verbatim from immutableRetainedBindings. Do not derive or rename identities.",
      "All evidence properties other than index must remain unchanged. Copy the complete original evidence objects, including source, quote, count and eventIndex where supplied; only reindex index to the retained operation's new position. Do not shorten quotes or omit citation properties.",
    ] : []),
    ...(missingOutput ? [
      "The prior child emitted no structured plan. Its raw stdout is intentionally unavailable and must not be requested, echoed, summarized, or treated as evidence.",
      "Reconstruct only from the bound snapshot and dossier paths in the supplied protocol. Do not perform independent exploration or use any other files.",
    ] : [
      "Change only the fields needed to resolve the validation errors below.",
      "If validation errors cite report, remove the optional report property entirely; do not rename its fields or repeat the invalid report.",
      "Use only the supplied JSON; do not request additional context, do not plan again, and do not re-run exploration.",
    ]),
    JSON.stringify({
      identity: {
        runId: input.run.manifest.runId,
        scopeDigest: input.run.manifest.scopeDigest,
        artifactHash: input.run.manifest.snapshotDigest,
      },
      ...(input.allowOmissions && rejected && Array.isArray(rejected.operations) ? {
        immutableRetainedBindings: rejected.operations.map((operation: unknown, originalIndex: number) => ({
          originalIndex,
          ...(isRecord(operation) ? { op: operation.op,
            ruleId: isRecord(operation.rule) ? operation.rule.id : undefined } : {}),
          evidence: originalEvidence.filter((value: unknown) => isRecord(value) && value.index === originalIndex),
        })),
      } : {}),
      errors: input.errors.map((error) => error.slice(0, 400)).slice(0, 24),
      ...(input.rejected === undefined ? {} : { rejectedPlan: input.rejected }),
    }),
  ].join("\n");
  const childStartedAt = Date.now();
  let childUsage: PiWorkerUsage | undefined;
  const recordAttempt = (outcome: LearningOutcome): void => {
    input.onAttempt?.({
      outcome,
      durationMs: Date.now() - childStartedAt,
      operations: 0,
      ...(childUsage ? { usage: childUsage } : {}),
    });
  };
  try {
    await fs.writeFile(taskFile, taskText, { mode: 0o600 });
  } catch (error) {
    recordAttempt("failed");
    return { ok: false, detail: `harness repair task could not be written: ${(error as Error).message}` };
  }
  const child = await runHarnessPlannerChild(input.cli, taskFile, input.cwd, {
    timeoutMs: input.timeoutMs,
    files: input.missingOutput ? [input.run.manifest.snapshotPath, path.join(input.run.manifest.runDir, "incremental-learning-dossier.json")] : [],
    current: input.current,
    ...(input.model ? { model: input.model } : {}),
    onChild: input.onChild,
    onUsage: (value) => {
      childUsage = value;
      input.onUsage?.(value);
    },
  });
  if (!child.ok) {
    recordAttempt(/cancelled/i.test(child.detail) ? "cancelled" : "failed");
    return child;
  }
  const extracted = extractChildPlan<HarnessConsolidationPlan>(child.stdout, {
    expectedIdentity: {
      runId: input.run.manifest.runId,
      scopeDigest: input.run.manifest.scopeDigest,
      artifactHash: input.run.manifest.snapshotDigest,
    },
    maxOutputBytes: MAX_STDOUT_BYTES,
    maxLines: MAX_JSONL_LINES,
    maxLineBytes: MAX_JSONL_LINE_BYTES,
    maxPlanBytes: MAX_PLAN_BYTES,
  });
  if (!extracted.ok) {
    recordAttempt(extracted.failure === "cancelled" ? "cancelled" : extracted.failure ? "failed" : "rejected");
    return { ok: false, detail: extracted.error };
  }
  recordAttempt("noop");
  return { ok: true, plan: extracted.plan };
}

/** Receipts use controlled categories, never validation text containing ids or evidence. */
function parentValidationDiagnostic(errors: readonly string[]): string {
  const counts = new Map<string, number>();
  for (const error of errors) {
    const category = /^operations\[\d+\]\.cases/.test(error) ? "fixtures"
      : /^(?:evidence|operations\[\d+\] has no evidence)/.test(error) ? "evidence"
      : /^(?:runId|scopeDigest|artifactHash|version|schemaVersion|kind)/.test(error) ? "protocol"
      : "structure";
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  return `Parent Harness validation: ${[...counts].map(([category, count]) => `${category}=${count}`).join(", ")}`;
}

export async function planHarnessConsolidationPhase(
  ctx: ExtensionContext,
  opts: HarnessConsolidationPhaseOptions,
  hooks: { current?: () => boolean; onChild?: (child: ChildProcess) => void } = {},
): Promise<HarnessConsolidationPlanResult> {
  const startedAt = Date.now();
  const current = hooks.current ?? (() => true);
  let run: ConsolidationRun | undefined = opts.run;
  let usage: PiWorkerUsage | undefined;
  const attempts: LearningAttempt[] = [];
  const fail = (detail: string): HarnessConsolidationPlanResult => {
    // A child that emitted a valid plan is tentatively recorded as `noop` until
    // the immutable snapshot and layer gates finish. If either gate fails, the
    // receipt must not make that transport-successful child look like a clean
    // phase; preserve explicit rejection/cancellation outcomes from earlier
    // gates and mark only the pending final attempt as failed/cancelled.
    const pending = attempts.at(-1);
    if (pending?.outcome === "noop") pending.outcome = /cancelled/i.test(detail) ? "cancelled" : "failed";
    return {
      ok: false,
      detail,
      durationMs: Date.now() - startedAt,
      ...(usage ? { usage } : {}),
      ...(run ? { run } : {}),
      ...(attempts.length > 0 ? { attempts: [...attempts] } : {}),
    };
  };

  try {
    run ??= await createConsolidationRun(ctx, opts.cwd);
    if (!current()) return fail("harness planner cancelled");

    const cli = (opts.resolveCli ?? resolvePiCli)();
    if (!cli) return fail("could not resolve the Pi CLI");
    const procedure = buildHarnessConsolidatorPrompt({
      runId: run.manifest.runId,
      scopeDigest: run.manifest.scopeDigest,
      artifactHash: run.manifest.snapshotDigest,
      snapshotPath: run.manifest.snapshotPath,
      dossierPath: opts.explorationPath ?? "",
      repoRoot: run.manifest.cwd,
    });
    const surface = await harnessSurfaceSummary(opts.cwd, undefined, new Set(opts.availableSkills ?? []));
    if (!current()) return fail("harness planner cancelled");
    const taskText = [
      `Task: produce a read-only structured harness consolidation plan for the project at ${opts.cwd}.`,
      `- Reason: ${opts.reason}`,
      ...(opts.explorationPath ? [
        "- Authoritative Learning Dossier and immutable task-slice snapshot paths are bound in the protocol below.",
        `- Dossier digest: ${opts.explorationDigest}`,
        "- Use the dossier and task-slice snapshot; do not perform independent repository-wide exploration.",
      ] : []),
      "- Current harness surface summary:",
      surface,
      "- Target layer for every change: <project>/.pi/harness.json only.",
      "- Your final assistant message must be exactly one JSON object with kind \"harness-consolidation-plan\".",
      "",
      procedure,
    ].join("\n");
    const taskFile = path.join(run.manifest.runDir, "harness-task.md");
    await fs.writeFile(taskFile, taskText, { mode: 0o600 });
    const configuredTimeout = opts.timeoutMs ?? HARNESS_PHASE_TIMEOUT_MS;
    const timeoutMs = Number.isFinite(configuredTimeout)
      ? Math.min(HARNESS_PHASE_TIMEOUT_MS, Math.max(1, configuredTimeout))
      : HARNESS_PHASE_TIMEOUT_MS;
    const childStartedAt = Date.now();
    let childUsage: PiWorkerUsage | undefined;
    const childResult = await runHarnessPlannerChild(cli, taskFile, opts.cwd, {
      timeoutMs,
      files: [run.manifest.snapshotPath, ...(opts.explorationPath ? [opts.explorationPath] : [])],
      current,
      ...(opts.model ? { model: opts.model } : {}),
      onChild: hooks.onChild,
      onUsage: (value) => {
        childUsage = value;
        usage = addPiWorkerUsage(usage, value);
      },
    });
    const recordInitialAttempt = (outcome: LearningOutcome): number => {
      attempts.push({
        phase: "harness",
        attempt: attempts.length,
        outcome,
        durationMs: Date.now() - childStartedAt,
        operations: 0,
        ...(childUsage ? { usage: childUsage } : {}),
      });
      return attempts.length - 1;
    };
    if (!childResult.ok) {
      recordInitialAttempt(/cancelled/i.test(childResult.detail) ? "cancelled" : "failed");
      return fail(childResult.detail);
    }
    if (!current()) {
      recordInitialAttempt("cancelled");
      return fail("harness planner cancelled");
    }

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
    let plan: HarnessConsolidationPlan;
    let initialAttempt = -1;
    let recoveryAttempt = -1;
    if (!extracted.ok) {
      initialAttempt = recordInitialAttempt(extracted.failure === "cancelled" ? "cancelled" : extracted.failure ? "failed" : "rejected");
      if (extracted.error !== MISSING_PLAN_ERROR) return fail(extracted.error);
      if (!current()) return fail("harness planner cancelled");
      const recovery = await repairHarnessPlan({
        cli,
        cwd: opts.cwd,
        run,
        missingOutput: true,
        errors: [MISSING_PLAN_ERROR],
        taskText,
        timeoutMs,
        current,
        ...(opts.model ? { model: opts.model } : {}),
        onChild: hooks.onChild,
        onUsage: (value) => { usage = addPiWorkerUsage(usage, value); },
        onAttempt: (attempt) => {
          attempts.push({ phase: "harness", attempt: attempts.length, ...attempt });
          recoveryAttempt = attempts.length - 1;
        },
      });
      if (!recovery.ok) return fail(`${recovery.detail} (after recovery attempt)`);
      plan = recovery.plan;
      if (recoveryAttempt < 0) return fail("harness recovery did not record an attempt");
    } else {
      plan = extracted.plan;
      initialAttempt = recordInitialAttempt("noop");
    }
    const snapshotBytes = await readLayerFileBytes(run.manifest.snapshotPath, MAX_SNAPSHOT_BYTES);
    if (!snapshotBytes) return fail("immutable harness evidence snapshot is missing");
    if (sha256Digest(snapshotBytes) !== run.manifest.snapshotDigest) return fail("immutable harness evidence snapshot changed after capture");
    let snapshot: unknown;
    try { snapshot = JSON.parse(snapshotBytes.toString("utf8")) as unknown; }
    catch { return fail("immutable harness evidence snapshot is not valid JSON"); }
    if (isRecord(snapshot) && snapshot.runId !== undefined && snapshot.runId !== run.manifest.runId) {
      return fail("immutable harness evidence snapshot run id mismatch");
    }
    const target = opts.targetPath ?? configPaths(opts.cwd).project;
    let localConfig: unknown;
    const localBytes = await readLayerFileBytes(target);
    if (localBytes) {
      try { localConfig = JSON.parse(localBytes.toString("utf8")) as unknown; } catch { localConfig = undefined; }
    }
    const validationOptions: HarnessPlanValidationOptions = {
      availableSkills: opts.availableSkills,
      targetSource: path.basename(target) === "harness.local.json" ? "project.local" : "project",
      snapshot,
      snapshotText: snapshotBytes.toString("utf8"),
      layers: [builtInDefaultsLayer(), ...loadLayers(opts.cwd)],
      learnedRules: learnedRuleRevisionsFromConfig(localConfig),
      automatic: true,
      proposingCorrections: Boolean(opts.validateSemantics),
    };
    // Optional display summaries have no authority. A malformed summary must
    // not discard otherwise valid rules or consume the shared repair slot.
    // Revalidate after removal; identity, evidence and executable cases remain
    // exact, and any non-report error still follows the normal rejection path.
    const validateCandidate = (candidate: HarnessConsolidationPlan) => {
      let errors = validateHarnessPlan(candidate, validationOptions);
      if (errors.length && errors.every(error => /^report(?:\[|\s|\.)/.test(error))) {
        const { report: _report, ...withoutReport } = candidate;
        candidate = withoutReport;
        errors = validateHarnessPlan(candidate, validationOptions);
      }
      return { candidate, errors };
    };
    const initialValidation = validateCandidate(plan);
    plan = initialValidation.candidate;
    const errors = initialValidation.errors;
    if (errors.length) {
      attempts[initialAttempt].outcome = "rejected";
      attempts[initialAttempt].diagnostic = parentValidationDiagnostic(errors);
      // A missing structured output already consumed the single recovery slot.
      // Do not turn a recovered-but-invalid plan into a second repair attempt.
      if (!extracted.ok) {
        if (recoveryAttempt >= 0) {
          attempts[recoveryAttempt].outcome = "rejected";
          attempts[recoveryAttempt].diagnostic = parentValidationDiagnostic(errors);
        }
        return fail(errors.join("; ").slice(-600));
      }
      // One bounded repair, mirroring the Memory delta path. A planner that emits
      // a structurally valid but unusable rule — a case list of strings, a
      // negative case that matches its own rule — is a recoverable authoring
      // mistake, not a reason to lose the phase. The repair is handed the exact
      // errors and the rejected plan, and may change nothing else: identity,
      // evidence, and the authoritative selected scope still have to survive.
      if (!current()) return fail("harness planner cancelled");
      let repairAttempt = -1;
      const repair = await repairHarnessPlan({
        cli,
        cwd: opts.cwd,
        run,
        rejected: plan,
        errors,
        taskText,
        timeoutMs,
        current,
        ...(opts.model ? { model: opts.model } : {}),
        onChild: hooks.onChild,
        onUsage: (value) => { usage = addPiWorkerUsage(usage, value); },
        onAttempt: (attempt) => {
          attempts.push({ phase: "harness", attempt: attempts.length, ...attempt });
          repairAttempt = attempts.length - 1;
        },
      });
      if (!repair.ok) return fail(`${repair.detail} (after repair attempt)`);
      const repairedValidation = validateCandidate(repair.plan);
      const repairedErrors = repairedValidation.errors;
      if (repairedErrors.length) {
        if (repairAttempt >= 0) {
          attempts[repairAttempt].outcome = "rejected";
          attempts[repairAttempt].diagnostic = parentValidationDiagnostic(repairedErrors);
        }
        return fail(repairedErrors.join("; ").slice(-600));
      }
      if (repairAttempt < 0) return fail("harness repair did not record an attempt");
      plan = repairedValidation.candidate;
    }
    // Parent-side coverage repair. An empty plan has no operations for the semantic
    // gate to judge, so this runs before it and does not depend on a judge verdict.
    // The repaired plan still passes the normal validation and, when Jev is enabled,
    // the normal semantic gate: the parent generates, the judge still judges.
    if (opts.coverageRepair && attempts.length === 1
      && Array.isArray(plan.operations) && plan.operations.length === 0) {
      // Local index: the planner block's own repairAttempt is out of scope here.
      let coverageAttempt = -1;
      const coverage = await repairHarnessPlan({
        cli, cwd: opts.cwd, run, rejected: plan, allowOmissions: false,
        errors: [
          "The Harness plan contains no rule although the screened evidence states a durable prohibition. Add exactly one rule that blocks the stated restriction in this project, cited to the user's own wording.",
          "Quote the original user text exactly. Do not invent scope, approval exceptions, arguments or expiry that the user did not state.",
          "Preserve exact-only limits: a rule about one exact invocation must not widen to its command family, and an existing rule must not be weakened.",
        ],
        taskText, timeoutMs, current, ...(opts.model ? { model: opts.model } : {}),
        onChild: hooks.onChild,
        onUsage: (value) => { usage = addPiWorkerUsage(usage, value); },
        onAttempt: (attempt) => {
          attempts.push({ phase: "harness", attempt: attempts.length, ...attempt });
          coverageAttempt = attempts.length - 1;
        },
      });
      if (coverage.ok) {
        const coverageValidation = validateCandidate(coverage.plan);
        const coverageOperations = Array.isArray(coverageValidation.candidate.operations) ? coverageValidation.candidate.operations.length : 0;
        if (coverageRepairAccepted(coverageValidation.errors, coverageOperations)) {
          plan = coverageValidation.candidate;
        } else if (coverageAttempt >= 0) {
          attempts[coverageAttempt].outcome = "rejected";
          attempts[coverageAttempt].diagnostic = parentValidationDiagnostic(coverageValidation.errors);
        }
      }
    }
    if (opts.validateSemantics) {
      const completed = completeHarnessLiteralMessages(plan);
      if (completed !== plan) {
        const checked = validateCandidate(completed);
        if (checked.errors.length) return fail(parentValidationDiagnostic(checked.errors));
        if (!current()) return fail("harness message completion cancelled");
        await fs.writeFile(path.join(run.manifest.runDir, "pre-message-completion-plan.json"), JSON.stringify(plan, null, 2), { mode: 0o600 });
        await fs.writeFile(path.join(run.manifest.runDir, "message-completed-plan.json"), JSON.stringify(checked.candidate, null, 2), { mode: 0o600 });
        if (!current()) return fail("harness message completion cancelled");
        plan = checked.candidate;
      }
    }
    let semanticDecision: "allow" | "propose" | undefined;
    let deferredPlan: HarnessConsolidationPlan | undefined;
    if (opts.validateSemantics && Array.isArray(plan.operations) && plan.operations.length) {
      const semanticManifest = run.manifest;
      const parentScope: BoundScopeContext = Object.freeze({ repoRoot: semanticManifest.cwd, runId: semanticManifest.runId, scopeKey: semanticManifest.scopeKey, evidenceDigest: sha256Digest(JSON.stringify(snapshot)) });
      const judge = async (candidate: HarnessConsolidationPlan) => {
        const attempt = attempts.at(-1)!;
        const semanticOperations = (candidate.operations as unknown[]).map(operation => {
          if (!isRecord(operation) || !isRecord(operation.correction) || !isRecord(operation.rule)) return operation;
          const priorRule = validationOptions.layers?.find(layer => layer.source === "project")?.rules?.find(rule => rule.id === (operation.rule as Record<string, unknown>).id);
          return {...operation, priorRule};
        });
        const verdict = await opts.validateSemantics!(snapshot, semanticOperations, candidate.evidence, parentScope);
        // Returned usage belongs to this attempt even if cancellation won the race.
        attempt.jev = verdict.telemetry;
        attempt.diagnostic = `Jev ${verdict.telemetry.status}: ${verdict.telemetry.reason}`;
        if (!current()) return undefined;
        const verifiedSnapshot = await readLayerFileBytes(semanticManifest.snapshotPath, MAX_SNAPSHOT_BYTES);
        if (!verifiedSnapshot || sha256Digest(verifiedSnapshot) !== semanticManifest.snapshotDigest) throw new Error("immutable harness evidence snapshot changed during semantic validation");
        if (!current()) return undefined;
        if (verdict.decision === "propose") attempt.outcome = "proposed";
        return verdict;
      };
      const verdict = await judge(plan);
      if (!verdict) return fail("harness semantic validation cancelled");
      semanticDecision = verdict.decision;
      if (semanticDecision === "propose" && opts.semanticRepair && attempts.length === 1
        && ["uncertain", "unsupported", "scope-expansion"].includes(verdict.telemetry.reason)) {
        const repair = await repairHarnessPlan({ cli, cwd: opts.cwd, run, rejected: plan, allowOmissions: true,
          errors: [
            `Semantic verification: ${verdict.telemetry.reason}${verdict.telemetry.dimension !== undefined && verdict.telemetry.candidateIndex !== undefined ? ` in candidate ${verdict.telemetry.candidateIndex} ${verdict.telemetry.dimension}` : ""}.`,
            "Preserve the quoted authorization and exceptions. Remove unsupported facts and extra obligations from the message. Do not infer approval expiration, revocation or transferability that the evidence does not state.",
            "For one exact command, use absolute literal matching and reject appended CR/NBSP; no scripts, variations or approval requirement may be invented.",
            "Scope repair: For a new command-family rule, only if quoted user evidence prohibits the whole family, prefer the documented anchored ASCII family matcher over operator-prefix searches.",
            "A semicolon or pipe inside a quoted printf argument does not execute that command. Include negative cases for quoted command strings containing operators and arguments.",
            "Git family coverage: retain same-project global-option positives (git -C . push, git -c core.quotePath=false push, git --no-pager push). Echo and quoted printf of those strings remain negative. Do not delete valid cases, use greedy wildcard matching, or broaden exact-only/project limits.",
            "Preserve exact-only limits and approval exceptions. Ordinary updates must not weaken existing rules; an explicitly authorized correction may replace or retire only the owned predecessor through the exact correction contract, never by inventing permission.",
            ...jevRepairFailureHints(verdict.telemetry),
          ],
          taskText, timeoutMs, current, ...(opts.model ? { model: opts.model } : {}), onChild: hooks.onChild,
          onUsage: value => { usage = addPiWorkerUsage(usage, value); },
          onAttempt: attempt => { attempts.push({ phase: "harness", attempt: attempts.length, ...attempt }); },
        });
        if (!current()) return fail("harness semantic repair cancelled");
        const freshSnapshot = await readLayerFileBytes(run.manifest.snapshotPath, MAX_SNAPSHOT_BYTES);
        if (!freshSnapshot || sha256Digest(freshSnapshot) !== run.manifest.snapshotDigest) return fail("immutable harness evidence snapshot changed during semantic repair");
        if (repair.ok) {
          const repairedValidation = validateCandidate(repair.plan);
          const repairedErrors = repairedValidation.errors;
          // An empty repair must not silently erase the original opportunity.
          if (repairedErrors.length || !Array.isArray(repair.plan.operations) || !repair.plan.operations.length) {
            attempts.at(-1)!.outcome = "rejected";
            attempts.at(-1)!.diagnostic = `${repairedErrors.length ? parentValidationDiagnostic(repairedErrors) : "Parent Harness validation: empty-plan"}; original proposal retained`;
          } else {
            const remainder = semanticRepairRemainder(plan, repairedValidation.candidate);
            if (typeof remainder === "string" || (remainder && validateHarnessPlan(remainder, validationOptions).length)) {
              attempts.at(-1)!.outcome = "rejected";
              attempts.at(-1)!.diagnostic = `Semantic repair changed rule identities or original citations; cause=${typeof remainder === "string" ? remainder : "remainder-validation"}; original proposal retained`;
            } else {
              if (remainder) {
                await recordLearningProposal(run.manifest.cwd, "harness", remainder);
                deferredPlan = remainder;
                if (!current()) return fail("harness semantic repair cancelled");
              }
              plan = repairedValidation.candidate;
              const repairedVerdict = await judge(plan);
              if (!repairedVerdict) return fail("harness semantic validation cancelled");
              semanticDecision = repairedVerdict.decision;
              if (deferredPlan && Array.isArray(deferredPlan.operations)) attempts.at(-1)!.diagnostic += `; ${deferredPlan.operations.length} omitted operation(s) saved for review`;
            }
          }
        }
      }
    }
    validationOptions.proposingCorrections = false;
    if (semanticDecision === "allow" && attempts.at(-1)?.jev?.status === "decided") {
      validationOptions.reviewedCorrections = Object.fromEntries((Array.isArray(plan.operations) ? plan.operations : [])
        .filter(operation => isRecord(operation) && isRecord(operation.correction) && isRecord(operation.rule))
        .map(operation => [(operation as HarnessOp).rule.id, correctionDigest(operation)]));
    }
    return {
      ok: true,
      value: {
        run,
        plan,
        validationOptions,
        ...(semanticDecision ? { semanticDecision } : {}),
        ...(deferredPlan ? { deferredPlan } : {}),
        target,
        durationMs: Date.now() - startedAt,
        ...(usage ? { usage } : {}),
        ...(attempts.length > 0 ? { attempts: [...attempts] } : {}),
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
  if (!current()) return { outcome: "cancelled", operations: ops.length };
  if (planning.semanticDecision === "propose") return { outcome: "rejected", operations: ops.length, error: "Harness semantic proposal requires review" };
  const errors = validateHarnessPlan(plan, validationOptions);
  if (errors.length) return { outcome: "rejected", operations: ops.length, error: errors.join("; ") };
  if (ops.length === 0) {
    await writeFileAtomic(path.join(runDir, "harness-noop.txt"), "verified no-op\n").catch(() => {});
    return { outcome: "noop", operations: 0 };
  }
  try {
    return await withFileMutationQueue(path.resolve(target), async () => {
      // A queued mutation must not use evidence changed during a prior await.
      const snapshotBytes = await readLayerFileBytes(run.manifest.snapshotPath, MAX_SNAPSHOT_BYTES);
      if (!snapshotBytes || sha256Digest(snapshotBytes) !== run.manifest.snapshotDigest) throw new Error("immutable harness evidence snapshot changed before application");
      if (!current()) return { outcome: "cancelled" as const, operations: ops.length };
      // Reload all three layers immediately before validation. Planning snapshots
      // cannot authorize overwriting a newer manual or personal declaration.
      const prepared = await prepareHarnessOps(target, ops, {
        ...validationOptions,
        layers: loadLayers(run.manifest.cwd ?? path.dirname(path.dirname(target))),
        evidence: plan.evidence, automatic: true, requireEvidence: true,
      });
      if (!current()) return { outcome: "cancelled" as const, operations: ops.length };
      return recordLearningMutation(run.manifest.cwd, "harness", [target], async () => {
        const planDigest = sha256Digest(JSON.stringify(plan));
        const receiptInput = {
          runId: run.manifest.runId, scopeDigest: run.manifest.scopeDigest,
          snapshotDigest: run.manifest.snapshotDigest, targetFile: target,
          digestBefore: prepared.before ? sha256Digest(prepared.before) : null, planDigest,
        };
        await writeFileAtomic(path.join(runDir, "harness-pre-receipt.json"), `${JSON.stringify(buildHarnessReceipt({ ...receiptInput, phase: "pre" }), null, 2)}\n`);
        await writePreparedHarness(target, prepared);
        const rollback = () => rollbackPreparedHarness(target, prepared);
        if (!current()) { await rollback(); return { outcome: "cancelled" as const, operations: ops.length }; }
        const receipt = buildHarnessReceipt({ ...receiptInput, phase: "post", digestAfter: sha256Digest(prepared.next), applied: prepared.applied });
        try { await writeFileAtomic(path.join(runDir, "harness-post-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`); }
        catch (error) { await rollback(); throw error; }
        return { outcome: "applied" as const, operations: ops.length, applied: prepared.applied };
      }, plan);
    });
  } catch (error) { return { outcome: "rejected", operations: ops.length, error: (error as Error).message }; }

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

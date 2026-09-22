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

import fs from "node:fs/promises";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import { withFileMutationQueue, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { recordLearningMutation } from "./learning-history";
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
import { assertHarnessConfigContainers, configPaths, loadLayers } from "./guardrail-config";
import type { RuleLayer } from "./guardrail-types";
import { legacyReservedNames } from "./legacy-harness";
import { buildHarnessConsolidatorPrompt, learningPlannerArgs } from "./planner-prompts";

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
const HARNESS_OP_KINDS = ["addRule", "updateRule"] as const;
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
  rule: Record<string, unknown>;
  /** Bounded selector fixtures evaluated without executing commands. */
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
  const selector = ["bash", "skill", "text"].find(key => rule[key] !== undefined);
  for (const side of ["positive", "negative"] as const) for (const [index, fixture] of cases[side].entries()) {
    const name = `${label}.cases.${side}[${index}]`;
    if (!selector || fixture[selector as keyof HarnessRuleCase] === undefined) { errors.push(`${name} selector does not match proposed rule`); continue; }
    let matched = false;
    let decision: string | undefined;
    if (selector === "bash") {
      const evaluation = evaluateBash(config, fixture.bash!);
      matched = evaluation.matchedRules.some(match => match.id === rule.id);
      decision = evaluation.decision;
    } else if (selector === "skill") matched = evaluateSkill(config, fixture.skill!).some(match => match.id === rule.id);
    else {
      const evaluation = evaluateText(config, fixture.text!);
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
      if (ruleWeakens(existing, raw.rule)) errors.push(`${label}: automatic learning cannot weaken, change selectors, disable, or re-enable an existing rule; use explicit /harness authorization`);
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
    if (Object.keys(raw).some(key => !["op", "rule", "cases"].includes(key))) errors.push(`${label} has unsupported operation fields`);
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
    if (validationOptions.automatic && rule.enabled === false) errors.push(`${label}: automatic learning cannot disable rules`);
    const fixtures = parseRuleCases(raw.cases, label, errors, strict || options.requireCases === true);
    if (fixtures && !declarationErrors.length) validateRuleCases(rule, fixtures, label, errors, skills);
    // A registry entry alone proves availability, not an evidence-backed scope.
    if (strict && (rule.skill !== undefined || rule.text !== undefined) && !declarationErrors.length) {
      const evidence = options.evidence ?? p.evidence;
      const quotes = Array.isArray(evidence) ? evidence.filter(item => isRecord(item) && item.index === index && typeof item.quote === "string").map(item => (item as HarnessEvidence).quote) : [];
      const config = mergeLayers([{ source: "candidate", rules: [rule] }], skills);
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
  const order = ["user", "project", "project.local"];
  layers.sort((a, b) => order.indexOf(a.source) - order.indexOf(b.source));
  const options = { ...requested, targetSource: source as "project" | "project.local", layers, learnedRules: learnedRuleRevisionsFromConfig(base) };
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
    const child = spawnPiChild(cli.command, [
      ...cli.args,
      ...minimalPiWorkerArgs(["read", "grep", "find", "ls"]),
      ...learningPlannerArgs(),
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
  if (!current()) return { outcome: "cancelled", operations: ops.length };
  const errors = validateHarnessPlan(plan, validationOptions);
  if (errors.length) return { outcome: "rejected", operations: ops.length, error: errors.join("; ") };
  if (ops.length === 0) {
    await writeFileAtomic(path.join(runDir, "harness-noop.txt"), "verified no-op\n").catch(() => {});
    return { outcome: "noop", operations: 0 };
  }
  try {
    return await withFileMutationQueue(path.resolve(target), async () => {
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

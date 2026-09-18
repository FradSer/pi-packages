/**
 * AGENTS.md consolidation phase — the third stage of the /consolidate pipeline.
 *
 * Runs after a verified memory phase and the harness phase against the SAME
 * immutable session snapshot: a read-only planner child proposes bounded,
 * evidence-cited edits to the repository-root AGENTS.md — rewrite, remove,
 * add, or extract addressable units. The parent verifies every cited quote
 * verbatim against the snapshot text in code, simulates the resulting
 * document, enforces the byte budget (zero-sum growth at budget), and applies
 * every operation that passes those gates autonomously. User-level
 * instruction files are never touched, and any failure here never touches
 * applied memory or harness results.
 */

import fs from "node:fs/promises";
import { constants as fsConstants, realpathSync } from "node:fs";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import { getAgentDir, type ExtensionContext } from "@earendil-works/pi-coding-agent";
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
  MAX_SNAPSHOT_BYTES,
  MAX_STDOUT_BYTES,
  type ConsolidationRun,
} from "./consolidation-run";
import { buildMemoryIndexContent, isMemoryFilename } from "./memory-files";
import { resolveMemoryPaths } from "./memory-paths";
import type { HarnessOp } from "./harness-consolidation";
import { buildAgentsMdConsolidatorPrompt } from "./planner-prompts";
import { assertHarnessConfigContainers, configPaths, loadLayers } from "./guardrail-config";
import { legacyReservedNames } from "./legacy-harness";
import { DEFAULT_RULES, evaluateSkill, mergeLayers, validateRuleDeclaration } from "./guardrail-engine";

export const AGENTS_PLAN_KIND = "agents-md-consolidation-plan";
/** Learning rate: at most five small edits per consolidation run. */
export const MAX_AGENTS_MD_OPS = 5;
/** Refuse to plan against absurd instruction files. */
export const MAX_AGENTS_MD_FILE_BYTES = 262_144;
/** One addressed unit stays bounded and auditable. */
export const MAX_UNIT_TEXT_CHARS = 4_000;
export const MAX_EXTRACT_INSTRUCTIONS_CHARS = 2_000;
/** Extraction can retain a discoverable route, not another detailed unit. */
export const MAX_REPLACEMENT_TEXT_CHARS = 500;
export const MAX_MEMORY_DESCRIPTION_CHARS = 120;
/** Default always-loaded budget (~4k English tokens by the common bytes/4
 * heuristic). Anchored conservatively below two industry reference points:
 * backpass defaults to ~20KB for its memory file, and Claude Code loads only
 * the first 25KB of MEMORY.md. Configurable per project. */
export const DEFAULT_AGENTS_MD_BUDGET_BYTES = 16_384;
export const MIN_BUDGET_BYTES = 2_048;
const AGENTS_PHASE_TIMEOUT_MS = 15 * 60 * 1000;

export type AgentsOpKind = "rewriteUnit" | "removeUnit" | "addUnit" | "extractUnit";
export type EvidenceKind = "violation" | "wrong" | "unused" | "gap";
const OP_KINDS: readonly AgentsOpKind[] = ["rewriteUnit", "removeUnit", "addUnit", "extractUnit"];
const EVIDENCE_KINDS: readonly EvidenceKind[] = ["violation", "wrong", "unused", "gap"];
const MEMORY_TYPES = ["project", "feedback", "reference"] as const;

export interface AgentsEvidence {
  kind?: EvidenceKind;
  quote: string;
  entryIndex: number;
  occurrences?: number;
}

interface ExtractionMemory {
  target: "memory";
  memoryName: string;
  description: string;
  type: (typeof MEMORY_TYPES)[number];
  classification: "safe" | "private";
}

interface ExtractionSkillRule {
  target: "skillRule";
  ruleId: string;
  skillName: string;
  instructions: string;
}

type Extraction = ExtractionMemory | ExtractionSkillRule;

export interface AgentsOp {
  op: AgentsOpKind;
  oldText?: string;
  /** Optional concise conditional pointer left where the extracted unit was. */
  replacementText?: string;
  newText?: string;
  text?: string;
  anchor?: string;
  position?: "before" | "after";
  reason?: string;
  rationale?: string;
  extraction?: Extraction;
  evidence: AgentsEvidence[];
}

export interface AgentsPlan {
  kind?: string;
  version?: number;
  schemaVersion?: number;
  runId?: string;
  scopeDigest?: string;
  artifactHash?: string;
  operations?: unknown;
  report?: unknown;
}

function boundedString(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function boundedLine(value: unknown, max: number): value is string {
  return boundedString(value, max) && value.trim().length > 0 && !/[\x00-\x1f\x7f\u2028\u2029]/.test(value);
}

function parseEvidence(raw: unknown, label: string, errors: string[]): AgentsEvidence[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    errors.push(`${label}.evidence must be a non-empty array`);
    return [];
  }
  const parsed: AgentsEvidence[] = [];
  raw.forEach((entry, i) => {
    const itemLabel = `${label}.evidence[${i}]`;
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      errors.push(`${itemLabel} is not an object`);
      return;
    }
    const record = entry as Record<string, unknown>;
    if (!boundedString(record.quote, 2_000)) {
      errors.push(`${itemLabel}.quote must be 1..2000 chars`);
      return;
    }
    if (record.kind !== undefined && !EVIDENCE_KINDS.includes(record.kind as EvidenceKind)) {
      errors.push(`${itemLabel}.kind must be one of ${EVIDENCE_KINDS.join(", ")}`);
      return;
    }
    if (typeof record.entryIndex !== "number" || !Number.isSafeInteger(record.entryIndex) || record.entryIndex < 0) {
      errors.push(`${itemLabel}.entryIndex must be a non-negative snapshot entry index`);
      return;
    }
    if (record.occurrences !== undefined && (typeof record.occurrences !== "number" || !Number.isInteger(record.occurrences) || record.occurrences < 1)) {
      errors.push(`${itemLabel}.occurrences must be a positive integer`);
      return;
    }
    parsed.push({ quote: record.quote, entryIndex: record.entryIndex, occurrences: record.occurrences ?? 1, kind: record.kind as EvidenceKind | undefined });
  });
  return parsed;
}

function parseExtraction(raw: unknown, label: string, errors: string[]): Extraction | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push(`${label}.extraction must be an object`);
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  if (record.target === "skillRule") {
    if (!boundedLine(record.ruleId, 128) || record.ruleId !== record.ruleId.trim()) {
      errors.push(`${label}.extraction.ruleId must be a non-blank 1..128 char ID without surrounding whitespace`);
      return undefined;
    }
    if (typeof record.skillName !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(record.skillName)) {
      errors.push(`${label}.extraction.skillName is invalid`);
      return undefined;
    }
    if (!boundedString(record.instructions, MAX_EXTRACT_INSTRUCTIONS_CHARS) || !record.instructions.trim()) {
      errors.push(`${label}.extraction.instructions must be non-blank and 1..${MAX_EXTRACT_INSTRUCTIONS_CHARS} chars`);
      return undefined;
    }
    return { target: "skillRule", ruleId: record.ruleId, skillName: record.skillName, instructions: record.instructions };
  }
  if (record.target === "memory") {
    const name = record.memoryName;
    if (
      typeof name !== "string" || !isMemoryFilename(name) || name.toLowerCase() === "memory.md"
    ) {
      errors.push(`${label}.extraction.memoryName is not a canonical memory filename`);
      return undefined;
    }
    if (!boundedLine(record.description, MAX_MEMORY_DESCRIPTION_CHARS)) {
      errors.push(`${label}.extraction.description must be a non-blank single line of 1..${MAX_MEMORY_DESCRIPTION_CHARS} chars`);
      return undefined;
    }
    if (!MEMORY_TYPES.includes(record.type as (typeof MEMORY_TYPES)[number])) {
      errors.push(`${label}.extraction.type must be one of ${MEMORY_TYPES.join(", ")}`);
      return undefined;
    }
    if (record.classification !== "safe" && record.classification !== "private") {
      errors.push(`${label}.extraction.classification must be "safe" or "private"`);
      return undefined;
    }
    return {
      target: "memory",
      memoryName: name,
      description: record.description,
      type: record.type as ExtractionMemory["type"],
      classification: record.classification,
    };
  }
  errors.push(`${label}.extraction.target must be "memory" or "skillRule"`);
  return undefined;
}

function coerceOperation(raw: unknown, label: string, errors: string[]): AgentsOp | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push(`${label} is not an object`);
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  if (!OP_KINDS.includes(record.op as AgentsOpKind)) {
    errors.push(`${label}.op must be one of ${OP_KINDS.join(", ")}`);
    return undefined;
  }
  const op = record.op as AgentsOpKind;
  if (record.replacementText !== undefined && op !== "extractUnit") {
    errors.push(`${label}.replacementText is only valid for extractUnit`);
    return undefined;
  }
  const evidence = parseEvidence(record.evidence, label, errors);
  const base: AgentsOp = {
    op,
    evidence,
    ...(typeof record.reason === "string" ? { reason: record.reason.slice(0, 500) } : {}),
    ...(typeof record.rationale === "string" ? { rationale: record.rationale.slice(0, 500) } : {}),
  };
  if (op === "addUnit") {
    if (!boundedString(record.text, MAX_UNIT_TEXT_CHARS)) {
      errors.push(`${label}.text must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
      return undefined;
    }
    base.text = record.text;
    if (record.anchor !== undefined || record.position !== undefined) {
      if (!boundedString(record.anchor, MAX_UNIT_TEXT_CHARS)) {
        errors.push(`${label}.anchor must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
        return undefined;
      }
      if (record.position !== "before" && record.position !== "after") {
        errors.push(`${label}.position must be "before" or "after"`);
        return undefined;
      }
      base.anchor = record.anchor;
      base.position = record.position;
    }
  } else {
    if (!boundedString(record.oldText, MAX_UNIT_TEXT_CHARS)) {
      errors.push(`${label}.oldText must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
      return undefined;
    }
    base.oldText = record.oldText;
    if (op === "rewriteUnit") {
      if (!boundedString(record.newText, MAX_UNIT_TEXT_CHARS)) {
        errors.push(`${label}.newText must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
        return undefined;
      }
      base.newText = record.newText;
    }
    if (op === "extractUnit") {
      if (record.replacementText !== undefined) {
        if (!boundedLine(record.replacementText, MAX_REPLACEMENT_TEXT_CHARS)) {
          errors.push(`${label}.replacementText must be a non-blank single line of 1..${MAX_REPLACEMENT_TEXT_CHARS} chars`);
          return undefined;
        }
        base.replacementText = record.replacementText;
      }
      base.extraction = parseExtraction(record.extraction, label, errors);
      if (!base.extraction) return undefined;
    }
  }
  return base;
}

/** Validate plan shape and bounds. Identity binding is enforced separately. */
export function validateAgentsMdPlan(plan: unknown): { ok: true; operations: AgentsOp[] } | { ok: false; errors: string[] } {
  const p = plan as AgentsPlan;
  if (!p || typeof p !== "object" || Array.isArray(p)) return { ok: false, errors: ["plan is not an object"] };
  if (p.kind !== AGENTS_PLAN_KIND) return { ok: false, errors: [`kind must be "${AGENTS_PLAN_KIND}"`] };
  if (p.operations === undefined) return { ok: true, operations: [] };
  if (!Array.isArray(p.operations)) return { ok: false, errors: ["operations must be an array"] };
  if (p.operations.length > MAX_AGENTS_MD_OPS) {
    return { ok: false, errors: [`operations exceed the maximum of ${MAX_AGENTS_MD_OPS}`] };
  }
  const errors: string[] = [];
  const operations: AgentsOp[] = [];
  p.operations.forEach((raw, i) => {
    const op = coerceOperation(raw, `operations[${i}]`, errors);
    if (op) operations.push(op);
  });
  if (errors.length) return { ok: false, errors };
  return { ok: true, operations };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function snapshotEntries(snapshotText: string): unknown[] {
  try {
    const snapshot = JSON.parse(snapshotText) as unknown;
    return isRecord(snapshot) && Array.isArray(snapshot.entries) ? snapshot.entries : [];
  } catch {
    return [];
  }
}

function snapshotEntryRole(entry: unknown): "user" | "tool" | undefined {
  if (!isRecord(entry)) return undefined;
  const message = isRecord(entry.message) ? entry.message : undefined;
  const role = typeof message?.role === "string"
    ? message.role.toLowerCase()
    : typeof entry.role === "string" ? entry.role.toLowerCase() : "";
  if (role === "user") return "user";
  if (["tool", "toolresult", "tool-result", "tool_result"].includes(role)) return "tool";
  const type = typeof entry.type === "string" ? entry.type.toLowerCase() : "";
  return type === "tool_execution_end" ? "tool" : undefined;
}

function contentTextLeaves(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(contentTextLeaves);
  if (!isRecord(value)) return [];
  if (typeof value.text === "string") return [value.text];
  return [value.content, value.output, value.stdout, value.stderr, value.error, value.result]
    .filter((item) => item !== undefined)
    .flatMap(contentTextLeaves);
}

function snapshotEntryEvidenceText(entry: unknown, role: "user" | "tool"): string {
  if (!isRecord(entry)) return "";
  const message = isRecord(entry.message) ? entry.message : undefined;
  if (role === "user") return contentTextLeaves(message?.content ?? entry.content).join("\n");
  const messageRole = typeof message?.role === "string" ? message.role.toLowerCase() : "";
  if (["tool", "toolresult", "tool-result", "tool_result"].includes(messageRole)) {
    return contentTextLeaves(message?.content ?? entry.content).join("\n");
  }
  return [entry.result, entry.output, entry.stdout, entry.stderr, entry.error]
    .filter((item) => item !== undefined)
    .flatMap(contentTextLeaves)
    .join("\n");
}

/** A quote is admissible only when it appears in the cited immutable snapshot
 * entry's user content or tool-result content. Snapshot envelope metadata and
 * assistant/system text are not evidence. */
export function quoteInSnapshot(quote: string, snapshotText: string, entryIndex: number): boolean {
  if (!quote.trim() || !Number.isSafeInteger(entryIndex) || entryIndex < 0) return false;
  const entry = snapshotEntries(snapshotText)[entryIndex];
  const role = snapshotEntryRole(entry);
  if (!role) return false;
  return snapshotEntryEvidenceText(entry, role).includes(quote);
}

export interface QuoteVerification {
  /** Operations whose evidence survived verification, quotes filtered. */
  operations: AgentsOp[];
  /** Original indexes of dropped operations. */
  dropped: number[];
  /** Verified quotes per surviving operation (aligned with `operations`). */
  verifiedQuotes: string[][];
}

/** Discard unverifiable quotes in code; drop operations left without any. */
export function verifyPlanQuotes(operations: readonly AgentsOp[], snapshotText: string): QuoteVerification {
  const result: QuoteVerification = { operations: [], dropped: [], verifiedQuotes: [] };
  operations.forEach((op, index) => {
    const evidence = op.evidence.filter((entry) => quoteInSnapshot(entry.quote, snapshotText, entry.entryIndex));
    if (evidence.length === 0) {
      result.dropped.push(index);
      return;
    }
    result.operations.push({ ...op, evidence });
    result.verifiedQuotes.push(evidence.map((entry) => entry.quote));
  });
  return result;
}

/** Batched-evidence gate for brand-new units. Only distinct verified snapshot
 * entries count; planner-supplied occurrence counts and repeated citations to
 * one entry are deliberately ignored. */
export function addUnitEvidenceSufficient(op: AgentsOp): boolean {
  if (op.op !== "addUnit") return true;
  return new Set(op.evidence.map((entry) => entry.entryIndex)).size >= 2;
}

export function fingerprintOp(op: AgentsOp): string {
  const material = JSON.stringify({
    op: op.op,
    oldText: op.oldText ?? null,
    replacementText: op.replacementText ?? null,
    newText: op.newText ?? null,
    text: op.text ?? null,
    anchor: op.anchor ?? null,
    position: op.position ?? null,
    extraction: op.extraction ?? null,
  });
  return sha256Digest(material);
}

/** Simulate applying operations to the document exactly like the edit tool
 * contract: every `oldText` / `anchor` must match exactly once. The whole
 * simulation fails closed on any ambiguity so no partial state is possible. */
export function simulateAgentsOps(
  doc: string,
  ops: readonly AgentsOp[],
): { ok: true; doc: string; applied: string[] } | { ok: false; error: string } {
  let next = doc;
  const applied: string[] = [];
  for (const [index, op] of ops.entries()) {
    const label = `operations[${index}]`;
    if (op.op === "addUnit") {
      const text = op.text!;
      if (op.anchor === undefined) {
        const separator = next.endsWith("\n") ? (next.endsWith("\n\n") ? "" : "\n") : "\n\n";
        next = `${next}${separator}${text}${text.endsWith("\n") ? "" : "\n"}`;
        applied.push(`addUnit[${index}] (append)`);
        continue;
      }
      const anchor = op.anchor;
      const first = next.indexOf(anchor);
      if (first < 0) return { ok: false, error: `${label}.anchor does not match the document` };
      if (next.indexOf(anchor, first + 1) >= 0) return { ok: false, error: `${label}.anchor matches more than once` };
      const inserted = `${text.replace(/\n$/, "")}\n`;
      // Insertion lands on whole-line boundaries relative to the anchor's line.
      if (op.position === "before") {
        const lineStart = next.lastIndexOf("\n", first) + 1;
        next = `${next.slice(0, lineStart)}${inserted}${next.slice(lineStart)}`;
      } else {
        const lineEnd = next.indexOf("\n", first + anchor.length);
        const insertAt = lineEnd === -1 ? next.length : lineEnd + 1;
        next = `${next.slice(0, insertAt)}${inserted}${next.slice(insertAt)}`;
      }
      applied.push(`addUnit[${index}] (${op.position} anchor)`);
      continue;
    }
    const oldText = op.oldText!;
    const first = next.indexOf(oldText);
    if (first < 0) return { ok: false, error: `${label}.oldText does not match the document` };
    if (next.indexOf(oldText, first + 1) >= 0) return { ok: false, error: `${label}.oldText matches more than once` };
    const replacement = op.op === "rewriteUnit" ? op.newText! : op.op === "extractUnit" ? op.replacementText ?? "" : "";
    next = next.slice(0, first) + replacement + next.slice(first + oldText.length);
    applied.push(`${op.op}[${index}]`);
  }
  return { ok: true, doc: next, applied };
}

/** Budget gate: growth is allowed only below budget; at or above it updates
 * are zero-sum — the post-edit document may not exceed the current one. */
export function budgetAllows(preBytes: number, postBytes: number, budgetBytes: number): boolean {
  return postBytes <= Math.max(preBytes, budgetBytes);
}

/** The consolidation target is exactly <cwd>/AGENTS.md. When that path would
 * resolve — lexically or through symlinks — to the user-level agent
 * instructions, it must never be touched. */
export function isUserLevelInstructionsFile(target: string, agentDir: string): boolean {
  const resolvedTarget = path.resolve(target);
  const agentInstructions = path.resolve(agentDir, "AGENTS.md");
  if (resolvedTarget === agentInstructions) return true;
  // Lexical equality misses symlinked project directories; compare real paths,
  // falling back to the real parent when the target does not exist yet.
  const realOf = (candidate: string): string | undefined => {
    try {
      return realpathSync(candidate);
    } catch {
      try {
        return path.join(realpathSync(path.dirname(candidate)), path.basename(candidate));
      } catch {
        return undefined;
      }
    }
  };
  const realTarget = realOf(resolvedTarget);
  const realAgent = realOf(agentInstructions);
  if (!realTarget || !realAgent) return false;
  return realTarget === realAgent;
}

export interface AgentsTargetResolution {
  path?: string;
  skipReason?: string;
}

export function resolveAgentsTargetFile(cwd: string, agentDir: string): AgentsTargetResolution {
  const target = path.resolve(cwd, "AGENTS.md");
  if (isUserLevelInstructionsFile(target, agentDir)) {
    return { skipReason: "project AGENTS.md resolves to user-level instructions; refusing to touch them" };
  }
  return { path: target };
}

export interface AgentsMdConsolidationPhaseOptions {
  pkgDir: string;
  cwd: string;
  reason: string;
  budgetBytes: number;
  disabled: boolean;
  availableSkills?: readonly string[];
  explorationPath?: string;
  explorationDigest?: string;
  /** Package-local public seams for deterministic transaction/planner regressions. */
  transactionFault?: "after-artifacts" | "after-agents" | "before-receipt";
  transactionHook?: (stage: "after-roots-opened" | "before-artifacts") => void | Promise<void>;
  timeoutMs?: number;
}

export interface AgentsMdConsolidationPlanResult {
  run: ConsolidationRun;
  targetPath: string;
  docBytes: Buffer;
  doc: string;
  preBytes: number;
  snapshotText: string;
  rawPlan: unknown;
  operations: AgentsOp[];
  droppedCount: number;
  usage?: PiWorkerUsage;
  durationMs: number;
}

export type AgentsMdConsolidationPlanningOutcome =
  | { outcome: "planned"; durationMs: number; usage?: PiWorkerUsage; planning: AgentsMdConsolidationPlanResult }
  | { outcome: "noop" | "rejected" | "failed" | "cancelled" | "skipped"; durationMs: number; usage?: PiWorkerUsage; detail?: string };

export interface AgentsMdConsolidationApplyResult {
  outcome: "applied" | "noop" | "failed" | "cancelled";
  applied: number;
  extractions: string[];
  detail?: string;
}

interface AgentsRecoveryReceipt {
  kind: "agents-md-consolidation-receipt";
  phase: "pre";
  runId: string;
  scopeDigest: string;
  snapshotDigest: string;
  targetFile: string;
  budgetBytes: number;
  planDigest: string;
  predecessors: Array<{ file: string; existed: boolean; mode: number | null; bytesBase64: string | null }>;
  directories: DirectorySnapshot[];
}

async function readRegularFileIfExists(filePath: string, maxBytes: number): Promise<Buffer | null> {
  try {
    const st = await fs.lstat(filePath);
    if (!st.isFile()) return null;
    if (st.size > maxBytes) throw new Error(`AGENTS.md exceeds ${maxBytes} bytes; refusing to plan against it`);
    return await fs.readFile(filePath);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function readSnapshotText(run: ConsolidationRun): Promise<string> {
  const bytes = await fs.readFile(run.paths.snapshotFile);
  if (bytes.byteLength > MAX_SNAPSHOT_BYTES) throw new Error(`AGENTS.md snapshot exceeds ${MAX_SNAPSHOT_BYTES} bytes`);
  if (sha256Digest(bytes) !== run.manifest.snapshotDigest) throw new Error("AGENTS.md immutable snapshot changed after capture");
  return bytes.toString("utf8");
}

interface TransactionSnapshot {
  file: string;
  existed: boolean;
  content?: Buffer;
  mode?: number;
}

interface DirectorySnapshot {
  path: string;
  existed: boolean;
}

interface StableMemoryRoot {
  path: string;
  existed: boolean;
  handle?: fs.FileHandle;
  device?: number;
  inode?: number;
}

async function captureTransactionFile(file: string): Promise<TransactionSnapshot> {
  try {
    const stat = await fs.lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`Transaction target is not a regular file: ${file}`);
    return { file, existed: true, content: await fs.readFile(file), mode: stat.mode & 0o777 };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { file, existed: false };
    throw error;
  }
}

async function captureDirectory(pathname: string): Promise<DirectorySnapshot> {
  try {
    const stat = await fs.lstat(pathname);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Transaction directory is unsafe: ${pathname}`);
    return { path: pathname, existed: true };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { path: pathname, existed: false };
    throw error;
  }
}

function insideRoot(file: string, root: string): boolean {
  const relative = path.relative(path.resolve(root), path.resolve(file));
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

async function restoreTransactionState(
  snapshots: readonly TransactionSnapshot[],
  directories: readonly DirectorySnapshot[],
  stableRoots: readonly StableMemoryRoot[],
): Promise<void> {
  const errors: string[] = [];
  const unsafeRoots = new Set<string>();
  for (const root of stableRoots) {
    try {
      await assertStableMemoryRoot(root);
    } catch (error) {
      unsafeRoots.add(root.path);
      errors.push((error as Error).message);
    }
  }
  for (const snapshot of [...snapshots].reverse()) {
    if ([...unsafeRoots].some((root) => insideRoot(snapshot.file, root))) continue;
    try {
      if (snapshot.existed) await writeFileAtomic(snapshot.file, snapshot.content!, snapshot.mode ?? 0o600);
      else await fs.rm(snapshot.file, { force: true });
    } catch (error) {
      errors.push((error as Error).message);
    }
  }
  for (const directory of [...directories].reverse()) {
    if (directory.existed) continue;
    try {
      await fs.rmdir(directory.path);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT" && (error as NodeJS.ErrnoException).code !== "ENOTEMPTY") {
        errors.push((error as Error).message);
      }
    }
  }
  if (errors.length) throw new Error(errors.join("; "));
}

async function openStableMemoryRoot(root: string): Promise<StableMemoryRoot> {
  try {
    const handle = await fs.open(root, fsConstants.O_RDONLY | (fsConstants.O_DIRECTORY ?? 0) | (fsConstants.O_NOFOLLOW ?? 0));
    const stat = await handle.stat();
    if (!stat.isDirectory()) {
      await handle.close();
      throw new Error(`Memory extraction root is not a regular directory: ${root}`);
    }
    return { path: root, existed: true, handle, device: stat.dev, inode: stat.ino };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { path: root, existed: false };
    throw new Error(`Memory extraction root is unsafe: ${root}`);
  }
}

async function assertStableMemoryRoot(root: StableMemoryRoot): Promise<void> {
  if (!root.handle) {
    let stat: Awaited<ReturnType<typeof fs.lstat>>;
    try {
      stat = await fs.lstat(root.path);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT" && !root.existed) return;
      throw error;
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Memory extraction root changed: ${root.path}`);
    const handle = await fs.open(root.path, fsConstants.O_RDONLY | (fsConstants.O_DIRECTORY ?? 0) | (fsConstants.O_NOFOLLOW ?? 0));
    const opened = await handle.stat();
    if (!opened.isDirectory() || opened.dev !== stat.dev || opened.ino !== stat.ino) {
      await handle.close();
      throw new Error(`Memory extraction root changed: ${root.path}`);
    }
    root.handle = handle;
    root.device = stat.dev;
    root.inode = stat.ino;
    return;
  }
  const current = await fs.lstat(root.path);
  const opened = await root.handle.stat();
  if (
    !current.isDirectory() ||
    current.isSymbolicLink() ||
    current.dev !== root.device ||
    current.ino !== root.inode ||
    opened.dev !== root.device ||
    opened.ino !== root.inode
  ) {
    throw new Error(`Memory extraction root changed: ${root.path}`);
  }
}

async function closeStableRoots(roots: readonly StableMemoryRoot[]): Promise<void> {
  await Promise.all(roots.map((root) => root.handle?.close().catch(() => {})));
}

function isAllowedRecoveryFile(file: string, allowedRoots: readonly string[], allowedFiles: ReadonlySet<string>): boolean {
  const resolved = path.resolve(file);
  if (allowedFiles.has(resolved)) return true;
  return allowedRoots.some((root) => insideRoot(resolved, root));
}

function parseRecoveryReceipt(raw: unknown, run: ConsolidationRun, cwd: string): AgentsRecoveryReceipt {
  if (!isRecord(raw) || raw.kind !== "agents-md-consolidation-receipt" || raw.phase !== "pre") {
    throw new Error("AGENTS.md recovery receipt kind or phase is invalid");
  }
  if (
    raw.runId !== run.manifest.runId ||
    raw.scopeDigest !== run.manifest.scopeDigest ||
    raw.snapshotDigest !== run.manifest.snapshotDigest ||
    typeof raw.targetFile !== "string" ||
    path.resolve(raw.targetFile) !== path.resolve(cwd, "AGENTS.md") ||
    !Array.isArray(raw.predecessors) ||
    !Array.isArray(raw.directories)
  ) {
    throw new Error("AGENTS.md recovery receipt identity is invalid");
  }
  const receipt = raw as unknown as AgentsRecoveryReceipt;
  const privateRoot = path.resolve(run.manifest.harnessDir);
  const publicRoot = run.manifest.publicDir ? path.resolve(run.manifest.publicDir) : undefined;
  const projectConfig = path.resolve(configPaths(cwd).project);
  const allowedRoots = [privateRoot, ...(publicRoot ? [publicRoot] : [])];
  const allowedFiles = new Set([path.resolve(cwd, "AGENTS.md"), projectConfig]);
  for (const predecessor of receipt.predecessors) {
    if (
      !isRecord(predecessor) ||
      typeof predecessor.file !== "string" ||
      typeof predecessor.existed !== "boolean" ||
      (predecessor.mode !== null && (typeof predecessor.mode !== "number" || !Number.isInteger(predecessor.mode))) ||
      (predecessor.bytesBase64 !== null && typeof predecessor.bytesBase64 !== "string") ||
      !isAllowedRecoveryFile(predecessor.file, allowedRoots, allowedFiles)
    ) {
      throw new Error("AGENTS.md recovery receipt predecessor is invalid");
    }
  }
  const allowedDirectories = new Set([
    path.dirname(privateRoot), privateRoot,
    ...(publicRoot ? [publicRoot] : []),
    path.dirname(projectConfig),
  ]);
  for (const directory of receipt.directories) {
    if (!isRecord(directory) || typeof directory.path !== "string" || typeof directory.existed !== "boolean" || !allowedDirectories.has(path.resolve(directory.path))) {
      throw new Error("AGENTS.md recovery receipt directory is invalid");
    }
  }
  return receipt;
}

/** Recover an interrupted AGENTS.md extraction transaction before new work. */
export async function recoverAgentsMdConsolidation(run: ConsolidationRun, cwd: string): Promise<boolean> {
  const preReceiptPath = path.join(run.manifest.runDir, "agents-pre-receipt.json");
  const postReceiptPath = path.join(run.manifest.runDir, "agents-post-receipt.json");
  try {
    const postStat = await fs.lstat(postReceiptPath).catch(() => undefined);
    if (postStat) return false;
    const preStat = await fs.lstat(preReceiptPath);
    if (!preStat.isFile() || preStat.isSymbolicLink()) throw new Error("AGENTS.md recovery receipt is unsafe");
    const receipt = parseRecoveryReceipt(JSON.parse(await fs.readFile(preReceiptPath, "utf8")) as unknown, run, cwd);
    const snapshots: TransactionSnapshot[] = receipt.predecessors.map((entry) => ({
      file: entry.file,
      existed: entry.existed,
      ...(entry.bytesBase64 !== null ? { content: Buffer.from(entry.bytesBase64, "base64") } : {}),
      ...(entry.mode !== null ? { mode: entry.mode } : {}),
    }));
    await restoreTransactionState(snapshots, receipt.directories, []);
    await fs.rm(preReceiptPath, { force: true });
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

function pendingRecoveryRun(raw: unknown, runDir: string, cwd: string): ConsolidationRun {
  if (!isRecord(raw)) throw new Error(`AGENTS.md recovery manifest is invalid: ${runDir}`);
  const expected = resolveMemoryPaths(cwd);
  if (
    typeof raw.runId !== "string" || raw.runId !== path.basename(runDir) ||
    typeof raw.cwd !== "string" || path.resolve(raw.cwd) !== expected.cwd ||
    raw.scopeKey !== expected.scopeKey ||
    typeof raw.scopeDigest !== "string" ||
    raw.harnessDir !== expected.harnessDir ||
    raw.publicDir !== expected.publicDir ||
    raw.runDir !== runDir ||
    typeof raw.snapshotPath !== "string" ||
    typeof raw.snapshotDigest !== "string"
  ) {
    throw new Error(`AGENTS.md recovery manifest identity is invalid: ${runDir}`);
  }
  return { manifest: raw as unknown as ConsolidationRun["manifest"] } as ConsolidationRun;
}

/** Discover and recover orphan pre-receipts from prior interrupted sessions. */
export async function recoverPendingAgentsMdConsolidations(cwd: string): Promise<number> {
  const paths = resolveMemoryPaths(cwd);
  let entries: Array<{ name: string; isDirectory(): boolean; isSymbolicLink(): boolean }>;
  try {
    entries = await fs.readdir(paths.runsDir, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return 0;
    throw error;
  }
  let recovered = 0;
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (!entry.isDirectory() || entry.isSymbolicLink() || !/^run_[A-Za-z0-9_-]+$/.test(entry.name)) continue;
    const runDir = path.join(paths.runsDir, entry.name);
    const prePath = path.join(runDir, "agents-pre-receipt.json");
    const postPath = path.join(runDir, "agents-post-receipt.json");
    if (await fs.lstat(postPath).then(() => true, () => false)) continue;
    const preStat = await fs.lstat(prePath).catch(() => undefined);
    if (!preStat) continue;
    if (!preStat.isFile() || preStat.isSymbolicLink()) throw new Error(`AGENTS.md recovery receipt is unsafe: ${prePath}`);
    const manifestPath = path.join(runDir, "manifest.json");
    const manifestStat = await fs.lstat(manifestPath);
    if (!manifestStat.isFile() || manifestStat.isSymbolicLink()) throw new Error(`AGENTS.md recovery manifest is unsafe: ${manifestPath}`);
    const run = pendingRecoveryRun(JSON.parse(await fs.readFile(manifestPath, "utf8")) as unknown, runDir, cwd);
    if (await recoverAgentsMdConsolidation(run, cwd)) recovered += 1;
  }
  return recovered;
}

const PRIVATE_INDEX_MARKER_RE = /\(\s*harness[\s_-]+only\s*\)/i;
const INDEX_MEMORY_NAME_RE = /[A-Za-z0-9][A-Za-z0-9_-]*\.md\b/i;

async function readPrivateMemoryNames(root: string): Promise<Set<string>> {
  let index: string;
  try {
    index = await fs.readFile(path.join(root, "MEMORY.md"), "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return new Set();
    throw error;
  }
  const privateNames = new Set<string>();
  for (const line of index.split(/\r?\n/)) {
    if (!PRIVATE_INDEX_MARKER_RE.test(line)) continue;
    const name = INDEX_MEMORY_NAME_RE.exec(line)?.[0];
    if (!name || !isMemoryFilename(name)) throw new Error(`Private memory marker has no canonical filename in ${root}`);
    privateNames.add(name.toLowerCase());
  }
  return privateNames;
}

async function memoryNames(root: string): Promise<string[]> {
  try {
    return (await fs.readdir(root)).filter(isMemoryFilename).sort((left, right) => left.localeCompare(right));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

async function writeMemoryIndex(root: string, privateNames: ReadonlySet<string>): Promise<void> {
  const content = await buildMemoryIndexContent(root, new Set(privateNames));
  await writeFileAtomic(path.join(root, "MEMORY.md"), content, 0o600);
}

async function assertMemoryNameAvailable(roots: readonly string[], name: string): Promise<void> {
  const key = name.toLowerCase();
  for (const root of roots) {
    const conflict = (await memoryNames(root)).find((candidate) => candidate.toLowerCase() === key);
    if (conflict) throw new Error(`Memory extraction would overwrite existing memory: ${conflict}`);
  }
}

async function readHarnessConfig(file: string): Promise<Record<string, unknown>> {
  try {
    const parsed = JSON.parse(await fs.readFile(file, "utf8")) as unknown;
    assertHarnessConfigContainers(parsed);
    return parsed;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { rules: [] };
    throw error;
  }
}

function assertSkillRulesAvailable(cwd: string, ops: readonly HarnessOp[], availableSkills: readonly string[]): void {
  const knownSkills = new Set(availableSkills);
  const layers = loadLayers(cwd);
  const incomplete = layers.flatMap((layer) => layer.errors?.length ? layer.errors : layer.stale ? [`${layer.source}: unreadable layer`] : []);
  if (incomplete.length) throw new Error(`Cannot establish skill rule ownership: ${incomplete.join("; ")}`);
  // Use declarations, not only active winners: invalid, disabled, and shadowed
  // IDs are still owned and automatic extraction must never replace them.
  const existing = new Set([
    ...DEFAULT_RULES.map((rule) => rule.id),
    ...layers.flatMap(legacyReservedNames),
    ...layers.flatMap((layer) => (layer.rules ?? []).flatMap((rule) =>
      isRecord(rule) && typeof rule.id === "string" ? [rule.id] : [],
    )),
  ]);
  for (const op of ops) {
    const errors = validateRuleDeclaration(op.rule, knownSkills);
    if (errors.length) throw new Error(`Invalid extracted skill rule: ${errors.join("; ")}`);
    const id = String(op.rule.id);
    if (existing.has(id)) throw new Error(`Skill rule ID already exists and cannot be overwritten: ${id}`);
    const skill = String(op.rule.skill);
    const candidate = mergeLayers([{ source: "extraction", rules: [op.rule] }], knownSkills);
    // Exact-skill routing has deterministic fixtures; this is selector evidence,
    // not proof that a live invocation delivered or followed the instructions.
    const positive = evaluateSkill(candidate, skill);
    const negative = evaluateSkill(candidate, `${skill}-other`);
    if (candidate.errors.length || positive.length !== 1 || positive[0].id !== id || negative.length !== 0) {
      throw new Error(`Extracted skill rule failed its exact-skill selector checks: ${id}`);
    }
    existing.add(id);
  }
}

function mergeSkillRules(base: Record<string, unknown>, ops: readonly HarnessOp[]): Record<string, unknown> {
  assertHarnessConfigContainers(base);
  const rules: unknown[] = Array.isArray(base.rules) ? [...base.rules] : [];
  for (const op of ops) {
    const id = String(op.rule.id);
    if (rules.some((rule) => isRecord(rule) && rule.id === id)) {
      throw new Error(`Skill rule ID already exists and cannot be overwritten: ${id}`);
    }
    rules.push(op.rule);
  }
  return { ...base, rules };
}

function extractedMemoryContent(op: AgentsOp): string {
  const extraction = op.extraction as ExtractionMemory;
  const frontmatter = ["---", `name: ${extraction.memoryName.replace(/\.md$/i, "")}`, `description: ${JSON.stringify(extraction.description)}`, `type: ${extraction.type}`, "---", ""].join("\n");
  return `${frontmatter}${(op.oldText ?? "").trim()}\n`;
}

async function assertProjectLocalTarget(cwd: string, target: string): Promise<void> {
  const projectRoot = await fs.realpath(path.resolve(cwd));
  const resolvedTarget = path.resolve(target);
  const relative = path.relative(projectRoot, resolvedTarget);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Skill rule target escapes the project: ${target}`);
  }
  let current = projectRoot;
  for (const component of relative.split(path.sep).filter(Boolean).slice(0, -1)) {
    current = path.join(current, component);
    try {
      const stat = await fs.lstat(current);
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Skill rule target has an unsafe path component: ${current}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") continue;
      throw error;
    }
  }
  try {
    const stat = await fs.lstat(resolvedTarget);
    if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Skill rule target is not a regular file: ${resolvedTarget}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
}

/** Build and validate a repository-read-only AGENTS.md plan. */
async function planAgentsMdConsolidationPhaseInternal(
  ctx: ExtensionContext,
  state: { active: boolean; generation: number; cancelled: boolean; child?: ChildProcess },
  opts: AgentsMdConsolidationPhaseOptions,
  run: ConsolidationRun,
  generation: number,
): Promise<AgentsMdConsolidationPlanningOutcome> {
  const startedAt = Date.now();
  const durationMs = (): number => Date.now() - startedAt;
  const current = (): boolean => !state.cancelled && generation === state.generation;
  const finalTarget = resolveAgentsTargetFile(opts.cwd, getAgentDir());
  if (!finalTarget.path) {
    notifyPi(ctx.ui, `AGENTS.md consolidation skipped: ${finalTarget.skipReason}`, "info");
    return { outcome: "skipped", durationMs: durationMs(), detail: finalTarget.skipReason };
  }
  const targetPath = finalTarget.path;
  const docBytes = await readRegularFileIfExists(targetPath, MAX_AGENTS_MD_FILE_BYTES);
  if (!docBytes) {
    const detail = "no project AGENTS.md found";
    notifyPi(ctx.ui, "AGENTS.md consolidation: no project AGENTS.md found; nothing to consolidate.", "info");
    return { outcome: "skipped", durationMs: durationMs(), detail };
  }
  const preBytes = docBytes.byteLength;
  const doc = docBytes.toString("utf8");
  const snapshotText = await readSnapshotText(run);
  const cli = resolvePiCli();
  if (!cli) return { outcome: "failed", durationMs: durationMs(), detail: "could not resolve the Pi CLI" };
  const procedure = buildAgentsMdConsolidatorPrompt({
    runId: run.manifest.runId,
    scopeDigest: run.manifest.scopeDigest,
    artifactHash: run.manifest.snapshotDigest,
    snapshotPath: run.manifest.snapshotPath,
    dossierPath: opts.explorationPath ?? "",
    repoRoot: run.manifest.cwd,
    budgetBytes: opts.budgetBytes,
  });
  if (!current()) return { outcome: "cancelled", durationMs: durationMs(), detail: "cancelled before planner start" };
  const taskText = [
    `Task: produce a read-only structured AGENTS.md consolidation plan for the project at ${opts.cwd}.`,
    `- Reason: ${opts.reason}`,
    ...(opts.explorationDigest ? [`- Dossier digest: ${opts.explorationDigest}`] : []),
    `- Registered skill names: ${JSON.stringify(opts.availableSkills ?? [])}`,
    `- Current AGENTS.md (${preBytes} bytes), authoritative for anchoring operations:`,
    "<<<AGENTS.MD>>>",
    doc,
    "<<<END AGENTS.MD>>>",
    "- Target file for every change: the embedded document's path on disk.",
    "- Your final assistant message must be exactly one JSON object.",
    "",
    procedure,
  ].join("\n");

  const taskFile = path.join(run.manifest.runDir, "agents-task.md");
  await fs.writeFile(taskFile, taskText, { mode: 0o600 });
  const child = spawnPiChild(
    cli.command,
    [...cli.args, ...minimalPiWorkerArgs(["read", "grep", "find", "ls"]), `@${taskFile}`],
    { cwd: opts.cwd, stdio: ["ignore", "pipe", "pipe"] },
  );
  if (!current()) {
    await terminateConsolidationChild(child, 5_000);
    return { outcome: "cancelled", durationMs: durationMs(), detail: "cancelled after planner start" };
  }
  state.child = child;

  const configuredTimeout = opts.timeoutMs ?? AGENTS_PHASE_TIMEOUT_MS;
  const timeoutMs = Number.isFinite(configuredTimeout)
    ? Math.min(AGENTS_PHASE_TIMEOUT_MS, Math.max(1, configuredTimeout))
    : AGENTS_PHASE_TIMEOUT_MS;
  const result = await new Promise<{ ok: true; stdout: string; stderr: string } | { ok: false; detail: string }>((resolve) => {
    let stdout = "";
    let stderr = "";
    let done = false;
    const finish = (value: { ok: true; stdout: string; stderr: string } | { ok: false; detail: string }) => {
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
      void terminateAndFinish("AGENTS.md planner timed out");
    }, timeoutMs);
    timer.unref?.();
    child.stdout?.on("data", (chunk: Buffer) => {
      if (done) return;
      stdout += chunk.toString("utf-8");
      if (Buffer.byteLength(stdout, "utf8") > MAX_STDOUT_BYTES) {
        void terminateAndFinish(`child stdout exceeded ${MAX_STDOUT_BYTES} bytes`);
      }
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      if (!done) stderr = (stderr + chunk.toString("utf-8")).slice(-64_000);
    });
    child.on("error", (err) => finish({ ok: false, detail: err.message }));
    child.on("close", (code) => {
      if (done) return;
      if (code !== 0) finish({ ok: false, detail: stderr.trim() || `exit code ${code}` });
      else finish({ ok: true, stdout, stderr: stderr.trim() });
    });
  });
  if (!current()) return { outcome: "cancelled", durationMs: durationMs(), detail: "cancelled while planner was running" };
  if (!result.ok) {
    await writeFileAtomic(path.join(run.manifest.runDir, "agents-error.txt"), result.detail.slice(-8_000)).catch(() => {});
    notifyPi(ctx.ui, `AGENTS.md consolidation finished without changes: ${result.detail.slice(-300)}`, "warning");
    return { outcome: "failed", durationMs: durationMs(), detail: result.detail };
  }

  const { usage } = parsePiWorkerOutput(result.stdout);
  const extracted = extractChildPlan(result.stdout, {
    expectedIdentity: { runId: run.manifest.runId, scopeDigest: run.manifest.scopeDigest, artifactHash: run.manifest.snapshotDigest },
    maxOutputBytes: MAX_STDOUT_BYTES,
    maxLines: MAX_JSONL_LINES,
    maxLineBytes: MAX_JSONL_LINE_BYTES,
    maxPlanBytes: MAX_PLAN_BYTES,
  });
  if (!extracted.ok) {
    await writeFileAtomic(path.join(run.manifest.runDir, "agents-error.txt"), extracted.error.slice(-8_000)).catch(() => {});
    notifyPi(ctx.ui, `AGENTS.md consolidation finished without changes: ${extracted.error.slice(-300)}`, "warning");
    return { outcome: "failed", durationMs: durationMs(), usage, detail: extracted.error };
  }
  const rawPlan = extracted.plan;
  const shape = validateAgentsMdPlan(rawPlan);
  if (!shape.ok) {
    const detail = shape.errors.join("; ");
    notifyPi(ctx.ui, `AGENTS.md plan rejected: ${detail.slice(-300)}`, "warning");
    return { outcome: "rejected", durationMs: durationMs(), usage, detail };
  }
  const quoteCheck = verifyPlanQuotes(shape.operations, snapshotText);
  const operations = quoteCheck.operations.filter((op) => addUnitEvidenceSufficient(op));
  const droppedCount = quoteCheck.dropped.length + quoteCheck.operations.length - operations.length;
  if (operations.length === 0) {
    await writeFileAtomic(path.join(run.manifest.runDir, "agents-noop.txt"), "verified no-op\n").catch(() => {});
    const detail = droppedCount > 0 ? `${droppedCount} operation(s) failed evidence gates` : "planner proposed no operations";
    notifyPi(ctx.ui, `AGENTS.md consolidation: verified no-op${droppedCount > 0 ? ` (${detail})` : ""}.`, "info");
    return { outcome: "noop", durationMs: durationMs(), usage, detail };
  }
  const simulated = simulateAgentsOps(doc, operations);
  if (!simulated.ok) {
    notifyPi(ctx.ui, `AGENTS.md plan rejected during simulation: ${simulated.error.slice(-300)}`, "warning");
    return { outcome: "rejected", durationMs: durationMs(), usage, detail: simulated.error };
  }
  if (!budgetAllows(preBytes, Buffer.byteLength(simulated.doc, "utf8"), opts.budgetBytes)) {
    const detail = `post-edit size exceeds the ${opts.budgetBytes}-byte budget and is not zero-sum`;
    notifyPi(ctx.ui, `AGENTS.md plan rejected: ${detail}.`, "warning");
    return { outcome: "rejected", durationMs: durationMs(), usage, detail };
  }
  const planning = { run, targetPath, docBytes, doc, preBytes, snapshotText, rawPlan, operations, droppedCount, usage, durationMs: durationMs() };
  return { outcome: "planned", durationMs: planning.durationMs, usage, planning };
}

export async function planAgentsMdConsolidationPhase(
  ctx: ExtensionContext,
  state: { active: boolean; generation: number; cancelled: boolean; child?: ChildProcess },
  opts: AgentsMdConsolidationPhaseOptions,
  run: ConsolidationRun,
  generation: number,
): Promise<AgentsMdConsolidationPlanningOutcome> {
  const startedAt = Date.now();
  try {
    return await planAgentsMdConsolidationPhaseInternal(ctx, state, opts, run, generation);
  } catch (error) {
    const detail = (error as Error).message;
    notifyPi(ctx.ui, `AGENTS.md consolidation finished without changes: ${detail.slice(-300)}`, "warning");
    return { outcome: state.cancelled || generation !== state.generation ? "cancelled" : "failed", durationMs: Date.now() - startedAt, detail };
  }
}

/** Revalidate and apply a previously planned result as one rollback unit. */
export async function applyAgentsMdConsolidationPlan(
  ctx: ExtensionContext,
  state: { active: boolean; generation: number; cancelled: boolean; child?: ChildProcess },
  opts: AgentsMdConsolidationPhaseOptions,
  planning: AgentsMdConsolidationPlanResult,
  generation: number,
  isActive?: () => boolean,
): Promise<AgentsMdConsolidationApplyResult> {
  const current = (): boolean => !state.cancelled && generation === state.generation && (isActive?.() ?? true);
  if (!current()) return { outcome: "cancelled", applied: 0, extractions: [], detail: "cancelled before apply" };
  const { run, targetPath, docBytes, doc, preBytes, rawPlan } = planning;
  const shape = validateAgentsMdPlan({ kind: AGENTS_PLAN_KIND, operations: planning.operations });
  if (!shape.ok) return { outcome: "failed", applied: 0, extractions: [], detail: shape.errors.join("; ") };
  const quoteCheck = verifyPlanQuotes(shape.operations, planning.snapshotText);
  if (quoteCheck.dropped.length || quoteCheck.operations.some((op) => !addUnitEvidenceSufficient(op))) {
    return { outcome: "failed", applied: 0, extractions: [], detail: "AGENTS.md plan failed its apply evidence gates" };
  }
  const operations = quoteCheck.operations;
  const currentDocBytes = await readRegularFileIfExists(targetPath, MAX_AGENTS_MD_FILE_BYTES);
  if (!currentDocBytes || !currentDocBytes.equals(docBytes)) {
    const detail = "AGENTS.md changed after planning";
    notifyPi(ctx.ui, `${detail}; nothing was written.`, "warning");
    return { outcome: "failed", applied: 0, extractions: [], detail };
  }
  const resimulated = simulateAgentsOps(doc, operations);
  if (!resimulated.ok || !budgetAllows(preBytes, Buffer.byteLength(resimulated.doc, "utf8"), opts.budgetBytes)) {
    const detail = resimulated.ok ? "AGENTS.md plan exceeds its apply budget" : resimulated.error;
    notifyPi(ctx.ui, `AGENTS.md plan failed re-validation: ${detail}`, "warning");
    return { outcome: "failed", applied: 0, extractions: [], detail };
  }
  if (operations.length === 0) return { outcome: "noop", applied: 0, extractions: [] };

  const memoryOps = operations.filter((op): op is AgentsOp & { extraction: ExtractionMemory } => op.op === "extractUnit" && op.extraction?.target === "memory");
  const skillOps: HarnessOp[] = operations.flatMap((op) =>
    op.op === "extractUnit" && op.extraction?.target === "skillRule"
      ? [{ op: "addRule", rule: { id: op.extraction.ruleId, skill: op.extraction.skillName, instructions: op.extraction.instructions } }]
      : [],
  );
  const privateRoot = run.manifest.harnessDir;
  const publicRoot = run.manifest.publicDir;
  const harnessConfig = configPaths(opts.cwd).project;
  const preReceiptPath = path.join(run.manifest.runDir, "agents-pre-receipt.json");
  const postReceiptPath = path.join(run.manifest.runDir, "agents-post-receipt.json");
  const files = new Set([targetPath, preReceiptPath, postReceiptPath]);
  const directoryPaths = [
    ...(memoryOps.length > 0 ? [path.dirname(privateRoot), privateRoot] : []),
    ...(memoryOps.length > 0 && publicRoot ? [publicRoot] : []),
    ...(skillOps.length > 0 ? [path.dirname(harnessConfig)] : []),
  ];
  let privateNames: Set<string>;
  let snapshots: TransactionSnapshot[];
  let directories: DirectorySnapshot[];
  const memoryNamesInPlan = new Set<string>();
  for (const op of memoryOps) {
    const key = op.extraction.memoryName.toLowerCase();
    if (memoryNamesInPlan.has(key)) {
      const detail = `Duplicate memory extraction name in one plan: ${op.extraction.memoryName}`;
      notifyPi(ctx.ui, `AGENTS.md consolidation failed: ${detail}`, "warning");
      return { outcome: "failed", applied: 0, extractions: [], detail };
    }
    memoryNamesInPlan.add(key);
  }
  const stableRoots: StableMemoryRoot[] = [];
  try {
    directories = await Promise.all([...new Set(directoryPaths)].map(captureDirectory));
    privateNames = await readPrivateMemoryNames(privateRoot);
    for (const op of memoryOps) {
      await assertMemoryNameAvailable([privateRoot, ...(publicRoot ? [publicRoot] : [])], op.extraction.memoryName);
      files.add(path.join(privateRoot, op.extraction.memoryName));
      if (publicRoot) files.add(path.join(publicRoot, op.extraction.memoryName));
    }
    if (memoryOps.length > 0) {
      files.add(path.join(privateRoot, "MEMORY.md"));
      if (publicRoot) files.add(path.join(publicRoot, "MEMORY.md"));
    }
    if (skillOps.length > 0) {
      await assertProjectLocalTarget(opts.cwd, harnessConfig);
      await readHarnessConfig(harnessConfig);
      assertSkillRulesAvailable(opts.cwd, skillOps, opts.availableSkills ?? []);
      files.add(harnessConfig);
    }
    snapshots = await Promise.all([...files].map(captureTransactionFile));
    if (memoryOps.length > 0) {
      stableRoots.push(await openStableMemoryRoot(privateRoot));
      if (publicRoot) stableRoots.push(await openStableMemoryRoot(publicRoot));
    }
    await opts.transactionHook?.("after-roots-opened");
  } catch (error) {
    await closeStableRoots(stableRoots);
    const detail = (error as Error).message;
    notifyPi(ctx.ui, `AGENTS.md consolidation failed: ${detail.slice(-300)}`, "warning");
    return { outcome: "failed", applied: 0, extractions: [], detail };
  }
  const extractionNotes: string[] = [];
  let transactionStarted = false;
  try {
    if (!current()) throw new Error("__CANCELLED__:before artifacts");
    await opts.transactionHook?.("before-artifacts");
    for (const root of stableRoots) await assertStableMemoryRoot(root);

    if (skillOps.length > 0) {
      await assertProjectLocalTarget(opts.cwd, harnessConfig);
      mergeSkillRules(await readHarnessConfig(harnessConfig), skillOps);
      assertSkillRulesAvailable(opts.cwd, skillOps, opts.availableSkills ?? []);
    }
    const planDigest = sha256Digest(JSON.stringify(rawPlan));
    const preReceipt = {
      kind: "agents-md-consolidation-receipt",
      phase: "pre",
      runId: run.manifest.runId,
      scopeDigest: run.manifest.scopeDigest,
      snapshotDigest: run.manifest.snapshotDigest,
      targetFile: targetPath,
      budgetBytes: opts.budgetBytes,
      planDigest,
      predecessors: snapshots
        .filter((snapshot) => snapshot.file !== preReceiptPath && snapshot.file !== postReceiptPath)
        .map((snapshot) => ({
          file: snapshot.file,
          existed: snapshot.existed,
          mode: snapshot.mode ?? null,
          bytesBase64: snapshot.content?.toString("base64") ?? null,
        })),
      directories,
    };
    transactionStarted = true;
    await writeFileAtomic(preReceiptPath, `${JSON.stringify(preReceipt, null, 2)}\n`);

    for (const op of memoryOps) {
      for (const root of stableRoots) await assertStableMemoryRoot(root);
      const content = extractedMemoryContent(op);
      await writeFileAtomic(path.join(privateRoot, op.extraction.memoryName), content, 0o600);
      for (const root of stableRoots) await assertStableMemoryRoot(root);
      const isPrivate = op.extraction.classification === "private";
      if (isPrivate) privateNames.add(op.extraction.memoryName.toLowerCase());
      else {
        privateNames.delete(op.extraction.memoryName.toLowerCase());
        if (publicRoot) await writeFileAtomic(path.join(publicRoot, op.extraction.memoryName), content, 0o600);
      }
      for (const root of stableRoots) await assertStableMemoryRoot(root);
      extractionNotes.push(`memory:${op.extraction.memoryName}`);
    }
    if (memoryOps.length > 0) {
      await writeMemoryIndex(privateRoot, privateNames);
      if (publicRoot) await writeMemoryIndex(publicRoot, new Set());
      for (const root of stableRoots) await assertStableMemoryRoot(root);
    }
    if (skillOps.length > 0) {
      await assertProjectLocalTarget(opts.cwd, harnessConfig);
      const base = await readHarnessConfig(harnessConfig);
      assertSkillRulesAvailable(opts.cwd, skillOps, opts.availableSkills ?? []);
      await writeFileAtomic(harnessConfig, `${JSON.stringify(mergeSkillRules(base, skillOps), null, 2)}\n`, 0o600);
      await assertProjectLocalTarget(opts.cwd, harnessConfig);
      extractionNotes.push(...skillOps.map((op) => `addRule:${op.rule.id}`));
    }
    if (opts.transactionFault === "after-artifacts") throw new Error("Injected transaction failure after artifacts");
    if (!current()) throw new Error("__CANCELLED__:after artifacts");

    const stat = await fs.lstat(targetPath);
    const mode = stat.isFile() && !stat.isSymbolicLink() ? stat.mode & 0o777 : 0o644;
    await writeFileAtomic(targetPath, Buffer.from(resimulated.doc, "utf8"), mode);
    if (opts.transactionFault === "after-agents") throw new Error("Injected transaction failure after AGENTS.md");
    if (!current()) throw new Error("__CANCELLED__:after AGENTS.md");

    const afterBytes = Buffer.from(resimulated.doc, "utf8");
    const receipt = {
      kind: "agents-md-consolidation-receipt",
      phase: "post",
      runId: run.manifest.runId,
      scopeDigest: run.manifest.scopeDigest,
      snapshotDigest: run.manifest.snapshotDigest,
      targetFile: targetPath,
      budgetBytes: opts.budgetBytes,
      bytesBefore: preBytes,
      bytesAfter: afterBytes.byteLength,
      digestEncoding: "base64 of raw file bytes",
      digestBefore: docBytes.toString("base64"),
      digestAfter: afterBytes.toString("base64"),
      sha256Before: sha256Digest(docBytes),
      sha256After: sha256Digest(afterBytes),
      applied: operations.map((op) => ({ op: op.op, fingerprint: fingerprintOp(op) })),
      rejected: [],
      extractions: extractionNotes,
      planDigest,
      preReceiptFile: preReceiptPath,
    };
    if (opts.transactionFault === "before-receipt") throw new Error("Injected transaction failure before receipt");
    if (!current()) throw new Error("__CANCELLED__:before receipt");
    await writeFileAtomic(postReceiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
    if (!current()) throw new Error("__CANCELLED__:after receipt");

    const parts = [`${operations.length} edit(s) applied`];
    if (extractionNotes.length > 0) parts.push(`extractions: ${extractionNotes.join(", ")}`);
    notifyPi(ctx.ui, `AGENTS.md consolidated: ${parts.join(" · ")} (${path.basename(targetPath)}).`, "info");
    return { outcome: "applied", applied: operations.length, extractions: extractionNotes };
  } catch (error) {
    const message = (error as Error).message;
    try {
      if (transactionStarted) await restoreTransactionState(snapshots, directories, stableRoots);
      await closeStableRoots(stableRoots);
    } catch (rollbackError) {
      const detail = `${message}; rollback failed: ${(rollbackError as Error).message}`;
      notifyPi(ctx.ui, `AGENTS.md consolidation failed: ${detail.slice(-300)}`, "warning");
      return { outcome: "failed", applied: 0, extractions: [], detail };
    }
    const cancelled = message.startsWith("__CANCELLED__:");
    const detail = cancelled ? message.slice("__CANCELLED__:".length) : message;
    notifyPi(ctx.ui, `AGENTS.md consolidation ${cancelled ? "cancelled" : "failed"}: ${detail.slice(-300)}`, "warning");
    return { outcome: cancelled ? "cancelled" : "failed", applied: 0, extractions: [], detail };
  } finally {
    await closeStableRoots(stableRoots);
  }
}

/** Third pipeline phase. Planning is read-only; validated operations apply without an interactive prompt. */
export async function runAgentsMdConsolidationPhase(
  ctx: ExtensionContext,
  state: { active: boolean; generation: number; cancelled: boolean; child?: ChildProcess },
  opts: AgentsMdConsolidationPhaseOptions,
): Promise<void> {
  if (state.active || opts.disabled) return;
  state.active = true;
  const generation = state.generation + 1;
  state.generation = generation;
  state.cancelled = false;
  const current = (): boolean => !state.cancelled && generation === state.generation;

  let run: ConsolidationRun;
  try {
    run = await createConsolidationRun(ctx, opts.cwd, false);
    if (!current()) {
      await releaseConsolidationRun(run);
      state.active = false;
      return;
    }
  } catch (err) {
    state.active = false;
    if (current()) notifyPi(ctx.ui, `AGENTS.md consolidation skipped: ${(err as Error).message}`, "warning");
    return;
  }

  try {
    const planned = await planAgentsMdConsolidationPhase(ctx, state, opts, run, generation);
    if (planned.outcome === "planned" && current()) await applyAgentsMdConsolidationPlan(ctx, state, opts, planned.planning, generation);
  } catch (err) {
    if (current()) notifyPi(ctx.ui, `AGENTS.md consolidation failed: ${(err as Error).message.slice(-300)}`, "warning");
  } finally {
    const owned = current();
    try {
      if (owned && state.child) {
        const child = state.child;
        state.child = undefined;
        if (!child.killed) void terminateConsolidationChild(child, 5_000).catch(() => {});
      }
    } finally {
      await releaseConsolidationRun(run, { keepArtifacts: owned }).catch(() => {});
      if (owned) state.active = false;
    }
  }
}

/**
 * The observation record.
 *
 * An observation is a *judgment* record, not a *content* record. It carries
 * the run's context digest, the model that answered, each verdict and its
 * confidence, the selector's own answer, and whether the two agreed. It carries
 * no request text and no tool output — that is what makes it safe to persist at
 * all, and it is why the log cannot be replayed to reconstruct what was asked.
 *
 * It lives under the private agent directory, per project, outside both Memory
 * roots, and never in the project-shared Memory surface.
 */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { resolveMemoryPaths } from "./memory-paths";

/** Bounded so a long-lived install cannot grow an unbounded private file. */
export const MAX_OBSERVATION_LOG_BYTES = 4 * 1024 * 1024;
const MAX_OBSERVATION_RECORD_BYTES = 64 * 1024;
const NEWLINE = 0x0a;
const OBSERVATION_DIR = "judgment";
const OBSERVATION_FILE = "observations.jsonl";

export interface JudgmentObservation {
  version: 1;
  contextDigest: string;
  /** The versioned model that answered, or `null` when nothing answered. */
  model: string | null;
  outcome: "observed" | "failed" | "cancelled";
  reason?: string;
  judged: boolean;
  /** Flattened verdicts keyed by question id. Values only — never content. */
  values: Record<string, number | string>;
  /** Only primitives that carry one contribute here. */
  confidences: Record<string, number>;
  /** Which decision surface produced this record. */
  phase: "selector" | "proposals" | "operations";
  /** The selector's decision, which is the one that reached the parent.
   *  Empty for proposal observations, where the parent had no competing choice. */
  selectorSelected: string[];
  selectorRouted: { memory: boolean; harness: boolean; agents: boolean };
  /** What a reporting threshold would have chosen. Never authoritative. */
  judgmentSelected: string[];
  agrees: boolean;
  /** Proposal observations only. How many proposals the plan carried. */
  proposed?: number;
  /** Proposal observations only. Ids a reporting level would have kept. */
  kept?: string[];
  /** Proposal observations only. Ids the duplicate question matched. */
  duplicates?: string[];
  /** Plan-surface observations only. Which plan was judged. */
  surface?: string;
  /** Plan-surface observations only. How many operations the plan carried. */
  operations?: number;
  /** Plan-surface observations only. Closed-set answers keyed `axis:id`. */
  verdictsByAxis?: Record<string, string>;
  usage?: { inputTokens?: number; outputTokens?: number };
}

/**
 * Where observations live.
 *
 * Beneath the private agent directory, per project, and deliberately *outside*
 * both Memory roots. A Memory root admits only regular `.md` children, so a
 * `.jsonl` beside them fails consolidation's privacy validation outright and
 * aborts the run. That is a hard rule of the Memory contract, not a style
 * preference, and it is the reason this is not simply written next to Memory.
 */
export function judgmentObservationFile(cwd: string, agentDir = getAgentDir()): string {
  const { agentDir: root, scopeKey } = resolveMemoryPaths(cwd, agentDir);
  return path.join(root, OBSERVATION_DIR, scopeKey, OBSERVATION_FILE);
}

/**
 * Keep the log within its cap by dropping the oldest complete lines.
 *
 * The incoming record is reserved, not ignored: rotating to exactly the cap and
 * then appending would leave the file over it. Retention walks byte offsets
 * once. Rebuilding the retained text per candidate line made a full log cost
 * seconds of CPU on every subsequent append, which is the sort of cost that
 * turns a background observer into a stall.
 *
 * A record larger than the whole cap is left alone rather than emptying the log
 * to make room for something that will not fit anyway.
 */
function rotateIfNeeded(file: string, reserveBytes: number): void {
  let size: number;
  try {
    size = fs.statSync(file).size;
  } catch {
    return;
  }
  const target = MAX_OBSERVATION_LOG_BYTES - reserveBytes;
  if (size <= target) return;
  let raw: Buffer;
  try {
    raw = fs.readFileSync(file);
  } catch {
    return;
  }
  let start = 0;
  while (raw.length - start > target) {
    const newline = raw.indexOf(NEWLINE, start);
    if (newline === -1) return;
    start = newline + 1;
  }
  if (start === 0) return;
  const temporary = `${file}.${process.pid}.rotate.tmp`;
  try {
    fs.writeFileSync(temporary, raw.subarray(start), { mode: 0o600 });
    fs.renameSync(temporary, file);
  } catch {
    try {
      fs.unlinkSync(temporary);
    } catch {
      // The temporary file may never have been created.
    }
  }
}

/** Append one observation. Returns false rather than throwing: a record that
 *  cannot be written is a lost measurement, never a failed run. */
export function appendJudgmentObservation(
  cwd: string,
  observation: JudgmentObservation,
  agentDir = getAgentDir(),
): boolean {
  const file = judgmentObservationFile(cwd, agentDir);
  const line = `${JSON.stringify(observation)}\n`;
  if (Buffer.byteLength(line, "utf-8") > MAX_OBSERVATION_RECORD_BYTES) return false;
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    rotateIfNeeded(file, Buffer.byteLength(line, "utf-8"));
    fs.appendFileSync(file, line, { encoding: "utf-8", mode: 0o600 });
    return true;
  } catch {
    return false;
  }
}

/** Read complete records for the promotion report. */
export function readJudgmentObservations(
  cwd: string,
  agentDir = getAgentDir(),
): { records: JudgmentObservation[]; malformed: number } {
  let raw: string;
  try {
    raw = fs.readFileSync(judgmentObservationFile(cwd, agentDir), "utf-8");
  } catch {
    return { records: [], malformed: 0 };
  }
  const records: JudgmentObservation[] = [];
  let malformed = 0;
  for (const line of raw.split("\n")) {
    if (!line) continue;
    try {
      const value = JSON.parse(line) as JudgmentObservation;
      if (value && value.version === 1) records.push(value);
      else malformed += 1;
    } catch {
      malformed += 1;
    }
  }
  return { records, malformed };
}

export interface PromotionReport {
  observations: number;
  /** Runs that produced answers, as opposed to failing or being cancelled. */
  observed: number;
  /** Judged runs whose reporting selection matched the selector's. */
  agreementRate: number | null;
  /** Proposals judged on generality, split at the reporting cut. A distribution
   *  rather than a single verdict, so one threshold cannot imply more than the
   *  data supports. */
  proposalsJudged: number;
  reusable: number;
  oneOff: number;
  /** Runs that produced answers at all. */
  coverage: number | null;
  cancelled: number;
  failed: number;
  byReason: Record<string, number>;
  malformedRecords: number;
  /** A report proposes no threshold. Choosing one is a human decision. */
  threshold: null;
}

/**
 * Summarize what shadow runs have measured. It deliberately reports rates and
 * stops there: a threshold chosen here would be a guess wearing a number's
 * clothes, and the whole point of shadow mode is to replace the guess.
 */
export function promotionReport(cwd: string, agentDir = getAgentDir()): PromotionReport {
  const { records, malformed } = readJudgmentObservations(cwd, agentDir);
  const judged = records.filter((record) => record.judged);
  const agreed = judged.filter((record) => record.agrees).length;
  const generality = records
    .flatMap((record) => Object.entries(record.values))
    .filter(([id, value]) => id.startsWith("general::") && typeof value === "number")
    .map(([, value]) => value as number);
  const byReason: Record<string, number> = {};
  for (const record of records) {
    if (record.reason) byReason[record.reason] = (byReason[record.reason] ?? 0) + 1;
  }
  return {
    observations: records.length,
    observed: judged.length,
    agreementRate: judged.length ? Number((agreed / judged.length).toFixed(4)) : null,
    proposalsJudged: generality.length,
    reusable: generality.filter((value) => value >= 1).length,
    oneOff: generality.filter((value) => value < 1).length,
    coverage: records.length ? Number((judged.length / records.length).toFixed(4)) : null,
    cancelled: records.filter((record) => record.outcome === "cancelled").length,
    failed: records.filter((record) => record.outcome === "failed").length,
    byReason,
    malformedRecords: malformed,
    threshold: null,
  };
}

// ── Promotion gate ──────────────────────────────────────────────────────

export interface SurfaceEligibility {
  surface: string;
  /** Whether authoritative behavior is implemented for it at all. */
  implemented: boolean;
  /** Whether the configuration currently asks for it. */
  requested: boolean;
  observations: number;
  /** Proposals the parent applied that Judgment would have dropped. */
  wouldDrop: number;
  proposed: number;
  /** `null` until enough data exists to say anything. */
  dropRate: number | null;
  /** A statement about the measurement, never a threshold. */
  verdict: "unmeasured" | "not enough data" | "not implemented" | "measured";
  /** The number a human would weigh. Never proposed as acceptable. */
  signal: string;
}

export interface PromotionGate {
  surfaces: SurfaceEligibility[];
  threshold: null;
  note: string;
}

/**
 * What shadow mode has actually measured, per surface.
 *
 * This proposes no threshold and flips no switch. The number that matters for
 * promotion is not accuracy but **how much real knowledge a wrong judgment would
 * cost** — for proposals, the share of parent-applied proposals Judgment would
 * have dropped. A report that offered a "recommended" bound would be a guess
 * wearing a number's clothes, which is the whole thing this design avoids.
 */
export function promotionGate(cwd: string, agentDir = getAgentDir()): PromotionGate {
  const { records } = readJudgmentObservations(cwd, agentDir);
  const surfaces: SurfaceEligibility[] = [];
  for (const surface of ["selector", "proposals", "memory-operations", "harness-operations", "agents-operations"]) {
    const judged = records.filter((record) => record.judged && record.surface === surface);
    const proposed = judged
      .filter((record) => record.phase === "proposals")
      .reduce((total, record) => total + Number(record.proposed ?? 0), 0);
    // A proposal the parent wrote that Judgment would not have kept. This is the
    // cost of a wrong judgment, not a disagreement rate.
    const wouldDrop = judged
      .filter((record) => record.phase === "proposals")
      .reduce((total, record) => total + Math.max(0, Number(record.proposed ?? 0) - (record.kept?.length ?? 0)), 0);
    const implemented = surface === "proposals";
    const dropRate = proposed > 0 ? Number((wouldDrop / proposed).toFixed(4)) : null;
    surfaces.push({
      surface,
      implemented,
      requested: false,
      observations: judged.length,
      proposed,
      wouldDrop,
      dropRate,
      verdict: !implemented
        ? "not implemented"
        : proposed === 0
          ? "unmeasured"
          : judged.length < 10
            ? "not enough data"
            : "measured",
      signal: implemented
        ? `${judged.length} judged run(s); ${wouldDrop} of ${proposed} applied proposal(s) would have been dropped`
        : `${judged.length} judged run(s); authoritative behavior is not implemented for this surface`,
    });
  }
  return {
    surfaces,
    threshold: null,
    note: "A gate reports what was measured. Choosing what is acceptable is a human decision, and no number here is a recommendation.",
  };
}

/**
 * Making a shadow surface visible.
 *
 * The whole point of shadow mode is to replace a guessed threshold with a
 * measured one, and that is only possible if the measurement can be read and
 * the fact that it is running can be seen. A report reachable only from a test
 * is a premise failure, not an omission.
 *
 * Two surfaces, both read-only. `/memory judgment` reports what has been
 * measured; a bounded entry row records that one observation happened. Neither
 * is ever authoritative, and neither proposes a threshold.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { keyHint, ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldLine, safeDisplayText } from "@fradser/pi-kit";
import { resolveJudgmentConfig, DEFAULT_JUDGMENT_MODEL } from "./judgment-config";
import { promotionGate, promotionReport, readJudgmentObservations } from "./judgment-observations";
import type { JudgmentReceiptSummary } from "./learning-efficiency";
import type { MemoryProposalObservation } from "./judgment-shadow";

/** Geometry bound once: every row shares hint and wrapping. */
const judgmentRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});

export const JUDGMENT_OBSERVATION_ENTRY = "judgment-observation";

export interface JudgmentObservationEntry {
  model: string | null;
  outcome: "observed" | "failed" | "cancelled";
  agrees: boolean;
  /** The rate so far, or `null` before anything has been measured. */
  agreementRate: number | null;
  reason?: string;
  /** Present only for Memory-plan proposal observations. */
  phase?: "proposals";
  summary?: string;
}

function percent(rate: number | null): string {
  return rate === null ? "not yet measured" : `${Math.round(rate * 100)}%`;
}

/**
 * Render the report.
 *
 * An unmeasured rate is "not yet measured", never `0%`: a zero would read as
 * "the two surfaces never agree", which is a claim nobody has evidence for.
 * The report never proposes a threshold — choosing one is a human decision
 * informed by this output, and a report that offered one would be a guess
 * wearing a number's clothes.
 */
export function judgmentReportLines(cwd: string, agentDir?: string): string[] {
  const config = resolveJudgmentConfig(agentDir ? { agentDir } : {});
  const report = promotionReport(cwd, agentDir);
  const models = [...new Set(
    readJudgmentObservations(cwd, agentDir).records
      .map((record) => record.model)
      .filter((model): model is string => typeof model === "string"),
  )];
  const lines: string[] = [];
  lines.push(
    config.active
      ? `Judgment: active (${config.model}). It observes; the selector still decides.`
      : `Judgment: inactive — ${config.reason ?? "not configured"}.`,
  );
  if (report.observations === 0) {
    lines.push("Nothing has been measured yet. Shadow mode records one observation per settled task.");
    return lines;
  }
  lines.push(`Observations: ${report.observations} · judged ${report.observed ?? 0} · coverage ${percent(report.coverage)}`);
  lines.push(`Agreement with the selector: ${percent(report.agreementRate)}`);
  if (models.length) lines.push(`Answering model: ${models.join(", ")}`);
  if (report.failed || report.cancelled) {
    const reasons = Object.entries(report.byReason).map(([reason, count]) => `${reason} (${count})`);
    lines.push(`Not answered: ${report.failed} failed, ${report.cancelled} cancelled${reasons.length ? ` — ${reasons.join("; ")}` : ""}`);
  }
  if (report.malformedRecords) lines.push(`Malformed records skipped: ${report.malformedRecords}`);
  lines.push(
    report.agreementRate === null
      ? "No threshold is proposed. Once enough observations accumulate, read this rate and choose one yourself."
      : `No threshold is proposed. Read this rate, then decide whether Judgment should ever become authoritative.`,
  );
  return lines;
}

/** Register the bounded row that shows shadow mode is running. */
export function registerJudgmentObservability(pi: ExtensionAPI): void {
  pi.registerEntryRenderer(JUDGMENT_OBSERVATION_ENTRY, (entry, { expanded }, theme) => {
    const details = entry.data as JudgmentObservationEntry | undefined;
    const base = !details
      ? "judgment observed"
      : details.outcome === "observed"
        ? details.agrees
          ? "judgment agrees"
          : "judgment differs"
        : details.outcome === "cancelled"
          ? "judgment cancelled"
          : "judgment unavailable";
    const label = details?.phase === "proposals"
      ? base === "judgment agrees"
        ? "proposals reviewed"
        : base === "judgment differs"
          ? "proposals narrowed"
          : base
      : base;
    const subject = details?.reason
      ? safeDisplayText(details.reason)
      : details?.summary
        ? safeDisplayText(details.summary)
        : details?.model
          ? `observed by ${safeDisplayText(details.model)}`
          : "shadow observation";
    return judgmentRows.message(() => eventToolLifecycle("judgment", subject, {
      label,
      details: [
        ...(details?.agreementRate === null || details?.agreementRate === undefined
          ? []
          : [fieldLine("agreement", percent(details.agreementRate))]),
      ],
    }))({ content: "", details }, { expanded }, theme);
  });
}

/** Summarize a completed observation for the transcript row. */
export function judgmentEntryFor(
  summary: { model: string | null; outcome: JudgmentObservationEntry["outcome"]; agrees: boolean },
  cwd: string,
  agentDir?: string,
): JudgmentObservationEntry {
  return {
    ...summary,
    // Recomputed rather than carried: the row shows the rate as of now, so
    // several rows in one transcript never disagree with each other.
    agreementRate: promotionReport(cwd, agentDir).agreementRate,
  };
}

/**
 * Summarize a proposal observation for the transcript row. The row reports what
 * a decision surface would have kept, never what the parent kept — those are
 * the same list today, and they must not be conflated.
 */
export function judgmentProposalEntryFor(observation: MemoryProposalObservation): JudgmentObservationEntry {
  const duplicateCount = observation.duplicates.length;
  return {
    model: observation.model,
    outcome: observation.outcome,
    // The parent applies every proposal, so there is no competing decision to
    // agree or differ from; "all kept" is a true statement, not a verdict.
    agrees: observation.kept.length === observation.proposed,
    agreementRate: null,
    phase: "proposals",
    summary: `${observation.proposed} proposed · ${observation.kept.length} would keep${duplicateCount ? ` · ${duplicateCount} duplicate` : ""}`,
  };
}

export { DEFAULT_JUDGMENT_MODEL };

/** The compact measurement `/consolidate` reports alongside what a run did. */
export function judgmentReceiptSummary(cwd: string, agentDir?: string): JudgmentReceiptSummary | undefined {
  const config = resolveJudgmentConfig(agentDir ? { agentDir } : {});
  if (!config.active) return undefined;
  const report = promotionReport(cwd, agentDir);
  const { records } = readJudgmentObservations(cwd, agentDir);
  const models = [...new Set(records.map((r) => r.model).filter((m): m is string => typeof m === "string"))];
  return {
    model: models[models.length - 1] ?? config.model,
    gate: promotionGateLine(cwd, agentDir),
    observations: report.observations,
    agreementRate: report.agreementRate,
    proposalsJudged: report.proposalsJudged,
    reusable: report.reusable,
    oneOff: report.oneOff,
    surfaces: [...new Set(records.filter((r) => r.judged && r.phase === "operations").map((r) => String(r.surface)))].sort(),
  };
}

/**
 * Promotion status, as one bounded line on the same receipt. The switch is a
 * configuration change; this says what the measurement currently supports, so
 * that change is informed rather than hopeful.
 */
export function promotionGateLine(cwd: string, agentDir?: string): string {
  const gate = promotionGate(cwd, agentDir);
  const parts = gate.surfaces
    .filter((surface) => surface.implemented)
    .map((surface) => `${surface.surface} ${surface.verdict}${surface.dropRate === null ? "" : ` · would drop ${Math.round(surface.dropRate * 100)}%`}`);
  return parts.length ? `gate ${parts.join(" · ")}` : "gate no surface has authoritative behavior implemented";
}

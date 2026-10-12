import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { eventToolLifecycle, renderToolLifecycle } from "@fradser/pi-kit";
import type { Verdict } from "./types.ts";
import { findings, nextAction } from "./guidance.ts";

export const E2E_FEEDBACK_MESSAGE_TYPE = "pi-e2e-feedback";

export interface AcceptanceFeedback {
  readonly passed: number;
  readonly total: number;
  readonly remaining: readonly string[];
}

export interface E2EFeedback {
  readonly label: "running" | "passed" | "failed" | "needs review" | "error" | "continue" | "waiting";
  readonly tone: "success" | "warning" | "error";
  readonly lines: readonly string[];
}

export function verdictFeedback(verdict: Verdict, options: {
  verifiedRun: boolean;
  modelError?: string;
  acceptance?: AcceptanceFeedback;
}): E2EFeedback {
  const review = verdict.status === "needs_review" || (verdict.status === "fulfilled" && !options.verifiedRun);
  const label = review ? "needs review" : verdict.status === "fulfilled" ? "passed" : "failed";
  const lines = [
    `Evidence: ${options.verifiedRun ? "verified fresh test process" : "caller-supplied; acceptance unverified"}`,
    `Feature: ${verdict.feature}`,
    `Scenario: ${verdict.scenario}`,
  ];
  if (options.acceptance) {
    const { passed, total, remaining } = options.acceptance;
    lines.push(`Feature acceptance: ${passed}/${total} scenarios passed`);
    for (const name of remaining) lines.push(`Remaining: ${name}`);
  } else if (options.verifiedRun) {
    lines.push("Feature acceptance: not tracked by this caller; this report covers one scenario");
  }
  lines.push(`Clauses: ${verdict.clauses.filter(clause => clause.status === "met").length}/${verdict.clauses.length} met`);
  if (verdict.status !== "fulfilled") lines.push(`Reason: ${verdict.reason}`);
  if (options.modelError) lines.push(`Provider: ${options.modelError}`);
  const action = nextAction(findings(verdict, options.verifiedRun), Boolean(options.modelError), options.verifiedRun);
  lines.push(`Action: ${action}`);
  if (review) lines.push(options.modelError
    ? "Next: resolve the provider blocker or add deterministic checks over actual observations, then rerun verification."
    : !options.verifiedRun && verdict.status === "fulfilled"
      ? "Supplied evidence verdict: fulfilled. Next: run e2e_verify with the configured project runner to verify acceptance."
      : "Next: collect missing observations or checks, or review the uncertain judgment before retrying.");
  else if (label === "failed") lines.push(action === "repair_code"
    ? "Next: repair the concrete observed mismatch, preserve the checks, then run fresh verification."
    : "Next: collect missing observations or correct the adapter checks before changing production code.");
  if (verdict.model) lines.push(`Model: ${verdict.model}`);
  if (verdict.modelVerdict) lines.push(`Model verdict: ${verdict.modelVerdict.choice}, probability ${verdict.modelVerdict.probability.toFixed(2)}, confidence ${verdict.modelVerdict.confidence.toFixed(2)}`);
  if (verdict.severity) lines.push(`Severity: ${verdict.severity.score.toFixed(2)} (${verdict.severity.label})`);
  for (const cause of verdict.triage) lines.push(`Cause ${cause.id}: ${cause.noul.toFixed(2)}`);
  // Put actionable clauses first, without losing any successful clause or tail.
  const clauses = [...verdict.clauses].sort((left, right) => Number(left.status === "met") - Number(right.status === "met") || left.clause - right.clause);
  for (const clause of clauses) {
    const mark = clause.status === "met" ? "PASS" : clause.status === "unmet" ? "FAIL" : "UNJUDGED";
    lines.push("", `${mark} ${clause.clause}. ${clause.text}`, `Source: ${clause.source}${clause.score === undefined ? "" : `, score ${clause.score.toFixed(2)}`}`);
    if (clause.detail) lines.push(clause.detail);
    for (const check of clause.checks ?? []) {
      if (!check.failureKind) continue;
      lines.push(`Check: ${check.path} (${check.op})`, `Expected: ${check.expected}`, `Observed: ${check.observed}`);
      if (check.step) lines.push(`Step: ${check.step}`);
      if (check.location) lines.push(`Location: ${check.location}`);
    }
  }
  return { label, tone: review ? "warning" : label === "passed" ? "success" : "error", lines };
}

/** Tool results and manual commands use one renderer, with a bare status row. */
export function renderFeedback(feedback: E2EFeedback, theme: Parameters<typeof renderToolLifecycle>[1]["theme"]) {
  return {
    render: (width: number) => renderToolLifecycle({
      ...eventToolLifecycle("e2e", "", { label: feedback.label }),
      fullSummary: true, verbatimSubject: true, summary: feedback.lines, details: [],
    }, { width, theme, isError: feedback.tone === "error", isPending: feedback.tone === "warning",
      fit: truncateToWidth, visibleWidth,
      wrapDetail: (line, available) => wrapTextWithAnsi(line, Math.max(1, available)),
    }),
    invalidate() {},
  };
}

export function registerFeedbackRenderer(pi: ExtensionAPI): void {
  pi.registerMessageRenderer<E2EFeedback>(E2E_FEEDBACK_MESSAGE_TYPE, (message, _state, theme) =>
    renderFeedback(message.details ?? {label:"error",tone:"error",lines:[String(message.content)]}, theme));
}

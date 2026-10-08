/**
 * One lifecycle row for /goal.
 *
 * The command delivers the user's requirement as a custom message. The model
 * still receives the complete goalRequest body in the same turn; the
 * transcript shows only one row. Management verbs never send this row.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  bindLifecycleRenderers,
  startedToolLifecycle,
} from "@fradser/pi-kit";

export const GOAL_PROCEDURE_ENTRY = "goal-procedure";

const goalProcedureRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

export interface GoalProcedureDetails {
  request?: string;
}

/** Deliver one transcript row carrying the full body for the model. */
export function deliverGoalProcedure(
  pi: ExtensionAPI,
  content: string,
  details: GoalProcedureDetails,
): void {
  pi.sendMessage(
    { customType: GOAL_PROCEDURE_ENTRY, content, display: false, details },
    { deliverAs: "followUp", triggerTurn: true },
  );
}

export function registerGoalProcedureRenderer(pi: ExtensionAPI): void {
  if (typeof (pi as unknown as { registerMessageRenderer?: unknown }).registerMessageRenderer !== "function") return;
  pi.registerMessageRenderer(GOAL_PROCEDURE_ENTRY, (message, options, theme) => {
    const details = (message.details ?? {}) as GoalProcedureDetails;
    const request = typeof details.request === "string" ? details.request : "";
    // Head stays "[goal] started"; the block carries the full verbatim requirement.
    return goalProcedureRows.message(() => startedToolLifecycle("goal", request.trim() || "goal request", {
      label: "started",
      verbatimSubject: true,
      subjectBlock: true,
      bgToken: "userMessageBg",
    }))(message, options, theme);
  });
}


/** Durable transcript outcome; no triggerTurn and no toast replacement. */
export const GOAL_EVENT_ENTRY = "goal-event";
export function emitGoalMessage(pi: ExtensionAPI, subject: string, summary = ""): void {
  pi.sendMessage({ customType: GOAL_EVENT_ENTRY, content: summary ? `${subject}\n\n${summary}` : subject,
    display: true, details: { subject, summary } }, { triggerTurn: false });
}
export function registerGoalEventRenderer(pi: ExtensionAPI): void {
  if (typeof pi.registerMessageRenderer !== "function") return;
  pi.registerMessageRenderer(GOAL_EVENT_ENTRY, goalProcedureRows.message((message) => {
    const details = message.details as {subject?: string; summary?: string} | undefined;
    return {tool:"goal",kind:"event",subject:details?.subject ?? "status",summary:details?.summary ? [details.summary] : [],verbatimSubject:true,fullSummary:true};
  }));
}

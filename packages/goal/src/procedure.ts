/**
 * One lifecycle row for /goal.
 *
 * The command delivers the user's requirement as a custom message. The model
 * still receives the complete goalRequest body in the same turn; the transcript
 * shows the request as one `[goal] requesting` row with the typed words. The
 * body stays out of the transcript, so a long request cannot bury the goal
 * record that follows it. Management verbs never send this row.
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

/** A host without message renderers would print the whole request body through
 * Pi's default custom-message rendering, so that host receives the previous
 * hidden message instead of a transcript copy of the model-only body. */
function hasMessageRenderer(pi: ExtensionAPI): boolean {
  return typeof (pi as unknown as { registerMessageRenderer?: unknown }).registerMessageRenderer === "function";
}

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
    { customType: GOAL_PROCEDURE_ENTRY, content, display: hasMessageRenderer(pi), details },
    { deliverAs: "followUp", triggerTurn: true },
  );
}

export function registerGoalProcedureRenderer(pi: ExtensionAPI): void {
  if (!hasMessageRenderer(pi)) return;
  pi.registerMessageRenderer(GOAL_PROCEDURE_ENTRY, (message, options, theme) => {
    const details = (message.details ?? {}) as GoalProcedureDetails;
    const request = typeof details.request === "string" ? details.request : "";
    // The head names the request, never the creation: `create_goal` owns the
    // `[goal] started` row that reports what the goal became. The block carries
    // the user's verbatim words, so the transcript keeps what they asked for.
    return goalProcedureRows.message(() => startedToolLifecycle("goal", request.trim() || "goal request", {
      label: "requesting",
      verbatimSubject: true,
      subjectBlock: true,
      bgToken: "userMessageBg",
    }))(message, options, theme);
  });
}


/** Durable transcript outcome; no triggerTurn and no toast replacement. */
const GOAL_EVENT_ENTRY = "goal-event";
export function emitGoalMessage(pi: ExtensionAPI, subject: string, summary = ""): void {
  pi.sendMessage({ customType: GOAL_EVENT_ENTRY, content: summary ? `${subject}\n\n${summary}` : subject,
    display: true, details: { subject, summary } }, { triggerTurn: false });
}
export function registerGoalEventRenderer(pi: ExtensionAPI): void {
  if (!hasMessageRenderer(pi)) return;
  pi.registerMessageRenderer(GOAL_EVENT_ENTRY, goalProcedureRows.message((message) => {
    const details = message.details as {subject?: string; summary?: string} | undefined;
    return {tool:"goal",kind:"event",subject:details?.subject ?? "status",summary:details?.summary ? [details.summary] : [],verbatimSubject:true,fullSummary:true};
  }));
}

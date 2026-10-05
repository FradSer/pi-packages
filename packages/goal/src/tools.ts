/**
 * The model-facing tool surface: four tools, one lifecycle.
 *
 * `create_goal` and `update_goal` carry an objective. `get_goal` reads one back.
 * There is no task tool and no separate planning structure, because a goal has
 * one exit condition and a second opinion about it can only contradict the first.
 *
 * Availability follows lifecycle through pi-kit's `setOwnedTools`, which
 * re-asserts this extension's own registrations rather than writing back a
 * snapshot-derived list — the failure mode pi-kit's own comment describes, where
 * a write before the harness publishes them silently erases them.
 *
 * Every executor validates lifecycle state even when its tool is advertised,
 * because a tool call can always arrive one transition late.
 */

import { Type } from "@earendil-works/pi-ai";
import type { AgentToolResult } from "@earendil-works/pi-coding-agent";
import {
  defineTool,
  keyHint,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, emptyToolCall, setOwnedTools } from "@fradser/pi-kit";
import { describeUnmet } from "./check.ts";
import type { GoalCore } from "./core.ts";
import { nowIso, type GoalRecord } from "./record.ts";
import type { GoalSettings } from "./settings.ts";
import type { GoalStore } from "./store.ts";

export const GOAL_TOOLS = ["get_goal", "create_goal", "update_goal", "research_goal"] as const;

/** Tools allowed after a decision ended the turn: reading the goal is how the
 * model finds out what it was supposed to be doing, so it stays available.
 * Research is excluded: a child process is work, not recall. */
const POST_STOP_ALLOWED = new Set(["read", "grep", "find", "ls", "get_goal"]);

/** One lifecycle geometry for every goal row: hint, wrapping, and bands all come
 * from pi-kit, so no goal row can invent its own. */
const rows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

/**
 * Closed sets of allowed strings.
 *
 * Typebox has no StringEnum here, so a union of literals is the same constraint
 * expressed the way the library supports. The schema and the TypeScript type are
 * both derived from the same tuple, so they cannot drift; the schema's contents
 * are asserted against the tuple in the tool-surface test.
 *
 * No cast is involved: naming the literals once and reading the type off the
 * tuple keeps the schema honest, where recovering a typebox type would mean
 * importing a library for one annotation — and pi's guide would then require it
 * to be declared as a peer.
 */
const GOAL_SECTIONS = ["summary", "objective", "history", "research"] as const;
const GOAL_STATUSES = ["complete", "blocked", "paused"] as const;

type GoalSection = (typeof GOAL_SECTIONS)[number];
type GoalStatus = (typeof GOAL_STATUSES)[number];

function closedSet<const T extends readonly string[]>(values: T) {
  return Type.Union(values.map((value) => Type.Literal(value)));
}

export function registerGoalTools(core: GoalCore): void {
  core.pi.registerTool(goalGet(core));
  core.pi.registerTool(goalCreate(core));
  core.pi.registerTool(goalUpdate(core));
  core.pi.registerTool(goalResearch(core));
}

/**
 * Re-assert which of this extension's tools are exposed.
 *
 * Reading the objective and recording an outcome are always possible; a goal that
 * has finished accepts neither.
 */
export function refreshGoalToolSurface(core: GoalCore, _ctx: ExtensionContext): void {
  const goal = core.goal;
  const live = !!goal && (goal.status === "active" || goal.status === "paused" || goal.status === "blocked");
  setOwnedTools(core.pi as unknown as Parameters<typeof setOwnedTools>[0], {
    owned: GOAL_TOOLS,
    // Creating, reading, and researching are never withdrawn: a user must
    // always be able to start a goal, a session with none focused still has to
    // see what is open, and research precedes creation.
    always: ["create_goal", "get_goal", "research_goal"],
    toggled: live ? ["update_goal"] : [],
    enabled: true,
  });
}

/** Whether a tool may still run after a decision ended this turn. */
export function allowsAfterStop(toolName: string): boolean {
  return POST_STOP_ALLOWED.has(toolName);
}

/** The registration binds the tool name because Pi supplies only content and details. */
interface GoalRenderedResult extends AgentToolResult<unknown> {
  tool?: string;
}

/** The shape every executor returns. A refusal is returned rather than thrown, so
 * a caller reads one shape whatever went wrong. */
type GoalToolResult = AgentToolResult<{ subject: string; summary?: string; details?: string[] }>;

/** pi-kit's band for one goal tool result. pi-kit owns the frame, the expansion
 * hint, the wrapping, and the error styling; this decides only which part of the
 * result is the subject, which is always visible, and which expands. */
const goalResultBand = rows.result<GoalRenderedResult>((value) => {
  const spec = (value.details ?? {}) as { subject?: string; summary?: string; details?: string[] };
  const tool = value.tool ?? "goal";
  const summary = spec.summary?.split("\n").filter((line) => line.length > 0) ?? [];
  const details = spec.details?.length ? spec.details : [];
  return {
    tool,
    kind: "event" as const,
    subject: spec.subject ?? tool,
    ...(summary.length > 0 ? { summary } : {}),
    ...(details.length > 0 ? { details } : {}),
  };
});

/** The tool renders its own call and result, through pi-kit's shared band. */
const renderShell = "self" as const;
const renderCall = () => emptyToolCall();
function renderGoalResultFor(tool: string) {
  return (
    result: AgentToolResult<unknown>,
    options: { expanded?: boolean; isPartial?: boolean },
    theme: Parameters<typeof goalResultBand>[2],
    context: { isError?: boolean },
  ) => goalResultBand({ ...result, tool }, options, theme, context);
}

function result(spec: { subject: string; summary?: string; details?: string[] }, error = false): GoalToolResult {
  const text = spec.summary ? `${spec.subject}\n\n${spec.summary}` : spec.subject;
  return {
    content: [{ type: "text", text }],
    details: spec,
    isError: error,
  };
}

// ── get_goal ─────────────────────────────────────────────────────────

function goalGet(core: GoalCore) {
  return defineTool({
    name: "get_goal",
    label: "Get Goal",
    description:
      "Read the focused goal: its objective, completion contract, how long it has run, and its recent ledger history.",
    promptSnippet: "Read the focused goal, or retrieve a requirement the current prompt omitted.",
    promptGuidelines: [],
    parameters: Type.Object({
      section: Type.Optional(closedSet(GOAL_SECTIONS)),
      cursor: Type.Optional(Type.String({ maxLength: 256, description: "Next history page." })),
    }, { additionalProperties: false }),
    renderShell,
    renderCall,
    renderResult: renderGoalResultFor("get_goal"),
    async execute(_id, params: { section?: GoalSection; cursor?: string }, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      const goal = core.goal;
      if (!goal) return result({ subject: "No focused goal", summary: "Use /goal <objective and completion conditions> to start this thread’s goal." });
      const section = params.section ?? "summary";
      if (section === "objective") {
        const parts = [
          `Objective:\n${goal.objective}`,
          goal.verificationContract ? `\nContract:\n${goal.verificationContract}` : "",
          goal.pauseReason ? `\nPaused:\n${goal.pauseReason}` : "",
        ].filter(Boolean).join("\n");
        return bounded("objective", parts);
      }
      if (section === "history") {
        const page = core.store.readHistory(goal.id, params.cursor);
        const lines = page.events.map((event) => `${event.at} ${event.type}`);
        // The cursor is the only way to reach the events this page did not
        // return. The tool accepts one as input, so it must hand one back or a
        // long history silently ends at the first page.
        const more = page.cursor
          ? `More history remains. Continue with get_goal(section="history", cursor="${page.cursor}").`
          : "End of history.";
        return result({
          subject: `${page.events.length} ledger events`,
          summary: [lines.join("\n"), more].join("\n"),
          details: page.diagnostics.length > 0 ? [`Ledger diagnostics: ${page.diagnostics.join("; ")}`] : [],
        });
      }
      if (section === "research") {
        const research = core.store.readResearch(goal.id).trim();
        if (!research) {
          return result({ subject: "no research", summary: "No research was attached when this goal was created." });
        }
        return bounded("research", research);
      }
      return bounded("summary", [
        `Goal — ${goal.status}`,
        goal.objective,
        goal.verificationContract ? `Contract: ${goal.verificationContract}` : "",
        goal.pauseReason ? `Paused: ${goal.pauseReason}` : "",
      ].filter(Boolean).join("\n"));
    },
  });
}

function bounded(section: string, body: string) {
  const cap = 4000;
  // No goal id in the subject: a session has one goal, so its id is noise the
  // reader must filter on every line.
  if (body.length <= cap) return result({ subject: section, summary: body });
  return result({
    subject: `${section} (${body.length} chars)`,
    summary: `${body.slice(0, cap)}\n\n[truncated at ${cap} characters.]`,
  });
}

// ── create_goal ───────────────────────────────────────────────────────

function goalCreate(core: GoalCore) {
  return defineTool({
    name: "create_goal",
    label: "Create Goal",
    description:
      "Create and focus a durable goal. Write the objective yourself from the conversation: it must say what is true when the goal is met. Use update_goal instead when the user is refining a goal this session already has focused.",
    promptSnippet: "Create a durable goal from what the user asked for.",
    promptGuidelines: [
      "Do not create a goal for an ordinary task that will finish in this turn.",
      "Write the objective so someone else could tell whether it is met. Include the requirements the user stated, not a summary of them away.",
      "Put a checkable requirement in verification_contract when the user gave one.",
    ],
    parameters: Type.Object({
      objective: Type.String({ minLength: 1, maxLength: 4000, description: "What must be true when this goal is met." }),
      verification_contract: Type.Optional(Type.String({ maxLength: 2000, description: "What evidence shows it is met." })),
    }, { additionalProperties: false }),
    renderShell,
    renderCall,
    renderResult: renderGoalResultFor("create_goal"),
    async execute(_id, params: { objective: string; verification_contract?: string }, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      if (core.goal) {
        return result({ subject: "This thread already has a goal", summary: "Revise it with update_goal, or use /goal clear before creating another." }, true);
      }
      const objective = params.objective.trim();
      if (!objective) return result({ subject: "No objective", summary: "create_goal needs a nonempty objective." }, true);
      // Research gathered this session attaches here, once. The store writes
      // it under the same lock as the record, so the material and the goal it
      // informs cannot be separated by a failure between two writes. The slot
      // is consumed only after the write lands, so a failed creation keeps
      // its material for the retry.
      const research = core.peekPendingResearch();
      const created = core.store.create({
        objective,
        contract: params.verification_contract?.trim(),
        owner: ctx.sessionManager.getSessionId() || "unknown-session",
        id: core.newId(),
        research: research ? { focus: research.focus, text: research.findings, tokens: research.tokens } : undefined,
      });
      if (!created.ok) return result({ subject: "Goal creation failed", summary: created.message }, true);
      if (research) core.takePendingResearch();
      core.focus(created.goal.id, ctx, "created");
      core.scheduler.schedule(created.goal, core.settings(ctx));
      refreshGoalToolSurface(core, ctx);
      return result({
        subject: "Goal created and focused",
        summary: `It now runs on its own until the completion check says it is met.${research ? " Read-only research gathered this session is attached." : ""}\n\n${objective}`,
      });
    },
  });
}

// ── update_goal ───────────────────────────────────────────────────────

function goalUpdate(core: GoalCore) {
  return defineTool({
    name: "update_goal",
    label: "Update Goal",
    description:
      "Record an outcome for the focused goal, revise its objective, or save what comes next. Completion is decided by the completion check, not by this call.",
    promptSnippet: "Record a goal outcome, revise its objective, or save the next action.",
    promptGuidelines: [],
    parameters: Type.Object({
      status: Type.Optional(closedSet(GOAL_STATUSES)),
      reason: Type.Optional(Type.String({ maxLength: 2000, description: "Required for paused and blocked: the concrete reason." })),
      objective: Type.Optional(Type.String({ maxLength: 4000, description: "Replace the objective. Use when the user refines this goal." })),
      verification_contract: Type.Optional(Type.String({ maxLength: 2000, description: "Replace the completion contract." })),
      completion_summary: Type.Optional(Type.String({ maxLength: 4000, description: "What you did. An untrusted claim, never evidence." })),
      next_action: Type.Optional(Type.String({ minLength: 1, maxLength: 2000, description: "Save the next action and end the turn." })),
    }, { additionalProperties: false }),
    renderShell,
    renderCall,
    renderResult: renderGoalResultFor("update_goal"),
    async execute(_id, params: {
        status?: GoalStatus;
        reason?: string;
        objective?: string;
        verification_contract?: string;
        completion_summary?: string;
        next_action?: string;
      }, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      const goal = core.goal;
      if (!goal) return result({ subject: "No focused goal", summary: "Create one first." }, true);
      const settings = core.settings(ctx);
      const outcomes = [params.status, params.objective, params.verification_contract, params.next_action].filter(Boolean);
      if (outcomes.length === 0) {
        return result({ subject: "Nothing to record", summary: "Pass a status, a new objective, or a next action." }, true);
      }
      if (params.status && (params.objective || params.verification_contract || params.next_action)) {
        return result({ subject: "Two decisions at once", summary: "status is exclusive with objective and next_action." }, true);
      }
      if (params.next_action && (params.objective || params.verification_contract)) {
        return result({ subject: "Two decisions at once", summary: "next_action is exclusive with a revision." }, true);
      }

      if (params.next_action) return saveNextAction(core, ctx, goal, settings, params.next_action);
      if (params.objective || params.verification_contract) return revise(core, ctx, goal, params.objective, params.verification_contract);
      if (params.status === "complete") return completeGoal(core, ctx, goal, settings, params.completion_summary);
      return pauseGoal(core, ctx, goal, params.reason);
    },
  });
}

/**
 * The one way a goal's requirements change.
 *
 * A revision is three fields or none: the objective prose, the start of the
 * evidence window, and the reset of the refusal count. Anything that writes
 * only the objective leaves `prompt.md` describing the superseded goal, keeps
 * observations collected under the old requirement admissible for the new one,
 * and lets a stale refusal count stop a goal under requirements it never
 * refused. Both the `update_goal` tool and `/goal` route through here so the
 * two cannot drift apart.
 */
export function applyRevision(
  store: GoalStore,
  goalId: string,
  objective: string,
  contract?: string,
): { ok: true; goal: GoalRecord } | { ok: false; message: string } {
  return store.apply({
    expectedGoalId: goalId,
    writePrompt: true,
    mutate: (draft) => {
      const nextContract = contract !== undefined ? contract.trim() || undefined : draft.verificationContract;
      const changed = objective !== draft.objective || nextContract !== draft.verificationContract;
      return {
        ...draft,
        ...(changed ? { evidenceSince: nowIso(), completionFailures: 0 } : {}),
        objective,
        verificationContract: nextContract,
      };
    },
  });
}

function revise(
  core: GoalCore,
  ctx: ExtensionContext,
  goal: GoalRecord,
  objective: string | undefined,
  contract: string | undefined,
) {
  const nextObjective = objective?.trim();
  if (nextObjective !== undefined && !nextObjective) {
    return result({ subject: "Empty objective", summary: "A revision needs text." }, true);
  }
  // Lifecycle state is checked even though `update_goal` is withdrawn for these
  // goals, because a call can arrive one transition late. A budget-limited goal
  // has spent its lifetime tokens and a completed goal is archived; rewriting
  // their requirements, prose and refusal count would revive work that stopped.
  if (goal.status !== "active" && goal.status !== "paused" && goal.status !== "blocked") {
    return result(
      { subject: "Goal not revisable", summary: `A ${goal.status.replace("_", " ")} goal cannot be revised. Use /goal resume to continue it.` },
      true,
    );
  }
  const outcome = applyRevision(
    core.store,
    goal.id,
    nextObjective ?? goal.objective,
    contract,
  );
  if (!outcome.ok) return result({ subject: "Objective not revised", summary: outcome.message }, true);
  const activated = core.activateRequestedRevision(goal.id, ctx);
  core.refreshUi(ctx);
  refreshGoalToolSurface(core, ctx);
  return result({
    subject: `Goal revised${activated === true ? " and activated" : ""}`,
    summary: `${outcome.goal.objective}${activated === false ? "\n\nThe revision was saved, but continuation is blocked by its current limits." : ""}`,
  });
}

function saveNextAction(core: GoalCore, _ctx: ExtensionContext, goal: GoalRecord, settings: GoalSettings, nextAction: string) {
  const generation = goal.scheduler?.generation;
  if (!generation) return result({ subject: "No scheduling state", summary: "Goal is not scheduled." }, true);
  const declared = core.scheduler.declare(goal, nextAction, settings);
  if (!declared.ok) return result({ subject: "Decision not saved", summary: declared.message }, true);
  core.markTurnStopped();
  // The decision is the model saying what comes next. Letting it keep working
  // would invalidate the answer it just gave, so the turn ends here.
  const text = `Next action saved: ${nextAction}. End this turn.`;
  return { content: [{ type: "text" as const, text }], details: { subject: "Saved a next action", summary: text }, terminate: true };
}

function pauseGoal(core: GoalCore, ctx: ExtensionContext, goal: GoalRecord, reason: string | undefined) {
  if (!reason?.trim()) {
    return result({ subject: "A reason is required", summary: "Say what is blocking this goal." }, true);
  }
  core.cancelGoalActivation();
  core.abortCheck();
  if (!core.scheduler.pause(goal, reason.trim(), "agent")) {
    return result({ subject: "Goal could not pause", summary: "The state write failed. Read the current goal before retrying." }, true);
  }
  core.markTurnStopped();
  refreshGoalToolSurface(core, ctx);
  return result({ subject: "Goal paused", summary: reason.trim() });
}

async function completeGoal(core: GoalCore, ctx: ExtensionContext, goal: GoalRecord, settings: GoalSettings, claim: string | undefined) {
  core.noteCompletionRequested();
  const at = nowIso();
  core.appendEvents(ctx, [{ type: "completion_requested", goalId: goal.id, summary: claim, at }]);
  const recorded = core.store.apply({
    expectedGoalId: goal.id,
    mutate: (draft) => ({ ...draft, completionClaim: claim?.trim() || draft.completionClaim }),
  });
  const current = recorded.ok ? recorded.goal : goal;

  if (settings.disableCheck) {
    core.appendEvents(ctx, [{ type: "check_skipped", goalId: goal.id, reason: "disabled in settings", at: nowIso() }]);
    return archive(core, ctx, current, "Completed with the completion check disabled.");
  }

  const verdict = await core.check(ctx, current, claim, settings, true);
  if (!verdict.met) {
    refreshGoalToolSurface(core, ctx);
    return {
      ...result({
        subject: verdict.stopped ? "Goal paused after three final refusals" : "Goal is not met",
        summary: `${describeUnmet(verdict)}${verdict.advice ? `\n\n${verdict.advice}` : ""}`,
      }, !verdict.stopped),
      ...(verdict.stopped ? { terminate: true } : {}),
    };
  }
  return archive(core, ctx, current, verdict.report);
}

function archive(core: GoalCore, ctx: ExtensionContext, goal: GoalRecord, summary: string) {
  const outcome = core.completeCheckedGoal(ctx, goal);
  if (!outcome.ok) return result({ subject: "Goal could not be archived", summary: outcome.message }, true);
  refreshGoalToolSurface(core, ctx);
  return result({ subject: "Goal completed", summary: `${summary}\n\nArchived under .pi/goals/archived/.` });
}

// ── research_goal ────────────────────────────────────────────────────────────

function goalResearch(core: GoalCore) {
  return defineTool({
    name: "research_goal",
    label: "Research Goal",
    description:
      "Explore the codebase read-only before writing an objective, and attach the findings to the next goal you create. The child has read, grep, find, and ls only — no shell, no writes. Findings are material for the objective, never evidence for the completion check.",
    promptSnippet: "Explore the codebase read-only before creating a goal.",
    promptGuidelines: [
      "Run this before create_goal when the conversation does not settle what exists in the codebase.",
      "State the focus as the open question the exploration should answer, not as an objective.",
      "The latest successful research replaces earlier findings. A failed run preserves them until creation or a session boundary.",
    ],
    parameters: Type.Object({
      focus: Type.String({ minLength: 1, maxLength: 2000, description: "What to investigate in the codebase." }),
    }, { additionalProperties: false }),
    renderShell,
    renderCall,
    renderResult: renderGoalResultFor("research_goal"),
    async execute(_id, params: { focus: string }, signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      const focus = params.focus.trim();
      if (!focus) return result({ subject: "No focus", summary: "research_goal needs a focus to investigate." }, true);
      const research = await core.research(focus, ctx.cwd, signal);
      if (research.error || !research.findings) {
        return result({
          subject: "Research failed",
          summary: `${research.error ?? "No findings were returned."}\n\nNo new findings were saved. Earlier successful research, if any, still waits for creation. Retry research_goal if needed.`,
        }, true);
      }
      return result({
        subject: `Research ready (${research.findings.length} chars)`,
        summary: `${research.findings}\n\nThese findings replace earlier research and attach to the next goal created in this session. They inform the objective; they are not evidence for the completion check.`,
      });
    },
  });
}
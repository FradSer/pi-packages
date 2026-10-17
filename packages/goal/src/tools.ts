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

import { createHash } from "node:crypto";
import { Type } from "@earendil-works/pi-ai";
import type { AgentToolResult } from "@earendil-works/pi-coding-agent";
import {
  defineTool,
  keyHint,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, emptyToolCall, extractTextContent, renderToolLifecycle, setOwnedTools, type ToolLifecycleSpec } from "@fradser/pi-kit";
import type { GoalCore } from "./core.ts";
import { nowIso, type GoalRecord } from "./record.ts";
import type { GoalSettings } from "./settings.ts";
import type { GoalStore } from "./store.ts";

const GOAL_TOOLS = ["get_goal", "create_goal", "update_goal"] as const;

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
 * both derived from the same tuple, so they cannot drift: `closedSet` reads the
 * tuple, and the type is read off it.
 *
 * No cast is involved: naming the literals once and reading the type off the
 * tuple keeps the schema honest, where recovering a typebox type would mean
 * importing a library for one annotation — and pi's guide would then require it
 * to be declared as a peer.
 */
const GOAL_SECTIONS = ["summary", "objective"] as const;
const GOAL_STATUSES = ["complete", "blocked", "paused"] as const;

/** Every parameter each tool declares. A call carrying anything else asks for a
 * surface this version does not have — a stale prompt, a schema an older session
 * cached, or a hand-built call — so the executor refuses it rather than applying
 * the declared part and ignoring the rest. Without this, a call that smuggled a
 * removed field past the schema would still be applied. */
const CREATE_GOAL_PARAMS = ["objective"] as const;
const UPDATE_GOAL_PARAMS = ["status", "reason", "objective", "completion_summary"] as const;

function undeclaredKeys(params: object, declared: readonly string[]): string[] {
  return Object.keys(params).filter((key) => !declared.includes(key));
}

type GoalSection = (typeof GOAL_SECTIONS)[number];

function closedSet<const T extends readonly string[]>(values: T) {
  return Type.Union(values.map((value) => Type.Literal(value)));
}

export function registerGoalTools(core: GoalCore): void {
  core.pi.registerTool(goalGet(core));
  core.pi.registerTool(goalCreate(core));
  core.pi.registerTool(goalUpdate(core));
}

/**
 * Re-assert which of this extension's tools are exposed.
 *
 * Creation and reading are always exposed; updates require an open goal.
 */
export function refreshGoalToolSurface(core: GoalCore, _ctx: ExtensionContext): void {
  const goal = core.goal;
  const focused = !!goal;
  const live = focused && (goal!.status === "active" || goal!.status === "paused" || goal!.status === "blocked");
  setOwnedTools(core.pi as unknown as Parameters<typeof setOwnedTools>[0], {
    owned: GOAL_TOOLS,
    always: ["create_goal", "get_goal"],
    toggled: focused ? (live ? ["get_goal", "update_goal"] : ["get_goal"]) : [],
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
  displayPartial?: boolean;
}

/** The shape every executor returns. A refusal is returned rather than thrown, so
 * a caller reads one shape whatever went wrong. */
type GoalToolResult = AgentToolResult<{ subject: string; summary?: string; details?: string[]; markdown?: boolean; label?: string; cursor?: string }>;

/** pi-kit's band for one goal tool result. pi-kit owns the frame, the expansion
 * hint, the wrapping, and the error styling; this decides only which part of the
 * result is the subject, which is always visible, and which expands. */
const goalSpec = (value: GoalRenderedResult): ToolLifecycleSpec => {
  const text = extractTextContent(value.content).trim();
  const [fallbackSubject, ...fallbackBody] = text.split(/\r\n|\r|\n/);
  const metadata = (value.details ?? {}) as { subject?: string; summary?: string; details?: string[]; markdown?: boolean; label?: string };
  const spec = { ...metadata, subject: metadata.subject ?? fallbackSubject, summary: metadata.summary ?? fallbackBody.join("\n").trim() };
  // Unified transcript tag: every goal tool row reads `[goal] ...`, with the
  // per-tool verb carried by the subject/summary so `ctrl+o to expand` still
  // applies via the shared band. The registered tool names stay distinct; only
  // the rendered tag is unified.
  const tool = "goal";
  // One body preserves authored paragraphs and code blocks. Settled results
  // show it in full; streaming progress keeps one compact preview.
  const summary = spec.summary?.trim() ? [spec.summary] : [];
  const details = spec.details?.length ? spec.details : [];
  return {
    tool,
    kind: "event" as const,
    label: spec.label,
    verbatimSubject: !value.displayPartial,
    fullSummary: !value.displayPartial,
    subject: spec.subject?.startsWith("Goal ") ? spec.subject.slice("Goal ".length) : spec.subject ?? tool,
    ...(summary.length > 0 ? { summary } : {}),
    // Native Markdown preserves paragraph and code-block boundaries.
    ...(spec.markdown ? { summaryFormat: "markdown" as const } : {}),
    ...(details.length > 0 ? { details } : {}),
  };
};
const goalResultBand = rows.result<GoalRenderedResult>(goalSpec);

/** The tool renders its own call and result, through pi-kit's shared band. */
const renderShell = "self" as const;
const renderCall = () => emptyToolCall();
function renderGoalResultFor(toolName?: string) {
  return (
    result: AgentToolResult<unknown>,
    options: { expanded?: boolean; isPartial?: boolean },
    theme: Parameters<typeof goalResultBand>[2],
    context: { isError?: boolean },
  ) => {
    const displayResult = { ...result, tool: "goal", displayPartial: options.isPartial === true };
    if (context.isError) {
      const spec = goalSpec(displayResult);
      if (toolName === "update_goal" && /^Validation failed for tool\b/.test(extractTextContent(result.content).trim())) {
        spec.label = "update not applied";
        spec.subject = "";
        spec.summary = [extractTextContent(result.content)];
      }
      // Goal errors carry authored recovery text too. Use the shared band with
      // error styling while retaining the full-summary layout and precise label.
      return {
        render: (width: number) => renderToolLifecycle({ ...spec, label: spec.label ?? spec.subject ?? "failed", subject: spec.label ? spec.subject : "" }, {
          width, expanded: options.expanded, theme, isError: true,
          fit: truncateToWidth, visibleWidth,
          wrapDetail: (text, contentWidth) => wrapTextWithAnsi(text, Math.max(1, contentWidth)),
        }),
        invalidate() {},
      };
    }
    return goalResultBand(displayResult, options, theme, context);
  };
}

function result(spec: { subject: string; summary?: string; details?: string[]; markdown?: boolean; label?: string; cursor?: string }, error = false): GoalToolResult {
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
      "Read the focused goal and its complete objective. Summary and objective read the same view; objective is a compatibility alias. Follow the returned cursor for long model-facing pages; the TUI retains the full body.",
    promptSnippet: "Read the focused goal, or retrieve a requirement the current prompt omitted.",
    promptGuidelines: ["Read only when requirements or current state are missing from context; ordinary continuation needs no get_goal or update_goal acknowledgement."],
    parameters: Type.Object({
      section: Type.Optional(closedSet(GOAL_SECTIONS)),
      cursor: Type.Optional(Type.String({ maxLength: 256, description: "Cursor returned by the previous read. Keep the same section; omit to restart after requirements change." })),
    }, { additionalProperties: false }),
    renderShell,
    renderCall,
    renderResult: renderGoalResultFor(),
    async execute(_id, params: { section?: GoalSection; cursor?: string }, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      const goal = core.goal;
      if (!goal) return result({ subject: "no active goal", summary: "Use /goal <objective> to start a goal." });
      const section = params.section ?? "summary";
      if (section === ("history" as GoalSection)) return result({ subject: "history", summary: "Goal lifecycle results are in this session's transcript. There is no separate Goal history." });
      if (section === ("research" as GoalSection)) return result({ subject: "research unavailable", summary: "Use ordinary read, grep, find and ls tools to investigate the work." });
      return paged(goal.status, [
        `Objective:\n${goal.objective}`,
        goal.pauseReason ? `\nPaused:\n${goal.pauseReason}` : "",

      ].filter(Boolean).join("\n"), params.cursor);
    },
  });
}

/** Model pages are bounded, but transcript details keep the complete authored
 * body. Every page carries a next cursor; nothing becomes irretrievable. */
function paged(subject: string, body: string, cursor?: string, markdown = false): GoalToolResult {
  const cap = 4000;
  const fingerprint = createHash("sha256").update(body).digest("hex").slice(0, 16);
  const match = cursor?.match(/^offset:([0-9]+):([a-f0-9]{16})$/);
  if (cursor !== undefined && (!match || match[2] !== fingerprint)) {
    return result({ subject: "read not applied", summary: "Use the cursor returned by get_goal, or omit it to read from the beginning." }, true);
  }
  const offset = cursor === undefined ? 0 : Number(match![1]);
  if (!Number.isSafeInteger(offset) || offset >= body.length) {
    return result({ subject: "read not applied", summary: "This page is no longer available. Read get_goal again without a cursor." }, true);
  }
  let end = Math.min(body.length, offset + cap);
  // Never split a UTF-16 surrogate pair between model pages.
  if (end < body.length && /[\uD800-\uDBFF]/.test(body[end - 1]!)) end--;
  const next = end < body.length ? `offset:${end}:${fingerprint}` : undefined;
  const view = result({ subject, summary: offset === 0 ? body : body.slice(offset, end), markdown, ...(next ? { cursor: next } : {}) });
  view.content = [{ type: "text", text: `${subject}\n\n${body.slice(offset, end)}${next ? `\n\nMore content remains. Continue with get_goal(cursor="${next}").` : ""}` }];
  return view;
}

// ── create_goal ───────────────────────────────────────────────────────

function goalCreate(core: GoalCore) {
  return defineTool({
    name: "create_goal", label: "Create Goal",
    description: "Create this thread's objective when the user requests a Goal.",
    parameters: Type.Object({
      objective: Type.String({ minLength: 1 }),
    }, { additionalProperties: false }),
    promptGuidelines: [
      "There is no spending cap and none can be set: a goal continues while it changes the workspace, and the user controls pause, resume and clear.",
    ],
    renderShell, renderCall, renderResult: renderGoalResultFor(),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      if (undeclaredKeys(params, CREATE_GOAL_PARAMS).length > 0) {
        return result({ subject: "creation not applied", summary: "Send the objective alone; a goal has no second requirement field." }, true);
      }
      if (core.goal) return result({ subject: "creation not applied", summary: "This thread already has a goal. Revise it with update_goal, or clear it first." }, true);
      const objective = params.objective.trim();
      if (!objective) return result({ subject: "creation not applied", summary: "Choose a nonempty objective." }, true);
      const created = core.store.create({ objective,
        owner: ctx.sessionManager.getSessionId() || "unknown-session", id: core.newId() });
      if (!created.ok) return result({ subject: "creation not applied", summary: created.message }, true);
      if (!core.focus(created.goal.id, ctx, "created")) return result({ subject: "creation not applied", summary: "The new goal could not be focused." }, true);
      refreshGoalToolSurface(core, ctx); core.refreshUi(ctx);
      return result({ subject: "started", summary: goalBody(created.goal) });
    },
  });
}

function goalUpdate(core: GoalCore) {
  return defineTool({
    name: "update_goal", label: "Update Goal",
    description: "Request evidence-based completion, report a recurring blocker, carry out a user pause, or commit a complete user-requested revision.",
    promptGuidelines: [
      "Request complete only after gathering the required evidence. Ordinary turns do not run completion checks.",
      "paused requires an explicit user request. Report blocked only when no defensible progress remains; the same blocker must recur on three consecutive turns.",
      "A revision must preserve the user's existing requirements unless the user explicitly removes them.",
    ],
    parameters: Type.Object({
      status: Type.Optional(closedSet(GOAL_STATUSES)),
      reason: Type.Optional(Type.String({ minLength: 1 })),
      objective: Type.Optional(Type.String({ minLength: 1 })),
      completion_summary: Type.Optional(Type.String()),
    }, { additionalProperties: false, oneOf: [
      { required: ["status"], not: { anyOf: [{required:["objective"]}] }, oneOf: [
        { properties: {status:{const:"complete"}}, not: {required:["reason"]} },
        { properties: {status:{enum:["paused","blocked"]}}, required:["reason"], not:{required:["completion_summary"]} },
      ] },
      { required:["objective"], not:{anyOf:["status","reason","completion_summary"].map(field=>({required:[field]}))} },
    ] }),
    renderShell, renderCall, renderResult: renderGoalResultFor("update_goal"),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      core.bindUi(ctx);
      const goal = core.goal;
      if (!goal) return result({subject:"no active goal",summary:"Create a goal first."},true);
      const revision = params.objective !== undefined;
      if ((!params.status && !revision) || (params.status && revision) ||
          (params.reason !== undefined && !["paused","blocked"].includes(params.status ?? "")) ||
          (params.completion_summary !== undefined && params.status !== "complete") ||
          undeclaredKeys(params, UPDATE_GOAL_PARAMS).length > 0) {
        return result({subject:"update not applied",summary:"Choose a status or a complete objective revision, and send only its fields."},true);
      }
      if (revision) return revise(core,ctx,goal,params.objective);
      if (params.status === "complete") return completeGoal(core,ctx,goal,core.settings(ctx),params.completion_summary,_signal);
      if (!params.reason?.trim()) return result({subject:"update not applied",summary:"Provide the reason for this status."},true);
      if (params.status === "blocked") {
        const blocked = core.reportBlocker(params.reason.trim());
        core.refreshUi(ctx); refreshGoalToolSurface(core,ctx);
        return result({subject:blocked ? "blocked" : "blocker reported",summary: blocked ? `${params.reason}\nUse /goal resume after resolving this blocker.` : `${params.reason}\nThe same blocker must recur on three consecutive turns before the goal is blocked.`});
      }
      if (!await core.pauseByUser(ctx,params.reason.trim())) return result({subject:"update not applied",summary:"The goal could not be paused."},true);
      refreshGoalToolSurface(core,ctx);
      return result({subject:"paused",summary:params.reason.trim()});
    },
  });
}

export function goalBody(goal: GoalRecord): string {
  return [`Objective:\n${goal.objective}`,
    goal.pauseReason ? `\nReason:\n${goal.pauseReason}` : "", `\nTokens used: ${goal.usage.tokensUsed}`].filter(Boolean).join("\n");
}

/**
 * The one way a goal's requirements change.
 *
 * A revision moves the objective and the start of the evidence window together.
 * Anything that writes only part of them keeps observations collected under the
 * old requirement admissible for the new one. The `update_goal` tool and a
 * `/goal <request>` that the model turns into a revision both land here, so the
 * two cannot drift apart.
 */
function applyRevision(
  store: GoalStore,
  goalId: string,
  objective: string,
): { ok: true; goal: GoalRecord } | { ok: false; message: string } {
  return store.apply({
    expectedGoalId: goalId,
    mutate: (draft) => {
      const changed = objective !== draft.objective;
      return {
        ...draft,
        ...(changed ? { evidenceSince: nowIso() } : {}),
        objective,
      };
    },
  });
}

function revise(
  core: GoalCore,
  ctx: ExtensionContext,
  goal: GoalRecord,
  objective: string | undefined,
) {
  const nextObjective = objective?.trim();
  if (nextObjective !== undefined && !nextObjective) {
    return result({ subject: "update not applied", summary: "Choose a nonempty objective." }, true);
  }
  // Lifecycle state is checked even though `update_goal` is withdrawn for these
  // goals, because a call can arrive one transition late. A goal that has spent
  // its lifetime cap and a completed goal have both ended; rewriting the
  // requirements of either would revive work that stopped.
  if (goal.status !== "active" && goal.status !== "paused" && goal.status !== "blocked") {
    return result(
      { subject: "update not applied", summary: `A ${goal.status} goal cannot be revised. Use /goal clear, then /goal <objective> to start a new goal.` },
      true,
    );
  }
  const outcome = applyRevision(
    core.store,
    goal.id,
    nextObjective ?? goal.objective,
  );
  if (!outcome.ok) return result({ subject: "update not applied", summary: outcome.message }, true);
  if (outcome.goal.objective !== goal.objective) core.requirementsChanged();
  const activated = core.activateRequestedRevision(goal.id, ctx);
  core.refreshUi(ctx);
  refreshGoalToolSurface(core, ctx);
  return result({
    subject: "updated",
    summary: `${goalBody(outcome.goal)}${activated === false ? "\n\nThe revision was saved, but continuation is blocked by its current limits." : ""}`,
  });
}

async function completeGoal(core: GoalCore, ctx: ExtensionContext, goal: GoalRecord, settings: GoalSettings, claim: string | undefined, signal?: AbortSignal) {
  const verdict = await core.check(ctx,goal,claim,settings,signal);
  if (!verdict.met) {
    refreshGoalToolSurface(core,ctx); core.refreshUi(ctx);
    const subject = verdict.stale ? "check discarded" : verdict.cancelled ? "check cancelled" : verdict.error ? "check failed" : "not met";
    // The tool owns this result, so a check failure is reported here rather than as
    // a second error row.
    return result({subject,summary:verdict.error ?? verdict.report},!!verdict.error);
  }
  const outcome = core.completeCheckedGoal(ctx,goal);
  if (!outcome.ok) return result({subject:"check discarded",summary:outcome.message},true);
  refreshGoalToolSurface(core,ctx); core.refreshUi(ctx);
  return {...result({subject:"completed",summary:verdict.report}),terminate:true};
}

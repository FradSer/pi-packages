/**
 * The goal status row: one passive line below the editor.
 *
 * Rendered directly through `ui.setWidget` rather than pi-kit's live-activity
 * row, because that row language always prefixes a spinner and this one must
 * read as `<verb> · <elapsed>` — e.g. `Pursuing goal · 2h 15m`. The component exposes only `render` and `invalidate`, so it is passive and owns no input.
 */
import { truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { GoalCore } from "./core.ts";
import { formatElapsed, type GoalRecord } from "./record.ts";

/** One passive widget below the editor. It never owns input. The goal row reads
 * `<verb> · <elapsed>` without a tag. A running check replaces it with one
 * neutral activity line, for the same reason: the row already belongs to this
 * goal, so a `[goal]` heading above it says nothing new. No goal id appears,
 * because a session holds one goal. */
function statusRow(core: GoalCore): string[] {
  if (core.checkProgress) return [core.checkProgress];
  const goal = core.goal;
  if (!goal) return [];
  return [`${goalPhrase(goal, core)} · ${formatElapsed(goal.usage.activeSeconds)}`];
}

const mounted = new WeakMap<ExtensionContext["ui"], { core: GoalCore; requestRender: () => void }>();

function mountStatusWidget(core: GoalCore, ctx: ExtensionContext): void {
  if (statusRow(core).length === 0) {
    if (mounted.has(ctx.ui)) clearDashboard(ctx);
    return;
  }
  const widget = mounted.get(ctx.ui);
  if (widget?.core === core) { widget.requestRender(); return; }
  ctx.ui?.setWidget(
    "goal-status",
    (tui) => {
      mounted.set(ctx.ui, { core, requestRender: () => tui.requestRender() });
      return {
        render: (width: number) => statusRow(core).flatMap((line) => wrapTextWithAnsi(line, Math.max(1, width))).map((line) => truncateToWidth(line, width, "", true)),
        invalidate: () => tui.requestRender(),
      };
    },
    { placement: "belowEditor" },
  );
}

export function refreshDashboard(core: GoalCore, ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;
  mountStatusWidget(core, ctx);
}

export function clearDashboard(ctx: ExtensionContext): void {
  mounted.delete(ctx.ui);
  ctx.ui?.setWidget("goal-status", undefined);
}

/** The verb for one goal state. A session holds one goal, so naming it or
 * printing its id adds noise to every line the reader sees. The status belongs
 * in the verb, and the elapsed time is the only progress figure a goal has. */
function goalPhrase(goal: GoalRecord, core: GoalCore): string {
  if (goal.status === "active") return goal.autoContinue && (core.scheduler?.isRunning() || core.scheduler?.isArmed() || goal.scheduler?.phase === "claimed") ? "Pursuing goal" : "Goal waiting";
  if (goal.status === "paused") return "Goal paused";
  return "Goal blocked";
}


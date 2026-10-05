/**
 * The goal status row: one passive line below the editor.
 *
 * Rendered directly through `ui.setWidget` rather than pi-kit's live-activity
 * row, because that row language always prefixes a status marker and this one
 * must read as a plain sentence — `Pursuing goal · 2h 15m`. The component
 * exposes only `render` and `invalidate`, so it is passive and owns no input.
 */
import { truncateToWidth } from "@earendil-works/pi-tui";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { GoalCore } from "./core.ts";
import { formatElapsed, type GoalRecord } from "./record.ts";

/** One passive row below the editor. It is never interactive and never owns
 * input: a widget that grabs keys cannot be dismissed predictably.
 *
 * The row is a plain sentence — `Pursuing goal · 2h 15m` — with no leading status
 * glyph and no goal id. A session holds exactly one goal, so naming it would add
 * noise to every line the reader sees. */
function statusRow(core: GoalCore): string {
  const goal = core.goal;
  if (core.checkProgress) return core.checkProgress.label;
  if (!goal) return "";
  return `${goalPhrase(goal)} · ${formatElapsed(goal.usage.activeSeconds)}`;
}

function mountStatusWidget(core: GoalCore, ctx: ExtensionContext): void {
  // No focused goal means no status row at all. Mounting one anyway would show
  // progress for work this session is not doing, and would claim a goal the
  // user never focused.
  if (!statusRow(core)) {
    ctx.ui?.setWidget("goal-status", undefined);
    return;
  }
  ctx.ui?.setWidget(
    "goal-status",
    (tui) => ({
      render: (width: number) => {
        const text = statusRow(core);
        return text ? [truncateToWidth(text, width, "…", true)] : [];
      },
      invalidate: () => tui.requestRender(),
    }),
    { placement: "belowEditor" },
  );
}

export function refreshDashboard(core: GoalCore, ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;
  mountStatusWidget(core, ctx);
}

export function clearDashboard(ctx: ExtensionContext): void {
  ctx.ui?.setWidget("goal-status", undefined);
}

/** The row reads as a sentence, not as fields: "Pursuing goal · 2h 15m".
 *
 * A session holds one goal, so naming it or printing its id adds noise to every
 * line the reader sees. The status belongs in the verb, and the elapsed time is
 * the only progress figure a goal has. */
function goalPhrase(goal: GoalRecord): string {
  if (goal.status === "active") return goal.autoContinue ? "Pursuing goal" : "Goal held";
  if (goal.status === "paused") return "Goal paused";
  if (goal.status === "budget_limited") return "Goal budget limited";
  return "Goal blocked";
}



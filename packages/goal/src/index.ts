/**
 * Goal runtime for Pi.
 *
 * A durable objective, automatic continuation, and a one-shot completion check. The installer wires the pieces and owns nothing: state
 * lives in GoalCore, every write goes through the store, and every scheduling
 * decision is durable before it can authorize a run.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { GoalCore, type GoalCoreOptions } from "./core.ts";
import { registerGoalCommands } from "./commands.ts";
import { registerGoalEvents } from "./events.ts";
import { registerGoalTools } from "./tools.ts";
import { refreshDashboard } from "./dashboard.ts";

/**
 * Dependencies are injectable so a test harness can supply its own verdict and
 * a fixed project root. Nothing in production passes either; the default
 * resolution is what a real install runs.
 */
export default function goalExtension(pi: ExtensionAPI, dependencies: GoalCoreOptions = {}): void {
  const core = new GoalCore(pi, dependencies.projectRoot ?? process.cwd(), dependencies);
  core.onRefresh = (ctx) => refreshDashboard(core, ctx);
  registerGoalTools(core);
  registerGoalCommands(core);
  registerGoalEvents(core);
  // Exposed so the test harness can drive the runtime without reaching into
  // module internals. Read-only hook; no behavior depends on it.
  (pi as unknown as { _goalCore?: GoalCore })._goalCore = core;
}



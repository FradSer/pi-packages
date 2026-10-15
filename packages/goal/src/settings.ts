/**
 * Layered settings: global defaults, then a project override, then the
 * environment. A later layer wins per field, not wholesale, so setting one
 * project option does not silently reset the others.
 *
 * `undefined` means "not set at this layer" and falls through. `null` is not
 * accepted as a value: clearing an override means removing it from the file, so
 * an inherited default can never be turned into "no value" by accident.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { nonEmpty, parseModelRef, writeJsonAtomic } from "@fradser/pi-kit";
import { GOALS_DIR, agentDir, goalsPlacementRefusal } from "./paths.ts";

export interface GoalSettings {
  /** Lifetime automatic continuation allowance. Undefined is
   * unlimited; 0 disables automatic continuation entirely. */
  maxAutonomousRuns?: number;
  /** Provider and model the completion check uses instead of the session's. */
  provider?: string;
  model?: string;

}

/** Project override file, inside the goals directory so a project's goal state
 * and its goal settings live together and travel with the project. */
function projectSettingsPath(projectRoot: string): string {
  return path.join(projectRoot, GOALS_DIR, "settings.json");
}

/** Global defaults, under the agent directory so they apply everywhere. */
function globalSettingsPath(): string {
  return path.join(agentDir(), "goal.json");
}

function readSettingsFile(file: string): Partial<GoalSettings> {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(file, "utf-8"));
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as Partial<GoalSettings>;
  } catch {
    // An unreadable or malformed settings file is treated as absent rather than
    // fatal: losing a preference must never stop the session from working.
    return {};
  }
}

/** Accept a value only if it is of the right shape, so one bad field cannot
 * make the whole layer unusable. */
function sanitize(raw: Partial<GoalSettings>): Partial<GoalSettings> {
  const out: Partial<GoalSettings> = {};
  if (typeof raw.maxAutonomousRuns === "number" && Number.isSafeInteger(raw.maxAutonomousRuns) && raw.maxAutonomousRuns >= 0) {
    out.maxAutonomousRuns = raw.maxAutonomousRuns;
  }
  if (nonEmpty(raw.provider)) out.provider = raw.provider;
  if (nonEmpty(raw.model)) out.model = raw.model;
  return out;
}

/** Global defaults with the project override applied on top, then the
 * environment last so a one-off run can override a saved preference. */
export function loadGoalSettings(projectRoot: string): GoalSettings {
  const resolved: GoalSettings = {
    ...sanitize(readSettingsFile(globalSettingsPath())),
    ...sanitize(readSettingsFile(projectSettingsPath(projectRoot))),
  };
  const envModel = parseModelRef(process.env.PI_GOAL_MODEL);
  const envProvider = nonEmpty(process.env.PI_GOAL_PROVIDER);
  if (envModel?.provider) resolved.provider = envModel.provider;
  if (envModel?.model) resolved.model = envModel.model;
  if (envProvider) resolved.provider = envProvider;
  const envRuns = process.env.PI_GOAL_MAX_RUNS;
  if (envRuns !== undefined && /^\d+$/.test(envRuns)) resolved.maxAutonomousRuns = Number.parseInt(envRuns, 10);
  return resolved;
}

/**
 * Write the project override.
 *
 * The refusal is returned rather than thrown: this writes into the goals
 * directory, so it refuses exactly when goal creation refuses, and a settings
 * save must not be the one path that recreates a directory goal creation
 * rejected.
 */
export function writeProjectSettings(projectRoot: string, settings: GoalSettings): { ok: true } | { ok: false; message: string } {
  const refusal = goalsPlacementRefusal(projectRoot);
  if (refusal) return { ok: false, message: refusal };
  const file = projectSettingsPath(projectRoot);
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeJsonAtomic(file, settings);
  return { ok: true };
}

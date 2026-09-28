/**
 * The roster: the long-lived child processes this session knows about.
 *
 * Owned here because a child process is an execution fact, not a coordination
 * fact. `@fradser/pi-tasks` refuses to know what a resident is, and a package that
 * only manages a board must therefore be able to run without this module at all;
 * a package that spawns children cannot.
 *
 * `assignment` and `currentTaskId` reference the task domain, so this module
 * imports `@fradser/pi-tasks`. That is the allowed direction: the domain does not
 * import the process layer, and nothing here creates or reads a task.
 *
 * The map is exported by identity rather than copied, so a consumer's snapshot can
 * point at it directly. That is what keeps the roster out of the snapshot schema
 * without a version bump, and it mirrors how `@fradser/pi-tasks` exports its own
 * board map.
 */

import type { WorkAssignment } from "@fradser/pi-tasks";
import type { ChildEnvDiagnostic } from "./child-env.ts";
import type { WorkerUsage } from "./types.ts";

/** Lifecycle of one resident child process.
 *
 * A plain union rather than a TypeBox schema: the runtime value existed only to
 * be converted straight back with `Static<>`, and no tool parameter uses it, so
 * keeping it would make this package depend on typebox for nothing. This is the
 * same reduction `@fradser/pi-tasks` applied to `TaskStatus`. */
export type TeammateStatus = "starting" | "idle" | "working" | "stopped";

/** One named child Pi process on the roster. */
export interface Teammate {
  /** Unique among living teammates; also the mailbox and roster key. */
  name: string;
  /** Resolved agent definition name. */
  agent: string;
  /** Per-spawn capability identity, regenerated for every process. */
  spawnId: string;
  /** Task currently held by this teammate, if any. */
  workId?: string;
  context?: "fresh" | "fork";
  pid: number;
  status: TeammateStatus;
  /** Working directory of the child. */
  cwd?: string;
  /** Whether this teammate owns a dedicated Git worktree. */
  isolation: "worktree" | "none";
  currentTaskId?: string;
  /** The one assignment this child is allowed to execute. */
  assignment?: WorkAssignment;
  /** Most recent assignment retained for successor handoff after release or shutdown. */
  lastAssignment?: WorkAssignment;
  lastTaskId?: string;
  /** Effective launch model reference ("provider/model"); absent when Pi picks its default. */
  model?: string;
  /** Live assistant text assembled from the RPC stream. */
  liveText?: string;
  /** Current child tool name, if a tool is executing. */
  activeTool?: string;
  /** Live assistant reasoning streamed while no tool runs. */
  liveThinking?: string;
  /** Assistant turns observed in the current wake-up sequence. */
  turns?: number;
  /** The child finished its current sequence and awaits the next prompt. */
  sequenceEnded?: boolean;
  /** Reports are closed until a new prompt starts after a terminal report. */
  reportSequenceEnded?: boolean;
  /** When the harness last sent a claimable-task notice to this teammate. */
  lastNoticeAt?: number;
  /** Task ids already announced to this teammate; one notice per id until it re-arms. */
  noticedTaskIds?: string[];
  usage?: WorkerUsage;
  error?: string;
  /** Effective tool allowlist granted to the child process. */
  tools?: string[];
  /** What the spawn environment policy withheld from this child. Names and
   *  counts only, never values. Console telemetry, never a notification. */
  envPolicy?: ChildEnvDiagnostic;
  /** True once recognized model/stream activity was observed for this
   *  incarnation; console telemetry only, never a notification. */
  modelOutputSeen?: boolean;
  createdAt: number;
  updatedAt: number;
  stoppedAt?: number;
  /** Last wall-clock time output was observed. */
  lastOutputAt?: number;
}

/** The live roster, exported by identity.
 *
 * Created without a prototype: a teammate named `constructor` is a legal name, so
 * the map must not inherit one. */
export const teammates: Record<string, Teammate> = Object.create(null);

let rosterRevisionCounter = 0;
let progressRevisionCounter = 0;
/** Revision of the worker-readable roster. A streamed token must not bump it, or
 *  every running child would rewrite the roster on every frame. */
export function rosterRevision(): number {
  return rosterRevisionCounter;
}

/** Revision of streamed progress only; never persisted on its own. */
export function progressRevision(): number {
  return progressRevisionCounter;
}

/** Drop every teammate and reset the counters. A session restart must not inherit
 *  a roster from the previous one, or a stale child handle would still resolve. */
export function resetRoster(): void {
  for (const name of Object.keys(teammates)) delete teammates[name];
  rosterRevisionCounter++;
  progressRevisionCounter++;
}

const NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

export function isValidTeammateName(name: string): boolean {
  return NAME_PATTERN.test(name);
}

export function getTeammate(name: string): Teammate | undefined {
  return teammates[name];
}

export function listTeammates(): Teammate[] {
  return Object.values(teammates).sort((a, b) => a.createdAt - b.createdAt);
}

export function livingTeammates(): Teammate[] {
  return listTeammates().filter((t) => t.status !== "stopped");
}

export function idleTeammates(): Teammate[] {
  return livingTeammates().filter((t) => t.status === "idle");
}

export function registerTeammate(teammate: Teammate): { ok: true } | { ok: false; error: string } {
  if (!isValidTeammateName(teammate.name)) {
    return { ok: false, error: `Invalid teammate name "${teammate.name}". Use letters, digits, dots, dashes, underscores.` };
  }
  if (livingTeammates().some((t) => t.name === teammate.name)) {
    // Named as a precondition because the obvious next move is to spawn again
    // with the same name and get this same refusal forever. The caller has to
    // inspect or stop the living incarnation first.
    return {
      ok: false,
      error: `A living teammate named "${teammate.name}" already exists. Inspect it with agent action=inspect, or stop that incarnation with agent action=stop, then start again.`,
    };
  }
  teammates[teammate.name] = teammate;
  rosterRevisionCounter++;
  return { ok: true };
}

/** Fields whose change is stream progress rather than persisted state. A progress
 *  tick must not republish the roster. */
const VOLATILE_TEAMMATE_FIELDS = new Set<string>([
  "liveText",
  "liveThinking",
  "activeTool",
  "turns",
  "sequenceEnded",
  "modelOutputSeen",
  "usage",
  "lastOutputAt",
  "updatedAt",
  "lastNoticeAt",
  "noticedTaskIds",
]);

export function updateTeammate(name: string, patch: Partial<Teammate>): Teammate | undefined {
  const teammate = teammates[name];
  if (!teammate) return undefined;
  const changed = (Object.keys(patch) as Array<keyof Teammate>)
    .filter((field) => !Object.is(teammate[field], patch[field]));
  Object.assign(teammate, patch, { updatedAt: Date.now() });
  if (patch.status === "stopped") teammate.stoppedAt = Date.now();
  if (changed.some((field) => !VOLATILE_TEAMMATE_FIELDS.has(field as string))) {
    rosterRevisionCounter++;
  } else if (changed.length > 0) {
    progressRevisionCounter++;
  }
  return teammate;
}

/** Merge an assignment into a living teammate, retaining the previous one for
 *  successor handoff. */
export function assignTeammate(
  name: string,
  assignment: WorkAssignment | undefined,
  currentTaskId?: string,
): Teammate | undefined {
  const teammate = getTeammate(name);
  if (!teammate) return undefined;
  const lastAssignment = assignment ?? teammate.assignment ?? teammate.lastAssignment;
  const lastTaskId = currentTaskId ?? teammate.currentTaskId ?? teammate.lastTaskId;
  return updateTeammate(name, {
    assignment,
    currentTaskId,
    lastAssignment,
    lastTaskId,
    ...(assignment && assignment.id !== teammate.assignment?.id ? { reportSequenceEnded: false } : {}),
  });
}

/** Merge streaming child-process progress. Bound to `spawnId` so a retired
 *  incarnation's late frames cannot revive a replaced one. */
export function updateTeammateProgress(
  name: string,
  spawnId: string,
  progress: Pick<Teammate, "liveText" | "activeTool" | "liveThinking" | "turns"> & {
    sequenceEnded?: boolean;
    modelOutputSeen?: boolean;
    usage?: WorkerUsage;
  },
): boolean {
  const teammate = teammates[name];
  if (!teammate || teammate.spawnId !== spawnId) return false;
  const changed = teammate.liveText !== progress.liveText
    || teammate.activeTool !== progress.activeTool
    || teammate.liveThinking !== progress.liveThinking
    || teammate.turns !== progress.turns
    || (progress.sequenceEnded !== undefined && teammate.sequenceEnded !== progress.sequenceEnded)
    || (progress.modelOutputSeen === true && teammate.modelOutputSeen !== true);
  teammate.liveText = progress.liveText;
  teammate.activeTool = progress.activeTool;
  teammate.liveThinking = progress.liveThinking;
  teammate.turns = progress.turns;
  if (progress.sequenceEnded !== undefined) teammate.sequenceEnded = progress.sequenceEnded;
  if (progress.modelOutputSeen) teammate.modelOutputSeen = true;
  if (progress.usage) teammate.usage = progress.usage;
  if (teammate.status === "starting") {
    teammate.status = progress.sequenceEnded ? "idle" : "working";
    // A status transition is roster state, not stream noise.
    rosterRevisionCounter++;
  }
  teammate.updatedAt = Date.now();
  if (changed) progressRevisionCounter++;
  return true;
}

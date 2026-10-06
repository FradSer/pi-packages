/**
 * The roster: the long-lived child processes this session knows about.
 *
 * Owned here because a child process is an execution fact, not a coordination
 * fact. `@fradser/pi-tasks` refuses to know what a resident is, and a package that
 * only manages a task set must therefore be able to run without this module at all;
 * a package that spawns children cannot.
 *
 * **This module imports no other Pi package.** Not the task domain, not a team
 * runtime. What a holder is holding is described structurally, in
 * `./participant-registry.ts`, because the two halves of that integration meet at a
 * published shape rather than at an import: a process roster that named the
 * tasks's domain would make every execution-layer install drag the tasks along,
 * and would put the dependency direction the other way round for the two packages
 * whose whole split is that neither knows the other's shape.
 *
 * The map is exported by identity rather than copied, so a consumer's snapshot can
 * point at it directly. That is what keeps the roster out of the snapshot schema
 * without a version bump, and it mirrors how `@fradser/pi-tasks` exports its own
 * tasks map.
 */

import type { AgentScope } from "./agents.ts";
import type { ChildEnvDiagnostic } from "./child-env.ts";
import type { ParticipantAssignment } from "./participant-registry.ts";
import type { AgentUsage } from "./types.ts";
import type { UnansweredReason } from "./session-result.ts";

/** Lifecycle of one resident child process.
 *
 * A plain union rather than a TypeBox schema: the runtime value existed only to
 * be converted straight back with `Static<>`, and no tool parameter uses it, so
 * keeping it would make this package depend on typebox for nothing. This is the
 * same reduction `@fradser/pi-tasks` applied to `TaskStatus`. */
export type AgentStatus = "starting" | "idle" | "working" | "stopped";

/** One named child Pi process on the roster. */
export interface Agent {
  /** Unique among living agents; also the mailbox and roster key. */
  name: string;
  /** The resolved role this agent runs: the definition name it was started with. */
  role: string;
  /** Display label; never an identity selector or control address. */
  label?: string;
  /** Explicit disk identity selected by the new model interface. */
  identity?: string;
  /** Current accepted input reservation, independent of task acceptance. */
  inputId?: string;
  /** Per-spawn capability identity, regenerated for every process. */
  spawnId: string;
  /** Task currently held by this agent, if any. */
  workId?: string;
  context?: "fresh" | "fork";
  pid: number;
  status: AgentStatus;
  /** This incarnation is owned by the standalone execution path, not a host. */
  standalone?: boolean;
  /** Scope pinned at launch. Only disk definitions have non-session scope. */
  scope?: AgentScope;
  /** Absolute canonical agent.md source; absent for an inline role. */
  source?: string;
  /** Working directory of the child, normally the original project. */
  cwd?: string;
  /** Original project path, separate from ordinary scratch storage. */
  projectCwd?: string;
  /** Ordinary private scratch directory, only for a disk-defined identity. */
  workspacePath?: string;
  /** Private project-scoped history, only for a disk-defined identity. */
  sessionDir?: string;
  currentTaskId?: string;
  /** The one assignment this child is allowed to execute. Described
   *  structurally, in the shape a published registry hands over: this roster
   *  stores what it is given and reads three fields of it. */
  assignment?: ParticipantAssignment;
  /** Most recent assignment retained for successor handoff after release or shutdown. */
  lastAssignment?: ParticipantAssignment;
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
  /** Observed settled output classification, never a semantic acceptance verdict. */
  resultKind?: "result" | "unanswered";
  unansweredReason?: UnansweredReason;
  stopReason?: string;
  finalDiagnostic?: string;
  /** The Leader asked for this child to stop, so its ending is planned rather
   *  than a death. Cleared by the next start, which reserves a fresh entry. */
  leaderRequestedEnd?: boolean;
  /** Reports are closed until a new prompt starts after a terminal report. */
  reportSequenceEnded?: boolean;
  /** When the harness last sent a claimable-task notice to this agent. */
  lastNoticeAt?: number;
  /** Task ids already announced to this agent; one notice per id until it re-arms. */
  noticedTaskIds?: string[];
  usage?: AgentUsage;
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

/**
 * The live roster, exported by identity.
 *
 * Created without a prototype: an agent named `constructor` is a legal name, so
 * the map must not inherit one.
 *
 * Held on `globalThis` under a `Symbol.for` key rather than in a module variable,
 * for the same reason the published host is. Pi loads each installed package with
 * its own module root, so the team runtime's roster and the agent tool's roster can
 * be two module instances — and then a spawn writes a child the leader cannot
 * list, which is how a real child ended up invisible one call after it started.
 * Sharing the object is what lets `list` see what `start` just wrote.
 */
const ROSTER_KEY = Symbol.for("fradser.pi-subagents.roster");
/** Revisions live beside the map, on the same `globalThis` carrier, for the same
 *  reason the map does. Two module instances are the normal case here, and a
 *  counter that one instance cannot see leaves the other instance deciding that
 *  nothing changed — so a roster write is never republished to the children that
 *  read it. */
const ROSTER_REVISIONS_KEY = Symbol.for("fradser.pi-subagents.roster-revisions");

const ROSTER_LISTENERS_KEY = Symbol.for("fradser.pi-subagents.roster-listeners");

interface RosterCarrier {
  [ROSTER_KEY]?: Record<string, Agent>;
  [ROSTER_REVISIONS_KEY]?: { roster: number; progress: number };
  [ROSTER_LISTENERS_KEY]?: Set<() => void>;
}

const carrier = globalThis as RosterCarrier;

export const agents: Record<string, Agent> = carrier[ROSTER_KEY]
  ?? (carrier[ROSTER_KEY] = Object.create(null));

const revisions = carrier[ROSTER_REVISIONS_KEY] ?? (carrier[ROSTER_REVISIONS_KEY] = { roster: 0, progress: 0 });
const listeners = carrier[ROSTER_LISTENERS_KEY] ?? (carrier[ROSTER_LISTENERS_KEY] = new Set());

/** Observe state and stream changes across package module roots without polling. */
export function observeAgentRoster(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function notifyRosterChange(): void {
  for (const listener of [...listeners]) {
    try { listener(); } catch (error) {
      // A failed UI observer cannot invalidate accepted input or lose a result.
      console.warn("[pi-subagents] roster observer failed:", error);
    }
  }
}
/** Revision of the Agent-readable roster. A streamed token must not bump it, or
 *  every running child would rewrite the roster on every frame. */
export function rosterRevision(): number {
  return revisions.roster;
}

/** Revision of streamed progress only; never persisted on its own. */
export function progressRevision(): number {
  return revisions.progress;
}

/** Drop every agent and reset the counters. A session restart must not inherit
 *  a roster from the previous one, or a stale child handle would still resolve. */
export function resetRoster(): void {
  for (const name of Object.keys(agents)) delete agents[name];
  revisions.roster++;
  revisions.progress++;
  notifyRosterChange();
}

const NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

export function isValidAgentName(name: string): boolean {
  return NAME_PATTERN.test(name);
}

export function getAgent(name: string): Agent | undefined {
  return agents[name];
}

export function listAgents(): Agent[] {
  return Object.values(agents).sort((a, b) => a.createdAt - b.createdAt);
}

export function livingAgents(): Agent[] {
  return listAgents().filter((t) => t.status !== "stopped");
}

export function idleAgents(): Agent[] {
  return livingAgents().filter((t) => t.status === "idle");
}

export function registerAgent(entry: Agent): { ok: true } | { ok: false; error: string } {
  if (!isValidAgentName(entry.name)) {
    return { ok: false, error: `Invalid agent name "${entry.name}". Use letters, digits, dots, dashes, underscores.` };
  }
  if (livingAgents().some((t) => t.name === entry.name)) {
    // Named as a precondition because the obvious next move is to spawn again
    // with the same name and get this same refusal forever. The caller has to
    // address or stop the living incarnation first.
    return {
      ok: false,
      error: `A living agent named "${entry.name}" already exists. List the current handles with agent_list, or stop that incarnation with agent_stop, then start again.`,
    };
  }
  agents[entry.name] = entry;
  revisions.roster++;
  notifyRosterChange();
  return { ok: true };
}

/** Fields whose change is stream progress rather than persisted state. A progress
 *  tick must not republish the roster. */
const VOLATILE_AGENT_FIELDS = new Set<string>([
  "liveText",
  "inputId",
  "liveThinking",
  "activeTool",
  "turns",
  "sequenceEnded",
  "resultKind",
  "unansweredReason",
  "stopReason",
  "finalDiagnostic",
  "leaderRequestedEnd",
  "modelOutputSeen",
  "usage",
  "lastOutputAt",
  "updatedAt",
  "lastNoticeAt",
  "noticedTaskIds",
]);

export function updateAgent(name: string, patch: Partial<Agent>): Agent | undefined {
  const agent = agents[name];
  if (!agent) return undefined;
  const changed = (Object.keys(patch) as Array<keyof Agent>)
    .filter((field) => !Object.is(agent[field], patch[field]));
  Object.assign(agent, patch, { updatedAt: Date.now() });
  if (patch.status === "stopped") agent.stoppedAt = Date.now();
  if (changed.some((field) => !VOLATILE_AGENT_FIELDS.has(field as string))) {
    revisions.roster++;
  } else if (changed.length > 0) {
    revisions.progress++;
  }
  if (changed.length > 0) notifyRosterChange();
  return agent;
}

/** Merge an assignment into a living agent, retaining the previous one for
 *  successor handoff. */
export function assignAgent(
  name: string,
  assignment: ParticipantAssignment | undefined,
  currentTaskId?: string,
): Agent | undefined {
  const agent = getAgent(name);
  if (!agent) return undefined;
  const lastAssignment = assignment ?? agent.assignment ?? agent.lastAssignment;
  const lastTaskId = currentTaskId ?? agent.currentTaskId ?? agent.lastTaskId;
  return updateAgent(name, {
    assignment,
    currentTaskId,
    lastAssignment,
    lastTaskId,
    ...(assignment && assignment.id !== agent.assignment?.id ? { reportSequenceEnded: false } : {}),
  });
}

/** Merge streaming child-process progress. Bound to `spawnId` so a retired
 *  incarnation's late frames cannot revive a replaced one. */
export function updateAgentProgress(
  name: string,
  spawnId: string,
  progress: Pick<Agent, "liveText" | "activeTool" | "liveThinking" | "turns"> & {
    sequenceEnded?: boolean;
    modelOutputSeen?: boolean;
    usage?: AgentUsage;
  },
): boolean {
  const agent = agents[name];
  if (!agent || agent.spawnId !== spawnId) return false;
  const changed = agent.liveText !== progress.liveText
    || agent.activeTool !== progress.activeTool
    || agent.liveThinking !== progress.liveThinking
    || agent.turns !== progress.turns
    || (progress.sequenceEnded !== undefined && agent.sequenceEnded !== progress.sequenceEnded)
    || (progress.modelOutputSeen === true && agent.modelOutputSeen !== true);
  agent.liveText = progress.liveText;
  agent.activeTool = progress.activeTool;
  agent.liveThinking = progress.liveThinking;
  agent.turns = progress.turns;
  if (progress.sequenceEnded !== undefined) agent.sequenceEnded = progress.sequenceEnded;
  if (progress.modelOutputSeen) agent.modelOutputSeen = true;
  if (progress.usage) agent.usage = progress.usage;
  const transitioned = agent.status === "starting" && !agent.leaderRequestedEnd;
  if (transitioned) {
    agent.status = progress.sequenceEnded ? "idle" : "working";
    // A status transition is roster state, not stream noise.
    revisions.roster++;
  }
  agent.updatedAt = Date.now();
  if (changed) revisions.progress++;
  if (changed || transitioned) notifyRosterChange();
  return true;
}

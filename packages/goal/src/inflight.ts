/**
 * Observable work a Goal is waiting on.
 *
 * A long objective often delegates a bounded review or steer to a child. While
 * that child is running, the honest turn is a report with no new tool receipt:
 * re-dispatching, polling and inventing the result would all be wrong. The
 * runtime used to read that quiet turn as "nothing new", spend one of its three
 * chances, and then strand the goal at `Goal waiting` exactly when the child's
 * result was about to arrive.
 *
 * These are observations, not authorization. A living child only holds the
 * no-new-work window (and only for a bounded wait), and a completed child result
 * only counts as new work and re-arms a goal whose continuation was lost.
 * Neither grants a completion verdict, a mutation or a run on its own; arm/claim
 * and the completion check still own those.
 *
 * The roster is process-global, so an entry is trusted only when it names a live
 * process in this project. A crashed child or another session's child must not
 * hold this thread's window forever, and only a result actually observed in
 * this session can be treated as the work this Goal was waiting for.
 */

import fs from "node:fs";
import path from "node:path";
import type { SessionEntry } from "@earendil-works/pi-coding-agent";

/** The roster `packages/subagents` publishes on `globalThis`. Read structurally:
 * Goal has no dependency on that package, so two module roots still agree. */
const ROSTER_KEY = Symbol.for("fradser.pi-subagents.roster");

interface RosterEntry {
  status?: unknown;
  pid?: unknown;
  cwd?: unknown;
  projectCwd?: unknown;
}

/** Custom messages whose arrival means delegated work finished. These are the
 * same kinds `evidence.ts` collects as attributed results. */
const RESULT_MESSAGES = new Set([
  "monitor-result",
  "agent-teams-report",
  "subagents-session-result",
  "subagents-session-unanswered",
  "subagents-session-ended",
]);

function rosterEntries(): RosterEntry[] {
  const roster = (globalThis as Record<symbol, unknown>)[ROSTER_KEY];
  if (typeof roster !== "object" || roster === null || Array.isArray(roster)) return [];
  return Object.values(roster as Record<string, unknown>).filter(
    (value): value is RosterEntry => typeof value === "object" && value !== null,
  );
}

/** A child process is still alive. `pid 0` is a kill-to-process-group marker,
 * not a single live child, so it never counts. */
function processAlive(pid: unknown, cwd: string): boolean {
  if (typeof pid !== "number" || !Number.isSafeInteger(pid) || pid <= 0) return false;
  if (!cwd) return false;
  try {
    process.kill(pid, 0);
  } catch {
    // EPERM means the process exists but belongs to another user. Either way it
    // is not a live child this session can wait on, so it cannot hold the window.
    return false;
  }
  return true;
}

/** Whether a child this project owns is still working. `starting` and `working`
 * are the two in-flight states the roster publishes; `idle` and `stopped`, a
 * dead pid, and a child from another project are not in-flight work for this
 * Goal, so none of them may hold the window. */
function canonicalProjectCwd(value: string): string {
  let existing = path.resolve(value);
  const missing: string[] = [];
  for (;;) {
    try {
      const resolved = fs.realpathSync(existing);
      return missing.length === 0 ? resolved : path.join(resolved, ...missing.reverse());
    } catch {
      const parent = path.dirname(existing);
      if (parent === existing) return path.join(existing, ...missing.reverse());
      missing.push(path.basename(existing));
      existing = parent;
    }
  }
}

export function hasInFlightDelegatedWork(projectCwd: string | undefined, entries: readonly SessionEntry[] = []): boolean {
  const project = typeof projectCwd === "string" && projectCwd.trim()
    ? canonicalProjectCwd(projectCwd.trim()) : "";
  if (!project) return false;
  const rosterWork = rosterEntries().some(entry => {
    const status = entry.status;
    if (status !== "starting" && status !== "working") return false;
    const cwd = typeof entry.cwd === "string" ? entry.cwd : typeof entry.projectCwd === "string" ? entry.projectCwd : "";
    if (!cwd || canonicalProjectCwd(cwd) !== project) return false;
    return processAlive(entry.pid, cwd);
  });
  if (rosterWork) return true;
  const launched = new Set<string>();
  const terminals = new Set<string>();
  for (const entry of entries) {
    if (entry.type === "message" && entry.message.role === "toolResult" && entry.message.toolName === "monitor_start" && !entry.message.isError) {
      const id = monitorId(entry.message.details);
      if (id) launched.add(id);
    } else if (entry.type === "custom_message" && entry.customType === "monitor-result" && isDelegatedWorkResult(entry)) {
      const id = monitorId(entry.details);
      if (id) terminals.add(id);
    }
  }
  return [...launched].some(id => !terminals.has(id));
}

function monitorId(details: unknown): string | undefined {
  if (typeof details !== "object" || details === null) return undefined;
  const value = (details as Record<string, unknown>).monitorId;
  return typeof value === "string" && value && !/^monitor_\d+$/.test(value) ? value : undefined;
}

/** Whether a custom message is a completed delegated-work result. Reports that
 * are still running, and the Goal's own checkpoint/procedure rows, are not. */
export function isDelegatedWorkResult(message: {
  customType?: unknown;
  details?: unknown;
}): boolean {
  if (typeof message.customType !== "string" || !RESULT_MESSAGES.has(message.customType)) return false;
  const details = message.details;
  if (typeof details !== "object" || details === null) return false;
  const record = details as Record<string, unknown>;
  switch (message.customType) {
    case "monitor-result": {
      const result = record.result;
      if (typeof result !== "object" || result === null) return false;
      const status = (result as Record<string, unknown>).status;
      return status === "success" || status === "failure" || status === "timeout"
        || status === "result_missing" || status === "stopped";
    }
    case "agent-teams-report":
      return record.origin === "agent" && (record.status === "completed" || record.status === "failed") && record.finished === true;
    case "subagents-session-result":
      return record.kind === "result" && typeof record.session === "string" && typeof record.turn === "number";
    case "subagents-session-unanswered":
    case "subagents-session-ended":
      return typeof record.session === "string";
    default:
      return false;
  }
}

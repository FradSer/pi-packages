/**
 * Where goal state lives on disk, and the safety rules for every path that
 * reaches it.
 *
 * One directory per goal, holding the authoritative record, the user-editable
 * prose, and the append-only ledger. Splitting record from prose is what lets
 * the record go through pi-kit's atomic JSON write while the prose stays
 * ordinary text a person can open and edit without a serializer in the way.
 */

import * as os from "node:os";
import * as path from "node:path";
import { nonEmpty, safeFileName } from "@fradser/pi-kit";

/** Project-relative goals directory. Goals belong to a project, not to a
 * session, so several sessions can see the same open goals. */
export const GOALS_DIR = ".pi/goals";

export const ARCHIVED_GOALS_DIR = ".pi/goals/archived";

/** Directory holding one open goal. */
export function goalDir(projectRoot: string, goalId: string): string {
  return path.join(projectRoot, GOALS_DIR, safeGoalId(goalId));
}

/** Directory holding one archived goal. */
export function archivedGoalDir(projectRoot: string, goalId: string): string {
  return path.join(projectRoot, ARCHIVED_GOALS_DIR, safeGoalId(goalId));
}

/** The authoritative record. Written only through pi-kit's atomic write. */
export function goalRecordPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(projectRoot, goalId), "record.json");
}

/** The objective as editable prose. Plain Markdown, no metadata. */
export function goalPromptPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(projectRoot, goalId), "prompt.md");
}

/** Read-only research findings attached at creation. Material for the
 * objective, written only by the store, never read by the completion check. */
export function goalResearchPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(projectRoot, goalId), "research.md");
}

/** Directory holding this goal's exclusive-create claim markers. */
export function goalClaimDir(projectRoot: string, goalId: string): string {
  return path.join(goalDir(projectRoot, goalId), "claims");
}

/**
 * Reduce a goal id to one safe path segment.
 *
 * `safeFileName` escapes separators and traversal, and the length cap keeps a
 * caller-supplied id from producing a path the filesystem rejects outright.
 * The result is still checked against the goals directory before any write, so
 * a separator that survived escaping cannot escape it.
 */
export function safeGoalId(goalId: string): string {
  const safe = safeFileName(goalId).replace(/%/g, "_");
  return safe.slice(0, 96) || "goal";
}

/** Whether `candidate` resolves inside `root`. Every path built from a goal id
 * is checked with this before it is opened for writing. */
export function isInside(root: string, candidate: string): boolean {
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(candidate);
  if (resolved === resolvedRoot) return true;
  return resolved.startsWith(resolvedRoot + path.sep);
}

/** The directory holding every goal's files in this project. */
export function goalsRoot(projectRoot: string): string {
  return path.join(projectRoot, GOALS_DIR);
}

// ── placement ────────────────────────────────────────────────────────

/** Where pi keeps its own configuration. Moved here from the settings module
 * because placement is a path question, and the settings module already reads
 * from this one. */
export function agentDir(): string {
  const configured = nonEmpty(process.env.PI_CODING_AGENT_DIR);
  if (configured) {
    return configured === "~" || configured.startsWith("~/")
      ? path.join(process.env.HOME ?? os.homedir(), configured.slice(1))
      : configured;
  }
  return path.join(process.env.HOME ?? os.homedir(), ".pi", "agent");
}

/** Pi's own home, holding its sessions, memory, and install.
 *
 * This is `$HOME/.pi` and deliberately not the agent directory's parent: an
 * overridden agent directory is an isolation knob, and treating an arbitrary
 * directory as pi's home would make every project that happens to sit next to
 * it look nested. */
export function piHomeDir(): string {
  return path.join(process.env.HOME ?? os.homedir(), ".pi");
}

/**
 * Why the goals directory may not be created under this project root.
 *
 * The project root decides the whole path, so a session run from inside pi's
 * own layout puts a second `.pi` inside it: `~/.pi/.pi/goals`. A project at
 * the home directory does the same thing one level up, dropping a goals
 * directory next to pi's sessions and memory. Both are refused rather than
 * created, because a doubled directory is not a project a person can find.
 *
 * Only new state is refused. Reads, ledger appends, and an already stored goal
 * keep working where they are, so a goal created before this rule existed is
 * never stranded by it. Returns undefined when the placement is fine.
 */
export function goalsPlacementRefusal(projectRoot: string): string | undefined {
  const root = goalsRoot(path.resolve(projectRoot));
  const forbidden: [string, string][] = [[piHomeDir(), "Pi's home directory"], [agentDir(), "the agent directory"]];
  for (const [dir, what] of forbidden) {
    if (isInside(dir, root)) {
      return [
        `Goals cannot be stored in ${root}: this session's directory is inside ${what} (${dir}),`,
        "so the goals directory would nest a second .pi inside Pi's own layout.",
        "Start Pi from a project directory to use goals here.",
        "A goal already stored in that place keeps running.",
      ].join(" ");
    }
  }
  return undefined;
}
/**
 * Where goal state lives on disk, and the safety rules for every path that
 * reaches it.
 *
 * State lives under Pi's own agent directory, keyed by project, and not inside
 * the project: a goal is runtime state for the sessions that share a working
 * directory, and a `.pi/goals` tree inside the working tree leaves goal records,
 * claims and lock files behind in every repository a goal was ever started in.
 * The key keeps two projects apart, so a pool scan in one project never offers
 * another project's goal. A goal an earlier version stored inside a project is
 * still read, locked and written where it is, and nothing new is created there.
 *
 * One directory per goal holds the authoritative record and the claim markers
 * that serialize writes to it. The record goes through pi-kit's atomic JSON write.
 * A prose file written by an earlier version is left where it is and is never read
 * as the objective: the record holds the objective.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { safeFileName } from "@fradser/pi-kit";

/** Agent-directory subdirectory holding every project's goals. */
const GOALS_SUBDIR = "goals";

/** Project-relative directory an earlier version wrote. Nothing new is created
 * here; a goal already stored in one is still read and still mutated where it
 * lives, so moving the layout cannot strand it. */
export const LEGACY_GOALS_DIR = ".pi/goals";

/** Agent-directory subdirectory holding the settings for one project's goals. */
export const SETTINGS_FILE = "settings.json";

/** Cap on the byte length of one readable project key, well below the 255-byte
 * file-system limit so the goal directory name below it still fits. */
const SCOPE_MAX_BYTES = 160;

/** Hex length of the digest that keeps two lookalike project names apart. */
const SCOPE_DIGEST_CHARS = 8;

/** Where Pi keeps its own configuration. Placement is a path question, so this
 * lives here rather than in the settings module that reads it too. */
export function agentDir(): string {
  return getAgentDir();
}

/**
 * Reduce one project root to a single directory name.
 *
 * Readable, so a person can find a project's goals by looking at the agent
 * directory, and stable, because the path is made canonical first: two spellings
 * of one directory have to agree. The readable part is not an identity —
 * punctuation can collide, and `/a/b-c` and `/a-b/c` reduce to the same words —
 * so a short digest of the canonical path is always appended and two projects
 * never share one state directory.
 *
 * A path too long for one directory name is cut to fit instead of failing: a goal
 * must still be creatable from a deep directory.
 */
export function projectScopeKey(projectRoot: string): string {
  const canonical = canonicalProjectRoot(projectRoot);
  const digest = createHash("sha256").update(canonical).digest("hex").slice(0, SCOPE_DIGEST_CHARS);
  const readable = `--${canonical.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")}--${digest}`;
  if (Buffer.byteLength(readable, "utf8") <= SCOPE_MAX_BYTES) return readable;
  const room = SCOPE_MAX_BYTES - digest.length - 1;
  const head = Buffer.from(readable, "utf8").subarray(0, room).toString("utf8");
  return `${head.replace(/[\uFFFD-]+$/, "")}-${digest}`;
}

/** The directory spelling that has to be the same in every process, including one
 * whose project directory has since been removed. The deepest part of the path
 * that still exists is resolved and the rest is appended as written: resolving
 * only the whole path would fall back to a lexical spelling the moment the
 * directory disappeared, and the key would change under a goal still stored. */
function canonicalProjectRoot(projectRoot: string): string {
  let existing = path.resolve(projectRoot);
  const missing: string[] = [];
  for (;;) {
    try {
      const resolved = fs.realpathSync(existing);
      return missing.length === 0 ? resolved : path.join(resolved, ...missing.reverse());
    } catch {
      const parent = path.dirname(existing);
      // A resolved path always has a parent, so this terminates at the root.
      if (parent === existing) return path.join(existing, ...missing.reverse());
      missing.push(path.basename(existing));
      existing = parent;
    }
  }
}

/** The directory holding every goal's files for one project. */
export function goalsRoot(projectRoot: string): string {
  return path.join(agentDir(), GOALS_SUBDIR, projectScopeKey(projectRoot));
}

/** The directory an earlier version used for the same project. */
export function legacyGoalsRoot(projectRoot: string): string {
  return path.join(path.resolve(projectRoot), LEGACY_GOALS_DIR);
}

/** Directory holding one open goal. */
function goalDir(root: string, goalId: string): string {
  return path.join(root, safeGoalId(goalId));
}

/** The authoritative record. Written only through pi-kit's atomic write. */
export function goalRecordPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(goalsRoot(projectRoot), goalId), "record.json");
}

/** The record as an earlier version stored it, inside the project. */
export function legacyGoalRecordPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(legacyGoalsRoot(projectRoot), goalId), "record.json");
}

/** Where an earlier version kept the objective as editable prose. The record
 * holds the objective now, and this file is preserved but never read as it. */
export function legacyGoalPromptPath(projectRoot: string, goalId: string): string {
  return path.join(goalDir(legacyGoalsRoot(projectRoot), goalId), "prompt.md");
}

/** Directory holding this goal's exclusive-create claim markers. */
export function goalClaimDir(projectRoot: string, goalId: string): string {
  return path.join(goalDir(goalsRoot(projectRoot), goalId), "claims");
}

/** The claim directory an earlier version used, which is the one a goal stored
 * under that layout is still locked by. */
export function legacyGoalClaimDir(projectRoot: string, goalId: string): string {
  return path.join(goalDir(legacyGoalsRoot(projectRoot), goalId), "claims");
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
  const safe = safeFileName(goalId).replace(/%/g, "_").slice(0, 96);
  // `encodeURIComponent` leaves a dot alone, and a dot-only segment is not a name
  // below the goal directory: `..` addresses the directory above it.
  if (!safe || /^\.+$/.test(safe)) return "goal";
  return safe;
}

/** Whether `candidate` resolves inside `root`. Every path built from a goal id
 * is checked with this before it is opened for writing. */
export function isInside(root: string, candidate: string): boolean {
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(candidate);
  if (resolved === resolvedRoot) return true;
  return resolved.startsWith(resolvedRoot + path.sep);
}
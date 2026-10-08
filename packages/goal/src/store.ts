/** One mutation boundary: lock, reconcile, compare revision, atomically write
 * one Goal record or release it. Legacy history is never moved or removed. */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  createExclusiveJsonFile,
  safeFileName,
  writeJsonAtomic,
} from "@fradser/pi-kit";
import {
  GOALS_DIR,
  goalClaimDir,
  goalRecordPath,
  goalsRoot,
  goalsPlacementRefusal,
  isInside,
  safeGoalId,
} from "./paths.ts";
import {
  GOAL_RECORD_VERSION,
  cloneGoal,
  newGoalScheduler,
  normalizeGoalRecord,
  nowIso,
  type GoalRecord,
} from "./record.ts";

/** How long a write lock may sit before another writer treats it as abandoned.
 * A crashed process leaves its lock behind; without this the goal would be
 * unwritable until the directory was cleared by hand. */
const LOCK_STALE_MS = 30_000;
const LOCK_POLL_MS = 20;
const LOCK_TIMEOUT_MS = 2_000;

/** What a mutation may require before it runs. */
export interface GoalMutationSpec {
  /** If set, the focused goal must be this one. Rejects a call aimed at a goal
   * that was replaced while the caller was thinking about it. */
  expectedGoalId?: string;
  /** If set, the record on disk must carry this revision. This is the
   * cross-process lost-update guard. */
  expectedRevision?: number;
  /** Mutate a clone of the goal read from disk. Returning undefined aborts
   * without a write. */
  mutate: (goal: GoalRecord) => GoalRecord | undefined;
  /** Release the authoritative runtime record after the guarded mutation. */
  finish?: boolean;
}

export type GoalMutationOutcome =
  | { ok: true; goal: GoalRecord; diagnostics: string[] }
  | { ok: false; message: string; diagnostics: string[] };

export interface GoalStoreOptions {
  projectRoot: string;
}

export class GoalStore {
  private readonly projectRoot: string;

  constructor(options: GoalStoreOptions) {
    this.projectRoot = path.resolve(options.projectRoot);
  }

  // ── reads ──────────────────────────────────────────────────────────

  /**
   * Every open goal, in a deterministic order.
   *
   * A file that cannot be read or parsed is skipped rather than failing the
   * scan: one unreadable goal must not hide the rest of the pool. Symlinks are
   * never followed, so a link planted in the goals directory cannot pull a
   * record in from outside the project.
   */
  readPool(): GoalRecord[] {
    const root = goalsRoot(this.projectRoot);
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(root, { withFileTypes: true });
    } catch {
      return [];
    }
    const goals: GoalRecord[] = [];
    for (const entry of entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
      if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
      const record = this.readGoal(entry.name);
      // Completed legacy records do not authorize new work.
      if (record && record.status !== "complete") goals.push(record);
    }
    return goals;
  }

  /** One goal by id, or undefined. */
  readGoal(goalId: string): GoalRecord | undefined {
    const record = this.readRecordFile(goalRecordPath(this.projectRoot, goalId));
    return record;
  }

  /** Read straight from disk. The write path uses this so
   * a mutation always starts from what is actually stored. */
  readGoalFromDisk(goalId: string): GoalRecord | undefined {
    return this.readRecordFile(goalRecordPath(this.projectRoot, goalId));
  }

  /** The user-editable objective prose. */
  readPrompt(goalId: string): string {
    return this.readGoal(goalId)?.objective ?? "";
  }

  // ── writes ─────────────────────────────────────────────────────────

  /** Create one authoritative record before work begins. */
  create(input: {
    objective: string;
    contract?: string;
    tokenBudget?: number;
    owner: string;
    id: string;
    initialTokens?: number;
  }): GoalMutationOutcome {
    // Refused before anything is written, so a nested placement leaves no
    // directory behind for a later run to adopt. Reads and an already stored
    // goal are untouched, which is what keeps a goal created under an earlier
    // version running where it already lives.
    const refusal = goalsPlacementRefusal(this.projectRoot);
    if (refusal) return { ok: false, message: refusal, diagnostics: [] };
    const at = nowIso();
    const goal: GoalRecord = {
      id: input.id,
      threadId: input.owner,
      objective: input.objective,
      status: "active",
      autoContinue: true,
      usage: { tokensUsed: input.initialTokens ?? 0, activeSeconds: 0 },
      createdAt: at,
      updatedAt: at,
      revision: 0,
      scheduler: newGoalScheduler(input.owner, randomToken()),
    };
    if (input.contract) goal.verificationContract = input.contract;
    if (input.tokenBudget !== undefined && input.tokenBudget > 0) goal.tokenBudget = input.tokenBudget;
    if (goal.tokenBudget !== undefined && goal.usage.tokensUsed >= goal.tokenBudget) {
      goal.status = "budget_limited"; goal.autoContinue = false;
      goal.pauseReason = `The lifetime token cap of ${goal.tokenBudget} tokens was reached during creation.`;
    }
    goal.activePath = path.posix.join(GOALS_DIR, safeGoalId(input.id), "record.json");
    try {
      const locked: { ok: true; goal: GoalRecord } | { ok: false; message: string } =
        this.withLock(input.id, (stillHeld) => {
          if (this.readGoalFromDisk(input.id)) {
            return { ok: false as const, message: `A goal with that id already exists.` };
          }
          this.writeGoalFiles(goal, stillHeld);
          return { ok: true as const, goal };
        });
      if (!locked.ok) return { ...locked, diagnostics: [] };
      const diagnostics: string[] = [];
      return { ok: true, goal, diagnostics };
    } catch (error) {
      return { ok: false, message: `Goal creation failed: ${describe(error)}`, diagnostics: [] };
    }
  }

  /**
   * Run one ordered mutation. See the module comment for the pipeline.
   */
  apply(spec: GoalMutationSpec): GoalMutationOutcome {
    const goalId = spec.expectedGoalId;
    if (!goalId) return { ok: false, message: "No goal to mutate.", diagnostics: [] };
    try {
      const locked: { ok: true; goal: GoalRecord } | { ok: false; message: string } =
        this.withLock(goalId, (stillHeld) => {
          // 1. Reconcile: disk is authoritative.
          const current = this.readGoalFromDisk(goalId);
          if (!current) return { ok: false as const, message: `The goal no longer exists.` };
          // 2. Identity checks against the record just read.
          if (spec.expectedRevision !== undefined && current.revision !== spec.expectedRevision) {
            return {
              ok: false as const,
              message: `The goal changed underneath this write (expected revision ${spec.expectedRevision}, found ${current.revision}). Nothing was written.`,
            };
          }
          // 3. Mutate a clone.
          const draft = cloneGoal(current);
          const next = spec.mutate(draft);
          if (!next) {
            return { ok: false as const, message: `The change to the goal was declined; nothing was written.` };
          }
          next.revision = current.revision + 1;
          next.updatedAt = nowIso();
          // 4. Write or release under the same lock.
          let written: GoalRecord;
          // Verified last: if the lock was taken from us while we computed the
          // mutation, the revision we based it on is no longer the truth.
          stillHeld();
          if (spec.finish) {
            // Release only runtime files. Existing research and history are user
            // data and remain untouched; no archive directory is ever written.
            const record = goalRecordPath(this.projectRoot, goalId);
            this.assertSafePath(record);
            fs.unlinkSync(record);
            written = next;
          } else {
            this.writeGoalFiles(next, stillHeld);
            written = next;
          }
          return { ok: true as const, goal: written };
        });
      if (!locked.ok) return { ...locked, diagnostics: [] };
      const written = locked.goal;
      const diagnostics: string[] = [];
      return { ok: true, goal: written, diagnostics };
    } catch (error) {
      return { ok: false, message: describe(error), diagnostics: [] };
    }
  }

  // ── internals ──────────────────────────────────────────────────────

  /** Reject existing links below the trusted project root before file access.
   * This check does not provide a sandbox against concurrent directory replacement. */
  private assertSafePath(file: string): void {
    if (!isInside(this.projectRoot, file)) throw new Error("Goal path is outside the project.");
    const segments = path.relative(this.projectRoot, file).split(path.sep);
    let current = this.projectRoot;
    for (const segment of segments) {
      current = path.join(current, segment);
      const stats = fs.lstatSync(current, { throwIfNoEntry: false });
      if (stats?.isSymbolicLink()) throw new Error("Goal paths must not contain symbolic links.");
    }
  }

  private readRecordFile(file: string): GoalRecord | undefined {
    let raw: string;
    try {
      this.assertSafePath(file);
      const stats = fs.lstatSync(file);
      if (stats.isSymbolicLink() || !stats.isFile()) return undefined;
      raw = fs.readFileSync(file, "utf-8");
    } catch {
      return undefined;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return undefined;
    }
    // A version this version does not understand is refused rather than read on
    // its known fields, because a newer record's extra fields may carry the
    // state the missing ones would have.
    // A parsed `null` is a readable file that holds no record. It is skipped
    // like unreadable bytes, so one bad file never hides its valid siblings.
    if (typeof parsed !== "object" || parsed === null) return undefined;
    const version = typeof (parsed as { version?: unknown }).version === "number"
      ? (parsed as { version: number }).version
      : undefined;
    if (version !== undefined && version > GOAL_RECORD_VERSION) return undefined;
    return normalizeGoalRecord((parsed as { goal?: unknown }).goal ?? parsed);
  }

  private writeGoalFiles(goal: GoalRecord, stillHeld: () => void): void {
    const file = goalRecordPath(this.projectRoot, goal.id);
    if (!isInside(goalsRoot(this.projectRoot), file)) throw new Error("Goal path is outside its runtime directory.");
    this.assertSafePath(file);
    stillHeld();
    writeJsonAtomic(file, { version: GOAL_RECORD_VERSION, goal });
  }

  /**
   * Run `body` while holding this goal's write lock, passing it a guard.
   *
   * Exclusion is pi-kit's exclusive create: exactly one process can win
   * `createExclusiveJsonFile` for a given name, so the winner is the only
   * writer until it releases. A lock older than `LOCK_STALE_MS` is taken over,
   * because a process that died mid-write must not leave the goal unwritable.
   *
   * The guard is not decoration. A stale takeover deliberately breaks
   * exclusivity — that is what makes a crashed holder recoverable — so a
   * suspended holder can come back to find its lock already stolen. Without a
   * check immediately before the write, that holder would still rename its
   * temporary file over whatever the new holder committed, and two processes
   * would both believe they advanced the goal from the same revision. The
   * guard makes the loss visible: the displaced holder writes nothing.
   */
  private withLock<T>(goalId: string, body: (stillHeld: () => void) => T): T {
    const dir = goalClaimDir(this.projectRoot, goalId);
    const name = "write-lock";
    const file = path.join(dir, `${safeFileName(name)}.json`);
    this.assertSafePath(file);
    const token = randomToken();
    const deadline = Date.now() + LOCK_TIMEOUT_MS;
    for (;;) {
      if (createExclusiveJsonFile(dir, name, { token, at: Date.now() }, { label: "Goal write lock" })) break;
      // pi-kit's exclusive create returns false only on EEXIST, so the lock file
      // exists here and a genuinely abandoned lock can be taken over. Reporting a
      // missing file as stale would instead let a create that failed for an
      // unrelated reason spin here without sleeping or reaching the deadline.
      if (lockIsStale(file)) {
        try {
          fs.rmSync(file, { force: true });
        } catch {
          // Another writer won the takeover race; loop and contend normally.
        }
        continue;
      }
      if (Date.now() > deadline) {
        throw new Error(`The goal is locked by another writer. Nothing was written.`);
      }
      sleep(LOCK_POLL_MS);
    }
    try {
      return body(() => assertLockHeld(file, token));
    } finally {
      // Release only our own lock: a stale takeover may already hold it.
      try {
        if (readLockToken(file) === token) fs.rmSync(file, { force: true });
      } catch {
        // A lock that cannot be removed is taken over once it goes stale.
      }
    }
  }
}

/** Refuse to write once this holder's lock has been taken from it. */
function assertLockHeld(file: string, token: string): void {
  if (readLockToken(file) !== token) {
    throw new Error(
      `The goal lost its write lock while the change was being prepared, so the change was discarded `
        + `rather than written over another writer's.`,
    );
  }
}

function lockIsStale(file: string): boolean {
  try {
    return Date.now() - fs.statSync(file).mtimeMs > LOCK_STALE_MS;
  } catch {
    // The holder released between the failed create and this stat. There is no
    // lock to take over, so the caller retries instead of deleting anything.
    return false;
  }
}

function readLockToken(file: string): string | undefined {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(file, "utf-8"));
    const token = (parsed as { token?: unknown }).token;
    return typeof token === "string" ? token : undefined;
  } catch {
    return undefined;
  }
}

function sleep(milliseconds: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function randomToken(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function describe(error: unknown): string {
  if (error instanceof Error) {
    return error.message.replace(/,\s*(?:open|mkdir|rename|unlink|rmdir|copyfile|scandir|stat|lstat)\s+.*$/i, "").trim();
  }
  return String(error);
}

/** Exported for the tool layer, which needs a fresh id for a new goal. */
export function newGoalId(): string {
  return `goal_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}


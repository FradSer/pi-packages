/**
 * The sole mutation boundary for goal state.
 *
 * Every record write, prose write, archive, and ledger append in this package
 * goes through this module. That is the whole point of it: a goal is durable
 * state that several sessions and the agent itself write to, so a mutation
 * that skipped the ordered pipeline would be a mutation nobody could reason
 * about. Handlers validate and decide; they never touch storage.
 *
 *   reconcile from disk  (disk is the truth; no in-memory copy)
 *   -> identity checks   (expected goal id, expected revision)
 *   -> mutate a clone    (never the caller's live object)
 *   -> exclusive lock    (pi-kit exclusive create: one writer at a time)
 *   -> atomic write      (pi-kit atomic replace)
 *   -> archive           (when completing or clearing)
 *   -> ledger append     (best effort, after the authoritative write)
 *
 * If the write fails, nothing is committed and no event is appended. If the
 * ledger append fails after a successful write, the transition still stands and
 * the failure is returned as a diagnostic: the state change is real, and
 * dropping it because history could not be written would misrepresent reality.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  createExclusiveJsonFile,
  safeFileName,
  writeJsonAtomic,
} from "@fradser/pi-kit";
import {
  appendGoalEvents,
  readGoalHistoryPage,
  type GoalHistoryPage,
  type GoalLedgerEvent,
} from "./ledger.ts";
import {
  ARCHIVED_GOALS_DIR,
  GOALS_DIR,
  archivedGoalDir,
  goalClaimDir,
  goalDir,
  goalPromptPath,
  goalRecordPath,
  goalResearchPath,
  goalsRoot,
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
  /** Appended after the authoritative write. Best effort. */
  ledger?: GoalLedgerEvent[];
  /** Move the goal to the archive directory instead of writing it in place. */
  archive?: boolean;
  /** Also write `prompt.md`. Set when the objective changed. */
  writePrompt?: boolean;
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
      // A completed goal is archived, so one still sitting in the open pool is
      // a goal that finished without being archived. It is not offered as open
      // work: continuing it would be continuing something already done.
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
    try {
      return this.readProse(goalPromptPath(this.projectRoot, goalId));
    } catch {
      return "";
    }
  }

  /** Read-only research findings attached at creation, or "" when absent. */
  readResearch(goalId: string): string {
    try {
      return this.readProse(goalResearchPath(this.projectRoot, goalId));
    } catch {
      return "";
    }
  }

  /** One page of ledger history, from wherever the goal currently lives. */
  readHistory(goalId: string, cursor?: string, archived = false): GoalHistoryPage {
    return readGoalHistoryPage(this.projectRoot, goalId, cursor, undefined, archived);
  }

  /** Whether a goal is currently archived rather than open. */
  isArchived(goalId: string): boolean {
    return fs.existsSync(path.join(archivedGoalDir(this.projectRoot, goalId), "record.json"));
  }

  // ── writes ─────────────────────────────────────────────────────────

  /**
   * Create a goal. Write prose before the authoritative record.
   * A prose failure leaves no active goal and no creation event.
   *
   * `research` is pre-creation read-only findings. They are written through
   * this same locked path — the store stays the only writer — and their tokens
   * are seeded into usage, because spend attributed to the goal includes the
   * research that produced it. Findings written here never reach the
   * completion check.
   */
  create(input: {
    objective: string;
    contract?: string;
    tokenBudget?: number;
    owner: string;
    id: string;
    research?: { focus: string; text: string; tokens: number };
  }): GoalMutationOutcome {
    const at = nowIso();
    const goal: GoalRecord = {
      id: input.id,
      threadId: input.owner,
      objective: input.objective,
      status: "active",
      autoContinue: true,
      usage: { tokensUsed: Math.max(0, input.research?.tokens ?? 0), activeSeconds: 0 },
      createdAt: at,
      updatedAt: at,
      revision: 0,
      scheduler: newGoalScheduler(input.owner, randomToken()),
    };
    if (input.contract) goal.verificationContract = input.contract;
    if (input.tokenBudget !== undefined && input.tokenBudget > 0) goal.tokenBudget = input.tokenBudget;
    goal.activePath = path.posix.join(GOALS_DIR, safeGoalId(input.id), "record.json");
    try {
      const locked: { ok: true; goal: GoalRecord } | { ok: false; message: string } =
        this.withLock(input.id, (stillHeld) => {
          if (this.readGoalFromDisk(input.id)) {
            return { ok: false as const, message: `A goal with that id already exists.` };
          }
          this.writeGoalFiles(goal, { writePrompt: true, research: input.research?.text, recordLast: true }, stillHeld);
          return { ok: true as const, goal };
        });
      if (!locked.ok) return { ...locked, diagnostics: [] };
      const events: GoalLedgerEvent[] = [{
        type: "goal_created",
        goalId: goal.id,
        objective: goal.objective,
        autoContinue: goal.autoContinue,
        at,
      }];
      if (input.research) {
        events.push({
          type: "research_attached",
          goalId: goal.id,
          focus: input.research.focus.slice(0, 200),
          tokens: Math.max(0, input.research.tokens),
          at,
        });
      }
      const diagnostics = appendGoalEvents(this.projectRoot, events);
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
          // 4. Write (or archive) atomically.
          let written: GoalRecord;
          // Verified last: if the lock was taken from us while we computed the
          // mutation, the revision we based it on is no longer the truth.
          stillHeld();
          if (spec.archive) {
            written = this.archiveGoalFiles(next, stillHeld);
          } else {
            this.writeGoalFiles(next, { writePrompt: spec.writePrompt === true }, stillHeld);
            written = next;
          }
          return { ok: true as const, goal: written };
        });
      if (!locked.ok) return { ...locked, diagnostics: [] };
      const written = locked.goal;
      // 5. Ledger, best effort, after the authoritative write.
      // The archive moved the goal directory, history included, so an append
      // aimed at the open path would recreate an empty directory beside the
      // archive and leave the completing event in a ledger of its own.
      const diagnostics = spec.ledger?.length ? appendGoalEvents(this.projectRoot, spec.ledger, spec.archive === true) : [];
      return { ok: true, goal: written, diagnostics };
    } catch (error) {
      return { ok: false, message: describe(error), diagnostics: [] };
    }
  }

  /** Append events without a state change. Returns diagnostics for anything
   * that could not be written. */
  appendLedger(events: GoalLedgerEvent[], archived = false): string[] {
    return appendGoalEvents(this.projectRoot, events, archived);
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

  private readProse(file: string): string {
    this.assertSafePath(file);
    const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    try {
      if (!fs.fstatSync(fd).isFile()) return "";
      return fs.readFileSync(fd, "utf-8");
    } finally {
      fs.closeSync(fd);
    }
  }

  private readRecordFile(file: string): GoalRecord | undefined {
    let raw: string;
    try {
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

  private writeGoalFiles(goal: GoalRecord, options: { writePrompt: boolean; research?: string; recordLast?: boolean }, stillHeld: () => void = () => {}): void {
    const file = goalRecordPath(this.projectRoot, goal.id);
    if (!isInside(goalsRoot(this.projectRoot), file)) {
      throw new Error(`Refused to write outside the goals directory.`);
    }
    this.assertSafePath(file);
    if (options.writePrompt) this.assertSafePath(goalPromptPath(this.projectRoot, goal.id));
    if (options.research !== undefined) this.assertSafePath(goalResearchPath(this.projectRoot, goal.id));
    stillHeld();
    if (!options.recordLast) writeJsonAtomic(file, { version: GOAL_RECORD_VERSION, goal });
    if (options.writePrompt) {
      const prose = goalPromptPath(this.projectRoot, goal.id);
      fs.mkdirSync(path.dirname(prose), { recursive: true, mode: 0o700 });
      const fd = fs.openSync(prose, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_TRUNC | fs.constants.O_NOFOLLOW, 0o600);
      try {
        fs.writeFileSync(fd, `${goal.objective}\n`, "utf-8");
      } finally {
        fs.closeSync(fd);
      }
    }
    if (options.research !== undefined) {
      const research = goalResearchPath(this.projectRoot, goal.id);
      if (!isInside(goalsRoot(this.projectRoot), research)) {
        throw new Error(`Refused to write research outside the goals directory.`);
      }
      const tmp = `${research}.${process.pid}.tmp`;
      this.assertSafePath(tmp);
      fs.writeFileSync(tmp, `${options.research}\n`, { encoding: "utf-8", mode: 0o600, flag: "wx" });
      try {
        fs.renameSync(tmp, research);
      } catch (error) {
        fs.rmSync(tmp, { force: true });
        throw error;
      }
    }
    if (options.recordLast) {
      stillHeld();
      writeJsonAtomic(file, { version: GOAL_RECORD_VERSION, goal });
    }
  }

  private archiveGoalFiles(goal: GoalRecord, stillHeld: () => void = () => {}): GoalRecord {
    const from = goalDir(this.projectRoot, goal.id);
    const to = archivedGoalDir(this.projectRoot, goal.id);
    if (!isInside(path.join(this.projectRoot, ARCHIVED_GOALS_DIR), to)) {
      throw new Error(`Refused to archive outside the archive directory.`);
    }
    this.assertSafePath(from);
    this.assertSafePath(to);
    fs.mkdirSync(path.dirname(to), { recursive: true, mode: 0o700 });
    // Checked once, immediately before the move. The lock file lives inside the
    // directory being moved, so it cannot be re-read afterwards; and a check
    // after the move could not undo a move that had already happened.
    stillHeld();
    // The record is rewritten in place inside the moved directory so its stored
    // `activePath` cannot outlive the move and point at a file that is gone.
    fs.renameSync(from, to);
    const archived: GoalRecord = {
      ...goal,
      archivedPath: path.posix.join(ARCHIVED_GOALS_DIR, safeGoalId(goal.id), "record.json"),
    };
    delete archived.activePath;
    writeJsonAtomic(path.join(to, "record.json"), { version: GOAL_RECORD_VERSION, goal: archived });
    return archived;
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


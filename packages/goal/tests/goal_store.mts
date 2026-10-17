/**
 * Storage and prompt-block contracts.
 *
 * These run against the real pi-kit primitives the store binds, so a change in
 * either package fails here rather than diverging silently. The scenarios are
 * the "Goal record and durable state", "Ledger", and "Prompt stability" blocks
 * of features/goal.feature.
 */

import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";
import { writeFileSync as writeObservationFile } from "node:fs";
import { spawn } from "node:child_process";
import { existsSync, readdirSync as importedDirectoryEntries, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { GoalStore, newGoalId } from "../src/store.ts";
import { goalClaimDir, goalRecordPath, goalsRoot, isInside, legacyGoalPromptPath, legacyGoalRecordPath, safeGoalId } from "../src/paths.ts";
import { isolatedAgentDir } from "./isolated-agent.mts";

const agent = isolatedAgentDir();
const repoRoot = resolve(import.meta.dirname, "..", "..", "..");
const root = mkdtempSync(join(tmpdir(), "goal-store-"));
const store = new GoalStore({ projectRoot: root });
const results: string[] = [];
/** Async-capable: the cross-process race needs it, and an unhandled rejection
 * here would abort the harness instead of being reported by name. */
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await observeScenario(name, body);
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

const objective = "Add CSV export to the reports page, with documentation and tests.";

await scenario("a legacy contract field is dropped while its objective survives", () => {
  // An earlier version stored a second requirement text beside the objective. This
  // version judges the objective alone, so the field must not survive
  // normalization: leaving it reachable would keep a requirement no check reads.
  const id = "goal_legacy_contract";
  mkdirSync(dirname(goalRecordPath(root, id)), { recursive: true });
  writeFileSync(goalRecordPath(root, id), JSON.stringify({
    version: 1,
    goal: {
      id, threadId: "session-a", objective, status: "active", autoContinue: true,
      usage: { tokensUsed: 0, activeSeconds: 0 }, createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(), revision: 1,
      verificationContract: "The download holds only the filtered rows.",
      scheduler: { owner: "session-a", phase: "idle", used: 0, generation: "g" },
    },
  }));
  const read = store.readGoal(id);
  assert.equal(read?.objective, objective, "the objective still reads unchanged");
  assert.equal("verificationContract" in (read ?? {}), false, "the dropped field is not carried forward");
});

await scenario("a created goal is durable before any work begins", () => {
  const id = newGoalId();
  const created = store.create({ objective, owner: "session-a", id });
  assert.equal(created.ok, true, JSON.stringify(created));
  // Readable through a brand new store, i.e. through disk and nothing else.
  const fresh = new GoalStore({ projectRoot: root });
  assert.equal(fresh.readGoal(id)?.objective, objective);
  assert.equal(fresh.readObjective(id).trim(), objective);
  assert.equal(existsSync(join(dirname(goalRecordPath(root, id)), "history.jsonl")), false);
});

await scenario("a failed record write leaves the directory untouched", () => {
  const id = newGoalId();
  // Occupy this goal's directory with a regular file so creating it fails.
  mkdirSync(goalsRoot(root), { recursive: true });
  writeFileSync(dirname(goalRecordPath(root, id)), "occupied");
  const created = store.create({ objective, owner: "session-a", id });
  assert.equal(created.ok, false);
  assert.equal(existsSync(join(dirname(goalRecordPath(root, id)), "history.jsonl")), false);
});

await scenario("the pool returns open goals deterministically and ignores junk", () => {
  const dir = new GoalStore({ projectRoot: root });
  const a = dir.create({ objective: "first", owner: "s", id: "goal_pool_a" });
  const b = dir.create({ objective: "second", owner: "s", id: "goal_pool_b" });
  assert.ok(a.ok && b.ok);
  mkdirSync(join(goalsRoot(root), "broken"), { recursive: true });
  writeFileSync(join(goalsRoot(root), "broken", "record.json"), "{ not json");
  const outside = mkdtempSync(join(tmpdir(), "goal-outside-"));
  writeFileSync(join(outside, "record.json"), JSON.stringify({ version: 1, goal: { id: "linked", objective: "o" } }));
  symlinkSync(outside, join(goalsRoot(root), "linked"), "dir");

  const pool = new GoalStore({ projectRoot: root }).readPool().map((goal) => goal.id);
  assert.ok(pool.includes("goal_pool_a") && pool.includes("goal_pool_b"));
  assert.ok(!pool.includes("broken"), "a malformed file must be skipped");
  assert.ok(!pool.includes("linked"), "a symlink must never be followed");
  const twice = new GoalStore({ projectRoot: root }).readPool().map((goal) => goal.id);
  assert.deepEqual(pool, twice, "pool order must be deterministic");
});

await scenario("existing record and claim links refuse writes without changing outside files", () => {
  for (const target of ["record.json", "claims", "claims/write-lock.json"]) {
    const local = mkdtempSync(join(tmpdir(), "goal-link-local-"));
    const outside = mkdtempSync(join(tmpdir(), "goal-link-sentinel-"));
    try {
      const linkedStore = new GoalStore({projectRoot: local});
      const id = "linked-write";
      const sentinel = join(outside, "sentinel.json");
      writeFileSync(sentinel, "outside bytes must remain unchanged");
      const record = goalRecordPath(local, id);
      mkdirSync(dirname(record), {recursive: true});
      if (target === "claims") symlinkSync(outside, join(dirname(record), target), "dir");
      else {
        mkdirSync(dirname(join(dirname(record), target)), {recursive: true});
        symlinkSync(sentinel, join(dirname(record), target));
      }
      const created = linkedStore.create({id, owner: "session", objective: "Refuse redirected creation."});
      assert.equal(created.ok, false, target);
      assert.equal(readFileSync(sentinel, "utf8"), "outside bytes must remain unchanged", target);
      assert.deepEqual(importedDirectoryEntries(outside), ["sentinel.json"]);
    } finally { rmSync(local, {recursive: true, force: true}); rmSync(outside, {recursive: true, force: true}); }
  }
});

await scenario("linked paths refuse mutation of an existing valid Goal without outside changes", () => {
  for (const target of ["record.json", "claims", "claims/write-lock.json"]) {
    const local = mkdtempSync(join(tmpdir(), "goal-link-mutation-"));
    const outside = mkdtempSync(join(tmpdir(), "goal-link-valid-record-"));
    try {
      const linkedStore = new GoalStore({projectRoot: local});
      const id = "existing-link";
      assert.equal(linkedStore.create({id, owner:"session", objective:"Existing legitimate Goal."}).ok,true);
      const record = goalRecordPath(local,id);
      const sentinel = join(outside,"sentinel.json");
      const original = readFileSync(record,"utf8");
      writeFileSync(sentinel,original);
      const destination = join(dirname(record),target);
      rmSync(destination,{recursive:true,force:true});
      symlinkSync(target === "claims" ? outside : sentinel,destination,target === "claims" ? "dir" : "file");
      const changed = linkedStore.apply({expectedGoalId:id,mutate:goal=>({...goal,objective:"Redirected mutation."})});
      assert.equal(changed.ok,false,target);
      if (!changed.ok) assert.match(changed.message,target === "record.json" ? /no longer exists/ : /symbolic links/,target);
      assert.equal(readFileSync(sentinel,"utf8"),original,target);
      assert.deepEqual(importedDirectoryEntries(outside),["sentinel.json"]);
      if (target !== "record.json") assert.equal(readFileSync(record,"utf8"),original);
    } finally {rmSync(local,{recursive:true,force:true});rmSync(outside,{recursive:true,force:true});}
  }
});

await scenario("disk wins over a stale cached copy", () => {
  const id = "goal_reconcile";
  store.create({ objective, owner: "session-a", id });
  // Another process rewrites the record behind our back.
  const file = goalRecordPath(root, id);
  const onDisk = JSON.parse(readFileSync(file, "utf-8"));
  onDisk.goal.revision = 41;
  writeFileSync(file, JSON.stringify(onDisk));
  const outcome = store.apply({ expectedGoalId: id, mutate: (goal) => ({ ...goal, pauseReason: "x" }) });
  assert.ok(outcome.ok);
  assert.equal(outcome.goal.revision, 42, "the mutation starts from disk, not from the cache");
});

await scenario("a stale revision is refused and changes nothing", () => {
  const id = "goal_conflict";
  store.create({ objective, owner: "session-a", id });
  const before = store.readGoal(id)?.revision;
  const outcome = store.apply({ expectedGoalId: id, expectedRevision: before! + 99, mutate: (goal) => ({ ...goal, pauseReason: "nope" }) });
  assert.equal(outcome.ok, false);
  if (!outcome.ok) assert.match(outcome.message, /changed underneath this write/);
  assert.equal(store.readGoal(id)?.revision, before, "a refused write changes nothing");
});

await scenario("a finished goal keeps its terminal status and creates no archive", () => {
 const id="goal_end"; store.create({objective,owner:"session-a",id});
 const done=store.apply({expectedGoalId:id,mutate:g=>({...g,status:"complete",autoContinue:false})});
 assert.ok(done.ok);
 assert.equal(store.readGoal(id)?.status,"complete","the record stays with the outcome it reached");
 assert.equal(existsSync(join(goalsRoot(root),"archived",id)),false);
});

await scenario("a writer whose lock was taken from it writes nothing", () => {
  // Age-based takeover exists so a crashed holder cannot wedge a goal, which
  // deliberately means a slow holder CAN be displaced. Without a check at the
  // moment of writing, the displaced holder would rename its record over
  // whatever the new holder committed and both would believe they advanced the
  // goal from the same revision.
  const id = "goal_displaced";
  store.create({ objective, owner: "session-a", id });
  const revision = store.readGoal(id)!.revision;
  const lockFile = join(goalClaimDir(root, id), "write-lock.json");

  const outcome = store.apply({
    expectedGoalId: id,
    mutate: (goal) => {
      // Another holder takes the lock while this mutation is being prepared.
      writeFileSync(lockFile, JSON.stringify({ token: "someone-else", at: Date.now() }));
      return { ...goal, pauseReason: "computed before the lock was lost" };
    },
  });

  assert.equal(outcome.ok, false, "the displaced writer is refused");
  if (!outcome.ok) assert.match(outcome.message, /lost its write lock/);
  const after = new GoalStore({ projectRoot: root }).readGoal(id)!;
  assert.equal(after.revision, revision, "the record was not advanced");
  assert.equal(after.pauseReason, undefined, "and the change it had computed was discarded");
});

await scenario("real processes racing for one goal produce exactly one winner", async () => {
  // In-process stores cannot interleave inside the synchronous critical section,
  // so this has to be real processes. Every writer reads revision 0 before any of
  // them writes; without the exclusive-create lock all eight would succeed and
  // all eight would write revision 1.
  const id = "goal_process_race";
  store.create({ objective, owner: "session-a", id });
  assert.equal(store.readGoal(id)?.revision, 0, "the goal starts at revision 0");

  const worker = resolve(repoRoot, "packages/goal/tests/goal_race_worker.mts");
  const racers = 8;
  const startAt = Date.now() + 800;
  const outputs = await Promise.all(
    Array.from({ length: racers }, () => new Promise<string>((done, fail) => {
      const child = spawn(process.execPath, ["--import", "tsx", worker, root, id, String(startAt)], {
        cwd: repoRoot,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let out = "";
      let err = "";
      child.stdout?.on("data", (chunk) => { out += String(chunk); });
      child.stderr?.on("data", (chunk) => { err += String(chunk); });
      child.on("error", fail);
      child.on("close", () => done(err ? `ERROR ${err.trim()}` : out.trim()));
    })),
  );

  const verdicts = outputs.map((output) => output.trim());
  const won = verdicts.filter((verdict) => verdict === "won");
  assert.equal(won.length, 1, `expected exactly one winner, got ${JSON.stringify(verdicts)}`);
  const after = new GoalStore({ projectRoot: root }).readGoal(id)!;
  assert.equal(after.revision, 1, "the record advanced exactly once");
  assert.match(after.pauseReason ?? "", /^writer \d+$/, "and the surviving write is one of the racers");
});

await scenario("a record from a newer version is refused, not partially read", () => {
  mkdirSync(dirname(goalRecordPath(root, "goal_future")), { recursive: true });
  writeFileSync(goalRecordPath(root, "goal_future"), JSON.stringify({ version: 99, goal: { id: "goal_future", objective: "o", status: "complete" } }));
  assert.equal(new GoalStore({ projectRoot: root }).readGoal("goal_future"), undefined);
});

await scenario("prose written directly by a user never overrides the record", () => {
  const id = "goal_prose";
  store.create({ objective, owner: "session-a", id });
  const revision = store.readGoal(id)!.revision;
  // The prose file belongs to the layout an earlier version wrote.
  mkdirSync(dirname(legacyGoalPromptPath(root, id)), { recursive: true });
  writeFileSync(legacyGoalPromptPath(root, id), "objective the user edited by hand\n");
  const outcome = store.apply({ expectedGoalId: id, mutate: (goal) => goal });
  assert.ok(outcome.ok);
  assert.equal(outcome.goal.revision, revision + 1);
  assert.equal(new GoalStore({ projectRoot: root }).readObjective(id).trim(), objective, "legacy prose does not override the atomic record");
  assert.equal(readFileSync(legacyGoalPromptPath(root,id), "utf8"), "objective the user edited by hand\n", "legacy files remain untouched");
});

await scenario("one malformed record does not hide the valid ones", () => {
  const id = newGoalId();
  assert.ok(store.create({ objective, owner: "session-a", id }).ok);
  const broken = "goal_broken";
  mkdirSync(dirname(goalRecordPath(root, broken)), { recursive: true });
  // A record file that parses to `null` is unreadable, not fatal: the pool
  // skips it and still offers every readable sibling.
  writeFileSync(goalRecordPath(root, broken), "null\n");
  const ids = new GoalStore({ projectRoot: root }).readPool().map((goal) => goal.id);
  assert.ok(!ids.includes(broken), "the malformed record is not offered as work");
  assert.ok(ids.includes(id), `the valid sibling must survive, saw ${ids.join(",")}`);
});

await scenario("filesystem errors never leak goal id or directory paths", () => {
  const id = "goal_leak_test_path";
  store.create({ objective, owner: "session-a", id });
  const errorWithPaths = new Error("EXDEV: cross-device link not permitted, rename '/tmp/from/goal_leak_test_path' -> '/tmp/to/goal_leak_test_path'");
  const outcome = store.apply({
    expectedGoalId: id,
    mutate: () => { throw errorWithPaths; },
  });
  assert.equal(outcome.ok, false);
  if (!outcome.ok) {
    assert.doesNotMatch(outcome.message, /goal_/);
    assert.doesNotMatch(outcome.message, /->/);
    assert.equal(outcome.message, "EXDEV: cross-device link not permitted");
  }
});

await scenario("a completed goal cannot be moved out of its terminal status", () => {
  // Everything that writes a record after completion — a late charge, a stop
  // computed before another session's verdict, a rebuilt pause — reaches a
  // completed record instead of finding nothing, because the record is kept.
  // Completion is terminal, so none of those may land.
  const id = "goal_terminal";
  assert.ok(store.create({ objective, owner: "session-a", id }).ok);
  assert.ok(store.apply({ expectedGoalId: id, mutate: (goal) => ({ ...goal, status: "complete", autoContinue: false }) }).ok);
  const late = store.apply({ expectedGoalId: id, mutate: (goal) => ({ ...goal, status: "paused", autoContinue: false }) });
  assert.equal(late.ok, false, "a late writer cannot revive a finished goal");
  const after = new GoalStore({ projectRoot: root }).readGoal(id)!;
  assert.equal(after.status, "complete", "the terminal status stands");
  assert.equal(after.revision, 1, "and nothing was written");
});

await scenario("a project path keeps one key while its directory exists and after it is gone", () => {
  // The key has to be the same in every process, including one whose project
  // directory is already gone: resolving only the whole path would fall back to a
  // lexical spelling the moment the directory disappeared, and a record stored
  // under the resolved spelling would become unreachable.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-scope-"));
  try {
    const real = join(sandbox, "real");
    mkdirSync(real, { recursive: true });
    const link = join(sandbox, "link");
    symlinkSync(real, link, "dir");
    assert.equal(goalRecordPath(link, "goal_scope"), goalRecordPath(real, "goal_scope"), "a symlinked spelling resolves to the same key");
    const project = join(sandbox, "gone");
    mkdirSync(project, { recursive: true });
    const whileItExists = goalRecordPath(project, "goal_scope");
    rmSync(project, { recursive: true, force: true });
    assert.equal(goalRecordPath(project, "goal_scope"), whileItExists, "and the key survives its directory disappearing");
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
});

await scenario("a dot-only goal id never addresses a directory of its own", () => {
  // `encodeURIComponent` leaves a dot alone, and `..` as one path segment names
  // the directory above the goal directory.
  assert.equal(safeGoalId(".."), "goal", "a dot-only id becomes one safe segment");
  assert.ok(isInside(goalsRoot(root), goalRecordPath(root, "..")), "the record stays inside the project's goals root");
  assert.ok(isInside(goalsRoot(root), goalClaimDir(root, "..")), "so does its claim directory");
});

await scenario("an unreadable current record never hides a readable legacy one", () => {
  // One goal, two layouts, and the copy in the current one is unreadable: a newer
  // record version. The goal is the readable one, and it is also the record a
  // mutation must lock, so the lock area and the read cannot disagree.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-mixed-"));
  const id = "goal_mixed_layout";
  try {
    mkdirSync(dirname(goalRecordPath(sandbox, id)), { recursive: true });
    writeFileSync(goalRecordPath(sandbox, id), JSON.stringify({ version: 99, goal: { id, objective: "from a newer version" } }));
    mkdirSync(dirname(legacyGoalRecordPath(sandbox, id)), { recursive: true });
    writeFileSync(legacyGoalRecordPath(sandbox, id), JSON.stringify({
      version: 1,
      goal: {
        id, threadId: "session-a", objective, status: "active", autoContinue: true,
        usage: { tokensUsed: 0, activeSeconds: 0 }, createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(), revision: 0,
        scheduler: { owner: "session-a", phase: "idle", used: 0, generation: "g" },
      },
    }));
    const mixed = new GoalStore({ projectRoot: sandbox });
    assert.equal(mixed.readPool().length, 1, "the readable legacy goal is still offered");
    assert.equal(mixed.apply({ expectedGoalId: id, mutate: (goal) => ({ ...goal, autoContinue: false }) }).ok, true, "and it is the record a mutation locks");
    assert.equal(new GoalStore({ projectRoot: sandbox }).readGoal(id)?.autoContinue, false, "so the outcome landed on the goal");
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
});

await scenario("goal state is stored under the agent directory and never inside the project", () => {
  // Goal state is runtime state for the sessions sharing a working directory, so
  // it belongs where Pi keeps its own state. A `.pi/goals` tree inside the
  // working tree survives the goal: it is left behind in every repository a goal
  // was ever started in.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-placement-"));
  try {
    const projectRoot = join(sandbox, "workspace-project");
    mkdirSync(projectRoot, { recursive: true });
    const project = new GoalStore({ projectRoot });
    const made = project.create({ objective, owner: "session-a", id: newGoalId() });
    assert.equal(made.ok, true, made.ok ? "" : made.message);
    const record = goalRecordPath(projectRoot, made.ok ? made.goal.id : "missing");
    assert.ok(isInside(agent, record), "the record is written under the agent directory");
    assert.ok(existsSync(record), "and a fresh store reads it there");
    assert.ok(!existsSync(join(projectRoot, ".pi")), "the project gains no .pi tree");
    // Two projects under one agent directory keep their own goals: a pool scan
    // must never offer another project's goal as work.
    const otherRoot = join(sandbox, "other-project");
    mkdirSync(otherRoot, { recursive: true });
    const other = new GoalStore({ projectRoot: otherRoot });
    assert.deepEqual(other.readPool(), [], "another project sees no goals");
    const otherMade = other.create({ objective, owner: "session-b", id: newGoalId() });
    assert.equal(otherMade.ok, true, otherMade.ok ? "" : otherMade.message);
    assert.equal(new GoalStore({ projectRoot }).readPool().length, 1, "and each project reads its own");
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
});

await scenario("two lookalike project paths never share one goals directory", () => {
  // Reduced to readable words, `/a-b/c` and `/a/b-c` are the same name, so the key
  // carries a digest of the canonical path: a shared directory would let one
  // project's pool offer the other's goal.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-lookalike-"));
  try {
    const left = join(sandbox, "a-b", "c");
    const right = join(sandbox, "a", "b-c");
    for (const dir of [left, right]) mkdirSync(dir, { recursive: true });
    const created = new GoalStore({ projectRoot: left }).create({ objective, owner: "left", id: "goal_left" });
    assert.equal(created.ok, true, created.ok ? "" : created.message);
    assert.notEqual(goalRecordPath(left, "goal_left"), goalRecordPath(right, "goal_left"), "lookalike paths reduce to different keys");
    assert.deepEqual(new GoalStore({ projectRoot: right }).readPool(), [], "and neither project reads the other's goal");
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
});

await scenario("a goal stored under the legacy layout is still read and mutated where it lives", () => {
  // A goal created before the move is never stranded by it: it is read, locked
  // and written in the project directory it already lives in, because a move
  // would leave two processes locking different directories for one goal.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-legacy-"));
  const projectRoot = join(sandbox, "legacy-project");
  const id = "goal_legacy_in_project";
  try {
    mkdirSync(dirname(legacyGoalRecordPath(projectRoot, id)), { recursive: true });
    writeFileSync(legacyGoalRecordPath(projectRoot, id), JSON.stringify({
      version: 1,
      goal: {
        id, threadId: "session-a", objective, status: "active", autoContinue: true,
        usage: { tokensUsed: 0, activeSeconds: 0 }, createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(), revision: 0,
        scheduler: { owner: "session-a", phase: "idle", used: 0, generation: "g" },
      },
    }));
    const legacy = new GoalStore({ projectRoot });
    assert.equal(legacy.readGoal(id)?.objective, objective, "an existing goal is still readable where it lives");
    const applied = legacy.apply({ expectedGoalId: id, mutate: (draft) => ({ ...draft, autoContinue: false }) });
    assert.equal(applied.ok, true, applied.ok ? "" : applied.message);
    assert.equal(legacy.readGoal(id)?.autoContinue, false, "and it still accepts outcomes in place");
    assert.ok(existsSync(legacyGoalRecordPath(projectRoot, id)), "the legacy record stays where it is");
    assert.ok(!existsSync(goalRecordPath(projectRoot, id)), "and nothing is written to the new location for it");
    // A record an earlier version left at its spending cap keeps its reason and
    // reads as a stopped goal: this version writes no capped status, and it does not
    // read the ceiling the record carries.
    const cappedId = "goal_legacy_capped";
    mkdirSync(dirname(legacyGoalRecordPath(projectRoot, cappedId)), { recursive: true });
    writeFileSync(legacyGoalRecordPath(projectRoot, cappedId), JSON.stringify({
      version: 1,
      goal: {
        id: cappedId, threadId: "session-a", objective, status: "budget_limited", autoContinue: false,
        usage: { tokensUsed: 500, activeSeconds: 120 }, tokenBudget: 500,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), revision: 2,
        pauseReason: "The lifetime token cap of 500 tokens was reached.",
      },
    }));
    const capped = legacy.readGoal(cappedId);
    assert.equal(capped?.status, "paused", "a cap-era status still reads as a stopped goal");
    assert.equal(capped?.autoContinue, false, "and cannot continue on its own");
    assert.equal("tokenBudget" in (capped ?? {}), false, "its ceiling is ignored, not carried forward");
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
});

rmSync(root, { recursive: true, force: true });
process.stdout.write(`${JSON.stringify(results)}\n`);
if (process.env.PI_E2E_ASSERTION_PATH) writeObservationFile(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
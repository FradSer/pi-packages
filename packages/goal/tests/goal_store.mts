/**
 * Storage, ledger, and prompt-budget contracts.
 *
 * These run against the real pi-kit primitives the store binds, so a change in
 * either package fails here rather than diverging silently. The scenarios are
 * the "Goal record and durable state", "Ledger", and "Prompt stability" blocks
 * of features/goal.feature.
 */

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { GoalStore, newGoalId } from "../src/store.ts";
import { appendGoalEvent, readGoalHistoryPage, readGoalLedger, rebuildGoalFromLedger } from "../src/ledger.ts";
import { goalPromptPath, goalRecordPath } from "../src/paths.ts";
import { appendJsonlLine } from "@fradser/pi-kit";

const repoRoot = resolve(import.meta.dirname, "..", "..", "..");
const root = mkdtempSync(join(tmpdir(), "goal-store-"));
const store = new GoalStore({ projectRoot: root });
const results: string[] = [];
/** Async-capable: the cross-process race needs it, and an unhandled rejection
 * here would abort the harness instead of being reported by name. */
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await body();
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

const objective = "Add CSV export to the reports page, with documentation and tests.";

await scenario("a created goal is durable before any work begins", () => {
  const id = newGoalId();
  const created = store.create({ objective, owner: "session-a", id });
  assert.equal(created.ok, true, JSON.stringify(created));
  // Readable through a brand new store, i.e. through disk and nothing else.
  const fresh = new GoalStore({ projectRoot: root });
  assert.equal(fresh.readGoal(id)?.objective, objective);
  assert.equal(fresh.readPrompt(id).trim(), objective);
  assert.equal(readGoalLedger(root, id)[0]?.type, "goal_created");
});

await scenario("a failed record write appends no ledger event", () => {
  const id = newGoalId();
  // Occupy the goals directory with a regular file so mkdir fails.
  writeFileSync(join(root, ".pi", "goals", `${id}`), "occupied");
  const created = store.create({ objective, owner: "session-a", id });
  assert.equal(created.ok, false);
  assert.equal(readGoalLedger(root, id).length, 0);
});

await scenario("the pool returns open goals deterministically and ignores junk", () => {
  const dir = new GoalStore({ projectRoot: root });
  const a = dir.create({ objective: "first", owner: "s", id: "goal_pool_a" });
  const b = dir.create({ objective: "second", owner: "s", id: "goal_pool_b" });
  assert.ok(a.ok && b.ok);
  mkdirSync(join(root, ".pi", "goals", "broken"), { recursive: true });
  writeFileSync(join(root, ".pi", "goals", "broken", "record.json"), "{ not json");
  const outside = mkdtempSync(join(tmpdir(), "goal-outside-"));
  writeFileSync(join(outside, "record.json"), JSON.stringify({ version: 1, goal: { id: "linked", objective: "o" } }));
  symlinkSync(outside, join(root, ".pi", "goals", "linked"), "dir");

  const pool = new GoalStore({ projectRoot: root }).readPool().map((goal) => goal.id);
  assert.ok(pool.includes("goal_pool_a") && pool.includes("goal_pool_b"));
  assert.ok(!pool.includes("broken"), "a malformed file must be skipped");
  assert.ok(!pool.includes("linked"), "a symlink must never be followed");
  const twice = new GoalStore({ projectRoot: root }).readPool().map((goal) => goal.id);
  assert.deepEqual(pool, twice, "pool order must be deterministic");
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
  const before = store.readGoalFromDisk(id)?.revision;
  const outcome = store.apply({ expectedGoalId: id, expectedRevision: before! + 99, mutate: (goal) => ({ ...goal, pauseReason: "nope" }) });
  assert.equal(outcome.ok, false);
  if (!outcome.ok) assert.match(outcome.message, /changed underneath this write/);
  assert.equal(store.readGoalFromDisk(id)?.revision, before, "a refused write changes nothing");
});

await scenario("archiving removes the goal from the open pool", () => {
  const id = "goal_archive";
  store.create({ objective, owner: "session-a", id });
  const outcome = store.apply({
    expectedGoalId: id,
    archive: true,
    mutate: (goal) => ({ ...goal, status: "complete", autoContinue: false }),
    ledger: [{ type: "goal_completed", goalId: id, archivePath: ".pi/goals/archived/goal_archive/record.json", at: new Date().toISOString() }],
  });
  assert.ok(outcome.ok);
  assert.ok(!new GoalStore({ projectRoot: root }).readPool().some((goal) => goal.id === id));
  assert.ok(outcome.ok && outcome.goal.archivedPath);
  // Archiving moves the goal directory, history included, so the ledger has to
  // be read from the archive. Reading the open path would find a directory the
  // append recreated beside it and report a one-event history.
  assert.equal(new GoalStore({ projectRoot: root }).isArchived(id), true);
  assert.equal(readGoalLedger(root, id, undefined, true).at(-1)?.type, "goal_completed");
  assert.equal(
    readGoalLedger(root, id).length,
    0,
    "and no stray open-goal ledger was left beside the archive",
  );
});

await scenario("a writer whose lock was taken from it writes nothing", () => {
  // Age-based takeover exists so a crashed holder cannot wedge a goal, which
  // deliberately means a slow holder CAN be displaced. Without a check at the
  // moment of writing, the displaced holder would rename its record over
  // whatever the new holder committed and both would believe they advanced the
  // goal from the same revision.
  const id = "goal_displaced";
  store.create({ objective, owner: "session-a", id });
  const revision = store.readGoalFromDisk(id)!.revision;
  const lockFile = join(root, ".pi", "goals", id, "claims", "write-lock.json");

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
  const after = new GoalStore({ projectRoot: root }).readGoalFromDisk(id)!;
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
  assert.equal(store.readGoalFromDisk(id)?.revision, 0, "the goal starts at revision 0");

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
  const after = new GoalStore({ projectRoot: root }).readGoalFromDisk(id)!;
  assert.equal(after.revision, 1, "the record advanced exactly once");
  assert.match(after.pauseReason ?? "", /^writer \d+$/, "and the surviving write is one of the racers");
});

await scenario("ledger events append in order and read back in order", () => {
  const id = "goal_order";
  store.create({ objective, owner: "session-a", id });
  store.apply({
    expectedGoalId: id,
    mutate: (goal) => ({ ...goal, status: "paused", autoContinue: false }),
    ledger: [{ type: "goal_paused", goalId: id, reason: "first", stopReason: "user", at: new Date().toISOString() }],
  });
  store.apply({
    expectedGoalId: id,
    mutate: (goal) => ({ ...goal, status: "active", autoContinue: true }),
    ledger: [{ type: "goal_resumed", goalId: id, reason: "user", at: new Date().toISOString() }],
  });
  assert.deepEqual(readGoalLedger(root, id).map((event) => event.type), ["goal_created", "goal_paused", "goal_resumed"]);
});

await scenario("a malformed record is consumed and reported, never blocking the drain", () => {
  const id = "goal_malformed";
  store.create({ objective, owner: "session-a", id });
  store.apply({
    expectedGoalId: id,
    mutate: (goal) => goal,
    ledger: [{ type: "goal_resumed", goalId: id, reason: "r", at: new Date().toISOString() }],
  });
  // Append a broken line directly, as another process or a partial write would.
  appendJsonlLine(join(root, ".pi", "goals", id, "ledger.jsonl"), "not-an-object");
  store.apply({
    expectedGoalId: id,
    mutate: (goal) => goal,
    ledger: [{ type: "goal_resumed", goalId: id, reason: "r2", at: new Date().toISOString() }],
  });
  const page = readGoalHistoryPage(root, id);
  assert.ok(page.events.length >= 3, `expected the good records, got ${page.events.length}`);
  // The match used to be `/malformed/i`, which satisfied itself on the goal id
  // this scenario is named for rather than on the diagnostic. It now asserts the
  // diagnostic itself, and separately that no goal id is printed in it.
  assert.ok(
    page.diagnostics.some((diagnostic) => /unrecognized|malformed/i.test(diagnostic)),
    `expected a diagnostic, got ${JSON.stringify(page.diagnostics)}`,
  );
  assert.ok(
    page.diagnostics.every((diagnostic) => !/goal_[a-z0-9]/.test(diagnostic)),
    `a diagnostic must not print the goal id: ${JSON.stringify(page.diagnostics)}`,
  );
});

await scenario("history paging returns complete records exactly once", () => {
  const id = "goal_paging";
  store.create({ objective, owner: "session-a", id });
  for (let index = 0; index < 60; index++) {
    store.apply({
      expectedGoalId: id,
      mutate: (goal) => goal,
      ledger: [{ type: "goal_resumed", goalId: id, reason: `r${index}`, at: new Date().toISOString() }],
    });
  }
  const seen = new Set<string>();
  let cursor: string | undefined;
  let pages = 0;
  do {
    const page = readGoalHistoryPage(root, id, cursor, 512);
    pages++;
    for (const event of page.events) {
      const key = `${event.type}:${(event as { reason?: string }).reason ?? ""}`;
      assert.ok(!seen.has(key), `duplicate record ${key}`);
      seen.add(key);
    }
    cursor = page.cursor;
  } while (cursor && pages < 50);
  assert.equal(seen.size, 61, "the creation event plus sixty");
});

await scenario("lifecycle state rebuilds from the ledger when the record is gone", () => {
  const id = "goal_rebuild";
  store.create({ objective, owner: "session-a", id });
  store.apply({
    expectedGoalId: id,
    mutate: (goal) => ({ ...goal, status: "paused", autoContinue: false, pauseReason: "waiting on credentials" }),
    ledger: [{ type: "goal_paused", goalId: id, reason: "waiting on credentials", stopReason: "agent", at: new Date().toISOString() }],
  });
  rmSync(goalRecordPath(root, id), { force: true });
  const rebuilt = rebuildGoalFromLedger(root, id);
  assert.equal(rebuilt?.status, "paused");
  assert.equal(rebuilt?.pauseReason, "waiting on credentials");
  assert.equal(rebuilt?.objective, objective);
});

await scenario("a record from a newer version is refused, not partially read", () => {
  mkdirSync(join(root, ".pi", "goals", "goal_future"), { recursive: true });
  writeFileSync(goalRecordPath(root, "goal_future"), JSON.stringify({ version: 99, goal: { id: "goal_future", objective: "o", status: "complete" } }));
  assert.equal(new GoalStore({ projectRoot: root }).readGoal("goal_future"), undefined);
});

await scenario("prose written directly by a user is picked up without a record revision", () => {
  const id = "goal_prose";
  store.create({ objective, owner: "session-a", id });
  const revision = store.readGoalFromDisk(id)!.revision;
  writeFileSync(goalPromptPath(root, id), "objective the user edited by hand\n");
  const outcome = store.apply({ expectedGoalId: id, mutate: (goal) => goal });
  assert.ok(outcome.ok);
  assert.equal(outcome.goal.revision, revision + 1);
  assert.equal(new GoalStore({ projectRoot: root }).readPrompt(id).trim(), "objective the user edited by hand");
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


await scenario("ledger append errorKind never leaks goal id or directory paths", () => {
  const id = "goal_ledger_leak_path";
  const badRoot = join(root, "ledger_error_file");
  writeFileSync(badRoot, "not a directory");
  const err = appendGoalEvent(badRoot, { type: "goal_resumed", goalId: id, reason: "r", at: new Date().toISOString() });
  assert.ok(err, "expected an error");
  assert.doesNotMatch(err, new RegExp(id));
  assert.doesNotMatch(err, new RegExp(root));
  assert.doesNotMatch(err, /->/);
});

await scenario("goals are refused inside Pi's own directories and left untouched there", () => {
  // The real case: a session run from Pi's home writes to ~/.pi/.pi/goals, a
  // second .pi inside Pi's own layout. HOME and the agent directory are set here
  // rather than read from the machine, so the rule is what is measured.
  const sandbox = mkdtempSync(join(tmpdir(), "goal-placement-"));
  const previousHome = process.env.HOME;
  const previousAgentDir = process.env.PI_CODING_AGENT_DIR;
  // HOME is what pi's home directory is derived from, so the tree below is
  // shaped exactly like the real one: <home>/.pi/agent.
  const home = join(sandbox, "home");
  const piHome = join(home, ".pi");
  const agent = join(piHome, "agent");
  mkdirSync(agent, { recursive: true });
  process.env.HOME = home;
  process.env.PI_CODING_AGENT_DIR = agent;
  try {
    const refused: { label: string; projectRoot: string }[] = [
      { label: "Pi's home itself", projectRoot: piHome },
      { label: "a directory inside the agent directory", projectRoot: join(agent, "config") },
      { label: "the home directory", projectRoot: home },
      { label: "a directory inside Pi's home", projectRoot: join(piHome, "workspace") },
    ];
    for (const row of refused) {
      const store = new GoalStore({ projectRoot: row.projectRoot });
      const created = store.create({ objective, owner: "session-a", id: newGoalId() });
      assert.equal(created.ok, false, `${row.label}: creation must be refused`);
      assert.match(created.ok ? "" : created.message, /\.pi\/goals/, `${row.label}: the message must name the path it refused`);
      // The refusal has to happen before the write, or the doubled directory
      // survives the refusal and the next run adopts it.
      assert.ok(!existsSync(join(row.projectRoot, ".pi", "goals")), `${row.label}: no goals directory may be left behind`);
    }
    // A goal stored before this rule existed is never stranded by it: reads and
    // mutations still work in place.
    const legacyRoot = join(piHome, "legacy");
    const legacy = new GoalStore({ projectRoot: legacyRoot });
    mkdirSync(join(legacyRoot, ".pi", "goals", "goal_legacy_nested"), { recursive: true });
    writeFileSync(join(legacyRoot, ".pi", "goals", "goal_legacy_nested", "record.json"), JSON.stringify({
      version: 1,
      goal: {
        id: "goal_legacy_nested", threadId: "session-a", objective, status: "active", autoContinue: true,
        usage: { tokensUsed: 0, activeSeconds: 0 }, createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(), revision: 0, scheduler: { owner: "session-a", phase: "idle", used: 0, idleRuns: 0, generation: "g" },
      },
    }));
    assert.equal(legacy.readGoal("goal_legacy_nested")?.objective, objective, "an existing goal is still readable where it lives");
    const applied = legacy.apply({ expectedGoalId: "goal_legacy_nested", mutate: (draft) => ({ ...draft, autoContinue: false }) });
    assert.equal(applied.ok, true, applied.ok ? "" : applied.message);
    assert.equal(legacy.readGoal("goal_legacy_nested")?.autoContinue, false, "and it still accepts outcomes in place");
    // A project directory is unaffected, which is the ordinary case this rule
    // must never touch.
    const projectRoot = join(sandbox, "workspace-project");
    mkdirSync(projectRoot, { recursive: true });
    const project = new GoalStore({ projectRoot });
    const made = project.create({ objective, owner: "session-a", id: newGoalId() });
    assert.equal(made.ok, true, made.ok ? "" : made.message);
    assert.ok(existsSync(goalRecordPath(projectRoot, made.ok ? made.goal.id : "missing")), "a project keeps its own .pi/goals");
  } finally {
    if (previousHome === undefined) delete process.env.HOME;
    else process.env.HOME = previousHome;
    if (previousAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = previousAgentDir;
    rmSync(sandbox, { recursive: true, force: true });
  }
});

rmSync(root, { recursive: true, force: true });
process.stdout.write(`${JSON.stringify(results)}\n`);
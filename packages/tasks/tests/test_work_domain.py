"""Work Item domain rules and durable tasks persistence.

Contract: packages/tasks/features/work-domain.feature

Everything here imports through the package barrel, so a symbol missing from
`index.ts` fails rather than silently passing through a deep relative path.
`PI_CODING_AGENT_DIR` is redirected to a temporary directory because the tasks
layout is rooted at the agent directory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from task_helpers import PACKAGE, run_node

TASK = (PACKAGE / "index.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f'''\
        import * as task from "{TASK}";
        {script}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


# ── Rule: a derived Work id stays readable and filesystem-safe ──


def test_work_id_derivation(tmp_path: Path) -> None:
    result = run(
        '''
        const taken = new Set(["polish-login-flow", "polish-login-flow-2"]);
        console.log(JSON.stringify({
          slug: task.taskIdFromSubject("Polish login flow", new Set()),
          punct: task.taskIdFromSubject("  Fix__THE  thing--now! ", new Set()),
          collision: task.taskIdFromSubject("Polish login flow", taken),
          long: task.taskIdFromSubject("x".repeat(120), new Set()),
          fallback: task.taskIdFromSubject("!!!", new Set()),
          limit: task.MAX_TASK_ID_LENGTH,
        }));
        ''',
        tmp_path,
    )
    assert result["slug"] == "polish-login-flow"
    assert result["punct"] == "fix-the-thing-now"
    assert result["collision"] == "polish-login-flow-3"
    long_id = str(result["long"])
    assert len(long_id) <= int(str(result["limit"]))
    assert not long_id.endswith("-")
    assert result["fallback"] == "task", "a subject with no usable characters still yields an id"


# ── Rule: resource tags describe a lease, not a string ──


def test_resource_normalization_and_conflict_semantics(tmp_path: Path) -> None:
    result = run(
        '''
        console.log(JSON.stringify({
          normalized: task.normalizeResources(["  b ", "", "/a/", "a", "b", "c/"]),
          undefinedIs: task.normalizeResources(undefined),
          self: task.resourcesConflict(["firmware/sub-node"], ["firmware/sub-node"]),
          descendant: task.resourcesConflict(["firmware/sub-node"], ["firmware/sub-node/app"]),
          ancestor: task.resourcesConflict(["firmware/sub-node/app"], ["firmware/sub-node"]),
          sibling: task.resourcesConflict(["firmware/sub-node"], ["firmware/other"]),
          prefixNotParent: task.resourcesConflict(["firmware/sub-node"], ["firmware/sub-nodex"]),
          emptyLeft: task.resourcesConflict([], ["firmware/sub-node"]),
          emptyRight: task.resourcesConflict(["firmware/sub-node"], []),
        }));
        ''',
        tmp_path,
    )
    assert result["normalized"] == ["a", "b", "c"], "trimmed, de-duplicated, slash-stripped, sorted"
    assert result["undefinedIs"] == []
    assert result["self"] is True
    assert result["descendant"] is True
    assert result["ancestor"] is True, "conflict is symmetric across the lease hierarchy"
    assert result["sibling"] is False
    assert result["prefixNotParent"] is False, "a shared string prefix is not a shared lease"
    assert result["emptyLeft"] is False
    assert result["emptyRight"] is False


# ── Rule: supersession chains resolve or are refused ──


def test_supersession_chains_and_cycle_detection(tmp_path: Path) -> None:
    result = run(
        '''
        const chain = {
          a: { id: "a", status: "superseded", supersededBy: "b" },
          b: { id: "b", status: "superseded", supersededBy: "c" },
          c: { id: "c", status: "pending" },
        };
        const broken = { a: { id: "a", status: "superseded", supersededBy: "missing" } };
        const cyclic = { a: { id: "a", status: "superseded", supersededBy: "a" } };
        console.log(JSON.stringify({
          chain: task.canonicalDependency("a", chain),
          live: task.canonicalDependency("c", chain),
          absent: task.canonicalDependency("nope", chain) ?? null,
          broken: task.canonicalDependency("a", broken) ?? null,
          cyclic: task.canonicalDependency("a", cyclic) ?? null,
          many: task.canonicalDependencies(["a", "b", "c"], chain),
          manyBroken: task.canonicalDependencies(["a", "nope"], chain) ?? null,
          cycle: task.hasDependencyCycle(new Map([["a", ["b"]], ["b", ["a"]]])),
          noCycle: task.hasDependencyCycle(new Map([["a", ["c"]], ["b", ["c"]], ["c", []]])),
        }));
        ''',
        tmp_path,
    )
    assert result["chain"] == "c"
    assert result["live"] == "c"
    assert result["absent"] is None
    assert result["broken"] is None, "a dangling replacement is refused, not silently unclaimable"
    assert result["cyclic"] is None
    assert result["many"] == ["c"], "two links of one chain collapse to one canonical target"
    assert result["manyBroken"] is None
    assert result["cycle"] is True
    assert result["noCycle"] is False


# ── Rule: the tasks file is durable and refuses to guess ──


def test_tasks_round_trip_and_refusals(tmp_path: Path) -> None:
    result = run(
        '''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "tasks-"));
        const file = task.tasksFilePath("session-one.jsonl", cwd);
        const tasks = {
          "fix-storage": { id: "fix-storage", subject: "Fix storage", dependsOn: [], resources: ["firmware/storage"],
            status: "pending", createdAt: 1, updatedAt: 1 },
          "add-tests": { id: "add-tests", subject: "Add tests", dependsOn: ["fix-storage"], resources: [],
            status: "in_progress", claimedBy: "reviewer", createdAt: 2, updatedAt: 3 },
        };
        task.writeTasksFile(file, tasks);
        const roundTrip = task.readTasksFile(file);
        const absent = task.readTasksFile(path.join(cwd, "nope", "tasks.json"));
        const garbage = path.join(cwd, "garbage.json");
        fs.writeFileSync(garbage, "{not json");
        let garbageError = "";
        try { task.readTasksFile(garbage); } catch (error) { garbageError = error.message; }
        const old = path.join(cwd, "old.json");
        fs.writeFileSync(old, JSON.stringify({ runtimeVersion: 1, tasks: { x: { id: "x" } } }));
        let versionError = "";
        try { task.readTasksFile(old); } catch (error) { versionError = error.message; }
        console.log(JSON.stringify({
          roundTrip,
          absent: absent ?? null,
          garbageError,
          versionError,
          expectedVersion: task.TASKS_FILE_VERSION,
          perSession: task.tasksDir("session-two.jsonl", cwd) !== path.dirname(file),
          deterministic: task.tasksDir("session-one.jsonl", cwd) === path.dirname(file),
          cwdScope: task.tasksDir(undefined, cwd) !== path.dirname(file),
          claims: path.basename(task.claimsDir(path.dirname(file))),
          submissions: path.basename(task.submissionsDir(path.dirname(file))),
          underAgentDir: file.startsWith(process.env.PI_CODING_AGENT_DIR),
        }));
        fs.rmSync(cwd, { recursive: true, force: true });
        ''',
        tmp_path,
    )
    round_trip = result["roundTrip"]
    assert isinstance(round_trip, dict)
    assert sorted(round_trip["tasks"]) == ["add-tests", "fix-storage"]
    assert round_trip["tasks"]["add-tests"]["claimedBy"] == "reviewer"
    assert result["absent"] is None, "an absent tasks is a fresh session, not an error"
    assert "not valid JSON" in str(result["garbageError"]) and "refusing to treat it as empty" in str(result["garbageError"])
    assert str(result["expectedVersion"]) in str(result["versionError"])
    assert "Incompatible task file version 1" in str(result["versionError"]), (
        "the message names the file, not a package that may not be installed"
    )
    assert result["perSession"] is True
    assert result["deterministic"] is True
    assert result["cwdScope"] is True, "with no session file the working directory is the scope"
    assert result["claims"] == "claims" and result["submissions"] == "submissions"
    assert result["underAgentDir"] is True


# ── Rule: a contested intent has exactly one winner ──


def test_intent_race_validation_and_grace(tmp_path: Path) -> None:
    result = run(
        '''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "task-intent-"));
        const intent = { taskId: "t_1", participant: "frontend", spawnId: "s1", timestamp: Date.now() };
        const won = task.createTaskIntent(dir, "t_1", intent);
        const lost = task.createTaskIntent(dir, "t_1", { ...intent, participant: "backend" });
        const traversal = task.createTaskIntent(dir, "../../../escape", intent);
        const escaped = fs.existsSync(path.resolve(dir, "../../../escape.json"));
        const taken = task.takeTaskIntent(dir);

        const bad = fs.mkdtempSync(path.join(os.tmpdir(), "task-intent-bad-"));
        fs.writeFileSync(path.join(bad, "b.json"), JSON.stringify({ taskId: "t", participant: "", spawnId: "s", timestamp: 1 }));
        const missingIdentity = task.takeTaskIntent(bad);
        fs.writeFileSync(path.join(bad, "c.json"), JSON.stringify({ taskId: "t", participant: "w", spawnId: "s", timestamp: 1, status: "maybe" }));
        const badStatus = task.takeTaskIntent(bad);

        const grace = fs.mkdtempSync(path.join(os.tmpdir(), "task-intent-grace-"));
        const young = path.join(grace, "young.json");
        fs.writeFileSync(young, '{"half":');
        const youngTake = task.takeTaskIntent(grace);
        const youngSurvived = fs.existsSync(young);
        fs.utimesSync(young, Date.now() / 1000 - 3600, Date.now() / 1000 - 3600);
        const oldTake = task.takeTaskIntent(grace);

        console.log(JSON.stringify({
          won, lost, traversal, escaped,
          markers: fs.readdirSync(dir).filter((name) => name.endsWith(".json")),
          taken,
          missingIdentity: missingIdentity.diagnostic ?? null,
          badStatus: badStatus.diagnostic ?? null,
          youngIntent: youngTake.intent ?? null,
          youngDiagnostic: youngTake.diagnostic ?? null,
          youngSurvived,
          oldDiagnostic: oldTake.diagnostic ?? null,
          grace: task.INTENT_PUBLISH_GRACE_MS,
          empty: task.takeTaskIntent(path.join(dir, "absent")),
        }));
        for (const d of [dir, bad, grace]) fs.rmSync(d, { recursive: true, force: true });
        ''',
        tmp_path,
    )
    assert result["won"] is True
    assert result["lost"] is False, "the second racer is told, not silently overwritten"
    assert result["markers"] == ["t_1.json"]
    assert result["traversal"] is True and result["escaped"] is False, "a marker name cannot escape its directory"
    taken = result["taken"]
    assert isinstance(taken, dict) and taken["intent"]["participant"] == "frontend"
    assert result["missingIdentity"] == 'malformed task intent "b.json" was consumed (requires non-empty taskId/participant/spawnId and finite timestamp)'
    assert result["badStatus"] == 'malformed task intent "c.json" was consumed (invalid submission status)'
    assert result["youngIntent"] is None
    assert result["youngDiagnostic"] is None, "a half-written marker inside the grace is not an error yet"
    assert result["youngSurvived"] is True, "destroying an in-flight intent would strand its author"
    assert result["oldDiagnostic"] == 'unreadable task intent "young.json" was consumed'
    assert int(str(result["grace"])) == 30_000
    assert result["empty"] == {}, "a missing directory is empty, not an error"


# ── Rule: a holder check applies only to work that is held ──


def test_a_restored_pending_task_with_a_stale_holder_is_not_held(tmp_path: Path) -> None:
    """`loadTasks` keeps `claimedBy` on a pending restore, but a pending task is
    unheld: `takeTask` already accepts it, so the completion path must not refuse
    it as work somebody else is doing. A task nobody ever took stays refused, so
    the two cases remain different."""
    result = run(
        '''
        task.loadTasks({
          stale: { id: "stale", subject: "Restored work", dependsOn: [], resources: [],
            status: "pending", claimedBy: "departed", createdAt: 1, updatedAt: 1 },
          untouched: { id: "untouched", subject: "Untouched work", dependsOn: [], resources: [],
            status: "pending", createdAt: 1, updatedAt: 1 },
        });
        const completed = task.completeTaskWithOutcome("stale", "arrived", "success", "Finished the restored work", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        const untouched = task.completeTaskWithOutcome("untouched", "arrived", "success", "Looks finished to me", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        console.log(JSON.stringify({
          accepted: completed.ok,
          reason: completed.ok ? null : completed.reason,
          status: task.getTask("stale").status,
          untouchedRefused: untouched.ok === false,
          untouchedCode: untouched.ok ? null : untouched.refusal,
          untouchedStatus: task.getTask("untouched").status,
        }));
        ''',
        tmp_path,
    )
    assert result["accepted"] is True, "a pending task is unheld, whatever its restored holder field says"
    assert "in progress" not in str(result["reason"]).lower(), "no refusal calls departed work in progress"
    assert result["status"] == "completed"
    assert result["untouchedRefused"] is True, "a task nobody ever took is still refused when the checks are on"
    assert result["untouchedCode"] == "never-taken"
    assert result["untouchedStatus"] == "pending"


# ── Rule: a failed attempt leaves no gate answer behind ──


def test_a_failed_attempt_clears_the_previous_attempt_gate_answer(tmp_path: Path) -> None:
    """The completion writes `completionVerdict` and `completionGate` from its
    own call, but a failure used to leave an earlier attempt's answer in place,
    so a reader saw a gate answer on a task whose current attempt failed."""
    result = run(
        '''
        task.createTask({ id: "gated", subject: "Ship the fix", verify: "A reviewer confirms the fix" });
        task.takeTask("gated", "alpha");
        const passed = task.completeTaskWithOutcome("gated", "alpha", "success", "Fix verified", {
          checks: task.ALL_COMPLETION_CHECKS, verdict: "pass",
        });
        const reopened = task.reopenTask("gated");
        const retaken = task.takeTask("gated", "beta");
        const failed = task.completeTaskWithOutcome("gated", "beta", "failed", "The fix regressed");
        const record = task.getTask("gated");
        console.log(JSON.stringify({
          passed: passed.ok, reopened: reopened.ok, retaken: retaken.ok, failed: failed.ok,
          verdict: record.completionVerdict ?? null,
          gate: record.completionGate ?? null,
          status: record.status,
          blocker: record.result ?? null,
        }));
        ''',
        tmp_path,
    )
    assert result["passed"] is True, "the setup must reach a recorded verdict before the failure"
    assert result["reopened"] is True and result["retaken"] is True
    assert result["failed"] is True
    assert result["status"] == "recovery_hold"
    assert result["blocker"] == "The fix regressed", "the failure keeps its blocker as evidence"
    assert result["verdict"] is None, "a failed attempt answered no gate"
    assert result["gate"] is None


# ── Rule: the package has no coordination coupling ──

# Vocabulary that belongs to a layer this package does not own. Enforced as
# words rather than left to review, because the failure is silent: a source file
# that says "leader" or "worker" compiles, passes every behavioural test, and
# quietly reintroduces the dependency the package is separated to avoid.
FORBIDDEN_VOCABULARY = (
    "teammate", "Teammate", "spawnResident", "mailbox", "Mailbox", "agent_event",
    "roster", "Roster",
    "leader", "Leader",
    "worker", "Worker",
    # This package's own separator from the process layer. Naming it anywhere in
    # the source would make a rename on that side a silent behaviour change here.
    "PI_TEAMMATE",
)


def test_the_package_imports_no_coordination_concept() -> None:
    """The boundary that makes @fradser/pi-tasks installable without the team runtime."""
    allowed_prefixes = (
        "node:",
        "@earendil-works/pi-coding-agent",
        "@earendil-works/pi-tui",
        "@fradser/pi-kit",
        "./",
    )
    for source_file in sorted((PACKAGE / "src").glob("*.ts")):
        text = source_file.read_text(encoding="utf-8")
        for specifier in re.findall(r'from "([^"]+)"', text):
            assert specifier.startswith(allowed_prefixes), f"{source_file.name} imports {specifier}"
        for forbidden in FORBIDDEN_VOCABULARY:
            assert forbidden not in text, f"{source_file.name} references {forbidden}"


def test_the_package_names_no_sibling_package() -> None:
    """A sibling named in source is a coupling waiting to be imported.

    The two runtime packages this one integrates with publish and read a shared
    contract through pi-kit precisely so that neither has to name the other.
    Naming one here is how that arrangement quietly stops holding: a later edit
    reaches for the import, and the boundary test above still passes because the
    specifier is a legal one.
    """
    siblings = ("@fradser/pi-subagents", "@fradser/pi-agent-teams", "@fradser/pi-continual-learning")
    for source_file in sorted((PACKAGE / "src").glob("*.ts")):
        text = source_file.read_text(encoding="utf-8")
        for sibling in siblings:
            assert sibling not in text, f"{source_file.name} names {sibling}"


def test_the_package_owns_its_own_environment_binding() -> None:
    """The env var a participant binds through belongs to the tasks.

    Reading a spawner's private env prefix would couple the tasks to that
    package's naming: renaming the variable there would turn every participant's
    take into a take by the main session, with no error anywhere.
    """
    result = run_node(
        f"""
        import {{ TASK_HOLDER_ENV, callerIdentity }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          name: TASK_HOLDER_ENV,
          bound: callerIdentity({{ [TASK_HOLDER_ENV]: "alpha" }}),
          main: callerIdentity({{}}),
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": "/tmp"},
    )
    assert result["name"] == "PI_TASK_HOLDER", "the task store owns the binding name"
    assert result["bound"] == "alpha"
    assert result["main"] == "main"


def test_the_barrel_exposes_the_whole_domain() -> None:
    """A symbol missing from index.ts must fail here rather than silently
    passing through a deep relative import in some consumer."""
    result = run(
        f'''
        const names = {json.dumps([
            "taskIdFromSubject", "normalizeResources", "canonicalDependency", "canonicalDependencies",
            "hasDependencyCycle", "resourcesConflict", "MAX_TASK_ID_LENGTH",
            "tasksRoot", "tasksDir", "tasksFilePath", "claimsDir", "submissionsDir",
            "readTasksFile", "writeTasksFile", "createTaskIntent", "takeTaskIntent",
            "INTENT_PUBLISH_GRACE_MS", "TASKS_FILE_VERSION", "sessionKey",
        ])};
        console.log(JSON.stringify({{ missing: names.filter((name) => task[name] === undefined) }}));
        ''',
        Path("/tmp"),
    )
    assert result["missing"] == [], f"the barrel does not expose: {result['missing']}"


# ── Rule: an installed-alone tasks survives a restart ──────────────────────
#
# The package description claims durable tasks persistence. A claim the shipped
# entry did not honour would be a README that lies, so the round trip is driven
# through the extension entry rather than through the library alone.


def _entry_script(session_file: str | None, before_start: str = "") -> str:
    """Load the shipped extension entry and fire its session_start handler.

    Returns a `store` binding. The entry is what owns the durable file when
    nothing else does, so driving the tests through it is the only way to assert
    the feature is in the product rather than only in the library.

    `before_start` runs after the module is imported but before the session
    starts, which is where a real coordinator claims the store.
    """
    return f"""
        import fs from "node:fs";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        {before_start}
        const entry = (await import({json.dumps((PACKAGE / "index.ts").as_uri())})).default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        await api.sessionStart(
          {{ type: "session_start", reason: "startup" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(session_file)} }} }},
        );
    """


def test_a_standalone_tasks_is_written_and_read_back(tmp_path: Path) -> None:
    """create -> take -> complete, then a second session reading the same file.

    Both halves run through the shipped extension entry, because the entry is
    what owns the file when nothing else does. A library-only round trip would
    pass while the feature was absent from the product.
    """
    result = run_node(
        f"""
        {_entry_script(str(tmp_path / "session.jsonl"))}
        const {{ createTask, takeTask, completeTaskWithOutcome, clearTasks, listTasks, tasksFilePath }} = store;
        const file = tasksFilePath({json.dumps(str(tmp_path / "session.jsonl"))}, process.cwd());
        createTask({{ id: "durable", subject: "Survive a restart", resources: ["ledger"] }});
        takeTask("durable", "main");
        completeTaskWithOutcome("durable", "main", "success", "verified");
        const written = JSON.parse(fs.readFileSync(file, "utf-8"));
        clearTasks();
        const emptyAfterClear = listTasks().length;
        // Re-enter the shipped session handler. A disk-only assertion cannot
        // establish that the extension actually restores the saved task.
        await api.sessionStart(
          {{ type: "session_start", reason: "resume" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(str(tmp_path / "session.jsonl"))} }} }},
        );
        const restored = store.getTask("durable");
        console.log(JSON.stringify({{
          fileExists: fs.existsSync(file),
          persistedIds: Object.keys(written.tasks),
          persistedStatus: written.tasks.durable.status,
          persistedResult: written.tasks.durable.result,
          inMemoryAfterClear: emptyAfterClear,
          restoredStatus: restored?.status ?? null,
          restoredResult: restored?.result ?? null,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["fileExists"] is True, "a standalone tasks must reach disk"
    assert result["persistedIds"] == ["durable"]
    assert result["persistedStatus"] == "completed"
    assert result["persistedResult"] == "verified"
    assert result["inMemoryAfterClear"] == 0
    assert result["restoredStatus"] == "completed"
    assert result["restoredResult"] == "verified"


def test_a_restored_in_progress_task_returns_under_a_recovery_hold(tmp_path: Path) -> None:
    """A restored task has no holder, so it cannot still be in progress.

    Continuing to report it as in progress would show work nobody is doing, and
    handing it straight back out would retry an attempt whose outcome is unknown.
    """
    session_file = tmp_path / "session.jsonl"
    run_node(
        f"""
        {_entry_script(str(session_file))}
        const {{ createTask, takeTask, tasks, writeTasksFile, tasksFilePath }} = store;
        const file = tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        createTask({{ id: "held", subject: "Was in progress" }});
        takeTask("held", "someone");
        writeTasksFile(file, tasks);
        console.log(JSON.stringify({{ written: fs.existsSync(file) }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    result = run_node(
        f"""
        {_entry_script(str(session_file))}
        const restored = store.getTask("held");
        console.log(JSON.stringify({{
          status: restored.status,
          claimedBy: restored.claimedBy ?? null,
          recoveryRequired: (restored.status === "recovery_hold") ?? false,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["status"] == "recovery_hold"
    assert result["claimedBy"] is None, "a restored tasks has no participants, so it names no holder"


def test_a_tasks_with_participants_but_no_coordinator_still_writes_its_file(tmp_path: Path) -> None:
    """A published roster is not a coordinator.

    `isCoordinated()` answers "does this task set know about anybody else", which is
    what a take needs. The durable file is a different question: whoever claimed
    the store owns the writes, and a roster published through the seam claims
    nothing. Standing down on the first answer lost the tasks file for every
    install of `@fradser/pi-subagents` beside `@fradser/pi-tasks` that did not also
    install the team runtime: tasks recorded, no file, and nothing said so.
    """
    session_file = tmp_path / "session.jsonl"
    result = run_node(
        f"""
        import fs from "node:fs";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        const ROSTER = new Map([["alpha", {{ name: "alpha", spawnId: "s1", status: "idle" }}]]);
        globalThis[Symbol.for("pi.participant-registry")] = {{
          get: (name) => ROSTER.get(name),
          list: () => [...ROSTER.values()],
          sync: () => {{}},
          current: (name, incarnation) => ROSTER.get(name)?.spawnId === (incarnation ?? "s1"),
        }};
        const entry = store.default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        await api.sessionStart(
          {{ type: "session_start", reason: "startup" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(str(session_file))} }} }},
        );
        const file = store.tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        store.createTask({{ id: "with-a-roster", subject: "recorded beside a roster" }});
        console.log(JSON.stringify({{
          hasParticipants: store.isCoordinated(),
          storeClaimed: store.isTaskStoreClaimed(),
          fileExists: fs.existsSync(file),
          persistedIds: fs.existsSync(file) ? Object.keys(JSON.parse(fs.readFileSync(file, "utf-8")).tasks) : [],
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["hasParticipants"] is True, "the roster is what the tasks reports as its mode"
    assert result["storeClaimed"] is False, "a published roster claims the store's writes from nobody"
    assert result["fileExists"] is True, "a task set nobody else writes is this package's to write"
    assert result["persistedIds"] == ["with-a-roster"]


def test_a_claimed_tasks_is_not_emptied_by_the_session_start_that_found_the_claim(tmp_path: Path) -> None:
    """The claimer loaded the tasks and owns it. Clearing on the way to standing
    down emptied the very tasks it had just restored, and because a clear records
    no change, nothing noticed before the claimer's next snapshot persisted that
    emptiness over durable work.

    The pre-existing guard asserted only that no second writer was attached, which
    is true whether the tasks was emptied or not. This drives the claimed path
    with a populated tasks, which is the only way the claim is worth anything.
    """
    session_file = tmp_path / "session.jsonl"
    result = run_node(
        f"""
        import fs from "node:fs";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        // What a claimer does before the session starts: take the store, then
        // restore the tasks it owns.
        store.configureTaskStore({{
          get: () => undefined, current: () => false, conflicting: () => undefined,
          sync: () => {{}}, changed: () => {{}},
        }});
        store.createTask({{ id: "restored", subject: "work the claimer restored" }});
        store.createTask({{ id: "restored-too", subject: "and its neighbour" }});
        const before = store.listTasks().map((task) => task.id).sort();
        const entry = store.default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        await api.sessionStart(
          {{ type: "session_start", reason: "startup" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(str(session_file))} }} }},
        );
        const file = store.tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        console.log(JSON.stringify({{
          before,
          after: store.listTasks().map((task) => task.id).sort(),
          claimed: store.isTaskStoreClaimed(),
          wroteTheFile: fs.existsSync(file),
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["claimed"] is True
    assert result["after"] == result["before"], (
        "the tasks a claimer restored must survive this package's session_start"
    )
    assert result["before"] == ["restored", "restored-too"]


def test_a_tasks_file_missing_its_arrays_is_read_not_crashed_on(tmp_path: Path) -> None:
    """The tasks file is durable: it can be hand-edited, truncated, or written by
    an older build. A single missing `dependsOn` made `list` throw inside the
    tool, which is a crash rather than a refusal — and the standalone durability
    work is exactly what makes such a file load in a one-package install."""
    result = run_node(
        f"""
        import * as task from {json.dumps((PACKAGE / "index.ts").as_uri())};
        task.loadTasks({{
          noArrays: {{ id: "noArrays", subject: "hand-edited", resources: [], status: "pending", createdAt: 1, updatedAt: 1 }},
          noResources: {{ id: "noResources", subject: "also hand-edited", dependsOn: [], status: "pending", createdAt: 1, updatedAt: 1 }},
        }});
        const listed = await task.executeTaskList({{}});
        const taken = await task.executeTaskUpdate({{ id: "noArrays", status: "in_progress" }});
        console.log(JSON.stringify({{
          listed: listed.details.ok,
          count: listed.details.count,
          dependsOn: task.getTask("noArrays").dependsOn,
          resources: task.getTask("noResources").resources,
          takeable: taken.details.ok,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["listed"] is True, "a task set missing an array is read, not thrown on"
    assert result["count"] == 2
    assert result["dependsOn"] == []
    assert result["resources"] == []
    assert result["takeable"] is True, "and the task is still usable"


def test_a_supersession_reaches_the_durable_file_and_not_only_the_tasks(tmp_path: Path) -> None:
    """A supersession rewrites the obsolete task and every dependent's edges, and
    the mark that persisted them sat *between* the new task and those rewrites.
    The tasks file therefore kept saying the obsolete task was pending and its
    dependents still pointed at it, and nothing marked it again — so a session
    whose last change was a supersession left a file disagreeing with the tasks
    it had just changed, and a restart loaded that disagreement.

    Asserted against the file, not against memory: memory was always right, which
    is why every in-memory assertion of this transition passed.
    """
    session_file = tmp_path / "session.jsonl"
    result = run_node(
        f"""
        import fs from "node:fs";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        const entry = store.default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        await api.sessionStart(
          {{ type: "session_start", reason: "startup" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(str(session_file))} }} }},
        );
        const file = store.tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        store.createTask({{ id: "old", subject: "obsolete work" }});
        store.createTask({{ id: "dependent", subject: "builds on it", dependsOn: ["old"] }});
        // The last change this session makes is the supersession itself.
        store.createTask({{ subject: "replacement work", supersedes: ["old"] }});
        const disk = JSON.parse(fs.readFileSync(file, "utf-8")).tasks;
        console.log(JSON.stringify({{
          diskOldStatus: disk.old?.status ?? null,
          diskSupersededBy: disk.old?.supersededBy ?? null,
          diskDependentDeps: disk.dependent?.dependsOn ?? null,
          memoryOldStatus: store.getTask("old").status,
          memoryDependentDeps: store.getTask("dependent").dependsOn,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["diskOldStatus"] == "superseded", (
        "the durable tasks must record the supersession the call reported"
    )
    assert result["diskSupersededBy"] == "replacement-work"
    assert result["diskDependentDeps"] == ["replacement-work"], (
        "a dependent's migrated edge has to reach the file too, or a restart "
        "brings back the dependency on work that was replaced"
    )
    assert result["diskOldStatus"] == result["memoryOldStatus"]
    assert result["diskDependentDeps"] == result["memoryDependentDeps"]


def test_retired_task_file_is_ignored_and_preserved(tmp_path: Path) -> None:
    """The user retires the old filename. Loading and new writes use tasks.json only."""
    session_file = tmp_path / "session.jsonl"
    result = run_node(
        f"""
        import fs from "node:fs";
        import path from "node:path";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        const legacy = path.join(store.tasksDir({json.dumps(str(session_file))}, process.cwd()), "board.json");
        fs.mkdirSync(path.dirname(legacy), {{ recursive: true }});
        const oldBytes = JSON.stringify({{
          runtimeVersion: store.TASKS_FILE_VERSION,
          tasks: {{ "written-before-the-rename": {{ id: "written-before-the-rename", subject: "durable work", dependsOn: [], resources: [], status: "completed", result: "kept", createdAt: 1, updatedAt: 2 }} }},
        }});
        fs.writeFileSync(legacy, oldBytes);
        const entry = store.default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        await api.sessionStart(
          {{ type: "session_start", reason: "startup" }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => {json.dumps(str(session_file))} }} }},
        );
        const current = store.tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        // Restoring is not a change, so nothing is written until something
        // changes. That is the same rule the single-writer contract states, and
        // it is why the new file only appears after the change below.
        const beforeAnyChange = fs.existsSync(current);
        store.createTask({{ id: "after-the-rename", subject: "newer work" }});
        console.log(JSON.stringify({{
          restored: store.getTask("written-before-the-rename")?.status ?? null,
          result: store.getTask("written-before-the-rename")?.result ?? null,
          noticeSaysWhere: (store.storeNotice() ?? "").includes("pre-rename"),
          legacyStillThere: fs.existsSync(legacy),
          legacyUnchanged: fs.readFileSync(legacy, "utf8") === oldBytes,
          retiredExports: ["LEGACY_TASKS_FILE", "legacyTasksFilePath", "resolveTasksFileToRead"].filter(name => name in store),
          beforeAnyChange,
          wroteToTheNewName: fs.existsSync(current),
          newFileHasBoth: fs.existsSync(current)
            ? Object.keys(JSON.parse(fs.readFileSync(current, "utf-8")).tasks).sort()
            : [],
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["restored"] is None, "The retired file does not supply runtime tasks"
    assert result["result"] is None
    assert result["noticeSaysWhere"] is False
    assert result["retiredExports"] == []
    assert result["beforeAnyChange"] is False, "restoring is not a change, so nothing is written"
    assert result["wroteToTheNewName"] is True, "writes only ever go to tasks.json"
    assert result["newFileHasBoth"] == ["after-the-rename"], "Only current tasks enter the new task file"
    assert result["legacyStillThere"] is True
    assert result["legacyUnchanged"] is True, "Retirement removes support, not the user's file"


def test_a_coordinator_keeps_sole_ownership_of_the_tasks_file(tmp_path: Path) -> None:
    """A layer that already owns the store must not gain a second writer.

    Two writers on one file is the failure this guards: the second rewrites the
    first's tasks from a container that never saw the first's edits. Claimed
    before the session starts, which is where a real coordinator does it.
    """
    session_file = tmp_path / "session.jsonl"
    result = run_node(
        _entry_script(
            str(session_file),
            before_start="""
        let changed = 0;
        store.configureTaskStore({
          get: () => undefined, current: () => false, conflicting: () => undefined,
          sync: () => {}, changed: () => { changed += 1; },
        });
        """,
        )
        + f"""
        const file = store.tasksFilePath({json.dumps(str(session_file))}, process.cwd());
        store.createTask({{ subject: "after a coordinator claimed the tasks" }});
        console.log(JSON.stringify({{
          changed,
          coordinated: store.isCoordinated(),
          wroteTheFile: fs.existsSync(file),
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["coordinated"] is True
    assert result["changed"] == 1, "the coordinator's own change hook is the one that ran"
    assert result["wroteTheFile"] is False, (
        "a coordinator owns the tasks file; this package must not attach a second writer"
    )


def test_a_session_that_cannot_be_read_does_not_inherit_the_last_writers_file(tmp_path: Path) -> None:
    """`/new` and resume re-fire session_start with a different tasks file, so a
    writer attached for the previous session has to be released before the new one
    is decided on. Keeping it means work recorded under the session you are in
    lands in the file of the session you left: two task sets, one writer, and neither
    one holding what it says it holds."""
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    result = run_node(
        f"""
        import fs from "node:fs";
        import path from "node:path";
        const store = await import({json.dumps((PACKAGE / "index.ts").as_uri())});
        const entry = store.default;
        const api = {{
          registerTool: () => {{}},
          on: (event, handler) => {{
            if (event !== "session_start") return;
            const previous = api.sessionStart;
            api.sessionStart = async (...args) => {{
              if (previous) await previous(...args);
              await handler(...args);
            }};
          }},
          events: {{ emit() {{}} }},
        }};
        entry(api);
        const start = (file, reason) => api.sessionStart(
          {{ type: "session_start", reason }},
          {{ cwd: process.cwd(), sessionManager: {{ getSessionFile: () => file }} }},
        );

        // A session this process owns and writes.
        await start({json.dumps(str(first))}, "startup");
        const firstFile = store.tasksFilePath({json.dumps(str(first))}, process.cwd());
        store.createTask({{ id: "from-first", subject: "recorded while the first session was active" }});
        const firstBefore = fs.readFileSync(firstFile, "utf-8");

        // A session switch, and the new tasks file is present but unreadable.
        const secondFile = store.tasksFilePath({json.dumps(str(second))}, process.cwd());
        fs.mkdirSync(path.dirname(secondFile), {{ recursive: true }});
        fs.writeFileSync(secondFile, "{{ not json", "utf-8");
        await start({json.dumps(str(second))}, "new");

        // Work recorded now belongs to the session that is open.
        store.createTask({{ id: "from-second", subject: "recorded after the switch" }});
        console.log(JSON.stringify({{
          firstUnchanged: fs.readFileSync(firstFile, "utf-8") === firstBefore,
          firstIds: Object.keys(JSON.parse(firstBefore).tasks),
          secondUntouched: fs.readFileSync(secondFile, "utf-8"),
          reported: (store.storeNotice() ?? "").includes(secondFile),
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["firstUnchanged"] is True, (
        "the writer for the session that was left must not still be attached"
    )
    assert result["firstIds"] == ["from-first"]
    assert result["secondUntouched"] == "{ not json", (
        "a task set this process could not read is left exactly as it was found"
    )
    assert result["reported"] is True, "the tool says why rather than presenting nothing"

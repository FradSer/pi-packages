"""Work Item domain rules and durable board persistence.

Contract: packages/tasks/features/work-domain.feature

Everything here imports through the package barrel, so a symbol missing from
`index.ts` fails rather than silently passing through a deep relative path.
`PI_CODING_AGENT_DIR` is redirected to a temporary directory because the board
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


# ── Rule: the board file is durable and refuses to guess ──


def test_board_round_trip_and_refusals(tmp_path: Path) -> None:
    result = run(
        '''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "task-board-"));
        const file = task.boardFilePath("session-one.jsonl", cwd);
        const tasks = {
          "fix-storage": { id: "fix-storage", subject: "Fix storage", dependsOn: [], resources: ["firmware/storage"],
            status: "pending", createdAt: 1, updatedAt: 1 },
          "add-tests": { id: "add-tests", subject: "Add tests", dependsOn: ["fix-storage"], resources: [],
            status: "in_progress", claimedBy: "reviewer", createdAt: 2, updatedAt: 3 },
        };
        task.writeBoardFile(file, tasks);
        const roundTrip = task.readBoardFile(file);
        const absent = task.readBoardFile(path.join(cwd, "nope", "board.json"));
        const garbage = path.join(cwd, "garbage.json");
        fs.writeFileSync(garbage, "{not json");
        let garbageError = "";
        try { task.readBoardFile(garbage); } catch (error) { garbageError = error.message; }
        const old = path.join(cwd, "old.json");
        fs.writeFileSync(old, JSON.stringify({ runtimeVersion: 1, tasks: { x: { id: "x" } } }));
        let versionError = "";
        try { task.readBoardFile(old); } catch (error) { versionError = error.message; }
        console.log(JSON.stringify({
          roundTrip,
          absent: absent ?? null,
          garbageError,
          versionError,
          expectedVersion: task.WORK_RUNTIME_VERSION,
          perSession: task.boardDir("session-two.jsonl", cwd) !== file.replace(/\\/board\\.json$/, ""),
          deterministic: task.boardDir("session-one.jsonl", cwd) === path.dirname(file),
          cwdScope: task.boardDir(undefined, cwd) !== path.dirname(file),
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
    assert result["absent"] is None, "an absent board is a fresh session, not an error"
    assert "not valid JSON" in str(result["garbageError"]) and "refusing to treat it as an empty board" in str(result["garbageError"])
    assert str(result["expectedVersion"]) in str(result["versionError"])
    assert "Incompatible Work snapshot version 1" in str(result["versionError"]), (
        "the message must not name a package that may not be installed"
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
        const intent = { taskId: "t_1", worker: "frontend", spawnId: "s1", timestamp: Date.now() };
        const won = task.createTaskIntent(dir, "t_1", intent);
        const lost = task.createTaskIntent(dir, "t_1", { ...intent, worker: "backend" });
        const traversal = task.createTaskIntent(dir, "../../../escape", intent);
        const escaped = fs.existsSync(path.resolve(dir, "../../../escape.json"));
        const taken = task.takeTaskIntent(dir);

        const bad = fs.mkdtempSync(path.join(os.tmpdir(), "task-intent-bad-"));
        fs.writeFileSync(path.join(bad, "b.json"), JSON.stringify({ taskId: "t", worker: "", spawnId: "s", timestamp: 1 }));
        const missingIdentity = task.takeTaskIntent(bad);
        fs.writeFileSync(path.join(bad, "c.json"), JSON.stringify({ taskId: "t", worker: "w", spawnId: "s", timestamp: 1, status: "maybe" }));
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
    assert isinstance(taken, dict) and taken["intent"]["worker"] == "frontend"
    assert result["missingIdentity"] == 'malformed task intent "b.json" was consumed (requires non-empty taskId/worker/spawnId and finite timestamp)'
    assert result["badStatus"] == 'malformed task intent "c.json" was consumed (invalid submission status)'
    assert result["youngIntent"] is None
    assert result["youngDiagnostic"] is None, "a half-written marker inside the grace is not an error yet"
    assert result["youngSurvived"] is True, "destroying an in-flight intent would strand its author"
    assert result["oldDiagnostic"] == 'unreadable task intent "young.json" was consumed'
    assert int(str(result["grace"])) == 30_000
    assert result["empty"] == {}, "a missing directory is empty, not an error"


# ── Rule: the package has no coordination coupling ──


def test_the_package_imports_no_coordination_concept() -> None:
    """The boundary that makes @fradser/pi-tasks installable without the team runtime."""
    allowed_prefixes = ("node:", "@earendil-works/pi-coding-agent", "@fradser/pi-kit", "./")
    for source_file in sorted((PACKAGE / "src").glob("*.ts")):
        text = source_file.read_text(encoding="utf-8")
        for specifier in re.findall(r'from "([^"]+)"', text):
            assert specifier.startswith(allowed_prefixes), f"{source_file.name} imports {specifier}"
        for forbidden in ("teammate", "Teammate", "spawnResident", "mailbox", "Mailbox", "agent_event"):
            assert forbidden not in text, f"{source_file.name} references {forbidden}"


def test_the_barrel_exposes_the_whole_domain() -> None:
    """A symbol missing from index.ts must fail here rather than silently
    passing through a deep relative import in some consumer."""
    result = run(
        f'''
        const names = {json.dumps([
            "taskIdFromSubject", "normalizeResources", "canonicalDependency", "canonicalDependencies",
            "hasDependencyCycle", "resourcesConflict", "MAX_TASK_ID_LENGTH",
            "tasksRoot", "boardDir", "boardFilePath", "claimsDir", "submissionsDir",
            "readBoardFile", "writeBoardFile", "createTaskIntent", "takeTaskIntent",
            "INTENT_PUBLISH_GRACE_MS", "WORK_RUNTIME_VERSION", "sessionKey",
        ])};
        console.log(JSON.stringify({{ missing: names.filter((name) => task[name] === undefined) }}));
        ''',
        Path("/tmp"),
    )
    assert result["missing"] == [], f"the barrel does not expose: {result['missing']}"

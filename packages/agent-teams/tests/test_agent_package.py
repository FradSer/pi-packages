from __future__ import annotations


# ── test_agent_package.py ──

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"
REPO = PACKAGE.parents[1]
# The subagent execution layer moved to its own package during the
# subagents / task / agent-teams split. Static-source assertions still need a
# real path; runtime imports go through the package specifier instead.
SUBAGENTS_SRC = REPO / "packages" / "subagents" / "src"

LEADER_TOOLS = {
    "agent_start",
    "agent_input",
    "agent_stop",
    "agent_list",
    "agent_list",
    "message",
}
WORKER_TOOLS = {
    "message",
    "task",
}
REMOVED_TOOLS = {
    "teammate_message",
    "teammate_run",
    "teammate_fanout",
    "teammate_cancel",
    "teammate_retry",
    "teammate_status",
    "teammate_register",
    "teammate_broadcast",
    "teammate_create_task",
    "teammate_start_task",
    "teammate_wait",
}


def source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def subagents_source(name: str) -> str:
    """Read a module that now lives in @fradser/pi-subagents."""
    return (SUBAGENTS_SRC / name).read_text(encoding="utf-8")


def run_node(
    script: str,
    *args: str,
    env_overrides: dict[str, str] | None = None,
    module_mocks: bool = False,
) -> dict[str, object]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    env.update(env_overrides or {})
    use_bun = not module_mocks and "node:test" not in script and shutil.which("bun") is not None
    cmd = (
        ["bun", "-e", textwrap.dedent(script), *args]
        if use_bun
        else [
            "node",
            *(  ["--experimental-test-module-mocks"] if module_mocks else []),
            "--input-type=module",
            "--eval",
            textwrap.dedent(script),
            *args,
        ]
    )
    result = subprocess.run(
        cmd,
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def agent_dir_env(tmp: Path) -> dict[str, str]:
    return {"PI_CODING_AGENT_DIR": str(tmp)}


def test_manifest_declares_a_bundle_of_three_extension_packages() -> None:
    """This package is a bundle. It registers `message` and loads the extension
    entries of the two packages that own `agent` and `task`, so installing it
    gives all three tools with one registrant each.

    The dependency entries are node_modules paths, which is what Pi sanctions for
    a bundled package: "Other Pi packages used as dependencies must be included in
    the published tarball and referenced through their node_modules resource
    paths." What is forbidden is naming the other package's *source*, which would
    break whenever its layout or packing changed.
    """
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-agent-teams"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"] == {
        "extensions": [
            "./index.ts",
            "./node_modules/@fradser/pi-subagents/index.ts",
        ]
    }
    assert "skills" not in manifest["files"]
    assert "references" in manifest["files"] and not (PACKAGE / "agents").exists()
    # The two bundled packages must be real runtime dependencies, not peers: a
    # peer is supplied by the host and would be absent in a plain install.
    for dependency in ("@fradser/pi-subagents",):
        assert dependency in manifest["dependencies"], dependency
        assert dependency not in manifest.get("peerDependencies", {}), dependency


def test_every_bundled_extension_entry_exists_and_is_loadable() -> None:
    """Each listed path must resolve to a real file that provides a default
    export. A library barrel would have none, and pointing at one fails at load
    time with nothing to suggest why.

    Both spellings count: a direct `export default function`, and a package entry
    that re-exports its implementation module's default.
    """
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    for relative in manifest["pi"]["extensions"]:
        resolved = (PACKAGE / relative.removeprefix("./")).resolve()
        assert resolved.is_file(), f"{relative} is declared but missing"
        text = resolved.read_text(encoding="utf-8")
        provides_default = "export default" in text or re.search(
            r"export\s*\{\s*default\s*\}", text
        )
        assert provides_default, f"{relative} provides no default export"


def test_the_coordination_contribution_is_declared_and_passed_to_every_spawn() -> None:
    """The execution layer hardcodes no capability set, so this package must
    declare what its own worker extension registers and contribute it per spawn.

    The declaration lives in a dependency-free module because both the
    registration site (worker.ts) and the presentation site (tool-copy.ts) read
    it, and worker.ts imports tool-copy.ts — declaring it in worker.ts would
    close a cycle.
    """
    capability = source("capability-tools.ts")
    assert '"message"' in capability and '"task"' in capability
    assert "WORKER_EXTENSION_PATH" in capability
    # The declaration must match what worker.ts actually registers, so a spawn
    # can never advertise a tool id nothing implements.
    worker = source("worker.ts")
    for tool in ("message", "task"):
        assert f'name: "{tool}"' in worker, tool
    # Every spawn contributes this package's worker extension and capability
    # set. Neither package may hardcode the other's contribution.
    machine = source("team-machine.ts")
    assert "spawnResident(" in machine
    assert "SUBAGENT_EXTENSION_PATH" in machine and "WORKER_EXTENSION_PATH" in machine
    assert "extensions: workerExtensions" in machine
    assert "...WORKER_CAPABILITY_TOOLS" in machine
    assert "capabilityTools," in machine
    # The two extensions really are combined into one list, not chosen between.
    assert "WORKER_EXTENSION_PATH," in machine and "] : [" in machine
    # The subagents contribution is memory-gated: a child with no memory folder
    # is handed neither the extension that registers agent_memory nor the tool,
    # so a grant line can never promise a capability the child lacks. Asserted
    # behaviourally in test_capability_and_blocker_contract.py; this pins the
    # two lists to one decision so they cannot drift apart.
    # Adopted VISION.md: every disk scope supplies Memory without an opt-in.
    assert 'const durable = agent.scope !== "session";' in machine
    assert "const memoryEnabled = durable;" in machine
    assert "...(memoryEnabled ? AGENT_MEMORY_CAPABILITY_TOOLS : [])" in machine
    assert "...(memoryEnabled ? [SUBAGENT_EXTENSION_PATH] : [])" in machine
    # And the execution layer stays agnostic about this package's tool names.
    assert "agent_event" not in subagents_source("spawner.ts")


def test_leader_tool_surface_is_exact() -> None:
    """Each tool has exactly one registrant *per process*.

    The task store is single-writer, so a spawned child cannot take a task by writing
    the tasks; it queues an intent and the leader applies it. That means `task`
    has two registrations by necessity — the worker
    slice's in the child — and they never load into the same process. Asserting
    one registrant per *file* would be asserting something false, and asserting
    nothing would let a second leader-side registrant in unnoticed, which is the
    failure that actually collides.

    So the leader side is enumerated exactly, and the worker side is enumerated
    separately.
    """
    shipped = [
        path
        for package in ("agent-teams", "subagents")
        for path in (REPO / "packages" / package).rglob("*.ts")
        if "node_modules" not in path.parts and "tests" not in path.parts
        and path != PACKAGE / "src" / "worker.ts"
    ]
    shipped_text = {str(path.relative_to(REPO)): path.read_text(encoding="utf-8") for path in shipped}
    # The intent family registers itself from one closed name list, so a literal
    # per-name search cannot find its registrant. Pin the registrar and the schema
    # home instead: each must have exactly one, and no shipped file may spell an
    # intent name into a registration of its own.
    assert [path for path, text in shipped_text.items() if "registerIntentTools(pi," in text] == [
        "packages/subagents/src/extension.ts"
    ], "the intent family must have exactly one registrar"
    assert [path for path, text in shipped_text.items() if "export const INTENT_TOOL_SCHEMAS" in text] == [
        "packages/subagents/src/intent-tools.ts"
    ], "the intent schemas must have exactly one home"
    # The leader registers exactly one tool. The retired task tools have no
    # registrant anywhere in the shipped source.
    leader_owners = {
        "message": PACKAGE / "src" / "tools.ts",
    }
    worker_owners = {
        "message": PACKAGE / "src" / "worker.ts",
        "task": PACKAGE / "src" / "worker.ts",
    }
    for tool, owner in leader_owners.items():
        registrants = [path for path, text in shipped_text.items() if f'name: "{tool}"' in text]
        assert registrants == [str(owner.relative_to(REPO))], f"leader {tool} has {registrants}"
    worker_text = (PACKAGE / "src" / "worker.ts").read_text(encoding="utf-8")
    for tool in worker_owners:
        assert f'name: "{tool}"' in worker_text, f"worker {tool}"
    # The child never gets a child control tool: nesting is bounded by the
    # depth guard, not by the tool being absent from a file. The check is on the
    # registration, not the bare name: `agent_start` is also a harness session
    # event the worker listens for.
    for tool in LEADER_TOOLS - WORKER_TOOLS:
        for path, text in list(shipped_text.items()) + [("worker.ts", worker_text)]:
            assert f'name: "{tool}"' not in text, (tool, path)
    for tool in REMOVED_TOOLS:
        for path in shipped + [PACKAGE / "src" / "worker.ts"]:
            assert f'name: "{tool}"' not in path.read_text(encoding="utf-8"), tool


def test_worker_surface_is_capability_bound() -> None:
    worker = source("worker.ts")
    for tool in WORKER_TOOLS:
        assert f'name: "{tool}"' in worker, tool
    # Worker capabilities bind through environment, never runtime registration.
    assert "PI_TEAMMATE_WORKER_NAME" in worker
    assert "PI_TEAMMATE_CLAIMS_DIR" in worker
    for tool in LEADER_TOOLS - WORKER_TOOLS:
        assert f'name: "{tool}"' not in worker


def test_worker_claim_uses_exclusive_create_marker_files() -> None:
    worker = source("worker.ts")
    assert "createTaskIntent" in worker
    payload = run_node(
        f'''\
        import {{ createTaskIntent, takeTaskIntent }} from "./src/task-domain/index.ts";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-intents-"));
        const intent = {{ taskId: "t_1", participant: "security", spawnId: "s1", timestamp: 1 }};
        const won = createTaskIntent(dir, "t_1", intent);
        const lost = createTaskIntent(dir, "t_1", {{ ...intent, participant: "backend" }});
        const drained = takeTaskIntent(dir);
        const next = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          won,
          lost,
          drainedHolder: drained?.intent?.participant ?? null,
          tasksEmptyAgain: next.intent === undefined && next.diagnostic === undefined,
        }}));
        '''
    )
    assert payload["won"] is True
    assert payload["lost"] is False
    assert payload["drainedHolder"] == "security"
    assert payload["tasksEmptyAgain"] is True


def test_task_intent_publishes_complete_records_without_leftover_temporaries() -> None:
    payload = run_node(
        f'''\
        import {{ createTaskIntent, takeTaskIntent }} from "./src/task-domain/index.ts";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-atomicintents-"));
        const intent = {{ taskId: "t_atomic", participant: "security", spawnId: "s1", timestamp: 1, status: "completed", result: "evidence" }};
        const won = createTaskIntent(dir, "t_atomic", intent);
        const filesAfterWin = fs.readdirSync(dir);
        const published = JSON.parse(fs.readFileSync(path.join(dir, "t_atomic.json"), "utf-8"));
        const lost = createTaskIntent(dir, "t_atomic", {{ ...intent, participant: "backend" }});
        const filesAfterLoss = fs.readdirSync(dir);
        const drained = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          won,
          lost,
          winnerIsComplete: published.participant === "security" && published.taskId === "t_atomic" && published.spawnId === "s1",
          noTemporariesAfterWin: filesAfterWin.every((name) => !name.endsWith(".tmp")),
          noTemporariesAfterLoss: filesAfterLoss.every((name) => !name.endsWith(".tmp")),
          onlyTheWinnerPublished: filesAfterLoss.length === 1,
          drainedHolder: drained?.intent?.participant ?? null,
        }}));
        '''
    )
    assert payload["won"] is True
    assert payload["lost"] is False
    assert payload["winnerIsComplete"] is True
    assert payload["noTemporariesAfterWin"] is True
    assert payload["noTemporariesAfterLoss"] is True
    assert payload["onlyTheWinnerPublished"] is True
    assert payload["drainedHolder"] == "security"


def test_fully_consumed_inbox_rotates_instead_of_destroying_records(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, routePeerInboxes }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ appendInboxMessage, inboxPath, stateFilePath }} from "{(SRC / "statefile.ts").as_uri()}";
        import {{ registerAgent, resetState }} from "{(SRC / "state.ts").as_uri()}";
        import fs from "node:fs";
        import path from "node:path";
        const root = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const inbox = inboxPath(stateFilePath(undefined, root), "w");
        const body = "x".repeat(48 * 1024);
        for (let index = 0; index < 7; index++) appendInboxMessage(inbox, {{ id: `msg-${{index}}`, from: "peer", subject: "s", body }});
        const sizeBefore = fs.statSync(inbox).size;
        routePeerInboxes();
        routePeerInboxes();
        routePeerInboxes();
        const dir = path.dirname(inbox);
        const archived = fs.readdirSync(dir).filter((name) => name.includes(".compacted-"));
        const archivedRecords = archived.length === 1 ? fs.readFileSync(path.join(dir, archived[0]), "utf-8").split("\\n").filter(Boolean).length : -1;
        console.log(JSON.stringify({{
          oversized: sizeBefore > 256 * 1024,
          archivedCount: archived.length,
          archivedRecords,
          liveInboxGone: !fs.existsSync(inbox),
          archiveIsNotConsoleVisible: archived.every((name) => !name.endsWith(".jsonl")),
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["oversized"] is True
    assert payload["archivedCount"] == 1
    # Rotation preserves every consumed record for forensics; truncation lost them.
    assert payload["archivedRecords"] == 7
    assert payload["liveInboxGone"] is True
    assert payload["archiveIsNotConsoleVisible"] is True


def test_take_task_intent_skips_malformed_records() -> None:
    payload = run_node(
        f'''\
        import {{ takeTaskIntent, INTENT_PUBLISH_GRACE_MS }} from "./src/task-domain/index.ts";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-badintents-"));
        fs.writeFileSync(path.join(dir, "a-broken.json"), "{{ not json");
        fs.writeFileSync(path.join(dir, "b-good.json"), JSON.stringify({{ taskId: "t_2", participant: "tests", spawnId: "s", timestamp: 2 }}));
        // A freshly unparseable file may still be mid-publish: it is retried,
        // never destroyed, so its author cannot be stranded silently.
        const fresh = takeTaskIntent(dir);
        const freshPreserved = fs.existsSync(path.join(dir, "a-broken.json"));
        // An aged unparseable file is a real malformed record and is consumed.
        const aged = Date.now() - INTENT_PUBLISH_GRACE_MS - 1000;
        fs.utimesSync(path.join(dir, "a-broken.json"), aged / 1000, aged / 1000);
        const drained = takeTaskIntent(dir);
        const after = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          freshHolder: fresh?.intent?.participant ?? null,
          freshPreserved,
          drainedWasDiagnostic: typeof drained.diagnostic === "string" && drained.intent === undefined,
          malformedConsumed: !fs.existsSync(path.join(dir, "a-broken.json")),
          drainedEmpty: after.intent === undefined && after.diagnostic === undefined,
        }}));
        '''
    )
    # The good intent behind the ambiguous file is still drained in the same pass.
    assert payload["freshHolder"] == "tests"
    assert payload["freshPreserved"] is True
    assert payload["drainedWasDiagnostic"] is True
    assert payload["malformedConsumed"] is True
    assert payload["drainedEmpty"] is True


def test_inbox_roundtrip_offsets_and_diagnostics() -> None:
    payload = run_node(
        f'''\
        import {{ appendInboxMessage, inboxPath, readJsonlBatch, writeRoster, readRoster, rosterPath, stateFilePath, writeStateFile }} from "{(SRC / "statefile.ts").as_uri()}";
        import {{ readTasksFile, writeTasksFile }} from "./src/task-domain/index.ts";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-mail-"));
        const stateFile = dir + "/state.json";
        const inbox = inboxPath(stateFile, "backend");
        appendInboxMessage(inbox, {{ id: "m1", from: "security", subject: "finding", body: "auth issue" }});
        appendInboxMessage(inbox, {{ id: "m2", from: "tests", subject: "flaky", body: "test flake" }});
        const first = readJsonlBatch(inbox, 0);
        const consumed = readJsonlBatch(inbox, first.nextOffset);
        fs.appendFileSync(inbox, "{{ broken\\n");
        const after = readJsonlBatch(inbox, first.nextOffset);
        writeRoster(rosterPath(stateFile), [{{ name: "backend", agent: "worker", status: "idle" }}]);
        const roster = readRoster(rosterPath(stateFile));
        writeStateFile(stateFile, {{ agents: {{}}, tasks: {{}}, leaderMailbox: [], messageCounter: 0, taskCounter: 0, workerEventOffsets: {{}}, workerEventIds: {{}}, peerInboxOffsets: {{}}, peerDeliveredIds: {{}} }});
        writeTasksFile(dir + "/tasks.json", {{ t_1: {{ id: "t_1", subject: "s", dependsOn: [], status: "pending", createdAt: 1, updatedAt: 1 }} }});
        const tasks = readTasksFile(dir + "/tasks.json");
        console.log(JSON.stringify({{
          firstCount: first.records.length,
          secondId: consumed.records.length === 0 ? "none" : JSON.parse(JSON.stringify(consumed.records[0])).id,
          diagnostics: after.diagnostics.length,
          rosterName: roster[0]?.name ?? null,
          tasksSubject: tasks?.tasks.t_1?.subject ?? null,
          inboxInsideSessionDir: inbox.startsWith(dir),
        }}));
        '''
    )
    assert payload["firstCount"] == 2
    assert payload["secondId"] == "none"
    assert payload["diagnostics"] >= 1
    assert payload["rosterName"] == "backend"
    assert payload["tasksSubject"] == "s"
    assert payload["inboxInsideSessionDir"] is True


def test_state_machine_roster_and_tasks_rules() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerAgent, getAgent, livingAgents, idleAgents,
                 failTasksHeldBy, loadTasks, updateAgent, isValidAgentName,
                 createTask, applyClaimIntent, applySubmissionIntent,
                 getTask, listTasks, pendingTasks, deliverToLeader, receiveWorkerMessage }} from "{(SRC / "state.ts").as_uri()}";
        function snapshot() {{
          const t = (id) => getTask(id)?.status ?? null;
          return {{}};
        }}
        resetState();
        const badName = registerAgent({{ name: "has space", role: "worker", spawnId: "s0", pid: 0, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const first = registerAgent({{ name: "security", role: "reviewer", spawnId: "sa", pid: 1, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const duplicate = registerAgent({{ name: "security", role: "worker", spawnId: "sb", pid: 2, status: "starting", isolation: "none", createdAt: 2, updatedAt: 2 }});
        updateAgent("security", {{ status: "idle" }});
        const gate = createTask({{ subject: "base review" }});
        const dependent = createTask({{ subject: "fix findings", dependsOn: [gate.task.id] }});
        const unknownDep = createTask({{ subject: "x", dependsOn: ["t_missing"] }});
        const emptySubject = createTask({{ subject: "  " }});
        const claimBlocked = applyClaimIntent({{ taskId: dependent.task.id, participant: "security", spawnId: "sa", timestamp: 1 }});
        const claimOk = applyClaimIntent({{ taskId: gate.task.id, participant: "security", spawnId: "sa", timestamp: 1 }});
        registerAgent({{ name: "ghost", role: "worker", spawnId: "sx", pid: 2, status: "idle", isolation: "none", createdAt: 2, updatedAt: 2 }});
        const doubleClaim = applyClaimIntent({{ taskId: gate.task.id, participant: "ghost", spawnId: "sx", timestamp: 2 }});
        const wrongHolder = applySubmissionIntent({{ taskId: gate.task.id, participant: "ghost", spawnId: "sx", status: "completed", timestamp: 3 }});
        const submitted = applySubmissionIntent({{ taskId: gate.task.id, participant: "security", spawnId: "sa", status: "completed", result: "clean", timestamp: 4 }});
        const unlocked = pendingTasks().map((task) => task.id);
        const staleEvent = receiveWorkerMessage({{ id: "e1", type: "message", worker: "security", spawnId: "OLD", body: "b" }});
        const freshEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const dupEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const released = failTasksHeldBy("nobody", "reason");
        // Capture pre-reset values before the resume simulation wipes the tasks.
        const before = {{
          gateStatus: getTask(gate.task.id)?.status ?? null,
          unlockedContainsDependent: pendingTasks().some((task) => task.id === dependent.task.id),
          staleEventAccepted: staleEvent,
          freshEventAccepted: freshEvent,
          duplicateSuppressed: dupEvent === false,
          releasedCount: released.length,
        }};
        // Resume semantics: claimed tasks die with their holders.
        resetState();
        const reloaded = loadTasks({{ t_9: {{ id: "t_9", subject: "carried over", dependsOn: [], status: "in_progress", claimedBy: "dead", createdAt: 1, updatedAt: 1 }}, t_8: {{ id: "t_8", subject: "finished", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }});
        console.log(JSON.stringify({{
          badNameOk: badName.ok,
          firstOk: first.ok,
          duplicateOk: duplicate.ok,
          unknownDepOk: unknownDep.ok,
          emptySubjectOk: emptySubject.ok,
          claimBlockedReason: claimBlocked.reason ?? null,
          claimOkApplied: claimOk.applied,
          doubleClaimReason: (doubleClaim.reason ?? "").includes("is in progress"),
          wrongHolderRefused: wrongHolder.refusal === "held-by-other" && (wrongHolder.reason ?? "").includes("is held by"),
          submittedOk: submitted.ok,
          ...before,
          reloadedCount: reloaded,
          resumedClaimBackToPending: getTask("t_9")?.status ?? null,
          resumeKeptCompleted: getTask("t_8")?.status ?? null,
        }}));
        ''',
    )
    assert payload["badNameOk"] is False
    assert payload["firstOk"] is True
    assert payload["duplicateOk"] is False
    assert payload["unknownDepOk"] is False
    assert payload["emptySubjectOk"] is False
    # The refusal names the unfinished prerequisite and what would satisfy it,
    # rather than a phrase the reader has to recognise.
    assert payload["claimBlockedReason"] is not None and '"base-review"' in payload["claimBlockedReason"] and "not completed" in payload["claimBlockedReason"]
    assert payload["claimOkApplied"] is True
    assert payload["doubleClaimReason"] is True
    assert payload["wrongHolderRefused"] is True
    assert payload["submittedOk"] is True
    assert payload["gateStatus"] == "completed"
    assert payload["unlockedContainsDependent"] is True
    assert payload["staleEventAccepted"] is False
    assert payload["freshEventAccepted"] is True
    assert payload["duplicateSuppressed"] is True
    assert payload["releasedCount"] == 0
    assert payload["reloadedCount"] == 2
    assert payload["resumedClaimBackToPending"] == "blocked"
    assert payload["resumeKeptCompleted"] == "completed"


def test_wake_prompt_composes_deliveries_and_paced_notice() -> None:
    payload = run_node(
        f'''\
        import {{ buildWakePrompt, NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        const prompt = buildWakePrompt(
          [{{ id: "m1", from: "security", subject: "challenge", body: "your finding misses X", timestamp: 1 }}],
          [{{ id: "t_3", subject: "verify hotfix" }}],
          true,
        );
        const quiet = buildWakePrompt([], [], false);
        console.log(JSON.stringify({{
          hasInbox: prompt.includes("=== INBOX (1 new) ==="),
          hasSender: prompt.includes("From security · challenge"),
          hasBody: prompt.includes("your finding misses X"),
          hasNotice: prompt.includes("Unclaimed tasks: t_3 (verify hotfix)"),
          suggestsTaking: prompt.includes("task update status=in_progress"),
          quietEmpty: quiet === "",
          paceMs: NOTICE_PACE_MS,
        }}));
        '''
    )
    assert payload["hasInbox"] is True
    assert payload["hasSender"] is True
    assert payload["hasBody"] is True
    assert payload["hasNotice"] is True
    assert payload["suggestsTaking"] is True
    assert payload["quietEmpty"] is True
    assert payload["paceMs"] == 5 * 60 * 1000


def test_notice_pacing_defaults_to_minutes_and_is_configurable() -> None:
    default_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        '''
    )
    override_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        ''',
        env_overrides={"PI_TEAMMATE_NOTICE_PACE_MS": "45000"},
    )
    invalid_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        ''',
        env_overrides={"PI_TEAMMATE_NOTICE_PACE_MS": "not-a-number"},
    )
    assert default_payload["paceMs"] == 5 * 60 * 1000
    assert override_payload["paceMs"] == 45_000
    assert invalid_payload["paceMs"] == 5 * 60 * 1000


def test_fresh_claimable_filter_is_one_shot_per_task() -> None:
    payload = run_node(
        f'''\
        import {{ freshClaimableTasks }} from "{(SRC / "team-machine.ts").as_uri()}";
        const tasks = [{{ id: "t_1" }}, {{ id: "t_2" }}, {{ id: "t_3" }}];
        console.log(JSON.stringify({{
          firstPass: freshClaimableTasks(undefined, tasks).map((task) => task.id),
          afterNotice: freshClaimableTasks(["t_1", "t_2"], tasks).map((task) => task.id),
          emptyWhenAllSeen: freshClaimableTasks(["t_1", "t_2", "t_3"], tasks).length === 0,
        }}));
        '''
    )
    assert payload["firstPass"] == ["t_1", "t_2", "t_3"]
    assert payload["afterNotice"] == ["t_3"]
    assert payload["emptyWhenAllSeen"] is True


def test_repeated_verify_failures_escalate_once_then_go_quiet() -> None:
    payload = run_node(
        f'''\
        import {{ reactToVerifyFailure, VERIFY_FAILURE_ESCALATE_AFTER }} from "{(SRC / "team-machine.ts").as_uri()}";
        const first = reactToVerifyFailure(undefined);
        const second = reactToVerifyFailure(first);
        const third = reactToVerifyFailure(second);
        console.log(JSON.stringify({{
          escalateAfter: VERIFY_FAILURE_ESCALATE_AFTER,
          first,
          second,
          third,
        }}));
        '''
    )
    assert payload["escalateAfter"] == 2
    assert payload["first"] == {"count": 1, "escalated": False, "escalateToLeader": False}
    assert payload["second"] == {"count": 2, "escalated": True, "escalateToLeader": True}
    assert payload["third"] == {"count": 3, "escalated": True, "escalateToLeader": False}


def test_task_ids_are_meaningful_slugs_of_their_subjects() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask, loadTasks }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const a = createTask({{ subject: "Polish login flow" }});
        const b = createTask({{ subject: "Polish login flow!" }});
        const c = createTask({{ subject: "修复登录流程" }});
        const d = createTask({{ subject: "***" }});
        loadTasks({{ t_9: {{ id: "t_9", subject: "carried over", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }});
        const afterResume = createTask({{ subject: "Carried over" }});
        console.log(JSON.stringify({{
          a: a.task.id,
          b: b.task.id,
          c: c.task.id,
          d: d.task.id,
          distinct: a.task.id !== b.task.id,
          afterResume: afterResume.task.id,
        }}));
        '''
    )
    assert payload["a"] == "polish-login-flow"
    assert payload["b"] == "polish-login-flow-1"
    assert payload["c"] == "修复登录流程"
    assert payload["d"] == "task"
    assert payload["distinct"] is True
    # A resumed tasks keeps its legacy ids; new slugs still never collide.
    assert payload["afterResume"] != "t_10"
    assert source("state.ts").count("taskCounter") == 0


def test_task_lookups_ignore_prototype_property_names() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask, getTask, applyClaimIntent, loadTasks, registerAgent }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerAgent({{ name: "w", role: "worker", spawnId: "s", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const depBefore = createTask({{ subject: "real work", dependsOn: ["constructor"] }});
        const made = createTask({{ subject: "Constructor" }});
        const resolved = getTask("constructor");
        const claim = applyClaimIntent({{ taskId: "constructor", participant: "w", spawnId: "s", timestamp: 1 }});
        // A JSON-parsed tasks (Object.prototype intact) must not leak either.
        resetState();
        loadTasks(JSON.parse(JSON.stringify({{ t_1: {{ id: "t_1", subject: "legacy", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }})));
        const afterLegacyDep = createTask({{ subject: "next step", dependsOn: ["hasOwnProperty"] }});
        console.log(JSON.stringify({{
          depBlockedBeforeCreation: depBefore.ok === false,
          madeId: made.task?.id ?? null,
          resolvedIsOwnEntry: resolved?.id === "constructor",
          resolvedNotAFunction: typeof resolved !== "function",
          claimApplied: claim.applied === true,
          legacyProtoDepBlocked: afterLegacyDep.ok === false,
        }}));
        '''
    )
    assert payload["depBlockedBeforeCreation"] is True
    assert payload["madeId"] == "constructor"
    assert payload["resolvedIsOwnEntry"] is True
    assert payload["resolvedNotAFunction"] is True
    assert payload["claimApplied"] is True
    assert payload["legacyProtoDepBlocked"] is True


def test_slug_ids_with_duplicate_suffixes_stay_within_length_cap() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const long = "Audit every single surface of the whole application very thoroughly".toLowerCase();
        const first = createTask({{ subject: long }});
        const second = createTask({{ subject: long + "!" }});
        console.log(JSON.stringify({{
          a: first.task.id,
          b: second.task.id,
          bothWithinCap: first.task.id.length <= 48 && second.task.id.length <= 48,
          distinct: first.task.id !== second.task.id,
        }}));
        '''
    )
    assert payload["bothWithinCap"] is True
    assert payload["distinct"] is True
    assert payload["b"].endswith("-1")


def test_retain_live_noticed_ids_prunes_stale_first() -> None:
    payload = run_node(
        f'''\
        import {{ retainLiveNoticedIds }} from "{(SRC / "team-machine.ts").as_uri()}";
        const noticed = ["old-done", "live-1", "live-2", "other-done"];
        const retained = retainLiveNoticedIds(noticed, new Set(["live-1", "live-2", "brand-new"]));
        console.log(JSON.stringify({{ retained }}));
        '''
    )
    assert payload["retained"] == ["live-1", "live-2"]


def test_unknown_agent_error_names_configured_user_dir_and_lists_agents() -> None:
    payload = run_node(
        f'''\
        import {{ unknownAgentError }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ message: unknownAgentError("ghost-role", "/tmp/proj") }}));
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": "/tmp/custom-agent-dir"},
    )
    message = payload["message"]
    assert "ghost-role" in message
    assert "/tmp/proj/.pi/agents" in message
    assert "/tmp/custom-agent-dir/agents" in message
    assert "~/.pi/agent/agents" not in message
    assert "stale" in message
    assert "definition" in message
    assert "references/agent-roles.md" in message
    assert "Available now:" in message


def test_stale_verify_result_cannot_complete_a_new_holding(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerAgent, createTask, applyClaimIntent, getTask, bindTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        const tick = () => new Promise((resolve) => setTimeout(resolve, 10));
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const made = createTask({{ subject: "gated work", verify: "Does the delivered gallery satisfy every acceptance criterion?" }});
        const id = made.task.id;
        applyClaimIntent({{ taskId: id, participant: "w", spawnId: "s1", timestamp: 1 }});
        let releaseStaleGate;
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseStaleGate = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", id, "completed");
        processTaskIntents();
        await tick();
        attemptSubmission("w", "s1", id, "failed");
        processTaskIntents();
        const releasedWhileVerifying = getTask(id).status === "blocked";
        // The second holding is a deliberate leader assignment. An autonomous
        // claim cannot clear a recovery hold, so that is the only path that can
        // reach the stale gate release this test is about.
        const rebound = bindTask(id, "w", {{ id: "attempt-2", kind: "direct", resources: [] }}, {{ from: ["blocked"] }});
        const reboundHeld = rebound.ok === true && getTask(id).status === "in_progress";
        releaseStaleGate();
        await tick();
        const staleCompleted = getTask(id).status === "completed";
        let releaseFreshGate;
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseFreshGate = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", id, "completed");
        processTaskIntents();
        await tick();
        releaseFreshGate();
        await tick();
        console.log(JSON.stringify({{
          releasedWhileVerifying,
          reboundHeld,
          staleCompleted,
          finalStatus: getTask(id).status,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["releasedWhileVerifying"] is True
    assert payload["reboundHeld"] is True, "A deliberate assignment must open a new holding"
    # The pre-release gate result must not complete the post-release holding.
    assert payload["staleCompleted"] is False
    assert payload["finalStatus"] == "completed"


def test_verify_reviewer_runs_as_a_bare_pi_child() -> None:
    payload = run_node(
        f'''\
        import {{ buildVerifyReviewWorkerOptions }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ minimalPiWorkerArgs }} from "@fradser/pi-kit";
        const options = buildVerifyReviewWorkerOptions({{
          verify: "Every scenario holds.", taskSubject: "Gallery refactor", workerResult: "Done.", cwd: "/repo",
        }});
        const args = minimalPiWorkerArgs(options.tools ?? []);
        console.log(JSON.stringify({{
          minimal: options.minimal,
          tools: options.tools,
          cwd: options.cwd,
          promptHasGate: options.prompt.includes("Every scenario holds."),
          noExtensions: args.includes("-ne"),
          noSession: args.includes("--no-session"),
        }}));
        '''
    )
    assert payload["minimal"] is True
    assert payload["tools"] == ["read", "bash", "grep", "find", "ls"]
    assert payload["cwd"] == "/repo"
    assert payload["promptHasGate"] is True
    assert payload["noExtensions"] is True
    assert payload["noSession"] is True
    assert "runPiWorker(buildVerifyReviewWorkerOptions(input))" in source("team-machine.ts")


def test_verify_review_verdict_protocol() -> None:
    payload = run_node(
        f'''\
        import {{ buildVerifyReviewPrompt, parseVerifyVerdict }} from "{(SRC / "team-machine.ts").as_uri()}";
        const NL = String.fromCharCode(10);
        const reply = (...lines) => lines.join(NL);
        console.log(JSON.stringify({{
          promptHasGate: buildVerifyReviewPrompt({{ verify: "Every scenario holds.", taskSubject: "Gallery refactor", workerResult: "Done.", cwd: "/repo" }}).includes("Every scenario holds."),
          pass: parseVerifyVerdict(reply("Evidence...", "VERDICT: PASS")),
          passLowerCase: parseVerifyVerdict("verdict: pass"),
          passTrailingProse: parseVerifyVerdict(reply("VERDICT: PASS", "(closing note)")),
          passWithJunkRejected: parseVerifyVerdict(reply("A", "VERDICT: PASS - also broken", "B")),
          failWithReason: parseVerifyVerdict(reply("Evidence...", "VERDICT: FAIL - overflow at 400px")),
          failExtraSpaces: parseVerifyVerdict("VERDICT:   FAIL   spaced reasons"),
          missing: parseVerifyVerdict("Looks good to me"),
          missingDetailTruncated: parseVerifyVerdict("x".repeat(5000)).detail.includes("[truncated]"),
        }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    assert payload["promptHasGate"] is True
    assert payload["pass"] == {"kind": "pass"}
    assert payload["passLowerCase"] == {"kind": "pass"}
    assert payload["passTrailingProse"] == {"kind": "pass"}
    assert payload["passWithJunkRejected"]["kind"] == "inconclusive"
    assert payload["failWithReason"]["kind"] == "fail"
    assert "overflow at 400px" in payload["failWithReason"]["detail"]
    assert payload["failExtraSpaces"]["kind"] == "fail"
    assert "spaced reasons" in payload["failExtraSpaces"]["detail"]
    assert payload["missing"]["kind"] == "inconclusive"
    assert payload["missingDetailTruncated"] is True


def test_agent_definitions_are_declarative_files_with_verify() -> None:
    ext = subagents_source("agents.ts") + source("tools.ts")
    assert "discoverAgents" in ext and "resolveAgent" in ext
    agents_ts = subagents_source("agents.ts")
    assert 'LOCAL_DEFINITION_SUFFIX = ".local"' in agents_ts
    assert 'gitManaged: scope === "project"' in agents_ts or 'return scope === "project";' in agents_ts
    assert "fields.verify" in agents_ts
    assert "PI_CODING_AGENT_DIR" in agents_ts or "getAgentDir" in agents_ts
    assert 'export type AgentScope = "user" | "project" | "project-local" | "session";' in agents_ts
    assert "registerSessionAgent" in agents_ts
    assert "clearSessionAgents" in agents_ts
    # Session-only role source is absent, not a persistent declaration.
    assert 'scope: "session"' in agents_ts


def test_generated_agent_roles_can_be_persisted_only_explicitly(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, persistAgentDefinition, clearSessionAgents }} from "@fradser/pi-subagents";
        import fs from "node:fs";
        clearSessionAgents();
        const persisted = persistAgentDefinition({{
          name: "saved-reviewer",
          description: "Review a requested scope",
          tools: ["read"],
          prompt: "Review only the assigned scope.",
        }}, "project-local", {json.dumps(str(tmp_path))});
        const found = discoverAgents({json.dumps(str(tmp_path))}).get("saved-reviewer");
        console.log(JSON.stringify({{
          scope: persisted.scope,
          sourceExists: typeof persisted.source === "string" && fs.existsSync(persisted.source),
          discoveredScope: found?.scope ?? null,
          gitManaged: found?.gitManaged ?? null,
        }}));
        ''',
    )
    assert payload == {
        "scope": "project-local",
        "sourceExists": True,
        "discoveredScope": "project-local",
        "gitManaged": False,
    }


def test_generated_agent_roles_are_session_scoped_and_not_persisted(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, registerSessionAgent, clearSessionAgents }} from "@fradser/pi-subagents";
        import fs from "node:fs";
        clearSessionAgents();
        const registered = registerSessionAgent({{
          name: "human-philosopher",
          description: "Analyze human nature",
          tools: ["read"],
          prompt: "Answer from philosophical traditions.",
        }});
        const current = discoverAgents({json.dumps(str(tmp_path))}).get("human-philosopher");
        const agentsDir = {json.dumps(str(tmp_path / ".pi" / "agents"))};
        const filesBefore = fs.existsSync(agentsDir) ? fs.readdirSync(agentsDir) : [];
        clearSessionAgents();
        const afterReset = discoverAgents({json.dumps(str(tmp_path))}).get("human-philosopher");
        console.log(JSON.stringify({{
          registered: registered.scope,
          sourceIsMemory: current?.source === undefined,
          gitManaged: current?.gitManaged ?? null,
          filesBefore,
          absentAfterReset: afterReset === undefined,
        }}));
        ''',
    )
    assert payload == {
        "registered": "session",
        "sourceIsMemory": True,
        "gitManaged": False,
        "filesBefore": [],
        "absentAfterReset": True,
    }


def test_persistent_definitions_outrank_generated_session_roles(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, registerSessionAgent, clearSessionAgents }} from "@fradser/pi-subagents";
        import fs from "node:fs";
        clearSessionAgents();
        const agentsDir = {json.dumps(str(tmp_path / ".pi" / "agents"))};
        fs.mkdirSync(`${{agentsDir}}/scout`, {{ recursive: true }});
        fs.writeFileSync(`${{agentsDir}}/scout/agent.md`, [
          "---",
          "name: scout",
          "description: File-based scout",
          "tools: read",
          "---",
          "File role.",
          "",
        ].join("\\n"));
        registerSessionAgent({{
          name: "scout",
          description: "Session scout",
          tools: ["bash"],
          prompt: "Session prompt.",
        }});
        registerSessionAgent({{
          name: "ghost",
          description: "Only in memory",
          tools: ["bash"],
          prompt: "Ghost prompt.",
        }});
        const scout = discoverAgents({json.dumps(str(tmp_path))}).get("scout");
        const ghost = discoverAgents({json.dumps(str(tmp_path))}).get("ghost");
        console.log(JSON.stringify({{
          scoutScope: scout?.scope ?? null,
          scoutTools: scout?.tools ?? null,
          ghostScope: ghost?.scope ?? null,
        }}));
        ''',
    )
    assert payload == {
        "scoutScope": "project",
        "scoutTools": ["read"],
        "ghostScope": "session",
    }


def test_inline_definitions_replace_stale_session_roles_but_not_files(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ inlineDefinitionApplies }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resolveAgent, registerSessionAgent, clearSessionAgents }} from "@fradser/pi-subagents";
        import fs from "node:fs";
        const cwd = {json.dumps(str(tmp_path))};
        clearSessionAgents();
        const noResolution = inlineDefinitionApplies(undefined);
        const beforeFile = (() => {{
          registerSessionAgent({{ name: "scout", description: "Stale role", tools: ["bash"], prompt: "Old." }});
          return inlineDefinitionApplies(resolveAgent("scout", cwd));
        }})();
        const agentsDir = `${{cwd}}/.pi/agents`;
        fs.mkdirSync(`${{agentsDir}}/scout`, {{ recursive: true }});
        fs.writeFileSync(`${{agentsDir}}/scout/agent.md`, [
          "---",
          "name: scout",
          "description: File-based scout",
          "tools: read",
          "---",
          "File role.",
          "",
        ].join("\\n"));
        const afterFile = inlineDefinitionApplies(resolveAgent("scout", cwd));
        console.log(JSON.stringify({{ noResolution, sessionRoleCase: beforeFile, fileCase: afterFile }}));
        ''',
    )
    assert payload == {"noResolution": True, "sessionRoleCase": True, "fileCase": False}
    machine = source("team-machine.ts")
    # The spawn path must gate generation on the helper so a corrected inline
    # definition replaces a stale session role instead of being ignored.
    assert "input.definition && inlineDefinitionApplies(resolved)" in machine


def test_spawn_model_resolution_precedence() -> None:
    payload = run_node(
        f'''\
        import {{ resolveSpawnModel }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{
          pin: resolveSpawnModel("anthropic/claude-opus-4-6", "openai/gpt-5.2", "google/gemini-3-pro"),
          inherit: resolveSpawnModel("inherit", "openai/gpt-5.2", "openai/gpt-5.2-leader"),
          inheritCaseInsensitive: resolveSpawnModel("Inherit", undefined, "google/gemini-3-pro"),
          teamDefault: resolveSpawnModel(undefined, "openai/gpt-5.2", "google/gemini-3-pro"),
          none: resolveSpawnModel(undefined, undefined, undefined),
          fallbackSession: resolveSpawnModel(undefined, undefined, "google/gemini-3-pro"),
          inheritWithoutLeaderModel: resolveSpawnModel("inherit", undefined, undefined),
          blankPinIsUnset: resolveSpawnModel("  ", "openai/gpt-5.2", undefined),
        }}));
        '''
    )
    assert payload["pin"] == {"model": "anthropic/claude-opus-4-6", "source": "pin"}
    assert payload["inherit"] == {"model": "openai/gpt-5.2-leader", "source": "inherit"}
    assert payload["inheritCaseInsensitive"] == {"model": "google/gemini-3-pro", "source": "inherit"}
    assert payload["teamDefault"] == {"model": "openai/gpt-5.2", "source": "team-default"}
    assert payload["none"] == {"source": "none"}
    assert payload["fallbackSession"] == {"model": "google/gemini-3-pro", "source": "leader-session"}
    assert payload["inheritWithoutLeaderModel"] == {"source": "none"}
    assert payload["blankPinIsUnset"] == {"model": "openai/gpt-5.2", "source": "team-default"}


def test_leader_model_and_thinking_switch_apply_to_later_spawns() -> None:
    payload = run_node(
        f'''\
        import {{ currentLeaderModelRef, currentLeaderThinkingLevel, initTeamMachine, shutdownTeamMachine, syncLeaderContext }} from "{(SRC / "team-machine.ts").as_uri()}";
        initTeamMachine(
          {{ cwd: "/tmp", model: {{ provider: "cli-proxy", id: "gpt-6-astra" }}, thinkingLevel: "low" }},
          {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }},
        );
        const beforeModel = currentLeaderModelRef();
        const beforeThinking = currentLeaderThinkingLevel();
        syncLeaderContext({{ model: {{ provider: "cli-proxy", id: "omen-alpha" }}, thinkingLevel: "high" }});
        const afterModel = currentLeaderModelRef();
        const afterThinking = currentLeaderThinkingLevel();
        const restore = process.env.PI_REASONING_LEVEL;
        process.env.PI_REASONING_LEVEL = "medium";
        process.env.PI_PROVIDER = "test-provider";
        process.env.PI_MODEL = "test-model";
        syncLeaderContext({{}});
        const envFallbackThinking = currentLeaderThinkingLevel();
        const envFallbackModel = currentLeaderModelRef();
        process.env.PI_REASONING_LEVEL = restore;
        shutdownTeamMachine();
        console.log(JSON.stringify({{ beforeModel, beforeThinking, afterModel, afterThinking, envFallbackThinking, envFallbackModel }}));
        '''
    )
    assert payload["beforeModel"] == "cli-proxy/gpt-6-astra"
    assert payload["beforeThinking"] == "low"
    assert payload["afterModel"] == "cli-proxy/omen-alpha"
    assert payload["afterThinking"] == "high"
    assert payload["envFallbackThinking"] == "medium"
    assert payload["envFallbackModel"] == "test-provider/test-model"


def test_spawner_forwards_thinking_flag() -> None:
    spawner = subagents_source("spawner.ts")
    assert '"--thinking", options.thinking' in spawner
    assert 'thinking?: string;' in spawner


def test_team_default_model_persists_in_state_snapshot() -> None:
    payload = run_node(
        f'''\
        import {{ getTeamDefaultModel, setTeamDefaultModel, getState }} from "{(SRC / "state.ts").as_uri()}";
        setTeamDefaultModel("openai/gpt-5.2");
        const stored = getTeamDefaultModel();
        const snapshotted = JSON.stringify(getState()).includes("openai/gpt-5.2");
        setTeamDefaultModel("  ");
        const cleared = getTeamDefaultModel();
        console.log(JSON.stringify({{ stored, snapshotted, cleared }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    assert payload["stored"] == "openai/gpt-5.2"
    assert payload["snapshotted"] is True
    assert payload["cleared"] is None


def test_picker_key_routes_printables_to_typing_and_keys_to_actions() -> None:
    payload = run_node(
        f'''\
        import {{ mapPickerKey }} from "{(SRC / "picker-keys.ts").as_uri()}";
        console.log(JSON.stringify({{
          letterC: mapPickerKey("c"),
          capitalC: mapPickerKey("C"),
          digit: mapPickerKey("3"),
          space: mapPickerKey(" "),
          escape: mapPickerKey("\\x1b"),
          enter: mapPickerKey("\\r"),
          up: mapPickerKey("\\x1b[A"),
          down: mapPickerKey("\\x1b[B"),
          backspace: mapPickerKey("\\x7f"),
          tabIgnored: mapPickerKey("\\t"),
          multiCharPasteIgnored: mapPickerKey("abc"),
        }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    # The regression core: letters route to typing, never to shortcuts.
    for key in ("letterC", "capitalC", "digit", "space"):
        assert payload[key] == {"kind": "type", "text": {"letterC": "c", "capitalC": "C", "digit": "3", "space": " "}[key]}, key
    assert payload["escape"] == {"kind": "cancel"}
    assert payload["enter"] == {"kind": "confirm"}
    assert payload["up"] == {"kind": "up"}
    assert payload["down"] == {"kind": "down"}
    assert payload["backspace"] == {"kind": "backspace"}
    assert payload["tabIgnored"] is None
    assert payload["multiCharPasteIgnored"] is None


def test_agent_frontmatter_parses_tools_model_verify(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".pi" / "agents" / "auditor"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent.md").write_text(
        "---\n"
        "name: auditor\n"
        "description: Reviews code for exploitable problems\n"
        "tools: read,grep # execution allowlist\n"
        "model: anthropic/claude-sonnet-4\n"
        'verify: "Every declared acceptance scenario holds in the built gallery"\n'
        "---\n"
        "Review the assigned scope.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "@fradser/pi-subagents";
        const agent = resolveAgent("auditor", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          found: Boolean(agent),
          tools: agent?.tools ?? [],
          model: agent?.model ?? null,
          verify: agent?.verify ?? null,
          hasRemovedFields: ["worktree", "memory", "isolation"].some(key => key in agent),
          scope: agent?.scope ?? null,
          promptIsBody: (agent?.prompt ?? "").includes("Review the assigned scope."),
        }}));
        ''',
    )
    assert payload["found"] is True
    assert payload["tools"] == ["read", "grep"]
    assert payload["model"] == "anthropic/claude-sonnet-4"
    assert payload["verify"] == "Every declared acceptance scenario holds in the built gallery"
    assert payload["hasRemovedFields"] is False
    assert payload["scope"] == "project"
    assert payload["promptIsBody"] is True


def test_agent_frontmatter_parses_multiline_dash_list_tools(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".pi" / "agents" / "scribe"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent.md").write_text(
        "---\n"
        "name: scribe\n"
        "description: Scoped writer\n"
        "tools:\n"
        "  - read\n"
        "  - bash\n"
        "  - edit # allow file edits\n"
        "  - write\n"
        "---\n"
        "Write only assigned project files.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "@fradser/pi-subagents";
        const agent = resolveAgent("scribe", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          found: Boolean(agent),
          tools: agent?.tools ?? [],
          hasRemovedFields: ["worktree", "memory", "isolation"].some(key => key in agent),
          promptIsBody: (agent?.prompt ?? "").includes("Write only assigned project files."),
        }}));
        ''',
    )
    assert payload["found"] is True
    assert payload["tools"] == ["read", "bash", "edit", "write"]
    assert payload["hasRemovedFields"] is False
    assert payload["promptIsBody"] is True


def test_agent_frontmatter_dash_list_edge_cases(tmp_path: Path) -> None:
    """Flush-left dashes, interleaved comments, no-space dashes, and
    comment-only entries must parse like a standard YAML block sequence."""
    agents_dir = tmp_path / ".pi" / "agents" / "edge"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent.md").write_text(
        "---\n"
        "name: edge\n"
        "description: Dash-list edge cases\n"
        "tools:\n"
        "# allowlist comment\n"
        "- read\n"
        "  - bash\n"
        "-edit\n"
        "  - # not a tool\n"
        "- write # trailing comment\n"
        "model: m\n"
        "---\n"
        "Edge body.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "@fradser/pi-subagents";
        const agent = resolveAgent("edge", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{ tools: agent?.tools ?? [], model: agent?.model ?? null }}));
        ''',
    )
    assert payload["tools"] == ["read", "bash", "edit", "write"]
    assert payload["model"] == "m"


def test_project_agent_overrides_user_scope(tmp_path: Path) -> None:
    user_dir = tmp_path / "user-config"
    project_dir = tmp_path / ".pi" / "agents"
    # VISION.md: only canonical per-name agent.md declares identity. The local
    # suffix belongs to the directory; all disk scopes get durable data.
    for directory, name, body in (
        (user_dir / "agents" / "dup", "dup", "user body"),
        (project_dir / "dup", "dup", "project body"),
        (project_dir / "dup.local", "dup", "project-local body"),
        (project_dir / "shared", "shared", "shared role"),
        (project_dir / "personal.local", "personal", "personal role"),
    ):
        directory.mkdir(parents=True)
        (directory / "agent.md").write_text(
            f"---\nname: {name}\ndescription: {name} role\ntools: read\n---\n{body}\n",
            encoding="utf-8",
        )
    payload = run_node(
        f'''\
        import {{ discoverAgents, resolveAgent }} from "@fradser/pi-subagents";
        const all = discoverAgents({json.dumps(str(tmp_path))});
        const dup = resolveAgent("dup", {json.dumps(str(tmp_path))});
        const shared = resolveAgent("shared", {json.dumps(str(tmp_path))});
        const personal = resolveAgent("personal", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          keys: [...all.keys()].sort(),
          dupScope: dup?.scope,
          dupBody: dup?.prompt,
          dupGitManaged: dup?.gitManaged,
          sharedScope: shared?.scope,
          sharedGitManaged: shared?.gitManaged,
          personalScope: personal?.scope,
          personalGitManaged: personal?.gitManaged,
        }}));
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(user_dir)},
    )
    # dedup: dup/ and dup.local/ collapse into one identity.
    # There are no built-in roles, so only the fixture definitions exist.
    assert sorted(payload["keys"]) == ["dup", "personal", "shared"]
    assert payload["dupScope"] == "project-local"
    assert payload["dupBody"] == "project-local body"
    assert payload["dupGitManaged"] is False
    assert payload["sharedScope"] == "project"
    assert payload["sharedGitManaged"] is True
    assert payload["personalScope"] == "project-local"
    assert payload["personalGitManaged"] is False


def test_leader_guidance_is_disclosed_only_for_active_team_state() -> None:
    payload = run_node(
        f'''\
        import {{ hasActiveTeamState }} from "{(SRC / "index.ts").as_uri()}";
        import {{ resetState, registerAgent, createTask, updateAgent }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const inactive = hasActiveTeamState();
        registerAgent({{ name: "worker", role: "worker", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const rosterActive = hasActiveTeamState();
        updateAgent("worker", {{ status: "stopped" }});
        createTask({{ subject: "task work" }});
        const tasksActive = hasActiveTeamState();
        console.log(JSON.stringify({{ inactive, rosterActive, tasksActive }}));
        '''
    )
    assert payload == {"inactive": False, "rosterActive": True, "tasksActive": True}
    index_ts = source("index.ts")
    assert "teamIsActive" in index_ts
    assert "buildIdleLeaderGuidance" in index_ts
    assert "? buildTeamLeaderGuidance" in index_ts


def test_team_status_clear_uses_pi_kit_transient_status_adapter() -> None:
    index = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'clearPiStatus(ctx.ui, "agent")' in index
    assert 'ctx.ui.setStatus("agent", undefined)' not in index


def test_unknown_agent_error_gives_the_complete_inline_spawn_recovery() -> None:
    team_machine = source("team-machine.ts")
    # Adopted flat six-verb surface: recovery cannot teach delegate/role-id or
    # nested definitions that the public agent tool refuses.
    assert "agent action=start using an existing name" in team_machine
    assert "supply description and role_prompt" in team_machine
    assert "for a temporary role" in team_machine


def test_follow_up_reports_use_wrapped_marker_format() -> None:
    payload = run_node(
        f'''\
        import {{ formatReports }} from "@fradser/pi-subagents";
        const content = formatReports([
          {{ agent: "security", body: "<b>bold finding</b>" }},
        ]);
        console.log(JSON.stringify({{
          wrapped: content.includes('<agent-message from="security">'),
          escaped: formatReports([{{ agent: 'a"b', body: "x" }}]).includes('from="a&quot;b"'),
          stamped: formatReports([{{ agent: "x", body: "y", timestamp: 0 }}]).includes('<agent-message from="x" at="1970-01-01T00:00:00.000Z">'),
          unstampedOmitsAt: !formatReports([{{ agent: "x", body: "y" }}]).includes(" at="),
          fullBodyKept: content.includes("<b>bold finding</b>"),
          noRunIds: !content.includes("run_"),
          noFinishedNotice: !content.includes("finished."),
          harnessEvent: formatReports([{{ origin: "harness", harnessEvent: {{ type: "unexpected-stop", subject: "@audit stopped unexpectedly" }}, body: "diagnostic" }}]).includes('<harness-event type="unexpected-stop" subject="@audit stopped unexpectedly">'),
          harnessIsNotAgentMessage: !formatReports([{{ origin: "harness", harnessEvent: {{ type: "unexpected-stop", subject: "@audit stopped unexpectedly" }}, body: "diagnostic" }}]).includes("<agent-message"),
          // A report carrying only the older `agent` field already groups under
          // that name; the envelope has to agree, or a delivered message is
          // attributed to nobody while its group is labelled with the Agent.
          agentProvenance: formatReports([{{ agent: "scout", body: "found" }}]).includes('<agent-message from="scout">'),
        }}));
        '''
    )
    assert payload["wrapped"] is True
    assert payload["escaped"] is True
    assert payload["stamped"] is True
    assert payload["unstampedOmitsAt"] is True
    assert payload["fullBodyKept"] is True
    assert payload["noRunIds"] is True
    assert payload["noFinishedNotice"] is True
    assert payload["harnessEvent"] is True
    assert payload["harnessIsNotAgentMessage"] is True
    assert payload["agentProvenance"] is True


def test_invalid_report_timestamp_is_omitted_without_losing_body() -> None:
    payload = run_node(
        f'''\
        import {{ formatReports }} from "@fradser/pi-subagents";
        const content = formatReports([{{ agent: "audit", body: "preserve this body", timestamp: 1e20 }}]);
        console.log(JSON.stringify({{ body: content.includes("preserve this body"), omitted: !content.includes(" at=") }}));
        '''
    )
    assert payload == {"body": True, "omitted": True}


def test_console_supports_mouse_wheel_scrolling() -> None:
    ext = source("ui.ts")
    # One SGR wheel parser shared by the list page and detail views.
    assert "function wheelDelta(data: string): number | undefined" in ext
    assert "/^\\x1b\\[<(\\d+);\\d+;\\d+[Mm]$/" in ext
    assert "(button & 64) === 0" in ext
    assert ext.count("const wheel = wheelDelta(data);") == 2


def test_console_has_roster_and_tasks_pages() -> None:
    ext = source("ui.ts")
    assert '"roster"' in ext and '"task"' in ext
    assert 'Key.tab' in ext
    assert "shutdownFromConsole" in ext
    assert "buildTaskDetail" in ext and "buildTeammateDetail" in ext
    assert "peer mail" in ext
    # Console names and ids use pi-kit's per-agent accent, so a name can never
    # read as a status color and every surface shows the same name color.
    assert "agentColor(" in ext
    assert "TEAM_COLORS" not in ext
    assert "colorFor" not in ext


def test_widget_shows_only_working_teammates() -> None:
    ext = source("ui.ts")
    widget = ext[ext.index("export function ensureTeamWidget"):ext.index("export function refreshTeamUI")]
    assert "createLiveActivityWidget" in ext
    assert 'key: "agent"' in ext
    assert 'placement: "aboveEditor"' in ext
    assert 'activityFormat: "markdown"' in ext
    assert "formatIdentity" not in ext
    assert "formatActivity" not in ext
    assert "teamActivityWidget.update(ctx, working.map" in widget
    assert "id: agent.name" in widget
    assert "identity: agent.name" in widget
    assert "activity: runningTeammateActivity(agent) + stallSuffix(agent)" in widget
    assert 'agent.status === "working" || agent.status === "starting"' in ext
    assert "listAgents()" not in widget


def test_activity_rows_use_the_shared_pi_kit_markdown_renderer() -> None:
    activity = source("activity.ts")
    assert "renderLiveActivityMarkdown" in activity
    assert "COLORLESS_ACTIVITY_THEME" in activity
    # The shared settings reader and policy keep every teammate row consistent.
    assert "configureTeamActivity" in activity
    assert "resolveLiveActivity" in activity
    assert "configureTeamActivity(() => hiddenThinkingEnabled(pi))" in (SRC / "index.ts").read_text()
    # The console nests activity inside its own status color, so no local
    # markdown parse or theme may survive here.
    assert "new Markdown(" not in activity
    assert "type { MarkdownTheme }" not in activity
    assert "buildMarkdownThemeCallbacks" not in activity


def test_render_lifecycle_result_survives_class_based_theme() -> None:
    script = f"""
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import {{ renderLifecycleResult }} from "{(SRC / "tool-render.ts").as_uri()}";

initTheme("dark");
class ClassTheme {{
  constructor() {{ this.bgColors = new Map([["toolSuccessBg", "\\u001B[44m"]]); }}
  fg(_color, text) {{ return text; }}
  bold(text) {{ return text; }}
  bg(color, text) {{ return this.bgColors.get(color) + text + "\\u001B[49m"; }}
}}
const view = renderLifecycleResult(
  {{ content: [{{ type: "text", text: "ok" }}] }},
  {{ expanded: true }},
  new ClassTheme(),
  {{ isError: false }},
  {{ kind: "started", tool: "teammate_spawn", subject: "reviewer", label: "spawn" }},
  ["detail line"],
);
const rendered = view.render(100).join("\\n");
console.log(JSON.stringify({{ painted: rendered.includes("\\u001B[44m"), rendered }}));
"""
    result = run_node(script)
    assert result["painted"], result["rendered"]


def test_activity_priority_tool_then_thinking_then_text(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ runningTeammateActivity }} from "{(SRC / "activity.ts").as_uri()}";
        const base = {{ name: "security", agent: "reviewer", spawnId: "s", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }};
        const withTool = runningTeammateActivity({{ ...base, activeTool: "bash: npm test", liveThinking: "**thinking**", liveText: "text" }});
        const withThinking = runningTeammateActivity({{ ...base, liveThinking: "reasoning about auth", liveText: "older text" }});
        const withText = runningTeammateActivity({{ ...base, liveText: "older\\nlatest" }});
        const fallback = runningTeammateActivity(base);
        const hiddenThinking = runningTeammateActivity({{ ...base, liveThinking: "reasoning about auth" }}, true);
        const hiddenWithAnswer = runningTeammateActivity({{ ...base, liveThinking: "reasoning about auth", liveText: "the answer" }}, true);
        const hiddenWithTool = runningTeammateActivity({{ ...base, activeTool: "bash: npm test", liveThinking: "reasoning about auth" }}, true);
        console.log(JSON.stringify({{
          withTool, withThinking,
          latestLineWins: withText === "latest",
          fallback, fallbackIsWorking: fallback === "Working...",
          hiddenThinking, hiddenWithAnswer, hiddenWithTool,
        }}));
        '''
    )
    assert payload["withTool"] == "bash: npm test"
    assert payload["withThinking"] == "reasoning about auth"
    # The widget shows the LATEST non-empty line of streamed text.
    assert payload["latestLineWins"] is True
    assert payload["fallbackIsWorking"] is True
    # A reader who hid thinking blocks sees Pi's label, never the reasoning.
    assert payload["hiddenThinking"] == "Thinking..."
    assert payload["hiddenWithAnswer"] == "the answer"
    assert payload["hiddenWithTool"] == "bash: npm test"
    assert payload["fallbackIsWorking"] is True


def test_rpc_control_stream_protocol_lines() -> None:
    spawner = subagents_source("spawner.ts")
    assert 'streamingBehavior: "followUp"' in spawner
    assert 'streamingBehavior: "steer"' in spawner
    assert '{ type: "steer", message }' not in spawner
    assert '"--mode", "rpc"' in spawner
    assert '"--no-session"' in spawner
    # The constitution: sequences are uncapped; the harness never terminates a
    # working child on its own — no budget counters, no auto-reclaim.
    assert "DEFAULT_TURN_BUDGET" not in spawner
    assert "turnBudgetExceeded" not in spawner
    assert "budgetExceeded" not in spawner
    # Residents never auto-exit after a report: no post-report grace shutdown.
    assert "finishReportedWorker" not in spawner
    assert "POST_REPORT_GRACE_MS" not in spawner


def test_resident_stream_limits_are_per_turn_and_fail_closed() -> None:
    spawner = subagents_source("spawner.ts")
    assert "MAX_JSONL_LINE_BYTES" in spawner
    assert "MAX_TURN_OUTPUT_BYTES" in spawner
    assert "outputLimitError" in spawner
    assert "terminateChildProcess" in spawner
    assert "failureReason" in spawner


def test_resident_unterminated_output_is_terminated_without_partial_success() -> None:
    payload = run_node(
        f'''\
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-stream-limit-"));
        const pkg = path.join(root, "fake-package");
        fs.mkdirSync(pkg);
        fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const child = path.join(pkg, "cli.mjs");
        fs.writeFileSync(child, `
          process.stderr.write("child-diagnostic-noise".repeat(1000));
          setTimeout(() => process.stdout.write("x".repeat(Number(process.env.PI_LINE_LIMIT) + 1)), 50);
          process.on("SIGTERM", () => {{}});
          const stream = setInterval(() => process.stdout.write("x".repeat(4096)), 1);
          setTimeout(() => {{ clearInterval(stream); process.exit(0); }}, 1000);
        `, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = child;
        const {{ spawnResident, MAX_JSONL_LINE_BYTES }} = await import("@fradser/pi-subagents");
        // The limit knob travels through this spawn's own overrides, which the
        // environment policy always honors. It must not rely on the leader's
        // ambient environment leaking into the child: that leak is exactly what
        // the policy closes, so an ambient knob would now silently vanish.
        const outcome = await new Promise((resolve) => spawnResident({{
          agentName: "limit-test",
          cwd: root,
          env: {{ PI_LINE_LIMIT: String(MAX_JSONL_LINE_BYTES) }},
          onUpdate: () => {{}},
          onExit: (result) => resolve({{ exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr }}),
          onError: (error) => resolve({{ error: error.message }}),
        }}));
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify(outcome));
        '''
    )
    assert payload["exitCode"] != 0
    assert payload["stdout"] == ""
    assert payload["stderr"].startswith("Resident Agent JSONL line exceeded")
    assert "child-diagnostic-noise" in payload["stderr"]


def test_finish_entry_announces_assignment_finished() -> None:
    payload = run_node(
        f'''\
        import extension from "{(PACKAGE / "index.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const renderers = new Map();
        extension({{
          on() {{}},
          registerCommand() {{}},
          registerEntryRenderer(type, renderer) {{ renderers.set(type, renderer); }},
          registerMessageRenderer() {{}},
          registerTool() {{}},
        }});
        const renderer = renderers.get("agent-teams-teammate-finished");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const lines = renderer({{ data: {{ agent: "e2e-layout-luna" }} }}, {{}}, theme).render(80);
        console.log(JSON.stringify({{ lines }}));
        '''
    )
    assert any("Assignment for @e2e-layout-luna finished." in line for line in payload["lines"])
    assert not any("Agent @" in line for line in payload["lines"])


def test_peer_traffic_stays_out_of_leader_context() -> None:
    machine = source("team-machine.ts")
    index_ts = source("index.ts")
    # Inbox routing never calls sendUpdate or deliverToLeader for peer messages.
    routing = machine[machine.index("export function routePeerInboxes"):machine.index("// ── Task intents")]
    assert "deliverToLeader" not in routing
    assert "sendUpdate" not in routing
    assert "dispatchInboxMessage" in machine
    # Only reports and harness diagnostics reach the leader mailbox.
    assert "receiveWorkerMessage" in machine
    assert "deliverFeedback" in machine


def test_tasks_path_is_stable_only_for_the_same_session_file(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ tasksFilePath, sessionKey }} from "./src/task-domain/index.ts";
        const cwd = {str(tmp_path)!r};
        const first = "/sessions/first.jsonl";
        const second = "/sessions/second.jsonl";
        console.log(JSON.stringify({{
          sameSession: tasksFilePath(first, cwd) === tasksFilePath(first, cwd),
          differentSessions: tasksFilePath(first, cwd) !== tasksFilePath(second, cwd),
          sameKey: sessionKey(first, cwd) === sessionKey(first, cwd),
          differentKey: sessionKey(first, cwd) !== sessionKey(second, cwd),
        }}));
        '''
    )
    assert payload == {
        "sameSession": True,
        "differentSessions": True,
        "sameKey": True,
        "differentKey": True,
    }


def test_intermediate_worker_reports_reach_the_leader_queue(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerAgent, getState }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange: () => {{}} }});
        resetState();
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, cwd), "w", "s1");
        appendWorkerEvent(outbox, {{ id: "evt1", type: "message", worker: "w", spawnId: "s1", body: "blocker: need model pin decision", status: "in_progress", timestamp: 222 }});
        appendWorkerEvent(outbox, {{ id: "evt2", type: "message", worker: "w", spawnId: "s1", body: "found the root cause" }});
        drainTeammateOutboxes();
        const mailboxEvt1 = getState().leaderMailbox.find((m) => m.id === "evt1");
        console.log(JSON.stringify({{
          bothQueued: sent.length === 2,
          noneTerminal: sent.every((report) => report.finished !== true),
          stampedFromRecord: sent[0].timestamp === 222,
          fallbackStamp: typeof sent[1].timestamp === "number",
          mailboxKeepsAuthoredAt: mailboxEvt1?.timestamp === 222,
          keepsEventEvidence: sent[0].eventId === "evt1" && sent[0].status === "in_progress"
            && sent[1].eventId === "evt2" && sent[1].status === undefined,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "bothQueued": True,
        "noneTerminal": True,
        "stampedFromRecord": True,
        "fallbackStamp": True,
        "mailboxKeepsAuthoredAt": True,
        "keepsEventEvidence": True,
    }


def test_terminal_report_closes_reporting_and_suppresses_following_reports(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import assert from "node:assert/strict";
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes, sendLeaderMessage, applyProgress }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerAgent, createBoundWork, getState }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange() {{}} }});
        resetState();
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, cwd), "w", "s1");
        const start = (id) => {{
          assert.ok(createBoundWork({{ id, subject: "Review", holder: "w", resources: [],
            assignment: {{ id: `attempt:${{id}}`, kind: "direct", resources: [] }} }}).ok);
          applyProgress("w", "s1", {{ text: "", turns: 1, finalResponse: false }});
        }};
        const report = (id, body, status) => appendWorkerEvent(outbox, {{ id, type: "message", worker: "w", spawnId: "s1",
          assignmentId: getState().agents.w.assignment?.id ?? getState().agents.w.lastAssignment?.id, body, status }});
        const settle = () => applyProgress("w", "s1", {{ text: "result", turns: 1, finalResponse: true }});
        start("first");
        report("evt1", "analysis", "in_progress");
        report("evt2", "recommendation", "in_progress");
        report("evt3", "review complete", "completed");
        report("evt4", "assignment complete", "completed");
        drainTeammateOutboxes();
        assert.equal(sent.length, 2, "Completion must wait for execution settlement");
        settle();
        report("evt-late", "duplicate complete", "completed");
        drainTeammateOutboxes();
        assert.equal(sent.length, 3);
        const rejected = sendLeaderMessage("w", "please report again");
        start("second");
        report("evt5", "follow-up complete", "completed");
        drainTeammateOutboxes();
        assert.equal(sent.length, 3);
        settle(); drainTeammateOutboxes();
        console.log(JSON.stringify({{ rejected, bodies: sent.map(r => r.body),
          mailbox: getState().leaderMailbox.map(r => r.body),
          completed: Object.values(getState().tasks).map(t => t.status) }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "rejected": {"ok": True, "outcome": "not-sent", "terminalReport": "review complete"},
        "bodies": ["analysis", "recommendation", "review complete", "follow-up complete"],
        "mailbox": ["analysis", "recommendation", "review complete", "follow-up complete"],
        "completed": ["completed", "completed"],
    }


def test_read_receipts_and_legacy_registry_are_gone() -> None:
    all_sources = "".join(source(name) for name in (
        "types.ts", "state.ts", "statefile.ts", "team-machine.ts", "worker.ts", "tools.ts", "ui.ts",
    ))
    for legacy in ("read receipt", "readReceipt", "markMessageRead", "broadcast"):
        assert legacy.lower() not in all_sources.lower(), legacy
    assert "ephemeral" not in all_sources.lower()

def test_teammate_report_message_renderer_toggles_with_mouse_click() -> None:
    payload = run_node(
        f'''\
        import extension from "{(PACKAGE / "index.ts").as_uri()}";
        import {{ AGENT_REPORT_MESSAGE_TYPE }} from "@fradser/pi-subagents";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";

        initTheme();

        const messageRenderers = new Map();
        const fakePi = {{
          registerEntryRenderer() {{}},
          registerMessageRenderer(type, renderer) {{ messageRenderers.set(type, renderer); }},
          registerTool() {{}},
          registerCommand() {{}},
          on() {{}},
        }};
        extension(fakePi);

        const renderer = messageRenderers.get(AGENT_REPORT_MESSAGE_TYPE);
        const message = {{
          customType: AGENT_REPORT_MESSAGE_TYPE,
          content: "Audit complete",
          details: [
            {{
              agent: "audit",
              agent: "audit",
              body: "PASS with verified evidence.",
            }}
          ],
        }};

        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};

        const comp = renderer(message, {{ expanded: false, outputPad: 1 }}, theme);
        const collapsedLines = comp.render(120);
        // Mouse click on content row (y: 0 in child coordinates)
        const clickRes1 = comp.handleMouse({{ type: "click", button: "left", x: 10, y: 0 }});
        const expandedLines = comp.render(120);
        const clickRes2 = comp.handleMouse({{ type: "click", button: "left", x: 10, y: 0 }});
        const reCollapsedLines = comp.render(120);

        console.log(JSON.stringify({{
          hasHandleMouse: typeof comp.handleMouse === "function",
          click1Handled: clickRes1?.handled,
          collapsed: collapsedLines,
          expanded: expandedLines,
          click2Handled: clickRes2?.handled,
          reCollapsed: reCollapsedLines,
        }}));
        '''
    )
    assert payload["hasHandleMouse"] is True
    assert payload["click1Handled"] is True
    assert "[message] from" in payload["collapsed"][1]
    assert "@audit" in payload["collapsed"][1]
    assert "to expand" in payload["collapsed"][1]
    assert "PASS with verified evidence" not in payload["collapsed"][1]
    assert "PASS with verified evidence" in " ".join(payload["expanded"])
    assert payload["click2Handled"] is True
    assert "[message] from" in payload["reCollapsed"][1]
    assert "to expand" in payload["reCollapsed"][1]

def test_peer_mail_addressed_to_a_retired_incarnation_is_not_delivered(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, routePeerInboxes }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ appendInboxMessage, inboxPath, stateFilePath, readJsonlBatch }} from "{(SRC / "statefile.ts").as_uri()}";
        import {{ getPeerDeliveryState, registerAgent, resetState }} from "{(SRC / "state.ts").as_uri()}";
        const root = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        // The inbox file belongs to the name; the message belongs to an incarnation.
        registerAgent({{ name: "sender", role: "reviewer", spawnId: "s-sender", pid: 2, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        registerAgent({{ name: "reader", role: "reviewer", spawnId: "s-replacement", pid: 3, status: "idle", isolation: "none", createdAt: 2, updatedAt: 2 }});
        const readerInbox = inboxPath(stateFilePath(undefined, root), "reader");
        appendInboxMessage(readerInbox, {{ id: "stale-1", from: "sender", subject: "For the old incarnation", body: "Old request", toSpawnId: "s-retired" }});
        appendInboxMessage(readerInbox, {{ id: "live-1", from: "sender", subject: "For this incarnation", body: "Current request", toSpawnId: "s-replacement" }});
        appendInboxMessage(readerInbox, {{ id: "unaddressed-1", from: "sender", subject: "Unaddressed", body: "Open letter" }});
        routePeerInboxes();
        routePeerInboxes();
        const senderMail = readJsonlBatch(inboxPath(stateFilePath(undefined, root), "sender"), 0).records;
        console.log(JSON.stringify({{
          staleState: getPeerDeliveryState("stale-1") ?? null,
          liveState: getPeerDeliveryState("live-1") ?? null,
          unaddressedState: getPeerDeliveryState("unaddressed-1") ?? null,
          senderNotices: senderMail.filter((m) => m.subject === "Message not delivered").length,
          noticeMentionsRetiredIncarnation: senderMail.some((m) => String(m.body).includes("earlier incarnation of @reader")),
        }}));
        shutdownTeamMachine();
        ''',
    )
    assert payload["staleState"] == "dropped"
    assert payload["liveState"] != "dropped"
    assert payload["unaddressedState"] != "dropped"
    # The sender, not the leader's context, learns its message could not arrive.
    assert payload["senderNotices"] == 1
    assert payload["noticeMentionsRetiredIncarnation"] is True


def test_persistent_snapshot_write_failure_is_reported_once(tmp_path: Path) -> None:
    unwritable = tmp_path / "not-a-directory"
    unwritable.write_text("occupied")
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, publishStateSnapshot }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ getState }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path / "cwd")!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        for (let attempt = 0; attempt < 6; attempt++) publishStateSnapshot();
        const noticed = getState().leaderMailbox.filter((message) => message.subject === "Work snapshot writes are failing");
        console.log(JSON.stringify({{
          warned: noticed.length,
          namesTheStreak: noticed[0] ? String(noticed[0].body).includes("failed 3 consecutive writes") : false,
          keepsRetrying: noticed[0] ? String(noticed[0].body).includes("still authoritative for this session") : false,
        }}));
        shutdownTeamMachine();
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(unwritable)},
    )
    assert payload["warned"] == 1
    assert payload["namesTheStreak"] is True
    assert payload["keepsRetrying"] is True


def test_a_second_live_leader_lease_is_reported_without_blocking(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ stateFilePath }} from "{(SRC / "statefile.ts").as_uri()}";
        import {{ createTask, getState, listTasks }} from "{(SRC / "state.ts").as_uri()}";
        import fs from "node:fs";
        import path from "node:path";
        const root = {str(tmp_path)!r};
        const lock = path.join(path.dirname(stateFilePath(undefined, root)), "leader.pid");
        fs.mkdirSync(path.dirname(lock), {{ recursive: true }});
        fs.writeFileSync(lock, `${{process.ppid}}\\n`);
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        const warned = getState().leaderMailbox.filter((message) => message.subject === "Another Leader process shares this session");
        const created = createTask({{ subject: "still usable" }});
        console.log(JSON.stringify({{
          warned: warned.length,
          namesTheOtherPid: warned[0] ? String(warned[0].body).includes(String(process.ppid)) : false,
          keepsWorking: created.ok && listTasks().length === 1,
          leaseTaken: fs.readFileSync(lock, "utf-8").trim() === String(process.pid),
        }}));
        shutdownTeamMachine();
        ''',
    )
    assert payload["warned"] == 1
    assert payload["namesTheOtherPid"] is True
    assert payload["keepsWorking"] is True
    assert payload["leaseTaken"] is True


def test_direct_work_bind_failure_names_the_work_a_person_recognizes() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerAgent, assignAgent, createBoundWork }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerAgent({{ name: "busy", role: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        assignAgent("busy", {{ id: "direct:held", kind: "direct", resources: ["src/held"] }});
        const attempted = createBoundWork({{
          id: "work:11111111-2222-3333-4444-555555555555",
          subject: "Audit the release path",
          resources: [],
          holder: "busy",
          assignment: {{ id: "direct:new", kind: "direct", resources: [] }},
        }});
        console.log(JSON.stringify({{ error: attempted.ok ? "" : attempted.reason }}));
        ''',
    )
    assert payload["error"].startswith('Cannot bind Task "Audit the release path"')
    assert "already holds an open lease" in payload["error"]
    # The rolled-back Work id would have rendered as an unresolvable handle.
    assert "work:" not in payload["error"]


def test_leader_message_creates_direct_work_with_a_single_line_subject(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, sendLeaderMessage }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ getTask, registerAgent, resetState }} from "{(SRC / "state.ts").as_uri()}";
        const root = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerAgent({{ name: "worker", role: "reviewer", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        sendLeaderMessage("worker", "Rebuild the index\\n\\nKeep the schema stable.", {{ reopen: true, workId: "explicit-work" }});
        const task = getTask("explicit-work");
        console.log(JSON.stringify({{ subject: task?.subject ?? null, description: task?.description ?? null }}));
        shutdownTeamMachine();
        ''',
    )
    assert payload["subject"] == "Rebuild the index"
    assert payload["description"] == "Rebuild the index\n\nKeep the schema stable."


def test_snapshots_write_only_what_changed(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, publishStateSnapshot, applyProgress, STATE_SNAPSHOT_MIN_INTERVAL_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerAgent, createTask, updateAgent }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, rosterPath }} from "{(SRC / "statefile.ts").as_uri()}";
        import {{ tasksFilePath }} from "./src/task-domain/index.ts";
        import fs from "node:fs";
        const root = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        const state = stateFilePath(undefined, root);
        const roster = rosterPath(state);
        const tasks = tasksFilePath(undefined, root);
        const stamp = (file) => {{ const s = fs.statSync(file); return `${{s.size}}:${{s.mtimeMs}}`; }};
        const missing = (file) => !fs.existsSync(file);
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        createTask({{ subject: "tracked work" }});
        publishStateSnapshot();
        const afterChange = {{ state: stamp(state), roster: stamp(roster), tasks: stamp(tasks) }};
        // Nothing changed: no artifact is rewritten.
        publishStateSnapshot();
        const afterNoop = {{ state: stamp(state), roster: stamp(roster), tasks: stamp(tasks) }};
        // Stream progress only: the debug snapshot follows, roster and tasks do not.
        applyProgress("w", "s1", {{ text: "streaming", turns: 3, finalResponse: false }});
        const beforeProgressFlush = {{ roster: stamp(roster), tasks: stamp(tasks) }};
        await new Promise((resolve) => setTimeout(resolve, STATE_SNAPSHOT_MIN_INTERVAL_MS + 50));
        publishStateSnapshot();
        const afterProgress = {{ state: stamp(state), roster: stamp(roster), tasks: stamp(tasks), before: beforeProgressFlush }};
        if (typeof afterChange.tasks !== "string" || typeof afterNoop.tasks !== "string"
          || typeof afterProgress.tasks !== "string" || typeof afterProgress.before.tasks !== "string") {{
          throw new Error("Persistence checks require recorded task timestamps.");
        }}
        console.log(JSON.stringify({{
          wroteOnChange: !missing(state) && !missing(roster) && !missing(tasks),
          noopState: afterChange.state === afterNoop.state,
          noopRoster: afterChange.roster === afterNoop.roster,
          noopTasks: afterChange.tasks === afterNoop.tasks,
          detectsNoopTaskChange: afterChange.tasks !== `${{afterNoop.tasks}}:changed`,
          progressRewroteState: afterProgress.state !== afterChange.state,
          progressKeptRoster: afterProgress.roster === afterProgress.before.roster,
          progressKeptTasks: afterProgress.tasks === afterProgress.before.tasks,
          detectsProgressTaskChange: afterProgress.tasks !== `${{afterProgress.before.tasks}}:changed`,
        }}));
        shutdownTeamMachine();
        ''',
    )
    assert payload["wroteOnChange"] is True
    assert payload["noopState"] is True
    assert payload["noopRoster"] is True
    assert payload["noopTasks"] is True
    assert payload["detectsNoopTaskChange"] is True
    assert payload["progressRewroteState"] is True
    assert payload["progressKeptRoster"] is True
    assert payload["progressKeptTasks"] is True
    assert payload["detectsProgressTaskChange"] is True


def test_leader_mailbox_is_bounded_by_bytes_not_only_count() -> None:
    payload = run_node(
        f'''\
        import {{ deliverToLeader, getState, resetState, MAX_LEADER_MAILBOX_BYTES }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const body = "x".repeat(256 * 1024);
        for (let index = 0; index < 40; index++) deliverToLeader({{ from: "w", subject: `report ${{index}}`, body }});
        const mailbox = getState().leaderMailbox;
        const bytes = mailbox.reduce((total, message) => total + message.body.length + message.subject.length + 64, 0);
        console.log(JSON.stringify({{
          retained: mailbox.length,
          withinBytes: bytes <= MAX_LEADER_MAILBOX_BYTES,
          keptNewest: mailbox[mailbox.length - 1].subject === "report 39",
          cap: MAX_LEADER_MAILBOX_BYTES,
        }}));
        ''',
    )
    assert payload["withinBytes"] is True
    assert payload["keptNewest"] is True
    # 40 x 256 KiB is far past the byte cap, so the count must have been trimmed.
    assert payload["retained"] < 40


def test_spawner_labels_search_tool_calls_by_their_pattern() -> None:
    payload = run_node(
        f'''\
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough, Writable }} from "node:stream";
        import {{ mock }} from "node:test";
        const children = [];
        mock.method(childProcess, "spawn", () => {{
          const child = Object.assign(new EventEmitter(), {{
            pid: children.length + 1,
            stdout: new PassThrough(),
            stderr: new PassThrough(),
          }});
          child.stdin = new Writable({{ write(_chunk, _encoding, done) {{ done(); }} }});
          children.push(child);
          return child;
        }});
        syncBuiltinESMExports();
        const {{ spawnResident }} = await import("@fradser/pi-subagents");
        const activities = [];
        spawnResident({{ agentName: "searcher", onUpdate: (update) => activities.push(update.activeTool), onExit: () => {{}} }});
        const stdout = children[0].stdout;
        // A search names its pattern; its path is only the search root.
        stdout.write(JSON.stringify({{ type: "tool_execution_start", toolCallId: "grep-1", toolName: "grep", args: {{ pattern: "MINIMAL_PI_WORKER_TOOLS", path: "/repo/packages/context" }} }}) + "\\n");
        stdout.write(JSON.stringify({{ type: "tool_execution_start", toolCallId: "find-1", toolName: "find", args: {{ pattern: "**/*.feature", path: "/repo/packages" }} }}) + "\\n");
        stdout.write(JSON.stringify({{ type: "tool_execution_start", toolCallId: "read-1", toolName: "read", args: {{ path: "/repo/packages/context/index.ts" }} }}) + "\\n");
        stdout.write(JSON.stringify({{ type: "tool_execution_start", toolCallId: "work-1", toolName: "task", args: {{ subject: "Ship the release" }} }}) + "\\n");
        await new Promise((resolve) => setImmediate(resolve));
        console.log(JSON.stringify({{ activities: activities.filter((activity) => typeof activity === "string") }}));
        children.forEach((child) => child.emit("close", 0, null));
        mock.restoreAll();
        ''',
        module_mocks=True,
    )
    activities = payload["activities"]
    assert "search: MINIMAL_PI_WORKER_TOOLS" in activities, activities
    assert "search: **/*.feature" in activities, activities
    assert "file: index.ts" in activities, activities
    # A message subject names what was said, not what the worker is doing.
    assert "message: Ship the release" in activities, activities
    assert not any(activity.startswith("file: ") and activity != "file: index.ts" for activity in activities), activities

# ── test_agent_delegation.py ──
"""Public strict child control registration contract."""

import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _agent_delegation_run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bun", "-e", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )


INTENT_TOOLS = ["agent_start", "agent_input", "agent_stop", "agent_list"]


def test_intent_tool_schemas_are_strict_flat_objects():
    """One closed flat object per intent tool, not a union root.

    The retired `agent` tool was a union of per-action objects, which forces a
    tolerance layer into every consumer because some harnesses deliver a nested
    object as a JSON string. The intent family keeps the same strictness without
    the nesting, and every registered operation still refuses unknown keys.
    """
    result = _agent_delegation_run_node("""
    import { registerComposedTools } from "./tests/composed-tools.ts";
    const tools = new Map();
    registerComposedTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
    const payload = {};
    for (const name of %s) {
      const tool = tools.get(name);
      payload[name] = {
        name: tool.name,
        required: tool.parameters.required,
        strict: tool.parameters.additionalProperties === false,
        outputStrict: tool.outputSchema.additionalProperties === false,
        dispositions: tool.outputSchema.properties.disposition.enum,
      };
    }
    console.log(JSON.stringify(payload));
    """ % json.dumps(INTENT_TOOLS))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == set(INTENT_TOOLS)
    for name in INTENT_TOOLS:
        assert payload[name]["name"] == name
        assert payload[name]["strict"] is True, name
        assert payload[name]["outputStrict"] is True, name
        # One closed input object and one closed receipt vocabulary per operation.
        assert "started" in payload[name]["dispositions"], name
        assert "rejected" in payload[name]["dispositions"], name
    assert payload["agent_start"]["required"] == ["prompt"]
    assert payload["agent_input"]["required"] == ["session", "prompt", "delivery"]
    assert payload["agent_stop"]["required"] == ["session"]
    assert payload["agent_list"]["required"] == [], "the roster reads a page, so it requires nothing"

# ── test_agent_widget_ownership.py ──
"""One widget owner when a standalone child runs alongside a team."""

import json
import os
import subprocess
from pathlib import Path


def test_team_widget_excludes_standalone_children(tmp_path: Path) -> None:
    package = Path(__file__).resolve().parents[1]
    script = r'''
      import { ensureTeamWidget } from './src/ui.ts';
      import { registerAgent, resetRoster } from '@fradser/pi-subagents';
      resetRoster();
      const rows=[];
      const ctx={mode:'tui',ui:{setWidget(_key,factory){
        if(factory)rows.push(...factory({requestRender(){}},{fg:(_color,text)=>text,bold:text=>text}).render(90));
      }}};
      const base={role:'test',pid:1,status:'working',isolation:'none',createdAt:1,updatedAt:1};
      registerAgent({...base,name:'hosted',spawnId:'h'});
      registerAgent({...base,name:'standalone',spawnId:'s',standalone:true});
      ensureTeamWidget(ctx);
      console.log(JSON.stringify({rows}));
    '''
    result = subprocess.run(['node', '--input-type=module', '--eval', script],
        cwd=package, capture_output=True, text=True, timeout=30,
        env={**{key: value for key, value in os.environ.items() if not key.startswith('PI_TEAMMATE_')},
            'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)['rows']
    assert len(rows) == 1, rows
    assert 'hosted' in rows[0]
    assert 'standalone' not in rows[0]

# ── test_bundle_ack.py ──
"""The native bundle smoke must be backed by a real correlated prompt receipt."""


import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
sys.path.insert(0, str(REPO / "tests" / "e2e" / "support"))
from harness import run_install  # noqa: E402


def test_bundle_kickoff_has_native_ack_and_all_session_controls(tmp_path: Path) -> None:
    run = run_install(tmp_path, ["agent-teams"], scenario="bundle", host="team")
    assert run.completed.returncode == 0, run.text
    started = run.calls_named("agent_start")[0]
    assert not started["isError"] and started["details"]["prompted"] is True
    # The intent family mints the roster name; the label is what a reader knows.
    assert started["details"]["session"].startswith("session:")
    assert started["details"]["label"] == "scout"
    assert started["details"]["grant"] == ["message", "task"]
    # The surfaces are the tool names this install registers: the intent family
    # and mail. The retired task tools must not reappear through the bundle.
    assert set(run.surfaces()) >= {"agent_start", "agent_input", "agent_stop", "agent_list", "message"}
    assert not {"create_task", "get_task", "list_tasks", "update_task"} & set(run.surfaces())
    assert run.live_children == [], "parent shutdown must close its child"
    spawn, = [event for event in run.rpc_events if event["type"] == "spawn"]
    assert "--no-session" in spawn["args"]
    commands = [event["command"] for event in run.rpc_events if event["type"] == "command" and event["pid"] == spawn["pid"]]
    kickoff = next(command for command in commands if command["type"] == "prompt" and "ROLE PROMPT" in command["message"])
    receipts = [event["response"] for event in run.rpc_events if event["type"] == "response" and event["pid"] == spawn["pid"]]
    accepted = next(receipt for receipt in receipts if receipt.get("id") == kickoff["id"])
    assert accepted["command"] == "prompt" and accepted["success"] is True
    assert accepted.get("data", {}).get("disposition") in {"started", "queued"}
    assert not any(command["type"] == "new_session" for command in commands)
    assert "@fradser/pi-agent-teams" not in str(spawn.get("bindings", {}))

# ── test_prompt_accuracy.py ──
"""Leader prompt accuracy: guidance and tool disclosure teach only leader Work actions."""



# One vocabulary for every participant. The leader/worker split is gone, so
# there is no longer a separate leader action list to keep in step.
TASK_ACTIONS = ["create", "list", "update", "complete", "reopen"]


def _guidance() -> dict[str, object]:
    return run_node(
        f'''\
        import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance }} from "{(SRC / "guidance.ts").as_uri()}";
        console.log(JSON.stringify({{ idle: buildIdleLeaderGuidance(), active: buildTeamLeaderGuidance() }}));
        '''
    )


def test_leader_guidance_explains_internal_work_without_a_task_tool() -> None:
    payload = _guidance()
    for key in ("idle", "active"):
        flat = " ".join(str(payload[key]).split())
        lowered = flat.lower()
        assert "work items are internal" in lowered or "runtime records work internally" in lowered
        for retired in ("create_task", "list_tasks", "get_task", "update_task"):
            assert retired not in flat, f"{key} still teaches the retired {retired} tool"
    active = " ".join(str(payload["active"]).split())
    assert "no leader task tool" in active.lower()

# ── test_snapshot_version.py ──
import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_incompatible_tasks_snapshot_raises_explicit_error(tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"runtimeVersion": 1, "tasks": {"old": {}}}))
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(f'''
        import {{ readTasksFile }} from "./src/task-domain/index.ts";
        try {{ readTasksFile({str(tasks)!r}); }} catch (error) {{ console.log(error.message); }}
        ''')],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # The file is a Work
    # snapshot, and this package may be installed without the team runtime, so
    # naming Agent Teams in the error would be wrong. The version numbers and
    # the refusal to treat an incompatible tasks as empty are unchanged.
    assert "Incompatible task file version 1; expected 2." in result.stdout

# ── test_reload_incompatible_snapshot.py ──
"""Reload archives incompatible Work state without breaking extension initialization."""

import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_incompatible_snapshot_is_archived_and_initialization_continues(tmp_path):
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(f'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ tasksFilePath }} from "./src/task-domain/index.ts";
        import {{ initTeamMachine, shutdownTeamMachine }} from "./src/team-machine.ts";
        const cwd = {str(tmp_path)!r};
        const tasks = tasksFilePath(undefined, cwd);
        fs.mkdirSync(tasks.slice(0, tasks.lastIndexOf("/")), {{ recursive: true }});
        fs.writeFileSync(tasks, JSON.stringify({{ runtimeVersion: 1, tasks: {{ "old-work": {{ id: "old-work" }} }} }}));
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate() {{}}, notifyChange() {{}} }});
        const archived = fs.readdirSync(tasks.slice(0, tasks.lastIndexOf("/"))).find((name) => name.startsWith("tasks.json.incompatible-"));
        assert.ok(archived);
        assert.equal(fs.existsSync(tasks), false);
        shutdownTeamMachine();
        console.log(JSON.stringify({{ archived }}));
        ''')],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "tasks.json.incompatible-" in result.stdout


def test_unreadable_snapshot_is_archived_instead_of_silently_emptied(tmp_path):
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(f'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ tasksFilePath }} from "./src/task-domain/index.ts";
        import {{ initTeamMachine, shutdownTeamMachine }} from "./src/team-machine.ts";
        import {{ listTasks }} from "./src/state.ts";
        const cwd = {str(tmp_path)!r};
        const tasks = tasksFilePath(undefined, cwd);
        fs.mkdirSync(tasks.slice(0, tasks.lastIndexOf("/")), {{ recursive: true }});
        fs.writeFileSync(tasks, "not a task set at all");
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate() {{}}, notifyChange() {{}} }});
        const dir = tasks.slice(0, tasks.lastIndexOf("/"));
        const archived = fs.readdirSync(dir).filter((name) => name.startsWith("tasks.json.incompatible-"));
        assert.equal(archived.length, 1, "a corrupt tasks must be preserved, not discarded");
        assert.equal(fs.existsSync(tasks), false);
        assert.equal(listTasks().length, 0);
        shutdownTeamMachine();
        console.log(JSON.stringify({{ archived: archived[0] }}));
        ''')],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "tasks.json.incompatible-" in result.stdout

# ── test_tool_param_schema.py ──
"""Union-root coordination tool schemas must expose structured parameters."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_union_root_schemas_expose_and_normalize_structured_parameters():
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = environment.get("PI_TEST_DIR", PACKAGE)
    result = subprocess.run(
        ["node", "tests/tool-param-schema-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "TOOL_PARAM_SCHEMA_OK" in result.stdout

# ── test_task_vocabulary.py ──
"""Task naming at the persistence, worker, and assignment seams."""

import json
import os
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]


def test_worker_binding_and_assignment_use_task_vocabulary(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PI_TEAMMATE_") and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR"}}
    env.update({"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    script = r'''
    import assert from "node:assert/strict";
    import * as tasks from "./src/task-domain/index.ts";
    import { workerBinding } from "./src/worker.ts";
    Object.assign(process.env, {
      PI_TEAMMATE_WORKER_NAME: "fixture", PI_TEAMMATE_SPAWN_ID: "fixture-1",
      PI_TEAMMATE_OUTBOX_FILE: "/tmp/events", PI_TEAMMATE_INBOX_FILE: "/tmp/inbox",
      PI_TEAMMATE_ROSTER_FILE: "/tmp/roster", PI_TEAMMATE_TASKS_FILE: "/tmp/tasks.json",
      PI_TEAMMATE_CLAIMS_DIR: "/tmp/claims", PI_TEAMMATE_SUBMISSIONS_DIR: "/tmp/submissions",
    });
    const binding = workerBinding();
    assert.ok(binding, "Current task environment must activate the worker");
    assert.equal(binding.tasksFile, "/tmp/tasks.json");
    delete process.env.PI_TEAMMATE_TASKS_FILE;
    process.env.PI_TEAMMATE_BOARD_FILE = "/tmp/board.json";
    assert.equal(workerBinding(), undefined, "Retired environment must not activate a worker");
    let assignment;
    tasks.configureTaskStore({ get: () => ({name:"fixture",spawnId:"fixture-1",status:"idle"}),
      current: () => true, conflicting: () => undefined,
      sync: (_name, value) => { assignment=value; }, changed() {} });
    assert.equal(tasks.createTask({subject:"Task vocabulary"}).ok,true);
    assert.equal(tasks.takeTask("task-vocabulary","fixture").ok,true);
    assert.equal(assignment.kind,"task");
    assert.ok(assignment.id.startsWith("task:"));
    console.log(JSON.stringify({binding,assignment}));
    '''
    result = subprocess.run(["node", "--input-type=module", "--eval", script],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["assignment"]["kind"] == "task"

# ── test_removed_verbs.py ──
"""The cutover: every removed verb is refused, with its replacement named.

Success criterion 5 of the goal. These exist because deleting a verb is only half
the work — the other half is proving the old name cannot quietly come back. Each
removal is asserted twice: against the schema, so the name is not even offered,
and against a live call, so a caller passing it anyway gets a refusal rather than
silence.
"""


import json
import os
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"
REPO = PACKAGE.parents[1]
SUBAGENT_TOOL = REPO / "packages" / "subagents" / "src" / "child-execution.ts"
PACKAGES = REPO / "packages"

# Verb -> what replaced it. `reopen` and `supersede` are still reachable, as a
# `status` value and as a `supersedes` field on an existing action, so a caller
# that remembers the verb has somewhere to be pointed.
REMOVED_AGENT_VERBS = {
    "delegate": "start with a prompt",
    "team": "list",
}

# Two of the removed leader verbs survive as *fields* rather than verbs: a task is
# reopened with `update status=pending` and replaced with `create supersedes`, so
# they must be absent from the action enum while remaining reachable. A test that
# swept them into the enum check would forbid the only spelling that works.
REMOVED_VERBS_REACHABLE_AS_FIELDS = {"reopen", "supersede"}


def _removed_verbs_run_node(script: str) -> dict[str, object]:
    """Run an inline ES module and parse its last stdout line as JSON.

    `PI_TEAMMATE_*` is stripped so a coordination binding left over in the
    developer's shell cannot make a spawned child believe it is a worker.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    result = subprocess.run(
        ["bun", "-e", textwrap.dedent(script)],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def package_sources() -> list[Path]:
    """Every shipped source file of the three packages, tests excluded."""
    files: list[Path] = []
    for package in ("agent-teams", "subagents", "tasks"):
        for path in (PACKAGES / package).rglob("*.ts"):
            if "node_modules" in path.parts or "tests" in path.parts:
                continue
            files.append(path)
    return files


# ── No removed verb is offered ──


def test_the_child_operation_enum_is_exactly_four() -> None:
    """The set the executor implements, no more and no less: one operation per
    intent tool, with `agent_input` carrying its own delivery. The vocabulary is
    checked against the registration rather than against a remembered list."""
    result = _removed_verbs_run_node(
        f"""
        import {{ CHILD_OPERATIONS }} from {json.dumps(SUBAGENT_TOOL.as_uri())};
        console.log(JSON.stringify(CHILD_OPERATIONS));
        """
    )
    assert result == ["start", "input", "list", "stop"]


# ── And a caller passing one anyway is told, not ignored ──


def test_every_removed_agent_verb_is_refused_by_a_live_call() -> None:
    result = _removed_verbs_run_node(
        f"""
        import {{ executeChildIntent }} from {json.dumps(SUBAGENT_TOOL.as_uri())};
        const removed = {json.dumps(sorted(REMOVED_AGENT_VERBS))};
        const out = {{}};
        for (const action of removed) {{
          const r = await executeChildIntent({{ action, name: "x" }});
          out[action] = {{ refused: r.details.ok === false }};
        }}
        console.log(JSON.stringify(out));
        """
    )
    for verb in REMOVED_AGENT_VERBS:
        assert result[verb]["refused"] is True, f"{verb} was not refused"


# ── And the old tool names are gone entirely ──


def test_the_removed_tool_names_are_gone_from_every_package() -> None:
    """`work` and `agent_event` were the tool names before the cutover. A
    remaining registration would mean some install combination still answers to
    them, which is the double-registrant problem the split exists to remove."""
    offenders: list[str] = []
    for path in package_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if 'name: "work"' in line or 'name: "agent_event"' in line:
                offenders.append(f"{path.relative_to(PACKAGES)}:{number}")
    assert offenders == []


def test_the_claimed_status_value_is_gone() -> None:
    """`claimed` became `in_progress`: a Task has no declared owner, so moving it
    into progress *is* taking it. The literal must not survive as a status, though
    the field `claimedBy` legitimately keeps its name."""
    offenders = [
        str(path.relative_to(PACKAGES))
        for path in package_sources()
        if '"claimed"' in path.read_text(encoding="utf-8")
        or "'claimed'" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ── And the wiring that served the removed tool is not left behind ──


def test_the_removed_coordinator_wrappers_have_no_callers() -> None:
    """The four orchestration wrappers existed only to serve the removed tool. A
    caller left behind would take a path the tasks no longer goes through, and
    would silently skip the notice and wake-up the event subscriber performs."""
    tools = (SRC / "tools.ts").read_text(encoding="utf-8")
    for wrapper in ("createCoordinatedTask", "assignExistingWork", "releaseExistingWork", "reopenExistingWork"):
        assert f"{wrapper}(" not in tools, f"{wrapper} is still called by the tool layer"


def test_this_package_registers_exactly_one_tool() -> None:
    """`agent` belongs to @fradser/pi-subagents and the leader task tools are
    retired. What is left here is `message`."""
    text = (SRC / "tools.ts").read_text(encoding="utf-8")
    assert text.count("pi.registerTool(") == 1
    assert 'name: "message"' in text
    assert 'name: "task"' not in text
    assert 'name: "agent"' not in text

# ── test_unassigned_start.py ──
"""Public unassigned-start lifecycle regression."""
import os
import subprocess
import pytest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["assign", "not-ready", "rejected", "timeout", "exit", "notice", "inbox", "in_progress"])
def test_public_start_then_assign_without_unassigned_model_turn(tmp_path, mode):
    env = {**os.environ, "PI_TEST_MODE": mode, "PI_TEST_DIR": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")}
    # The `timeout` mode waits out the runtime's own 30-second confirmation
    # window before it reports the failure it is modelling, so the budget covers
    # that deadline plus startup. A budget below it reports a harness timeout for
    # work the runtime is doing correctly.
    result = subprocess.run(["node", "tests/unassigned-start-fixture.ts"], cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=50)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNASSIGNED_START_OK" in result.stdout


def test_leader_priority_transport_and_fresh_assignment_queue():
    result = subprocess.run(["node", "tests/leader-priority-lifecycle-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout

# ── test_work_claim.py ──
"""Worker work.claim public-seam test."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_worker_queues_and_harness_accepts_a_work_claim(tmp_path):
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = str(tmp_path)
    result = subprocess.run(
        ["node", "tests/work-claim-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "WORK_CLAIM_OK" in result.stdout

# ── test_work_sessions.py ──
"""Behavioral checks for independent Work Sessions through registered tools."""

from pathlib import Path
import subprocess
import json
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parents[1] / "tests" / "e2e" / "support"))
from harness import isolated_environment  # noqa: E402


def run_work_fixture(tmp_path: Path, probe: str = "independent") -> subprocess.CompletedProcess[str]:
    env = isolated_environment(tmp_path)
    return subprocess.run(
        ["node", str(PACKAGE / "tests" / "independent-work-fixture.ts"), probe],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=50,
    )


def test_new_delegations_are_independent_and_work_ids_route_exactly(tmp_path: Path) -> None:
    result = run_work_fixture(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INDEPENDENT_WORK_OK" in result.stdout


# The intent family starts a child only with a prompt, so the acknowledgement that
# proves the start is the prompt's. The former readiness-only probes collapsed onto
# this path and are kept once, as `readiness`.
@pytest.mark.parametrize("probe", [
    "readiness", "prompt-rejected", "prompt-timeout", "prompt-handled", "prompt-wrong-id",
])
def test_child_start_requires_parsed_rpc_confirmation(tmp_path: Path, probe: str) -> None:
    result = run_work_fixture(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"RPC_CONFIRMATION_OK {probe}" in result.stdout


def test_result_envelope_keeps_work_and_failure_evidence_in_model_context(tmp_path: Path) -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", '''
        import { formatReports } from "@fradser/pi-subagents";
        const report = { agent: "worker", workId: "work:one", assignmentId: "attempt:two", body: "Same response" };
        console.log(JSON.stringify({
          completed: formatReports([{ ...report, status: "completed", finished: true }]),
          failed: formatReports([{ ...report, status: "failed", finished: true }]),
          progress: formatReports([{ ...report, status: "in_progress" }]),
          escaped: formatReports([{ ...report, workId: 'a"<b', status: "completed" }]),
        }));
        '''], cwd=PACKAGE, env=isolated_environment(tmp_path), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert 'work="work:one"' in output["completed"]
    assert 'assignment="attempt:two"' in output["completed"]
    assert 'status="completed"' in output["completed"]
    assert 'status="failed"' in output["failed"]
    assert 'status="in_progress"' in output["progress"]
    assert len({output["completed"], output["failed"], output["progress"]}) == 3
    assert 'work="a&quot;&lt;b"' in output["escaped"]

# ── test_shared_communication.py ──
"""
Tests for communication-only shared Agent Event (message({ message, to?, intent? })).
Verifies that:
1. message tool is registered and available for both leader and worker.
2. Leader can send messages to a specific worker without an Assignment Attempt.
3. Message parameters are strictly (message, to?, status?).
"""

import json
import os
import subprocess
import textwrap
import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _shared_communication_run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bun", "-e", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )

def test_message_registered_on_leader_and_worker():
    """Verify message tool exists with (message, to?, intent?) schema on leader tools."""
    script = """
    import { registerComposedTools } from "./tests/composed-tools.ts";
    
    const registeredTools = new Map();
    const fakePi = {
      registerTool(def) {
        registeredTools.set(def.name, def);
      },
      getActiveTools() { return []; },
      setActiveTools() {}
    };

    registerComposedTools(fakePi);
    
    if (!registeredTools.has("message")) {
      console.error("FAIL: 'message' tool was not registered on leader");
      process.exit(1);
    }
    
    const eventTool = registeredTools.get("message");
    console.log(JSON.stringify({
      name: eventTool.name,
      params: eventTool.parameters
    }));
    """
    res = _shared_communication_run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["name"] == "message"
    assert "body" in data["params"]["properties"]
    assert "to" in data["params"]["properties"]
    assert "kind" in data["params"]["properties"]
    # The removed pre-rename spellings, and a thread reference, must not come back.
    for absent in ("message", "intent", "in_reply_to", "reply_to"):
        assert absent not in data["params"]["properties"], absent


def test_message_registered_on_worker_and_allowed_in_universe():
    """Verify message is registered by this package's worker capabilities and
    is grantable once that capability set is contributed to the spawn.

    The universe is no longer a spawner constant: it is built from the capability
    tools the loaded worker extensions declare, so this asserts the contribution
    rather than a hardcoded list."""
    script = """
    import { registerChildCapabilities } from "./src/worker.ts";
    import { unknownAgentTools, agentToolUniverse, resolveAgentTools } from "@fradser/pi-subagents";
    import { WORKER_CAPABILITY_TOOLS } from "./src/capability-tools.ts";
    
    const subscriptions = new Map();
    const registeredTools = new Map();
    const fakePi = {
      registerTool(def) {
        registeredTools.set(def.name, def);
      },
      getActiveTools() { return []; },
      setActiveTools() {}
    };

    fakePi.on = (event, handler) => subscriptions.set(event, handler);
    registerChildCapabilities(fakePi);
    
    const hasWorkerEvent = registeredTools.has("message");
    const unknownWithEvent = unknownAgentTools(["message", "read"], WORKER_CAPABILITY_TOOLS);
    const resolvedTools = resolveAgentTools([], WORKER_CAPABILITY_TOOLS);
    // Every declared capability tool must be something this extension registers,
    // otherwise a spawn advertises an id nothing implements.
    const declaredButUnregistered = WORKER_CAPABILITY_TOOLS.filter((name) => !registeredTools.has(name));
    // With no contributed capability set, nothing beyond pi built-ins is grantable.
    const bareUnknown = unknownAgentTools(["message", "read"], []);
    
    console.log(JSON.stringify({
      hasWorkerEvent,
      lifecycleEvents: [...subscriptions.keys()],
      unknownWithEvent,
      hasInResolved: resolvedTools.includes("message"),
      universeHasEvent: agentToolUniverse(WORKER_CAPABILITY_TOOLS).includes("message"),
      declaredButUnregistered,
      bareUnknown
    }));
    """
    res = _shared_communication_run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["hasWorkerEvent"] is True
    assert "message_start" in data["lifecycleEvents"]
    assert data["unknownWithEvent"] == []
    assert data["hasInResolved"] is True
    assert data["universeHasEvent"] is True
    # The contributed set must name only tools this extension actually registers,
    # so no spawn can advertise an id nothing implements.
    assert data["declaredButUnregistered"] == []
    # With nothing contributed, the coordination tools are correctly ungrantable:
    # this is what keeps the execution layer honest when installed alone.
    assert data["bareUnknown"] == ["message"]


def test_model_resolution_defaults_to_session_model_when_unset():
    """Verify resolveSpawnModel defaults to current session model when role has no pin and no team default."""
    script = """
    import { resolveSpawnModel } from "./src/team-machine.ts";
    
    // Role has no model pin (undefined), no team default (undefined), leader has model 'gemini-3.8-flash-high'
    const res = resolveSpawnModel(undefined, undefined, "cli-proxy/gemini-3.8-flash-high");
    console.log(JSON.stringify(res));
    """
    res = _shared_communication_run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["model"] == "cli-proxy/gemini-3.8-flash-high"
    assert data["source"] == "leader-session"


# ── test_shutdown_confirmation.py ──
import json
import os
from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def run_fixture(tmp_path, mode="unconfirmed"):
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
        and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR", "PI_CODING_AGENT_SESSION_DIR"}
    }
    env["HOME"] = str(tmp_path)
    env["PI_CODING_AGENT_DIR"] = str(tmp_path / "agent")
    run = subprocess.run(
        ["node", "--experimental-test-module-mocks", "tests/shutdown-confirmation-fixture.ts", mode],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_unconfirmed_registered_child_keeps_shutdown_and_ownership_open(tmp_path):
    result = run_fixture(tmp_path)
    assert result["stopTime"] is None
    assert result["stoppedSummaries"] == 0
    assert result["terminationCalls"] == 1
    assert result["closeObserved"] is False
    assert result["result"]["ok"] is False, result
    assert result["status"] != "stopped"
    assert result["task"]["status"] == "in_progress"
    assert result["task"]["claimedBy"] == "worker"


def test_retry_confirms_stop_and_rejects_work_while_stopping(tmp_path):
    result = run_fixture(tmp_path, "retry")
    assert result["rejected"]["ok"] is False
    assert "stopping" in result["rejected"]["error"]
    assert result["retry"]["ok"] is True
    assert "requested" not in result["retry"]["body"].lower()
    assert result["status"] == "stopped"
    assert isinstance(result["stopTime"], int)
    assert result["task"]["status"] == "blocked"


def test_delayed_close_is_intentional_and_absent_replacement_preserves_evidence(tmp_path):
    result = run_fixture(tmp_path, "delayed")
    assert result["stopped"]["status"] == "stopped"
    assert result["stopped"].get("error") is None
    assert isinstance(result["stopTime"], int)
    assert result["retained"] == result["stopTime"]
    assert result["absent"]["ok"] is True
    assert result["replacementTime"] == 1234567890000
    assert result["resetTime"] is None


def test_clean_idle_close_keeps_results_without_a_crash_notification(tmp_path: Path) -> None:
    result = run_fixture(tmp_path, "close-idle")
    assert result["status"] == "stopped"
    assert result["stopTime"] == 1234567890000
    assert result["error"] is None
    assert result["reports"] == [], "A clean idle close must not start another leader turn"
    assert result["task"]["status"] == "completed"
    assert result["task"]["result"] == "Accepted review evidence"
    assert [message["subject"] for message in result["mailbox"]] == ["Agent stopped"]
    assert "unexpected" not in result["mailbox"][0]["body"].lower()


@pytest.mark.parametrize("mode, expected_alarm", [
    ("close-mail-current", True),
    ("close-mail-unbound", True),
    ("close-mail-late", True),
    ("close-mail-invalid-body", True),
    ("close-mail-invalid-binding", True),
    ("close-mail-broken-json", True),
    ("close-mail-incomplete", True),
    ("close-mail-stale", False),
    ("close-mail-delivered", False),
])
def test_unread_current_mail_prevents_passive_close_without_consuming_it(
    tmp_path: Path, mode: str, expected_alarm: bool,
) -> None:
    result = run_fixture(tmp_path, mode)
    assert result["status"] == "stopped"
    assert result["error"] is None
    assert result["stopTime"] == 1234567890000
    assert len(result["reports"]) == int(expected_alarm)
    if expected_alarm:
        assert result["reports"][0]["harnessEvent"]["type"] == "unexpected-stop"
    expected_subject = "Agent stopped unexpectedly" if expected_alarm else "Agent stopped"
    assert [message["subject"] for message in result["mailbox"]] == [expected_subject]
    assert result["task"]["status"] == "completed"
    assert result["task"]["result"] == "Accepted review evidence"
    assert result["inboxUnchanged"] is True
    assert result["deliveryStateUnchanged"] is True


@pytest.mark.parametrize("mode", ["close-owned", "close-crash", "close-signal", "close-unreported"])
def test_unrequested_failure_or_unfinished_work_still_reaches_the_leader(tmp_path: Path, mode: str) -> None:
    result = run_fixture(tmp_path, mode)
    assert result["status"] == "stopped"
    assert result["stopTime"] == 1234567890000
    assert len(result["reports"]) == 1, "Repeated close events must not repeat the alarm"
    assert result["reports"][0]["harnessEvent"]["type"] == "unexpected-stop"
    assert [message["subject"] for message in result["mailbox"]] == ["Agent stopped unexpectedly"]
    if mode in {"close-owned", "close-unreported"}:
        assert result["task"]["status"] == "blocked"
        assert "claimedBy" not in result["task"]
    else:
        assert result["error"] is not None
        assert result["task"]["status"] == "completed"
        assert result["task"]["result"] == "Accepted review evidence"

# ── test_coordination_rows.py ──
"""Human-facing coordination rows expose names, subjects, and typed text."""

import fcntl
import json
import os
import pty
import secrets
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path
from typing import Callable

import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_coordination_rows_are_readable_without_identifiers(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    result = subprocess.run(
        ["node", "tests/coordination-rows-fixture.ts"],
        cwd=PACKAGE,
        env={
            # A spawned teammate runs the suite with its own holder bound. A
            # fixture that inherits that binding takes work as the teammate and
            # fails for a reason the fixture chose, not for the one under test.
            **{key: value for key, value in os.environ.items()
               if not key.startswith("PI_TEAMMATE_") and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR"}},
            "PI_CODING_AGENT_DIR": str(agent_dir),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "COORDINATION_ROWS_OK" in result.stdout


@pytest.fixture
def native_message_fixture(tmp_path: Path) -> tuple[list[str], dict[str, str], Path]:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native message layout verification")
    fixture = tmp_path / "message-layout.ts"
    snapshots = tmp_path / "renders.jsonl"
    source = r'''
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import { initTheme, ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import { KeybindingsManager, setKeybindings, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { registerComposedTools } from "__COMPOSED__";
import { registerChildCapabilities } from "__WORKER__";

const message = "FIRST-CONTENT " + Array.from({ length: 28 }, (_, i) => `evidence-${i}`).join(" ") + " LAST-CONTENT";
const hyperlink = "\u001b]8;;https://example.test\u001b\\LINK-LABEL\u001b]8;;\u001b\\";
const literal = '\nPreserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
const args = { to: "continual-audit-close", body: message + " " + hyperlink + literal };
const result = { content: [{ type: "text", text: "EVENT ROUTING · steered" }], details: { to: args.to, outcome: "steered" }, isError: false };
const expected = `[message] to @${args.to} · steered · ${message} LINK-LABEL${literal}`;
const tools = new Map();
const capture = (prefix) => ({ registerTool: (tool) => tools.set(`${prefix}:${tool.name}`, tool), on() {} });
registerComposedTools(capture("leader"));
registerChildCapabilities(capture("worker"));

export default function (pi) {
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode === "tui") return;
    initTheme("dark", false);
    setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
    for (const surface of ["leader", "worker"]) {
      const component = new ToolExecutionComponent("message", "native-layout", args, {}, tools.get(`${surface}:message`), { requestRender() {} }, ctx.cwd);
      component.updateResult(result);
      const content = (width) => {
        const lines = component.render(width);
        assert.ok(lines.every((line) => visibleWidth(line) <= width));
        return lines.slice(2, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
      };
      for (const width of [48, 90, 240]) {
        component.setExpanded(false);
        assert.ok(content(width)[0].endsWith(" · ctrl+o to expand"));
        assert.equal(component.handleMouse({ type: "click", button: "left", x: 5, y: 2, width, height: 4 })?.handled, true);
        assert.deepEqual(content(width), wrapTextWithAnsi(expected, width - 2));
        assert.equal(component.handleMouse({ type: "click", button: "left", x: 5, y: 2, width, height: 20 })?.handled, true);
        assert.ok(content(width)[0].endsWith(" · ctrl+o to expand"));
      }
    }
    console.log("NATIVE_MESSAGE_LAYOUT_OK");
  });
  const tool = tools.get("leader:message");
  pi.registerTool({
    ...tool,
    // The original routing execute is never invoked: no peers or team writes.
    async execute() { return result; },
    renderResult(value, options, theme, context) {
      const component = tool.renderResult(value, options, theme, context);
      return {
        invalidate: () => component.invalidate(),
        render(width) {
          const lines = component.render(width);
          appendFileSync(process.env.PI_MESSAGE_LAYOUT_SNAPSHOTS, JSON.stringify({
            width, expanded: options.expanded, lines: lines.map(stripVTControlCharacters), expected,
            expectedLines: wrapTextWithAnsi(expected, width - 2).map((line) => line.trimEnd()),
          }) + "\n");
          return lines;
        },
      };
    },
  });
  let calls = 0;
  pi.registerProvider("message-layout-fixture", {
    api: "message-layout-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_MESSAGE_LAYOUT_AUTH,
    models: [{ id: "deterministic", name: "Message layout fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const first = ++calls === 1;
      const output = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: first ? [{ type: "toolCall", id: "message-row", name: "message", arguments: args }]
          : [{ type: "text", text: "MESSAGE_LAYOUT_READY" }],
        stopReason: first ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: output });
      stream.push({ type: "done", reason: output.stopReason, message: output });
      stream.end();
      return stream;
    },
  });
}
'''
    fixture.write_text(source
                       .replace("__COMPOSED__", Path(PACKAGE, "tests", "composed-tools.ts").as_uri())
                       .replace("__WORKER__", Path(PACKAGE, "src", "worker.ts").as_uri()))
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
        "PI_MESSAGE_LAYOUT_AUTH": secrets.token_hex(16), "PI_MESSAGE_LAYOUT_SNAPSHOTS": str(snapshots),
        "TERM": "xterm-256color",
    })
    command = [
        pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
        "--no-context-files", "--no-approve", "--extension", str(fixture), "--provider", "message-layout-fixture",
        "--model", "deterministic", "--thinking", "off", "--no-builtin-tools", "Render the isolated message fixture",
    ]
    return command, env, snapshots


def test_native_pi_print_message_mouse_expansion_and_resizing(
    native_message_fixture: tuple[list[str], dict[str, str], Path], tmp_path: Path,
) -> None:
    command, env, _snapshots = native_message_fixture
    result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NATIVE_MESSAGE_LAYOUT_OK" in result.stdout + result.stderr, result.stdout + result.stderr
    assert "MESSAGE_LAYOUT_READY" in result.stdout, result.stdout + result.stderr
    assert "AssertionError" not in result.stderr


def test_native_pi_tui_message_expand_key_and_terminal_resize(
    native_message_fixture: tuple[list[str], dict[str, str], Path], tmp_path: Path,
) -> None:
    command, env, snapshots = native_message_fixture
    master, slave = pty.openpty()
    transcript = bytearray()

    def resize(width: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 36, width, 0, 0))

    def renders() -> list[dict[str, object]]:
        if not snapshots.exists():
            return []
        lines = snapshots.read_text().splitlines()
        return [json.loads(line) for line in lines if line.endswith("}")]

    resize(90)
    try:
        with subprocess.Popen([*command, "--tui-mode", "fullscreen"], cwd=tmp_path, env=env,
                              stdin=slave, stdout=slave, stderr=slave) as process:
            os.close(slave)

            def wait_for(predicate: Callable[[], bool], timeout: float = 30) -> None:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.05)[0]:
                        try:
                            transcript.extend(os.read(master, 65536))
                        except OSError:
                            # The PTY master reports EIO/ENXIO/EBADF once the child
                            # closes its side. PTY closure can precede the
                            # observable exit status, so reap the child before
                            # deciding an exit predicate failed.
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                pass
                            if predicate():
                                return
                            break
                    if predicate():
                        return
                    if process.poll() is not None:
                        break
                raise AssertionError(transcript.decode(errors="replace"))

            def recorded_summary() -> list[tuple[object, object]]:
                return [(row["width"], row["expanded"]) for row in renders()]

            def until(action: Callable[[], None], predicate: Callable[[], bool]) -> None:
                """Drive the real TUI to an observable state, retrying the interaction.

                Synchronization is data-based but never single-shot: the host may
                paint its first frame at its own default width, and a key sent
                while the turn is still settling can be dropped, so each step
                retries until its row is recorded.
                """
                last: AssertionError | None = None
                for _attempt in range(3):
                    action()
                    try:
                        wait_for(predicate, timeout=12)
                        return
                    except AssertionError:
                        last = AssertionError(
                            f"action attempt {_attempt + 1} never reached its row; recorded={recorded_summary()}"
                        )
                raise last or AssertionError("interaction never reached its observable state")

            def matches(width: int, expanded: bool) -> bool:
                return any(row["width"] == width and row["expanded"] == expanded for row in renders())

            try:
                # The host may paint its first frame at its own default width, so
                # startup synchronization is semantic; every width below is then
                # driven explicitly and verified from the recorded rows.
                wait_for(lambda: b"MESSAGE_LAYOUT_READY" in transcript and any(row["expanded"] is False for row in renders()))
                until(lambda: (resize(90), process.send_signal(signal.SIGWINCH)), lambda: matches(90, False))
                until(lambda: os.write(master, b"\x0f"), lambda: matches(90, True))  # Configured Ctrl+O.
                for width in [48, 240]:
                    until(
                        lambda w=width: (resize(w), process.send_signal(signal.SIGWINCH)),
                        lambda w=width: matches(w, True),
                    )
                until(lambda: os.write(master, b"\x0f"), lambda: matches(240, False))
                until(lambda: (resize(48), process.send_signal(signal.SIGWINCH)), lambda: matches(48, False))
                for row in renders():
                    content = [line[1:].rstrip() for line in row["lines"][1:-1]]
                    if row["expanded"]:
                        assert content == row["expectedLines"], content
                        assert " ".join(content).count("FIRST-CONTENT") == 1
                    else:
                        assert content[0].endswith(" · ctrl+o to expand"), content
                # Every resize and both expansion states must have produced a
                # verified row: synchronization above is state-based, so the
                # coverage assertion belongs here, on the recorded data.
                for width in (48, 90, 240):
                    for expanded in (True, False):
                        assert matches(width, expanded), (width, expanded, renders())
                # Quit with the configured key, retrying: an impatient Ctrl+D can
                # arrive while the closing turn is still settling and be ignored.
                for _attempt in range(3):
                    if process.poll() is not None:
                        break
                    try:
                        os.write(master, b"\x04")
                    except OSError:
                        break  # The PTY is already closed: the child exited.
                    try:
                        wait_for(lambda: process.poll() is not None, timeout=10)
                        break
                    except AssertionError:
                        continue
                if process.poll() is None:
                    # The row contract above is already verified; the host's own
                    # quit timing is not this test's subject, so terminate
                    # gracefully instead of failing on it.
                    try:
                        process.terminate()
                    except OSError:
                        pass  # It exited between the check and the signal.
                wait_for(lambda: process.poll() is not None, timeout=10)
                exit_code = process.wait(timeout=5)
                assert exit_code in (0, -signal.SIGTERM), transcript.decode(errors="replace")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        os.close(master)
        (tmp_path / "terminal-transcript.txt").write_bytes(transcript)

# ── test_disk_identity_resident.py ──
"""Consumer regression for the adopted disk-only identity execution contract."""


import json
import os
import subprocess
from pathlib import Path

import pytest



@pytest.mark.parametrize("mode", ["accepted", "queued", "rejected", "handled", "exit", "timeout", "fast-result", "disk", "registry-owner", "two-results", "idle-send", "interrupt", "interrupt-rejected", "interrupt-handled", "interrupt-timeout", "interrupt-exit", "send-rejected", "send-handled", "send-timeout", "send-exit", "send-fast-result", "late-negative", "pending-start", "gate-on-drain", "intent-fast-report"])
def test_team_resident_contract(tmp_path: Path, mode: str) -> None:
    env = {**os.environ, "PI_TEST_MODE": mode, "PI_TEST_DIR": str(tmp_path)}
    # The `timeout` mode waits out the runtime's own 30-second confirmation
    # window before it reports the failure it is modelling, so the budget covers
    # that deadline plus startup. A budget below it reports a harness timeout for
    # work the runtime is doing correctly.
    result = subprocess.run(
        ["node", "tests/disk-identity-resident-fixture.ts"], cwd=PACKAGE,
        env=env, capture_output=True, text=True, timeout=50,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"] is True


def test_team_guidance_names_only_the_intent_tool_family() -> None:
    """The intent family replaces the retired `agent` surface, and the guidance
    must say so by naming the four tools and nothing else.

    ADR-0008 removed the legacy branch and its in-transcript notice: a recorded
    branch that named `agent` moves silently, so a "Legacy branches" line would
    now describe a surface no code can select. The guidance must still carry the
    surviving contract, and must not reintroduce the retired name as a tool.
    """
    payload = run_node(f'''
      import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      console.log(JSON.stringify({{ idle: buildIdleLeaderGuidance(), active: buildTeamLeaderGuidance() }}));
    ''')
    for text in payload.values():
        # The adopted fresh-session contract replaces six model actions with four intent tools.
        for tool in ("agent_start", "agent_input", "agent_list", "agent_stop"):
            assert f"`{tool}`" in text
        assert "Legacy branches" not in text, "The retired legacy branch has no selectable surface"
        assert "`agent`" not in text, "The retired agent tool must not appear as a surface"
        # `agent_inspect` was retired with the legacy tool, so guidance that still
        # names it teaches a model to call a tool no transport registers.
        assert "agent_inspect" not in text, "The retired inspect tool must not appear as a surface"
        assert "next" in text and "steer" in text
        for obsolete in ("persist: true", "persistent:", "memory: true", "worktree: true", "promot"):
            assert obsolete not in text.lower()
        assert "agent.md" in text


def test_consumer_has_no_identity_write_or_git_workspace_hooks() -> None:
    source = (SRC / "team-machine.ts").read_text()
    for removed in ("persistAgentDefinition", "preserveAgentWorkspace", "releaseAgentWorkspace", "liveWorkspaces", "finalizeWorktree", "discardWorkspaceQuietly", "persistScope", "generated.persist", "agent.memory", "agent.isolation"):
        assert removed not in source, removed
    definition = run_node(f'''
      import {{ InlineAgentDefinitionParams }} from "{(SRC / 'types.ts').as_uri()}";
      console.log(JSON.stringify({{ fields: Object.keys(InlineAgentDefinitionParams.properties) }}));
    ''')
    assert not set(definition["fields"]) & {"persist", "persistScope", "persistent", "memory", "worktree", "isolation"}

# ── test_native_disk_identity.py ──
"""Native Pi coordinator checks with fixture-only loopback config."""


import json
import os
import secrets
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


@pytest.fixture
def native_team_environment(tmp_path: Path) -> Iterator[tuple[dict[str, str], list[dict[str, object]]]]:
    core = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "package.json"
    # The root development requirement is the cohort of record, so this cannot drift from it.
    expected = json.loads((REPO / "package.json").read_text())["devDependencies"]["@earendil-works/pi-coding-agent"].lstrip("^")
    assert json.loads(core.read_text())["version"] == expected
    requests: list[dict[str, object]] = []
    started = threading.Event()
    release = threading.Event()
    if os.environ.get("PI_TEST_MODE") != "interrupt":
        release.set()

    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path != "/started" or not started.wait(timeout=20):
                self.send_error(408, "No actual model request arrived")
                return
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path == "/release":
                release.set()
                self.send_response(200)
                self.end_headers()
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            started.set()
            if not release.wait(timeout=25):
                self.send_error(504, "Model fixture was not released")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {"id": "team-data", "object": "chat.completion.chunk", "created": 1, "model": "evidence"}
            for delta, finish in (({"role": "assistant", "content": "LIVE_TEAM_DATA_OK"}, None), ({}, "stop")):
                event = {**chunk, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = Path(os.environ["PI_CODING_AGENT_DIR"])
    credential = secrets.token_hex(16)
    (config / "settings.json").write_text(json.dumps({"quietStartup": True, "defaultProjectTrust": "always"}))
    (config / "models.json").write_text(json.dumps({"providers": {
        "teams-local-fixture": {"api": "openai-completions", "apiKey": credential,
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "models": [{"id": "evidence", "name": "Team data fixture", "reasoning": False,
                "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TERM", "HOME", "PI_CODING_AGENT_DIR") if key in os.environ}
    env.update({"PI_OFFLINE": "1", "PI_TEST_DIR": str(tmp_path), "PI_TEST_MODEL": "teams-local-fixture/evidence",
        "PI_TEST_MODEL_CONTROL": f"http://127.0.0.1:{server.server_port}", "PI_TEST_MODE": os.environ.get("PI_TEST_MODE", "two-inputs")})
    try:
        yield env, requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("unread_mail", [False, True])
def test_native_clean_idle_close_has_no_unexpected_stop(
    native_team_environment: tuple, tmp_path: Path, unread_mail: bool,
) -> None:
    env, requests = native_team_environment
    loader = (PACKAGE / "tests/native-clean-close-loader.mjs").as_uri()
    env = {**env, "NODE_OPTIONS": f"--import={loader}", "PI_TEST_UNREAD_MAIL": "1" if unread_mail else "0"}
    result = subprocess.run(["node", str(PACKAGE / "tests/native-clean-close.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["nativePid"] > 0
    assert report["status"] == "stopped"
    assert report["unexpectedReports"] == int(unread_mail)
    assert report["subject"] == ("Agent stopped unexpectedly" if unread_mail else "Agent stopped")
    assert requests == [], "The clean-close slash command must not request a model"


def test_native_team_disk_memory_and_history(native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-workspace-memory.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["durableDataRetained"] is True
    assert len(requests) == 1
    messages = requests[0]["messages"]
    text = json.dumps(messages)
    assert "AGENT MEMORY" in text and "known-method.md" in text, text
    assert "Native durable data probe" not in text or "Return the requested evidence" in text
    assert str(tmp_path / "project") in text


def test_native_hosted_two_inputs_keep_process_and_history(native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-hosted-resident.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reports"] == 2 and report["sameProcess"] is True
    assert len(requests) == 2, "send creates exactly one model turn"
    history = json.dumps(requests[1]["messages"])
    assert "First input" in history and "Second input" in history and "LIVE_TEAM_DATA_OK" in history
    assert history.count("PINNED_HOSTED_ROLE") == 1, "standing role is delivered on first input only"


@pytest.fixture
def interrupt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_TEST_MODE", "interrupt")


def test_native_hosted_interrupt_is_same_sequence(interrupt_mode: None, native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-hosted-resident.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reports"] == 1 and report["sameProcess"] is True
    assert requests, "the active sequence must have actually reached the loopback model"
    assert len(requests) <= 2, "steering may continue the same sequence, never add an independent input"

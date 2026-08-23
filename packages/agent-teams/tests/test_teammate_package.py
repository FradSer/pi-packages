from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_spawn",
    "teammate_shutdown",
    "send_message",
    "task_create",
    "task_list",
}
WORKER_TOOLS = {
    "send_message",
    "task_list",
    "task_claim",
    "task_submit",
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


def run_node(script: str, *args: str, env_overrides: dict[str, str] | None = None) -> dict[str, object]:
    env = os.environ.copy()
    env.update(env_overrides or {})
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script), *args],
        cwd=PACKAGE,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout)


def agent_dir_env(tmp: Path) -> dict[str, str]:
    return {"PI_CODING_AGENT_DIR": str(tmp)}


def test_manifest_declares_native_extension_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-agent-teams"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "skills" not in manifest["files"]
    assert "agents" in manifest["files"] or (PACKAGE / "agents").exists()


def test_bdd_contract_covers_target_resources() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    for phrase in (
        "Feature: Agent Teams collaborative organization contract",
        "Agents are declarative Markdown files",
        "Discover agents from bundled, user, project, and project-local scopes",
        "Project scopes distinguish git-managed from local definitions",
        "xxx.local.md files mark personal overrides inside .pi/agents",
        "Local override files dedupe against their shared counterpart by teammate name",
        "Agent frontmatter declares tools, model, verify, and worktree; the body is the role prompt",
        "An unknown agent name fails the spawn",
        "Teammates are named resident processes",
        "Spawning creates one named resident teammate",
        "Teammate names are unique among living teammates",
        "The session-wide cap bounds resident teammates",
        "Idle teammates are suspended between turns",
        "Shutdown stops one teammate and frees its slot",
        "An unexpected teammate crash is reported to the leader",
        "Teammates do not survive session shutdown",
        "Turn budgets bound each wake-up sequence instead of wall-clock time",
        "Messaging is peer-to-peer through local inboxes",
        "Teammates exchange messages directly by name",
        "Delivered messages wake an idle teammate automatically",
        "Messages reach a working teammate without dropping",
        "Inbox delivery is at-least-once and deduplicated",
        "Peer traffic never enters the leader's model context",
        "Reports to the leader use the unified send_message primitive",
        "The leader addresses a living teammate by name through send_message",
        "An idle teammate with an unfinalized last report nudges the leader",
        "the reminder fires once per idle transition, not per stream tick",
        "the shared task_list view includes the living roster on both leader and worker sides",
        "Stale spawn events cannot affect a newer teammate incarnation",
        "The task board is shared coordination state",
        "The leader creates tasks; teammates never do",
        "Only resident teammates self-claim tasks",
        "Dependencies gate claimability",
        "Claimed tasks are released when their holder stops",
        "Completion is submitted by the claimer and gated by verify",
        "Failed submissions keep the task claimable by its holder",
        "The board persists across restarts while the runtime does not",
        "Board state has one writer",
        "The harness wakes idle teammates, the leader model never polls",
        "Claimable-task notices respect a per-teammate pacing interval",
        "Leader tool surface is exact",
        "Workers cannot access leader tools",
        "Worktree isolation is an agent-role option",
        "Console and widget visualize the team without intercepting input",
        "The widget shows only working teammates",
        "idle and stopped teammates never appear above the input box",
        "the widget stays hidden when nobody is working",
        "including idle and stopped teammates",
        "Spawning renders one started line per teammate",
        "Acceptance workflow — three-way review with cross-challenge",
    ):
        assert phrase in feature, phrase


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts") + source("tools.ts") + source("worker.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext, tool
    for tool in REMOVED_TOOLS:
        assert f'name: "{tool}"' not in ext, tool
    assert source("tools.ts").count('name: "task_list"') == 0
    assert source("worker.ts").count('name: "task_list"') == 1


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
        import {{ createTaskIntent, takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-intents-"));
        const intent = {{ taskId: "t_1", worker: "security", spawnId: "s1", timestamp: 1 }};
        const won = createTaskIntent(dir, "t_1", intent);
        const lost = createTaskIntent(dir, "t_1", {{ ...intent, worker: "backend" }});
        const drained = takeTaskIntent(dir);
        const next = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          won,
          lost,
          drainedWorker: drained?.intent?.worker ?? null,
          boardEmptyAgain: next.intent === undefined && next.diagnostic === undefined,
        }}));
        '''
    )
    assert payload["won"] is True
    assert payload["lost"] is False
    assert payload["drainedWorker"] == "security"
    assert payload["boardEmptyAgain"] is True


def test_take_task_intent_skips_malformed_records() -> None:
    payload = run_node(
        f'''\
        import {{ takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-badintents-"));
        fs.writeFileSync(path.join(dir, "a-broken.json"), "{{ not json");
        fs.writeFileSync(path.join(dir, "b-good.json"), JSON.stringify({{ taskId: "t_2", worker: "tests", spawnId: "s", timestamp: 2 }}));
        const first = takeTaskIntent(dir);
        const second = takeTaskIntent(dir);
        const third = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          firstWasDiagnostic: typeof first.diagnostic === "string" && first.intent === undefined,
          goodWorker: second?.intent?.worker ?? null,
          malformedConsumed: !fs.existsSync(path.join(dir, "a-broken.json")),
          drainedEmpty: third.intent === undefined && third.diagnostic === undefined,
        }}));
        '''
    )
    assert payload["firstWasDiagnostic"] is True
    assert payload["goodWorker"] == "tests"
    assert payload["malformedConsumed"] is True
    assert payload["drainedEmpty"] is True


def test_inbox_roundtrip_offsets_and_diagnostics() -> None:
    payload = run_node(
        f'''\
        import {{ appendInboxMessage, inboxPath, readJsonlBatch, writeRoster, readRoster, rosterPath, stateFilePath, writeStateFile, readBoardFile, writeBoardFile }} from "{(SRC / "statefile.ts").as_uri()}";
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
        writeStateFile(stateFile, {{ teammates: {{}}, tasks: {{}}, leaderMailbox: [], messageCounter: 0, taskCounter: 0, workerEventOffsets: {{}}, workerEventIds: {{}}, peerInboxOffsets: {{}}, peerDeliveredIds: {{}} }});
        writeBoardFile(dir + "/board.json", {{ t_1: {{ id: "t_1", subject: "s", dependsOn: [], status: "pending", createdAt: 1, updatedAt: 1 }} }});
        const board = readBoardFile(dir + "/board.json");
        console.log(JSON.stringify({{
          firstCount: first.records.length,
          secondId: consumed.records.length === 0 ? "none" : JSON.parse(JSON.stringify(consumed.records[0])).id,
          diagnostics: after.diagnostics.length,
          rosterName: roster[0]?.name ?? null,
          boardSubject: board?.tasks.t_1?.subject ?? null,
          inboxInsideSessionDir: inbox.startsWith(dir),
        }}));
        '''
    )
    assert payload["firstCount"] == 2
    assert payload["secondId"] == "none"
    assert payload["diagnostics"] >= 1
    assert payload["rosterName"] == "backend"
    assert payload["boardSubject"] == "s"
    assert payload["inboxInsideSessionDir"] is True


def test_state_machine_roster_and_board_rules() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, getTeammate, livingTeammates, idleTeammates,
                 releaseTasksOf, loadBoard, updateTeammate, isValidTeammateName,
                 createTask, applyClaimIntent, applySubmissionIntent, completeTask,
                 getTask, listTasks, pendingTasks, deliverToLeader, receiveWorkerMessage }} from "{(SRC / "state.ts").as_uri()}";
        function snapshot() {{
          const t = (id) => getTask(id)?.status ?? null;
          return {{}};
        }}
        resetState();
        const badName = registerTeammate({{ name: "has space", agent: "worker", spawnId: "s0", pid: 0, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const first = registerTeammate({{ name: "security", agent: "reviewer", spawnId: "sa", pid: 1, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const duplicate = registerTeammate({{ name: "security", agent: "worker", spawnId: "sb", pid: 2, status: "starting", isolation: "none", createdAt: 2, updatedAt: 2 }});
        updateTeammate("security", {{ status: "idle" }});
        const gate = createTask({{ subject: "base review" }});
        const dependent = createTask({{ subject: "fix findings", dependsOn: [gate.task.id] }});
        const unknownDep = createTask({{ subject: "x", dependsOn: ["t_missing"] }});
        const emptySubject = createTask({{ subject: "  " }});
        const claimBlocked = applyClaimIntent({{ taskId: dependent.task.id, worker: "security", spawnId: "sa", timestamp: 1 }});
        const claimOk = applyClaimIntent({{ taskId: gate.task.id, worker: "security", spawnId: "sa", timestamp: 1 }});
        const doubleClaim = applyClaimIntent({{ taskId: gate.task.id, worker: "ghost", spawnId: "sx", timestamp: 2 }});
        const wrongHolder = applySubmissionIntent({{ taskId: gate.task.id, worker: "ghost", spawnId: "sx", status: "completed", timestamp: 3 }});
        const submitted = applySubmissionIntent({{ taskId: gate.task.id, worker: "security", spawnId: "sa", status: "completed", result: "clean", timestamp: 4 }});
        const unlocked = pendingTasks().map((task) => task.id);
        const staleEvent = receiveWorkerMessage({{ id: "e1", type: "message", worker: "security", spawnId: "OLD", body: "b" }});
        const freshEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const dupEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const released = releaseTasksOf("nobody", "reason");
        // Capture pre-reset values before the resume simulation wipes the board.
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
        const reloaded = loadBoard({{ t_9: {{ id: "t_9", subject: "carried over", dependsOn: [], status: "claimed", claimedBy: "dead", createdAt: 1, updatedAt: 1 }}, t_8: {{ id: "t_8", subject: "finished", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }});
        console.log(JSON.stringify({{
          badNameOk: badName.ok,
          firstOk: first.ok,
          duplicateOk: duplicate.ok,
          unknownDepOk: unknownDep.ok,
          emptySubjectOk: emptySubject.ok,
          claimBlockedReason: claimBlocked.reason ?? null,
          claimOkApplied: claimOk.applied,
          doubleClaimReason: (doubleClaim.reason ?? "").includes("already claimed"),
          wrongHolderError: (wrongHolder.error ?? "").includes("claimed by") || (wrongHolder.error ?? "").includes("not currently"),
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
    assert payload["claimBlockedReason"] is not None and "unmet dependencies" in payload["claimBlockedReason"]
    assert payload["claimOkApplied"] is True
    assert payload["doubleClaimReason"] is True
    assert payload["wrongHolderError"] is True
    assert payload["submittedOk"] is True
    assert payload["gateStatus"] == "completed"
    assert payload["unlockedContainsDependent"] is True
    assert payload["staleEventAccepted"] is False
    assert payload["freshEventAccepted"] is True
    assert payload["duplicateSuppressed"] is True
    assert payload["releasedCount"] == 0
    assert payload["reloadedCount"] == 2
    assert payload["resumedClaimBackToPending"] == "pending"
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
          suggestsClaim: prompt.includes("task_claim"),
          quietEmpty: quiet === "",
          paceMs: NOTICE_PACE_MS,
        }}));
        '''
    )
    assert payload["hasInbox"] is True
    assert payload["hasSender"] is True
    assert payload["hasBody"] is True
    assert payload["hasNotice"] is True
    assert payload["suggestsClaim"] is True
    assert payload["quietEmpty"] is True
    assert payload["paceMs"] == 2000


def test_agent_definitions_are_declarative_files_with_verify() -> None:
    ext = source("agents.ts") + source("tools.ts")
    assert "discoverAgents" in ext and "resolveAgent" in ext
    agents_ts = source("agents.ts")
    assert 'LOCAL_DEFINITION_SUFFIX = ".local.md"' in agents_ts
    assert 'gitManaged: scope === "project"' in agents_ts or 'return scope === "project";' in agents_ts
    assert "fields.verify" in agents_ts
    assert 'return scope === "project";' in agents_ts
    assert "PI_CODING_AGENT_DIR" in agents_ts or "getAgentDir" in agents_ts


def test_agent_frontmatter_parses_tools_model_verify(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "auditor.md").write_text(
        "---\n"
        "name: auditor\n"
        "description: Reviews code for exploitable problems\n"
        "tools: read,grep # execution allowlist\n"
        "model: anthropic/claude-sonnet-4\n"
        'verify: "npm test"\n'
        "worktree: true\n"
        "---\n"
        "Review the assigned scope.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
        const agent = resolveAgent("auditor", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          found: Boolean(agent),
          tools: agent?.tools ?? [],
          model: agent?.model ?? null,
          verify: agent?.verify ?? null,
          worktree: agent?.worktree ?? null,
          scope: agent?.scope ?? null,
          promptIsBody: (agent?.prompt ?? "").includes("Review the assigned scope."),
        }}));
        ''',
    )
    assert payload["found"] is True
    assert payload["tools"] == ["read", "grep"]
    assert payload["model"] == "anthropic/claude-sonnet-4"
    assert payload["verify"] == "npm test"
    assert payload["worktree"] is True
    assert payload["scope"] == "project"
    assert payload["promptIsBody"] is True


def test_project_agent_overrides_user_and_bundled(tmp_path: Path) -> None:
    user_dir = tmp_path / "user-agents"
    project_dir = tmp_path / ".pi" / "agents"
    project_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    (user_dir / "dup.md").write_text("---\nname: dup\n---\nuser body\n", encoding="utf-8")
    # Same teammate, shared layer + personal local override in ONE directory.
    (project_dir / "dup.md").write_text("---\nname: dup\n---\nproject body\n", encoding="utf-8")
    (project_dir / "dup.local.md").write_text("---\nname: dup\n---\nproject-local body\n", encoding="utf-8")
    (project_dir / "shared.md").write_text("---\nname: shared\n---\nshared role\n", encoding="utf-8")
    (project_dir / "personal.local.md").write_text("---\nname: personal\n---\npersonal role\n", encoding="utf-8")
    payload = run_node(
        f'''\
        import {{ discoverAgents, resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
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
    # dedup: dup.md + dup.local.md collapse into ONE entry; no "dup.local" key.
    assert sorted(payload["keys"]) == [
        "dup", "observer", "personal", "reviewer", "shared", "specialist", "worker",
    ]
    assert payload["dupScope"] == "project-local"
    assert payload["dupBody"] == "project-local body"
    assert payload["dupGitManaged"] is False
    assert payload["sharedScope"] == "project"
    assert payload["sharedGitManaged"] is True
    assert payload["personalScope"] == "project-local"
    assert payload["personalGitManaged"] is False


def test_guidance_is_static_and_team_shaped() -> None:
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Prompt guidance reflects the team model" in feature
    assert "DO NOT poll or sleep" in guidance
    assert "teammate_spawn(name, agent, optional kickoff prompt)" in guidance
    assert "task_create(subject, description?, dependsOn?," in guidance
    assert "Peer traffic never reaches your" in guidance
    assert "resident teammate" in source("guidance.ts")
    # Worker protocol covers the five capabilities and mid-turn arrivals.
    for capability in ("send_message", "task_list", "task_claim", "task_submit"):
        assert capability in guidance
    assert 'to="leader"' in guidance
    assert "may arrive mid-turn" in guidance
    payload = run_node(
        f'''\
        import {{ buildTeamLeaderGuidance }} from "{(SRC / "guidance.ts").as_uri()}";
        const first = buildTeamLeaderGuidance("/tmp");
        const second = buildTeamLeaderGuidance("/tmp");
        console.log(JSON.stringify({{
          identical: first === second,
          noLiveState: !(first.includes("run_") || first.includes("@")),
        }}));
        '''
    )
    assert payload["identical"] is True
    assert payload["noLiveState"] is True


def test_follow_up_reports_use_wrapped_marker_format() -> None:
    payload = run_node(
        f'''\
        import {{ formatReports }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const content = formatReports([
          {{ teammate: "security", body: "<b>bold finding</b>" }},
        ]);
        console.log(JSON.stringify({{
          wrapped: content.includes('<agent-message from="security">'),
          escaped: formatReports([{{ teammate: 'a"b', body: "x" }}]).includes('from="a&quot;b"'),
          fullBodyKept: content.includes("<b>bold finding</b>"),
          noRunIds: !content.includes("run_"),
          noFinishedNotice: !content.includes("finished."),
        }}));
        '''
    )
    assert payload["wrapped"] is True
    assert payload["escaped"] is True
    assert payload["fullBodyKept"] is True
    assert payload["noRunIds"] is True
    assert payload["noFinishedNotice"] is True


def test_follow_up_queue_serializes_and_retries_with_backoff() -> None:
    payload = run_node(
        f'''\
        import {{ FollowUpQueue }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const events = [];
        let settled = true;
        const queue = new FollowUpQueue({{
          isIdle: () => settled,
          agentStartTimeoutMs: 80,
          retryBaseDelayMs: 10,
          retryMaxDelayMs: 20,
          maxAttempts: 2,
          dispatch: (reports) => {{ events.push(["dispatch", reports.length]); }},
          onFailure: (message) => {{ events.push(["fail"]); }},
        }});
        queue.enqueue({{ teammate: "a", body: "one", finished: true }});
        await sleep(5);
        queue.onBeforeAgentStart(undefined);
        // No matching prompt was prepared: watchdog fires and retry begins.
        await sleep(150);
        console.log(JSON.stringify({{
          dispatchedTwice: events.filter(([kind]) => kind === "dispatch").length >= 2,
          failuresObserved: events.some(([kind]) => kind === "fail"),
        }}));
        '''
    )
    assert payload["dispatchedTwice"] is True
    assert payload["failuresObserved"] is True


def test_follow_up_queue_batches_by_sender_order() -> None:
    payload = run_node(
        f'''\
        import {{ groupReportsByTeammate }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const groups = groupReportsByTeammate([
          {{ teammate: "b", body: "1" }},
          {{ teammate: "a", body: "2" }},
          {{ teammate: "b", body: "3" }},
        ]);
        console.log(JSON.stringify({{
          order: groups.map((group) => group.teammate).join(","),
          counts: groups.map((group) => group.reports.length).join(","),
        }}));
        '''
    )
    assert payload["order"] == "b,a"
    assert payload["counts"] == "2,1"


def test_console_supports_mouse_wheel_scrolling() -> None:
    ext = source("ui.ts")
    assert "const sgrWheel = /^\\x1b\\[<(\\d+);(\\d+);(\\d+)[Mm]$/" in ext
    assert "(button & 64) !== 0" in ext
    assert "direction === 0" in ext and "direction === 1" in ext


def test_console_has_roster_and_board_pages() -> None:
    ext = source("ui.ts")
    assert '"roster"' in ext and '"board"' in ext
    assert 'Key.tab' in ext
    assert "shutdownFromConsole" in ext
    assert "buildTaskDetail" in ext and "buildTeammateDetail" in ext
    assert "peer mail" in ext


def test_widget_shows_only_working_teammates() -> None:
    ext = source("ui.ts")
    widget = ext[ext.index("export function ensureTeamWidget"):ext.index("export function refreshTeamUI")]
    assert 'ctx.ui.setWidget("teammate", undefined)' in widget
    assert "placement: \"belowEditor\"" in widget
    # Only working or starting teammates appear above the input box.
    assert "for (const teammate of working)" in widget
    assert 'teammate.status === "working" || teammate.status === "starting"' in widget
    assert "fitTeammateRow" in widget
    # Idle and stopped teammates never render in the widget: no dim rows, no markers.
    assert "style.dim(" not in widget
    assert "○" not in widget and "\u25a0" not in widget
    assert "listTeammates()" not in widget

def test_spawn_renders_legacy_started_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Spawning renders one started line per teammate" in feature
    assert 'formatToolEventLabel("started", "", "agent")' in tools
    assert "formatAgentTaskName" in tools
    assert "details: { started: true }" in tools


def test_live_activity_renders_markdown_without_literal_emphasis_markers() -> None:
    payload = run_node(
        f'''\
        import {{ fitTeammateRow, renderActivityMarkdown }} from "{(SRC / "activity.ts").as_uri()}";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const emphasis = renderActivityMarkdown("**Inspecting unused variable in report code**");
        const row = fitTeammateRow("⠼", "security", "**Inspecting unused variable**", 48);
        console.log(JSON.stringify({{
          emphasis,
          emphasisHasMarkers: emphasis.includes("**"),
          rowHasMarkers: row.includes("**"),
          rowIsSingleLine: !row.includes("\\n"),
          rowFitsWidth: visibleWidth(row) <= 47,
        }}));
        '''
    )
    assert payload["emphasis"] == "Inspecting unused variable in report code"
    assert payload["emphasisHasMarkers"] is False
    assert payload["rowHasMarkers"] is False
    assert payload["rowIsSingleLine"] is True
    assert payload["rowFitsWidth"] is True


def test_activity_priority_tool_then_thinking_then_text(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ runningTeammateActivity }} from "{(SRC / "activity.ts").as_uri()}";
        const base = {{ name: "security", agent: "reviewer", spawnId: "s", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }};
        const withTool = runningTeammateActivity({{ ...base, activeTool: "bash: npm test", liveThinking: "**thinking**", liveText: "text" }});
        const withThinking = runningTeammateActivity({{ ...base, liveThinking: "reasoning about auth", liveText: "older text" }});
        const withText = runningTeammateActivity({{ ...base, liveText: "older\\nlatest" }});
        const fallback = runningTeammateActivity(base);
        console.log(JSON.stringify({{
          withTool, withThinking,
          latestLineWins: withText === "latest",
          fallback, fallbackIsWorking: fallback === "Working...",
        }}));
        '''
    )
    assert payload["withTool"] == "bash: npm test"
    assert payload["withThinking"] == "reasoning about auth"
    # The widget shows the LATEST non-empty line of streamed text.
    assert payload["latestLineWins"] is True
    assert payload["fallbackIsWorking"] is True


def test_consolidated_tool_schemas_keep_one_message_primitive() -> None:
    types = source("types.ts")
    tools = source("tools.ts")
    worker = source("worker.ts")
    assert 'export const LEADER_RECIPIENT = "leader"' in types
    message_schema = types[types.index("export const SendMessageParams"):types.index("/** Self-claim")]
    assert "message: Type.String" in message_schema
    assert "subject: Type.String" not in message_schema
    assert "body: Type.String" not in message_schema
    assert "TeammateMessageParams" not in types
    assert "TeammateLeaderMessageParams" not in types
    spawn_schema = types[types.index("export const TeammateSpawnParams"):types.index("/** Shut down")]
    assert "model:" not in spawn_schema and "worktree:" not in spawn_schema and "cwd:" not in spawn_schema
    assert 'name: "send_message"' in tools
    assert 'name: "send_message"' in worker
    assert 'name: "teammate_message"' not in tools + worker
    assert "agent.worktree" in source("team-machine.ts")


def test_rpc_control_stream_protocol_lines() -> None:
    spawner = source("spawner.ts")
    assert '{ type: "prompt", id: randomUUID(), message }' in spawner
    assert '{ type: "steer", message }' in spawner
    assert '"--mode", "rpc"' in spawner
    assert '"--no-session"' in spawner
    # Turn budgets are enforced per wake-up sequence against the baseline.
    assert "baselines.set" in spawner
    assert "turnBudgetExceeded" in spawner
    # Residents never auto-exit after a report: no post-report grace shutdown.
    assert "finishReportedWorker" not in spawner
    assert "POST_REPORT_GRACE_MS" not in spawner


def test_session_cap_and_shutdown_surface() -> None:
    machine = source("team-machine.ts")
    tools = source("tools.ts")
    assert "MAX_SESSION_WORKERS = 8" in machine
    assert "livingTeammates().length >= MAX_SESSION_WORKERS" in machine
    assert "NOTICE_PACE_MS = 2000" in machine
    assert "shutdownTeammate" in tools and "teammate_shutdown" in tools
    assert "pendingShutdowns" in machine
    assert "releaseTasksOf" in machine


def test_silent_teammate_watchdog_contract() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    machine = source("team-machine.ts")
    state = source("state.ts")
    types = source("types.ts")
    tools = source("tools.ts")
    ui = source("ui.ts")
    for phrase in (
        "A silent working teammate raises one stall notice per episode",
        "Activity re-arms the stall watchdog",
        "Prolonged silence is reclaimed safely",
        "last output time",
        "stall notice",
        "normal bounded shutdown path",
    ):
        assert phrase in feature, phrase
    assert "lastOutputAt" in types
    assert "stallNoticeSentAt" in types
    assert "STALL_NOTICE_MS" in machine
    assert "STALL_SHUTDOWN_MS" in machine
    assert "checkStalledTeammates" in machine
    assert "stallSilenceMs" in machine
    assert "sendUpdate" in machine
    assert "stalledMs" in machine and "stalled" in tools
    assert "formatSilenceDuration" in ui
    payload = run_node(
        f'''\
        import {{ stallSilenceMs, formatSilenceDuration, isStallThresholdReached, STALL_NOTICE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        const now = Date.now();
        const teammate = {{ status: "working", lastOutputAt: now - 3_725_000 }};
        console.log(JSON.stringify({{
          silence: stallSilenceMs(teammate, now),
          formatted: formatSilenceDuration(3_725_000),
          thresholdConfigured: STALL_NOTICE_MS > 0,
          reached: isStallThresholdReached(teammate, now, 3_000_000),
          notReached: isStallThresholdReached(teammate, now, 4_000_000),
        }}));
        '''
    )
    assert payload["silence"] == 3_725_000
    assert payload["formatted"] == "1h 2m"
    assert payload["thresholdConfigured"] is True
    assert payload["reached"] is True
    assert payload["notReached"] is False


def test_stall_reclaim_threads_reason_and_warns_on_steer() -> None:
    machine = source("team-machine.ts")
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    # Reclaim goes through the normal bounded shutdown path and names the reason.
    assert "the child is terminated through the normal bounded shutdown path" in feature
    assert "the leader receives the shutdown reason" in feature
    assert "void shutdownTeammate(teammate.name, reason)" in machine
    assert "pendingShutdownReasons.get(name)" in machine
    summary = machine[machine.index("function summarizeShutdown"):machine.index("async function finalizeWorktree")]
    assert "`Reason: ${reason.trim()}.`" in summary
    # A wake prompt restarts the silence clock so long-idle teammates never insta-stall.
    wake = machine[machine.index("export function wakeIdleTeammates"):]
    assert "lastOutputAt: Date.now()" in wake
    assert "stallNoticeSentAt: undefined" in wake
    # Steering a silent teammate reports stalledMs; the tool renders a warning.
    send = machine[machine.index("export function sendLeaderMessage"):]
    assert "stalledMs" in send and "isStallThresholdReached" in send
    assert "stalledMs !== undefined" in tools and "formatSilenceDuration" in tools


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


def test_board_persists_but_runtime_does_not() -> None:
    machine = source("team-machine.ts")
    statefile = source("statefile.ts")
    assert "removeRuntimeDir" in machine
    assert "loadBoard(persisted.tasks)" in machine
    assert 'path.join(getAgentDir(), "tasks")' in statefile
    assert 'path.join(getAgentDir(), "teammate")' in statefile
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "no automatic cleanup deletes persisted boards" in feature
    # cleanupExpiredStateDirs sweeps only the runtime root.
    sweep = statefile[statefile.index("export function cleanupExpiredStateDirs"):]
    assert "tasksRoot()" not in sweep


def test_worktree_capture_failure_returns_structured_error(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ captureWorktreeDiff, createWorktree }} from "{(SRC / "worktree.ts").as_uri()}";
        const outside = createWorktree("{tmp_path.as_uri()[7:]}", "nope");
        console.log(JSON.stringify({{
          createFailsCleanly: "error" in outside,
        }}));
        ''',
    )
    assert payload["createFailsCleanly"] is True


def test_read_receipts_and_legacy_registry_are_gone() -> None:
    all_sources = "".join(source(name) for name in (
        "types.ts", "state.ts", "statefile.ts", "team-machine.ts", "worker.ts", "tools.ts", "ui.ts",
    ))
    for legacy in ("read receipt", "readReceipt", "markMessageRead", "broadcast"):
        assert legacy.lower() not in all_sources.lower(), legacy
    assert "ephemeral" not in all_sources.lower()

def test_idle_without_terminal_report_nudge_exists() -> None:
    machine = source("team-machine.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "An idle teammate with an unfinalized last report nudges the leader" in feature
    assert "export function hasUnfinalizedReport" in machine
    assert "nudgeIfUnfinalized" in machine
    # One nudge per idle transition, keyed by name+spawn incarnation.
    assert "idleNudgesSent" in machine
    # A prompt-less spawn is idle from birth instead of sticking in starting.
    assert 'updateTeammate(input.name, { status: "idle" })' in machine


def test_worker_task_list_includes_roster_tail() -> None:
    worker = source("worker.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "the shared task_list view includes the living roster on both leader and worker sides" in feature
    roster_section = worker[worker.index("registerTaskListTool"):]
    assert "readRoster(binding.rosterFile)" in roster_section
    assert "Roster:" in roster_section


def test_terminal_status_discipline_is_documented_for_workers() -> None:
    reviewer = (PACKAGE / "agents" / "reviewer.md").read_text(encoding="utf-8")
    guidance = source("guidance.ts")
    assert 'MUST\ncarry status="completed"' in reviewer
    assert "MUST carry" in guidance and 'status="completed"' in guidance

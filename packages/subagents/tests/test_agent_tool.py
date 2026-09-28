"""The `agent` tool surface registered by @fradser/pi-subagents.

Contract: features/tool-surface.feature

The spawn and terminate functions are injected, so these scenarios assert the
tool's *decisions* — routing, validation, handle addressing, and what it reports —
without starting a real child process. Everything a real spawn would prove is
about the spawner, which has its own suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_node

EXTENSION = (PACKAGE / "extension.ts").as_uri()
BARREL = (PACKAGE / "index.ts").as_uri()
MANIFEST = PACKAGE / "package.json"

# A fake child process: records what it was asked to do and reports a pid.
PREAMBLE = """
const spawned = [];
const failedOnce = new Set();
const terminated = [];
const delivered = [];
const fakeSpawn = (options) => {
  // Fails once per name, so a retry can distinguish "the name was still held"
  // from "the child failed again".
  if (options.workerName === "unlucky" && !failedOnce.has(options.workerName)) {
    failedOnce.add(options.workerName);
    return { error: "child refused to start" };
  }
  spawned.push(options);
  return { pid: 4242 };
};
const fakeTerminate = async (name) => {
  terminated.push(name);
  return { outcome: name === "ghost" ? "missing" : "closed" };
};
const fakeDeliver = (name, message) => { delivered.push({ name, message }); return true; };
const tools = new Map();
const pi = { registerTool: (t) => tools.set(t.name, t), on() {}, events: { emit() {} } };
piSubagentsExtension(pi);
const agent = tools.get("agent");
const call = (params) => executeAgentAction(params, {
  cwd: process.cwd(),
  spawn: fakeSpawn,
  terminate: fakeTerminate,
  deliver: fakeDeliver,
}).then((r) => ({ ...r, text: r.content[0].text }));
"""


def run(script: str) -> dict[str, object]:
    return run_node(
        f"""\
        import piSubagentsExtension from {json.dumps(EXTENSION)};
        import * as roster from {json.dumps(BARREL)};
        import {{ executeAgentAction, setAgentHost, resolveAgentHost }} from {json.dumps(BARREL)};
        {PREAMBLE}
        roster.resetRoster();
        {script}
        """
    )


# ── The extension entry, not the barrel ──


def test_the_manifest_declares_a_loadable_extension_entry() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["pi"]["extensions"] == ["./extension.ts"]
    assert "extension.ts" in manifest["files"]
    assert "export default" in (PACKAGE / "extension.ts").read_text(encoding="utf-8")
    # The barrel must stay a barrel, or the manifest would stop proving which
    # file Pi loads.
    assert "export default" not in (PACKAGE / "index.ts").read_text(encoding="utf-8")


def test_it_registers_exactly_one_tool_and_nothing_else() -> None:
    result = run(
        """
        const names = [...tools.keys()];
        console.log(JSON.stringify({ names, count: tools.size }));
        """
    )
    assert result["count"] == 1
    assert result["names"] == ["agent"]


# ── Four actions, and no participant or task vocabulary ──


def test_the_action_set_is_exactly_four() -> None:
    result = run(
        """
        console.log(JSON.stringify({ actions: agent.parameters.properties.action.enum }));
        """
    )
    assert result["actions"] == ["start", "inspect", "list", "stop"]


def test_the_schema_exposes_no_task_or_participant_field() -> None:
    """No assignee, no owner, no subject, no verify, no resources. Spawning does
    not create a task, so there is nothing for those to attach to."""
    result = run(
        """
        const keys = Object.keys(agent.parameters.properties);
        console.log(JSON.stringify({
          keys,
          forbidden: keys.filter((k) => /assign|owner|subject|verify|resource|depend|supersed|task/i.test(k)),
        }));
        """
    )
    assert result["forbidden"] == []
    for banned in ("assign", "assignee", "owner", "subject", "verify", "resources", "dependsOn", "supersedes"):
        assert banned not in result["keys"]


def test_delegate_and_start_are_one_action() -> None:
    """The merge, asserted as behaviour: a prompt and no prompt are the same
    action differing in one optional field, not two named spawn paths."""
    result = run(
        """
        const withPrompt = await call({ action: "start", name: "a1", prompt: "do the thing" });
        const without = await call({ action: "start", name: "a2" });
        console.log(JSON.stringify({
          prompted: withPrompt.details.prompted,
          idle: without.details.prompted,
          bothSpawned: spawned.length,
          legacyRefused: (await call({ action: "delegate", name: "a3", prompt: "x" })).details.ok,
        }));
        """
    )
    assert result["prompted"] is True
    assert result["idle"] is False
    assert result["bothSpawned"] == 2
    # `delegate` is gone, and its absence is reported rather than ignored.
    assert result["legacyRefused"] is False


# ── fork, with and without a prompt ──


def test_fork_is_legal_with_and_without_a_prompt() -> None:
    result = run(
        """
        const forkedIdle = await call({ action: "start", name: "f1", fork: true });
        const forkedBusy = await call({ action: "start", name: "f2", prompt: "go", fork: true });
        console.log(JSON.stringify({
          idleOk: forkedIdle.details.ok,
          idleContext: forkedIdle.details.ok,
          busyOk: forkedBusy.details.ok,
          names: spawned.map((s) => s.workerName),
        }));
        """
    )
    assert result["idleOk"] is True
    assert result["busyOk"] is True
    assert result["names"] == ["f1", "f2"]


# ── Handles address one incarnation ──


def test_inspect_and_stop_require_an_exact_handle() -> None:
    result = run(
        """
        const started = await call({ action: "start", name: "alpha" });
        const session = started.details.session;
        const bare = await call({ action: "inspect", name: "alpha" });
        const good = await call({ action: "inspect", session });
        const stopped = await call({ action: "stop", session });
        console.log(JSON.stringify({
          session: session.startsWith("session:alpha:"),
          bareRefused: bare.details.ok === false,
          bareNamesSession: bare.text.includes(session),
          inspectOk: good.details.ok,
          stopped: stopped.details.outcome,
          evidencePresent: stopped.text.length > 0,
          evidenceWarns: JSON.stringify(stopped.details).includes("not evidence"),
        }));
        """
    )
    assert result["session"] is True
    assert result["bareRefused"] is True
    # Refusing a bare name has to say what to pass instead.
    assert result["bareNamesSession"] is True
    assert result["inspectOk"] is True
    assert result["stopped"] == "stopped"
    assert result["evidenceWarns"] is True


def test_a_retired_handle_never_resolves_to_its_replacement() -> None:
    result = run(
        """
        const first = await call({ action: "start", name: "alpha" });
        const stale = first.details.session;
        // A same-name start is refused while the incumbent lives, and the refusal
        // has to name the two ways out.
        const duplicate = await call({ action: "start", name: "alpha" });
        const duplicateSpawned = spawned.length;
        // Retire the incumbent, then reuse the name.
        const stopped = await call({ action: "stop", session: stale });
        const second = await call({ action: "start", name: "alpha" });
        const staleInspect = await call({ action: "inspect", session: stale });
        const liveInspect = await call({ action: "inspect", session: second.details.session });
        console.log(JSON.stringify({
          duplicateRefused: duplicate.details.ok === false,
          guides: duplicate.text.includes("action=inspect") && duplicate.text.includes("action=stop"),
          noProcessLeaked: duplicateSpawned === 1,
          stopped: stopped.details.outcome,
          reused: second.details.ok === true,
          distinct: second.details.session !== stale,
          staleResolved: staleInspect.details.ok === true,
          stalePointsForward: staleInspect.text.includes(second.details.session),
          liveOk: liveInspect.details.ok === true,
        }));
        """
    )
    assert result["duplicateRefused"] is True
    assert result["guides"] is True
    # The duplicate is refused *before* a process is created, so the refusal
    # cannot leave a running child with no roster entry to stop it by.
    assert result["noProcessLeaked"] is True
    assert result["stopped"] == "stopped"
    assert result["reused"] is True
    assert result["distinct"] is True
    # A retired handle must not resolve, and must point at the live one.
    assert result["staleResolved"] is False
    assert result["stalePointsForward"] is True
    assert result["liveOk"] is True


def test_list_enumerates_every_child_with_its_handle() -> None:
    result = run(
        """
        await call({ action: "start", name: "alpha" });
        await call({ action: "start", name: "beta", prompt: "go" });
        const listed = await call({ action: "list" });
        console.log(JSON.stringify({
          count: listed.details.count,
          rows: listed.text.split("\\n").length,
          hasHandles: listed.text.includes("session:alpha:") && listed.text.includes("session:beta:"),
        }));
        """
    )
    assert result["count"] == 2
    assert result["rows"] == 2
    assert result["hasHandles"] is True


# ── Validation ──


def test_a_name_alone_is_enough_and_the_grant_is_reported() -> None:
    """`start` with only a name is the idle-resident case, so it must not demand a
    role or a prompt. What it must do is report the grant it actually applied,
    because a caller that assumed file access it did not get is the failure this
    replaces."""
    result = run(
        """
        const bare = await call({ action: "start", name: "resident" });
        const withTools = await call({ action: "start", name: "reader", tools: ["read", "grep"] });
        const halfRole = await call({ action: "start", name: "half", description: "only one half" });
        const full = await call({ action: "start", name: "full", description: "reads a file", role_prompt: "Read it." });
        console.log(JSON.stringify({
          bareOk: bare.details.ok,
          bareGrant: bare.details.grant,
          bareIdle: bare.details.prompted,
          bareSaysNoRole: bare.text.includes("no standing") || bare.text.includes("ROLE · none"),
          toolsGrant: withTools.details.grant,
          halfOk: halfRole.details.ok,
          halfExplains: halfRole.text.includes("both"),
          fullOk: full.details.ok,
        }));
        """
    )
    assert result["bareOk"] is True
    assert result["bareGrant"] == []
    assert result["bareIdle"] is False
    assert result["bareSaysNoRole"] is True
    assert result["toolsGrant"] == ["read", "grep"]
    # A half-specified role is the case worth refusing: the missing half would
    # otherwise produce a child that silently has no instructions.
    assert result["halfOk"] is False
    assert result["halfExplains"] is True
    assert result["fullOk"] is True


def test_an_invalid_name_is_refused_with_the_rule() -> None:
    result = run(
        """
        const bad = await call({ action: "start", name: "../escape" });
        console.log(JSON.stringify({ ok: bad.details.ok === false, rule: bad.text }));
        """
    )
    assert result["ok"] is True
    assert "letters" in result["rule"]


def test_a_failed_spawn_is_reported_not_swallowed() -> None:
    result = run(
        """
        const failed = await call({ action: "start", name: "unlucky", description: "d", role_prompt: "p" });
        const listed = await call({ action: "list" });
        // Counted before the retry, because the whole claim is about the state
        // the failure left behind.
        const livingAfterFailure = (await call({ action: "list" })).details.agents
          .filter((a) => a.status !== "stopped").length;
        const retry = await call({ action: "start", name: "unlucky" });
        console.log(JSON.stringify({
          reportedFailure: failed.details.ok === false,
          namesTheName: failed.text.includes("unlucky"),
          livingAfterFailure,
          listed: listed.details.count,
          // The name must be reusable: a name held by a child that never started
          // is the worst outcome, because it looks taken and nothing is running.
          retryOk: retry.details.ok === true,
          retryNotDuplicate: retry.details.ok === true
            ? (await call({ action: "inspect", session: retry.details.session })).details.ok === true
            : false,
        }));
        """
    )
    assert result["reportedFailure"] is True
    assert result["namesTheName"] is True
    # The entry exists but is stopped, so it holds nothing and releases the name.
    assert result["livingAfterFailure"] == 0
    assert result["retryOk"] is True
    # The retry must produce a usable handle, not merely a non-error: that is
    # what proves the reservation was released rather than left in place.
    assert result["retryNotDuplicate"] is True


# ── The coordinator seam ──


def test_a_published_host_is_preferred_over_the_raw_spawner() -> None:
    result = run(
        """
        setAgentHost({
          start: (request) => ({ ok: true, session: `host:${request.name}` }),
          stop: async () => ({ ok: true }),
        });
        const started = await call({ action: "start", name: "alpha", prompt: "go" });
        const duringHost = spawned.length;
        const present = resolveAgentHost();
        setAgentHost(undefined);
        const standalone = await call({ action: "start", name: "beta" });
        console.log(JSON.stringify({
          hostUsed: started.details.session === "host:alpha",
          rawSpawnerUntouchedWhileHosted: duringHost,
          hostPresent: Boolean(present),
          rawSpawnerUsedAfterRelease: spawned.length - duringHost,
          afterRelease: standalone.details.standalone === true,
        }));
        """
    )
    assert result["hostUsed"] is True
    assert result["rawSpawnerUntouchedWhileHosted"] == 0
    assert result["hostPresent"] is True
    # Releasing the host must fall back, or a reload would leave a dead reference.
    assert result["afterRelease"] is True
    assert result["rawSpawnerUsedAfterRelease"] == 1


def test_the_spawner_is_never_given_a_second_participant() -> None:
    """The tool passes a name; the roster records the caller. Nothing in the
    surface can direct an assignment at somebody else."""
    result = run(
        """
        const spoofed = await call({
          action: "start", name: "alpha", prompt: "go",
          worker: "someone-else", spawnId: "forged", owner: "someone-else",
        });
        console.log(JSON.stringify({
          refused: spoofed.details.ok === false,
          name: spoofed.details.name,
        }));
        """
    )
    # Unknown fields are refused outright rather than silently dropped, because a
    # silently dropped field teaches the model the parameter exists.
    assert result["refused"] is True

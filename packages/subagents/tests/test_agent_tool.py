"""The child-execution surface behind @fradser/pi-subagents.

Contract: features/tool-surface.feature,
packages/subagents/features/child-role-delivery.feature

`executeChildIntent` is the one implementation the five `agent_*` intent tools
share, so these scenarios drive it directly with the spawn and terminate
functions injected: they assert the layer's *decisions* — routing, validation,
handle addressing, and what it reports — without starting a real child process.
Everything a real spawn would prove is about the spawner, which has its own
suite. The combined `agent` tool is retired (ADR-0008);
`test_it_registers_only_the_five_intent_tools` owns that claim at the
registered-surface seam.
"""

from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, run_isolated_node as run_node



EXTENSION = (PACKAGE / "index.ts").as_uri()
BARREL = (PACKAGE / "index.ts").as_uri()
SPAWNER = (PACKAGE / "src" / "spawner.ts").as_uri()
MANIFEST = PACKAGE / "package.json"

# A fake child process: records what it was asked to do and reports a pid.
PREAMBLE = """
const spawned = [];
const failedOnce = new Set();
const terminated = [];
const parentMessages = [];
let parentDeliveryFailure;
const fakeSpawn = (options) => {
  // Fails once per name, so a retry can distinguish "the name was still held"
  // from "the child failed again".
  if (options.agentName === "unlucky" && !failedOnce.has(options.agentName)) {
    failedOnce.add(options.agentName);
    return { error: "child refused to start" };
  }
  spawned.push(options);
  return { pid: 4242 };
};
const fakeTerminate = async (name) => {
  terminated.push(name);
  if (name === "ghost") return { outcome: "missing" };
  if (name === "wobbly") return { outcome: "unconfirmed" };
  return { outcome: "closed" };
};
const tools = new Map();
const pi = { registerTool: (t) => tools.set(t.name, t), on() {}, events: { emit() {} } };
piSubagentsExtension(pi);
// Agent definition discovery is cwd-relative, so a scenario about a persisted
// definition needs its own workspace rather than the package directory.
const WORKSPACE = process.env.PI_TEST_CWD || process.cwd();
const call = (params) => executeChildIntent(params, {
  cwd: WORKSPACE,
  spawn: fakeSpawn,
  terminate: fakeTerminate,
  contextMessages: () => [],
  prompt: async () => true,
  steer: () => true,
  deliverParentMessage: (notice) => {
    parentMessages.push(notice);
    if (parentDeliveryFailure === "throw") throw new Error("\x1b[31m" + "diagnostic ".repeat(400));
    if (parentDeliveryFailure === "reject") return Promise.reject(new Error("late delivery rejection"));
  },
}).then((r) => ({ ...r, text: r.content[0].text }));
"""


def run(script: str, workspace: Path | None = None) -> dict[str, object]:
    return run_node(
        f"""\
        import piSubagentsExtension from {json.dumps(EXTENSION)};
        import * as roster from {json.dumps(BARREL)};
        import {{ executeChildIntent, setAgentHost, resolveAgentHost, formatParentMessageNotice }} from {json.dumps(BARREL)};
        {PREAMBLE}
        roster.resetRoster();
        {script}
        """,
        env_overrides={"PI_TEST_CWD": str(workspace)} if workspace else None,
    )


# ── The extension entry, not the barrel ──


def test_the_manifest_declares_a_loadable_extension_entry() -> None:
    """One file is both the library surface and the extension Pi loads.

    That is the repository's package-root entry convention, pinned in
    `features/package-root-entry.feature`, and it is why the row renderer is
    reachable from the barrel at all. Splitting the two would fix that reach and
    break the convention every package in this repository follows, so the reach is
    bounded instead: `src/rows.ts` has exactly one importer, the entry body.
    `test_session_result.py` asserts that against real module resolution.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert "index.ts" in manifest["files"]
    assert "export { default }" in (PACKAGE / "index.ts").read_text(encoding="utf-8")


def test_it_registers_only_the_five_intent_tools() -> None:
    result = run(
        """
        const names = [...tools.keys()];
        console.log(JSON.stringify({ names, count: tools.size }));
        """
    )
    # ADR-0008 retired the combined `agent` tool, and its selection is still
    # scrubbed, so a selection recorded before the retirement cannot revive it.
    assert result["count"] == 5
    assert result["names"] == ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]
    assert "agent" not in result["names"]


# ── Resident input completes the process lifecycle without coordination ──


# ── fork, with and without a prompt ──


def test_fork_is_legal_with_and_without_a_prompt() -> None:
    result = run(
        """
        const forkedIdle = await call({ operation: "start", name: "f1", fork: true });
        const forkedBusy = await call({ operation: "start", name: "f2", prompt: "go", fork: true });
        console.log(JSON.stringify({
          idleOk: forkedIdle.details.ok,
          idleContext: forkedIdle.details.ok,
          busyOk: forkedBusy.details.ok,
          names: spawned.map((s) => s.agentName),
        }));
        """
    )
    assert result["idleOk"] is True
    assert result["busyOk"] is True
    assert result["names"] == ["f1", "f2"]


# ── Handles address one incarnation ──


def test_a_retired_handle_never_resolves_to_its_replacement() -> None:
    result = run(
        """
        const first = await call({ operation: "start", name: "alpha" });
        const stale = first.details.session;
        // A same-name start is refused while the incumbent lives, and the refusal
        // has to name the two ways out.
        const duplicate = await call({ operation: "start", name: "alpha" });
        const duplicateSpawned = spawned.length;
        // Retire the incumbent, then reuse the name.
        const stopped = await call({ operation: "stop", session: stale });
        const second = await call({ operation: "start", name: "alpha" });
        const staleInspect = await call({ operation: "inspect", session: stale });
        const liveInspect = await call({ operation: "inspect", session: second.details.session });
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
    # The predecessor was replaced on the roster, not merely stopped: it must
    # not resolve to the successor, and the diagnostic points at the live one.
    assert result["staleResolved"] is False
    assert result["stalePointsForward"] is True
    assert result["liveOk"] is True


def test_list_enumerates_every_child_with_its_handle() -> None:
    result = run(
        """
        await call({ operation: "start", name: "alpha" });
        await call({ operation: "start", name: "beta", prompt: "go" });
        const listed = await call({ operation: "list" });
        console.log(JSON.stringify({
          count: listed.details.count,
          rows: listed.text.split("\\n").length,
          hasHandles: listed.text.includes("session:alpha:") && listed.text.includes("session:beta:"),
        }));
        """
    )
    assert result["count"] == 2
    # agent-output.feature adds the aggregate-budget preview and page receipt.
    assert result["rows"] == 7
    assert result["hasHandles"] is True


# ── Validation ──


def test_a_name_alone_is_enough_and_the_grant_is_reported() -> None:
    """`start` with only a name is the idle-resident case, so it must not demand a
    role or a prompt. What it must do is report the grant it actually applied,
    because a caller that assumed file access it did not get is the failure this
    replaces."""
    result = run(
        """
        const bare = await call({ operation: "start", name: "resident" });
        const withTools = await call({ operation: "start", name: "reader", tools: ["read", "grep"] });
        const described = await call({ operation: "start", name: "described", description: "reads one file" });
        const instructed = await call({ operation: "start", name: "instructed", role_prompt: "Read exactly one file." });
        const full = await call({ operation: "start", name: "full", description: "reads a file", role_prompt: "Read it." });
        console.log(JSON.stringify({
          bareOk: bare.details.ok,
          bareGrant: bare.details.grant,
          bareIdle: bare.details.prompted,
          bareSaysNoRole: bare.text.includes("no standing") || bare.text.includes("role · none"),
          toolsGrant: withTools.details.grant,
          describedOk: described.details.ok,
          describedRole: described.details.role,
          describedSaysNoInstructions: described.text.includes("no standing instructions"),
          instructedOk: instructed.details.ok,
          instructedPrompt: roster.resolveAgent("instructed", WORKSPACE)?.prompt,
          fullOk: full.details.ok,
          fullRole: full.details.role,
          spawns: spawned.length,
        }));
        """
    )
    assert result["bareOk"] is True
    assert result["bareGrant"] == []
    assert result["bareIdle"] is False
    assert result["bareSaysNoRole"] is True
    assert result["toolsGrant"] == ["read", "grep"]
    # Half a role is legal. A description is a stated purpose and a role_prompt is
    # its instructions; a caller holding only one is not holding a broken role, and
    # refusing it left no legal way to say what the child is for. What a half role
    # must never do is pass silently: the receipt says the child has no standing
    # instructions.
    assert result["describedOk"] is True
    assert result["describedRole"] == "reads one file"
    assert result["describedSaysNoInstructions"] is True
    assert result["instructedOk"] is True
    assert result["instructedPrompt"] == "Read exactly one file."
    assert result["fullOk"] is True
    assert result["fullRole"] == "reads a file"
    # Five legal starts: there is nothing left to refuse.
    assert result["spawns"] == 5


def test_a_description_beside_a_resolved_definition_is_not_a_half_role(tmp_path: Path) -> None:
    """The definition already supplies the role, so a description beside it is a
    redundant note rather than a broken role. Refusing it would make a caller
    invent a role_prompt for a child that already has one."""
    agents = tmp_path / ".pi" / "agents" / "role-beside"
    agents.mkdir(parents=True)
    (agents / "agent.md").write_text(
        "---\nname: role-beside\ndescription: reads the file\ntools: read\n---\n\nBESIDE instructions\n",
        encoding="utf-8",
    )
    result = run(
        """
        const started = await call({ operation: "start", name: "role-beside", description: "a redundant note" });
        console.log(JSON.stringify({
          ok: started.details.ok,
          role: started.details.role,
          saysWon: started.text.includes("not applied"),
        }));
        """,
        workspace=tmp_path,
    )
    assert result["ok"] is True
    assert result["role"] == "reads the file"
    assert result["saysWon"] is True


def test_a_fresh_inline_role_replaces_a_session_role_of_the_same_name() -> None:
    """A session role is this process's own residue from an earlier spawn, not a
    user-owned definition. Letting it win hands the child the previous call's
    standing instructions and reports nothing about the swap."""
    result = run(
        """
        const first = await call({ operation: "start", name: "role-shadow", description: "first role", role_prompt: "FIRST instructions" });
        await call({ operation: "stop", session: first.details.session });
        const second = await call({ operation: "start", name: "role-shadow", description: "second role", role_prompt: "SECOND instructions" });
        const registered = roster.resolveAgent("role-shadow", WORKSPACE);
        console.log(JSON.stringify({
          ok: second.details.ok,
          prompt: registered?.prompt,
          description: registered?.description,
          role: second.details.role,
        }));
        """
    )
    assert result["ok"] is True
    assert result["prompt"] == "SECOND instructions"
    assert result["description"] == "second role"
    assert result["role"] == "second role"


def test_a_persisted_definition_wins_and_the_receipt_says_so(tmp_path: Path) -> None:
    """Filesystem scopes are user-owned and outrank an inline role. That is the
    right precedence, but a caller whose role was dropped must be told, or the
    child runs instructions its author never wrote."""
    agents = tmp_path / ".pi" / "agents" / "role-persisted"
    agents.mkdir(parents=True)
    (agents / "agent.md").write_text(
        "---\nname: role-persisted\ndescription: reads the file\ntools: read\n---\n\nPERSISTED instructions\n",
        encoding="utf-8",
    )
    result = run(
        """
        const started = await call({
          operation: "start", name: "role-persisted",
          description: "inline role", role_prompt: "INLINE instructions",
        });
        const registered = roster.resolveAgent("role-persisted", WORKSPACE);
        console.log(JSON.stringify({
          ok: started.details.ok,
          prompt: registered?.prompt,
          role: started.details.role,
          saysDropped: started.text.includes("not applied"),
        }));
        """,
        workspace=tmp_path,
    )
    assert result["ok"] is True
    assert result["prompt"] == "PERSISTED instructions"
    assert result["role"] == "reads the file"
    assert result["saysDropped"] is True


def test_a_roles_own_grant_and_model_reach_the_child() -> None:
    """A definition's `tools:` and `model:` are the contract its author wrote.
    Reporting `coordination only` for a role that declares read and bash is a
    receipt about a child that was never started."""
    result = run(
        """
        roster.registerSessionAgent({
          name: "role-grant", description: "reads and edits",
          prompt: "ROLE instructions", tools: ["read", "bash"], model: "anthropic/claude-opus-4",
        });
        const started = await call({ operation: "start", name: "role-grant", prompt: "do the thing" });
        const listed = (await call({ operation: "list" })).details.sessions[0];
        console.log(JSON.stringify({
          ok: started.details.ok,
          grant: started.details.grant,
          grantLine: started.text.split("\\n").find((line) => line.startsWith("tools ·")),
          spawnTools: spawned[0].tools,
          spawnModel: spawned[0].model,
          rosterTools: listed.tools,
        }));
        """
    )
    assert result["ok"] is True
    assert result["grant"] == ["read", "bash"]
    assert result["grantLine"] == "tools · read, bash"
    assert result["spawnTools"] == ["read", "bash"]
    assert result["spawnModel"] == "anthropic/claude-opus-4"
    assert result["rosterTools"] == ["read", "bash"]


def test_a_tool_id_a_bare_child_cannot_have_is_refused() -> None:
    """The child's `--tools` filter drops an id it cannot register, so a receipt
    naming one promises a grant the child does not have. Refusing before the
    claim is what keeps the refusal clean: no process, no held name."""
    result = run(
        """
        const refused = await call({ operation: "start", name: "role-unknown", prompt: "go", tools: ["read", "git_commit"] });
        const listed = await call({ operation: "list" });
        console.log(JSON.stringify({
          ok: refused.details.ok === false,
          namesIt: refused.text.includes("git_commit"),
          spawns: spawned.length,
          living: listed.details.sessions.filter((a) => a.status !== "stopped").length,
        }));
        """
    )
    assert result["ok"] is True
    assert result["namesIt"] is True
    assert result["spawns"] == 0
    assert result["living"] == 0


def test_agent_message_is_an_explicit_standalone_capability_with_bounded_delivery() -> None:
    result = run(
        """
        const absent = await call({ operation: "start", name: "without-message", prompt: "work", tools: ["read"] });
        const started = await call({ operation: "start", name: "messenger", prompt: "work", tools: ["read", "agent_message"] });
        const options = spawned.find((entry) => entry.agentName === "messenger");
        if (started.details.ok) roster.updateAgent("messenger", { status: "working", sequenceEnded: false });
        const emit = (toolCallId, text, sequence) => options?.onParentMessage?.({ toolCallId, text }, sequence);
        for (let i = 0; i < 32; i += 1) emit(`call-${i}`, "x".repeat(2048), i + 1);
        emit("too-many", "overflow", 33);
        const beforeNext = parentMessages.length;
        const countQuotaError = roster.getAgent("messenger")?.error ?? "";
        const countQuotaStatus = roster.getAgent("messenger")?.status;
        const aggregate = await call({ operation: "start", name: "aggregate-messenger", prompt: "work", tools: ["agent_message"] });
        const aggregateOptions = spawned.find((entry) => entry.agentName === "aggregate-messenger");
        if (aggregate.details.ok) roster.updateAgent("aggregate-messenger", { status: "working", sequenceEnded: false });
        for (let i = 0; i < 16; i += 1) aggregateOptions?.onParentMessage?.({ toolCallId: `aggregate-${i}`, text: "y".repeat(4096) }, i + 1);
        aggregateOptions?.onParentMessage?.({ toolCallId: "aggregate-overflow", text: "z" }, 17);
        const aggregateQuotaError = roster.getAgent("aggregate-messenger")?.error ?? "";
        const aggregateQuotaStatus = roster.getAgent("aggregate-messenger")?.status;
        const beforeEnded = parentMessages.length;
        if (started.details.ok) roster.updateAgent("messenger", { status: "idle", sequenceEnded: true });
        emit("late", "late", 34);
        const afterEnded = parentMessages.length;
        const sent = started.details.ok ? await call({ operation: "input", delivery: "next", session: started.details.session, prompt: "next" }) : { details: { ok: false } };
        const nextOptions = spawned.find((entry) => entry.agentName === "messenger");
        if (sent.details.ok) roster.updateAgent("messenger", { status: "working", sequenceEnded: false, inputId: "next-input" });
        nextOptions?.onParentMessage?.({ toolCallId: "next", text: "fresh input" }, 35);
        console.log(JSON.stringify({
          absentCaps: spawned.find((entry) => entry.agentName === "without-message")?.capabilityTools,
          absentExtensions: spawned.find((entry) => entry.agentName === "without-message")?.extensions,
          presentCaps: options?.capabilityTools ?? null,
          presentExtensions: options?.extensions ?? null,
          absentOk: absent.details.ok,
          startedOk: started.details.ok,
          aggregateOk: aggregate.details.ok,
          sentOk: sent.details.ok,
          countQuotaError,
          countQuotaStatus,
          aggregateQuotaError,
          aggregateQuotaStatus,
          firstInputCount: beforeNext,
          endedIgnored: afterEnded === beforeEnded,
          total: parentMessages.length,
          bytes: parentMessages.slice(0, beforeNext).reduce((sum, notice) => sum + Buffer.byteLength(notice.text, "utf8"), 0),
          attributions: parentMessages.map((notice) => ({ session: notice.session, inputId: notice.inputId, sequence: notice.sequence })),
        }));
        """
    )
    assert result["absentCaps"] == []
    assert not any(str(path).endswith("parent-message-extension.ts") for path in result["absentExtensions"])
    assert result["presentCaps"] == ["agent_message"]
    assert any(str(path).endswith("parent-message-extension.ts") for path in result["presentExtensions"])
    assert result["absentOk"] is True and result["startedOk"] is True and result["sentOk"] is True
    assert result["aggregateOk"] is True
    assert "32" in result["countQuotaError"]
    assert "64 KiB" in result["aggregateQuotaError"]
    assert result["countQuotaStatus"] == "working"
    assert result["aggregateQuotaStatus"] == "working"
    assert result["firstInputCount"] == 32
    assert result["endedIgnored"] is True
    assert result["total"] == 49
    assert result["bytes"] == 32 * 2048
    messenger_session = result["attributions"][0]["session"]
    assert [item["sequence"] for item in result["attributions"] if item["session"] == messenger_session] == list(range(1, 34))
    assert len([item for item in result["attributions"] if item["session"] != messenger_session]) == 16


def test_parent_message_sender_failures_are_bounded_and_do_not_cross_input_boundaries() -> None:
    result = run(
        """
        const started = await call({ operation: "start", name: "diagnostics", prompt: "work", tools: ["agent_message"] });
        const options = spawned.find((entry) => entry.agentName === "diagnostics");
        parentDeliveryFailure = "throw";
        options.onParentMessage({ toolCallId: "throw", text: "first" }, 1);
        const thrown = roster.getAgent("diagnostics")?.error ?? "";
        parentDeliveryFailure = "reject";
        roster.updateAgent("diagnostics", { status: "working", sequenceEnded: false, inputId: "first-input" });
        options.onParentMessage({ toolCallId: "reject", text: "second" }, 2);
        roster.updateAgent("diagnostics", { status: "working", sequenceEnded: false, inputId: "second-input" });
        // The next input is already accepted, but has not emitted a new parent
        // message yet. A late rejection from the prior input must not overwrite
        // its diagnostic owner.
        roster.updateAgent("diagnostics", { error: "successor-owned" });
        parentDeliveryFailure = undefined;
        await new Promise((resolve) => setImmediate(resolve));
        console.log(JSON.stringify({
          ok: started.details.ok,
          bounded: thrown.length <= 1024 && thrown.includes("diagnostic"),
          stripped: !thrown.includes("\\x1b"),
          sameOwner: roster.getAgent("diagnostics")?.error === "successor-owned",
          inputs: parentMessages.map((notice) => notice.inputId),
        }));
        """
    )
    assert result["ok"] is True
    assert result["bounded"] is True and result["stripped"] is True
    assert result["sameOwner"] is True
    assert result["inputs"] == [None, "first-input"]


def test_parent_message_callback_bounds_untrusted_tool_call_ids_before_dedupe() -> None:
    result = run(
        """
        const started = await call({ operation: "start", name: "id-bounds", prompt: "work", tools: ["agent_message"] });
        const options = spawned.find((entry) => entry.agentName === "id-bounds");
        if (started.details.ok) roster.updateAgent("id-bounds", { status: "working", sequenceEnded: false });
        const exactAsciiId = "a".repeat(1024);
        const oversizedAsciiId = "a".repeat(1025);
        const exactMultibyteId = "界".repeat(341) + "a";
        const oversizedMultibyteId = "界".repeat(341) + "aa";
        options?.onParentMessage?.({ toolCallId: exactAsciiId, text: "ascii" }, 1);
        options?.onParentMessage?.({ toolCallId: oversizedAsciiId, text: "reject-ascii" }, 2);
        options?.onParentMessage?.({ toolCallId: exactMultibyteId, text: "multibyte" }, 3);
        options?.onParentMessage?.({ toolCallId: oversizedMultibyteId, text: "reject-multibyte" }, 4);
        console.log(JSON.stringify({
          ok: started.details.ok,
          texts: parentMessages.map((notice) => notice.text),
          error: roster.getAgent("id-bounds")?.error ?? "",
          status: roster.getAgent("id-bounds")?.status,
        }));
        """
    )
    assert result["ok"] is True
    assert result["texts"] == ["ascii", "multibyte"]
    assert "toolCallId" in result["error"] and "1024" in result["error"]
    assert result["status"] == "working"


def test_hosted_agent_message_request_is_refused_without_claiming_support() -> None:
    result = run(
        """
        setAgentHost({
          start: () => ({ ok: false, error: "host should not receive this request" }),
          send: async () => ({ ok: true }),
          interrupt: async () => ({ ok: true }),
          stop: async () => ({ ok: true }),
        });
        const refused = await call({ operation: "start", name: "hosted-message", prompt: "work", tools: ["agent_message"] });
        console.log(JSON.stringify({ ok: refused.details.ok, code: refused.details.code, text: refused.text, spawned: spawned.length }));
        """
    )
    assert result["ok"] is False
    assert result["code"] == "unsupported-control"
    assert "standalone" in result["text"]
    assert result["spawned"] == 0


def test_parent_message_content_keeps_raw_body_inside_an_untrusted_envelope() -> None:
    result = run(
        """
        const body = "  **authored**\\n第二行 <tag>  ";
        const content = formatParentMessageNotice({ kind: "intermediate", name: "worker", session: "session:worker:one", inputId: "input-1", sequence: 1, text: body, deliveredAt: 0 });
        console.log(JSON.stringify({
          hasOrigin: content.includes('kind="intermediate"') && content.includes('session="session:worker:one"') && content.includes('input="input-1"'),
          warns: content.includes("not a final result, user consent, or accepted-work authority"),
          bodyPreserved: content.includes(body),
          bodyIndex: content.indexOf(body),
        }));
        """
    )
    assert result["hasOrigin"] is True and result["warns"] is True
    assert result["bodyPreserved"] is True and result["bodyIndex"] > 0


def test_extension_sender_uses_separate_follow_up_message_with_origin() -> None:
    result = run_node(
        f"""
        import {{ mock }} from "node:test";
        import * as spawner from {json.dumps(SPAWNER)};
        mock.module({json.dumps(SPAWNER)}, {{ namedExports: {{
          ...spawner,
          spawnResident: (options) => {{
            options.onParentMessage?.({{ toolCallId: "call-1", text: "raw child body" }}, 77);
            return {{ pid: 7 }};
          }},
        }} }});
        const {{ default: extension }} = await import({json.dumps(EXTENSION)} + "?parent-sender");
        const tools = new Map();
        const sent = [];
        extension({{
          registerTool: (tool) => tools.set(tool.name, tool),
          registerMessageRenderer() {{}}, on() {{}}, events: {{ emit() {{}} }},
          sendMessage: (message, options) => {{ sent.push({{ message, options }}); return Promise.resolve(); }},
        }});
        const result = await tools.get("agent_start").execute("call", {{ label: "sender", prompt: "work", tools: ["agent_message"] }});
        console.log(JSON.stringify({{
          started: result.details.ok,
          count: sent.length,
          content: sent[0]?.message.content,
          customType: sent[0]?.message.customType,
          options: sent[0]?.options,
        }}));
        """,
        module_mocks=True,
    )
    assert result["started"] is True and result["count"] == 1
    assert result["customType"] == "subagents-parent-message"
    assert "kind=\"intermediate\"" in str(result["content"])
    assert "raw child body" in str(result["content"])
    assert result["options"] == {"deliverAs": "followUp", "triggerTurn": True}


def test_a_refused_start_leaves_the_role_that_name_already_had_alone() -> None:
    """Registering the role before claiming the name let a refused call rewrite
    the role of a child that is still running."""
    result = run(
        """
        const first = await call({ operation: "start", name: "role-claim", description: "first", role_prompt: "FIRST" });
        const refused = await call({ operation: "start", name: "role-claim", description: "second", role_prompt: "SECOND" });
        console.log(JSON.stringify({
          refused: refused.details.ok === false,
          prompt: roster.resolveAgent("role-claim", WORKSPACE)?.prompt,
          spawns: spawned.length,
          first: first.details.ok === true,
        }));
        """
    )
    assert result["first"] is True
    assert result["refused"] is True
    assert result["prompt"] == "FIRST"
    assert result["spawns"] == 1


def test_a_name_whose_process_is_already_gone_can_be_released() -> None:
    """A process that is not running is what the caller asked for, so `stop` releases
    the name. Refusing left the entry claimed, `stop` was the one action that should
    have freed it, and a child that died without the roster learning left a name no
    later start could ever take."""
    result = run(
        """
        const started = await call({ operation: "start", name: "ghost", description: "d", role_prompt: "p" });
        // The fake terminate reports this name's process as already gone.
        const stopped = await call({ operation: "stop", session: started.details.session });
        const reused = await call({ operation: "start", name: "ghost", description: "d", role_prompt: "p" });
        console.log(JSON.stringify({
          ok: stopped.details.ok,
          outcome: stopped.details.outcome,
          // The release is reported in the evidence line, which is where a caller
          // reads why a name is free.
          saysReleased: String(stopped.details.body).includes("name is released"),
          body: stopped.details.body,
          reused: reused.details.ok === true,
        }));
        """
    )
    assert result["ok"] is True
    assert result["outcome"] == "stopped"
    assert result["saysReleased"] is True
    assert "was running" in str(result["body"])
    assert result["reused"] is True


def test_the_leader_exit_closes_the_children_it_started() -> None:
    """A child is a process, and a leader that exits leaving one running leaves a
    process nobody holds a handle to. `session_shutdown` is the runtime's own
    disposal — exit and signals, not a session switch — so closing there retires
    the children this process started. The spawner is mocked, because the claim
    here is about the entry's wiring, not about how a process is killed."""
    result = run_node(
        f"""\
        import {{ mock }} from "node:test";
        import * as spawner from {json.dumps(SPAWNER)};
        const terminations = [];
        const plannedAtShutdown = [];
        const warnings = [];
        mock.module({json.dumps(SPAWNER)}, {{
          namedExports: {{
            ...spawner,
            terminateAllAgents: async () => {{ terminations.push("all"); plannedAtShutdown.push((await import({json.dumps(BARREL)})).getAgent("child").leaderRequestedEnd === true); return [{{ name: "child", confirmedClosed: false }}]; }},
          }},
        }});
        const {{ default: piSubagentsExtension }} = await import({json.dumps(EXTENSION)});
        const handlers = new Map();
        const warn = console.warn;
        console.warn = (line) => warnings.push(String(line));
        piSubagentsExtension({{ registerTool() {{}}, on: (event, handler) => handlers.set(event, handler), events: {{ emit() {{}} }} }});
        const roster = await import({json.dumps(BARREL)});
        roster.resetRoster();
        roster.registerAgent({{ name:"child", role:"child", spawnId:"shutdown", pid:7, status:"working", scope:"session", createdAt:1, updatedAt:1 }});
        await handlers.get("session_shutdown")(undefined, undefined);
        console.warn = warn;
        console.log(JSON.stringify({{
          closed: terminations.length,
          planned: plannedAtShutdown[0],
          // A child that did not confirm is named, not swallowed: the session is
          // tearing down, so this is the last chance anyone hears about it.
          namesTheUnconfirmed: (warnings[0] ?? "").includes("child"),
        }}));
        """,
        module_mocks=True,
    )
    assert result["closed"] == 1
    assert result["planned"] is True
    assert result["namesTheUnconfirmed"] is True


def test_an_idle_standalone_resident_is_told_its_role_is_unread() -> None:
    """Nothing wakes a standalone resident — `deliverPrompt` has no caller without
    a coordinator — so the role it was registered with has not been read. Saying so
    beats a receipt that implies a child knows its role when it has never been
    told."""
    result = run(
        """
        const idle = await call({ operation: "start", name: "role-idle", description: "sits ready", role_prompt: "SIT role body." });
        const hasKickoff = spawned[0].description !== undefined;
        console.log(JSON.stringify({
          hasKickoff,
          saysUnread: idle.text.includes("reads no role"),
          namesTheRole: idle.text.includes("sits ready"),
          noClaimOfInstructions: !idle.text.includes("no standing instructions"),
          role: idle.details.role,
        }));
        """
    )
    assert result["hasKickoff"] is False
    assert result["saysUnread"] is True
    assert result["namesTheRole"] is True
    assert result["noClaimOfInstructions"] is True
    assert result["role"] == "sits ready"


def test_a_failed_spawn_is_reported_not_swallowed() -> None:
    result = run(
        """
        const failed = await call({ operation: "start", name: "unlucky", description: "d", role_prompt: "p" });
        const listed = await call({ operation: "list" });
        // Counted before the retry, because the whole claim is about the state
        // the failure left behind.
        const livingAfterFailure = (await call({ operation: "list" })).details.sessions
          .filter((a) => a.status !== "stopped").length;
        const retry = await call({ operation: "start", name: "unlucky" });
        console.log(JSON.stringify({
          reportedFailure: failed.details.ok === false,
          namesTheName: failed.text.includes("unlucky"),
          livingAfterFailure,
          listed: listed.details.count,
          // The name must be reusable: a name held by a child that never started
          // is the worst outcome, because it looks taken and nothing is running.
          retryOk: retry.details.ok === true,
          retryNotDuplicate: retry.details.ok === true
            ? (await call({ operation: "inspect", session: retry.details.session })).details.ok === true
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
          start: (request) => {
            roster.registerAgent({name:request.name,role:request.name,spawnId:"host-id",pid:7,status:"working",scope:"session",createdAt:1,updatedAt:1});
            return { ok: true, session: `session:${request.name}:host-id` };
          },
          send:async()=>({ok:true}),interrupt:async()=>({ok:true}),
          stop: async () => ({ ok: true }),
        });
        const started = await call({ operation: "start", name: "alpha", prompt: "go" });
        const duringHost = spawned.length;
        const present = resolveAgentHost();
        setAgentHost(undefined);
        const standalone = await call({ operation: "start", name: "beta" });
        console.log(JSON.stringify({
          hostUsed: started.details.session === "session:alpha:host-id",
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

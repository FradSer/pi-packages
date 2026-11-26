from __future__ import annotations

# --- Merged from test_agent_tool.py ---
"""The child-execution surface behind @fradser/pi-subagents.

Contract: features/tool-surface.feature,
packages/subagents/features/child-role-delivery.feature

`executeChildIntent` is the one implementation the four surviving `agent_*`
intent tools share, so these scenarios drive it directly with the spawn and
terminate functions injected: they assert the layer's *decisions* — routing,
validation, handle addressing, and what it reports — without starting a real
child process.
Everything a real spawn would prove is about the spawner, which has its own
suite. The combined `agent` tool and `agent_inspect` are retired (ADR-0008);
`test_it_registers_only_the_surviving_intent_tools` owns that claim at the
registered-surface seam.
"""


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


def _s0_run(script: str, workspace: Path | None = None) -> dict[str, object]:
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


def test_it_registers_only_the_surviving_intent_tools() -> None:
    result = _s0_run(
        """
        const names = [...tools.keys()];
        // Model-facing text is where a retired name does its damage: a description
        // that names a tool no host registers teaches a model to call it.
        const descriptions = names.map((name) => tools.get(name).description ?? "").join(" ");
        console.log(JSON.stringify({ names, count: tools.size, descriptions }));
        """
    )
    # ADR-0008 retired the combined `agent` tool and `agent_inspect`, and their
    # selections are still scrubbed, so a selection recorded before the
    # retirement cannot revive either name.
    assert result["count"] == 4
    assert result["names"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]
    assert "agent" not in result["names"]
    assert "agent_inspect" not in result["names"]
    assert "agent_inspect" not in result["descriptions"], (
        "a registered tool must not name the retired inspect tool"
    )


# ── Resident input completes the process lifecycle without coordination ──


# ── fork, with and without a prompt ──


def test_fork_is_legal_with_and_without_a_prompt() -> None:
    result = _s0_run(
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
    result = _s0_run(
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
        const staleStop = await call({ operation: "stop", session: stale });
        const liveList = await call({ operation: "list" });
        console.log(JSON.stringify({
          duplicateRefused: duplicate.details.ok === false,
          guides: duplicate.text.includes("agent_list") && duplicate.text.includes("agent_stop"),
          noProcessLeaked: duplicateSpawned === 1,
          stopped: stopped.details.outcome,
          reused: second.details.ok === true,
          distinct: second.details.session !== stale,
          staleRefused: staleStop.details.ok === false,
          staleCode: staleStop.details.code,
          rosterNamesAlpha: liveList.details.sessions.filter((entry) => entry.name === "alpha").length,
          rosterPointsAtSuccessor: liveList.details.sessions.some((entry) => entry.session === second.details.session),
          rosterForgetsPredecessor: !liveList.details.sessions.some((entry) => entry.session === stale),
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
    # The predecessor was replaced on the roster, not merely stopped: the stale
    # handle addresses no incarnation, and the roster holds only the successor.
    assert result["staleRefused"] is True
    assert result["staleCode"] == "not-found"
    assert result["rosterNamesAlpha"] == 1
    assert result["rosterPointsAtSuccessor"] is True
    assert result["rosterForgetsPredecessor"] is True


def test_list_enumerates_every_child_with_its_handle() -> None:
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
    result = _s0_run(
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
            ? (await call({ operation: "list" })).details.sessions.some((entry) => entry.session === retry.details.session)
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
    result = _s0_run(
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


# --- Merged from test_agent_tool_schema.py ---
"""The intent schemas are closed, flat and per-tool, and the handler keeps the rest."""

import json
from subagents_helpers import SRC, run_node


def test_intent_schemas_are_closed_flat_and_keep_handler_validation() -> None:
    report = run_node(f'''
      import assert from 'node:assert/strict';
      import {{Check}} from 'typebox/value';
      import {{INTENT_TOOL_SCHEMAS}} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      const schemas=INTENT_TOOL_SCHEMAS;
      for (const schema of Object.values(schemas)) {{
        assert.equal(schema.additionalProperties,false);
        assert.ok(Object.values(schema.properties).every(value=>value.type!=='object'&&!value.anyOf&&!value.oneOf));
      }}
      const start=schemas.agent_start;
      assert.deepEqual(start.required,['prompt']);
      for(const flag of ['persistent','memory','worktree','definition','name']){{
        assert.equal(Check(start,{{prompt:'Run',[flag]:true}}),false);
      }}
      assert.deepEqual(schemas.agent_input.required,['session','prompt','delivery']);
      assert.equal(Check(schemas.agent_input,{{session:'session:r:1',prompt:'Go',delivery:'later'}}),false);
      assert.deepEqual(schemas.agent_stop.required,['session']);
      assert.equal(Check(schemas.agent_stop,{{name:'reviewer'}}),false);
      // The schema stays flat; exact-handle requirements stay deterministic handler checks.
      const refused=await executeChildIntent({{operation:'stop',name:'reviewer'}});
      assert.equal(refused.structuredContent.ok,false);assert.match(refused.content[0].text,/session:/);
      console.log(JSON.stringify({{ok:true}}));
    ''')
    assert report["ok"] is True


# --- Merged from test_agent_tool_universe.py ---
"""The grantable built-in tool universe is Pi's own set, not a remembered copy.

`AGENT_BUILTIN_TOOLS` decides which ids a spawn refuses before a name is claimed.
A remembered list drifts the moment Pi adds or renames a built-in, and the drift
fails in the worse direction: a legitimate id would be refused. Pi's own
`allToolNames` is authoritative but unreachable — its exports map exposes no
tools subpath — so the installed module is read by absolute path, which is
available to a test and not to shipped code.
"""

import json

from subagents_helpers import REPO, SRC, run_node

FIND_PI_TOOLS = """
    import { existsSync } from "node:fs";
    import * as path from "node:path";
    const findInstalled = () => {
      // From the repository root, because that is the Pi the repo pins as a
      // devDependency and the version its checks run against. A nested copy
      // exists under a package when its `*` peer still resolves to an older
      // release, and comparing against that stale copy would fail for the wrong
      // reason: a version skew rather than a drift in this list.
      let dir = process.env.PI_REPO_ROOT ?? process.cwd();
      for (;;) {
        const candidate = path.join(dir, "node_modules", "@earendil-works", "pi-coding-agent", "dist", "core", "tools", "index.js");
        if (existsSync(candidate)) return candidate;
        const parent = path.dirname(dir);
        if (parent === dir) return "";
        dir = parent;
      }
    };
"""


def test_the_grantable_universe_matches_pis_canonical_builtin_set() -> None:
    result = run_node(f"""
      import {{ pathToFileURL }} from "node:url";
      import {{ AGENT_BUILTIN_TOOLS }} from {json.dumps((SRC / "agent-tools.ts").as_uri())};
      {FIND_PI_TOOLS}
      const file = findInstalled();
      if (!file) throw new Error("The installed pi-coding-agent tools module was not found.");
      const {{ allToolNames }} = await import(pathToFileURL(file).href);
      console.log(JSON.stringify({{ file, own: [...AGENT_BUILTIN_TOOLS].sort(), canonical: [...allToolNames].sort() }}));
    """, env_overrides={"PI_REPO_ROOT": str(REPO)})
    assert result["canonical"], "Pi reported no canonical built-in tools"
    assert result["own"] == result["canonical"]


def test_the_universe_is_what_the_refusal_message_advertises() -> None:
    """The refusal message names this list, so a universe that drifts from the
    advertised vocabulary is a spawn refused for an id the caller could only
    learn about by being refused. The `tools` parameter no longer enumerates the
    vocabulary, so the message is the one published copy a caller reads."""
    result = run_node(f"""
      import {{ AGENT_BUILTIN_TOOLS }} from {json.dumps((SRC / "agent-tools.ts").as_uri())};
      import {{ unknownAgentTools, unknownAgentToolsError }} from {json.dumps((SRC / "spawner.ts").as_uri())};
      const advertised = unknownAgentToolsError(["example"], []);
      console.log(JSON.stringify({{
        universe: [...AGENT_BUILTIN_TOOLS],
        unadvertised: AGENT_BUILTIN_TOOLS.filter((tool) => !advertised.includes(tool)),
        refused: unknownAgentTools(["example", ...AGENT_BUILTIN_TOOLS], []),
      }}));
    """)
    assert result["unadvertised"] == []
    assert result["refused"] == ["example"], result["refused"]


# --- Merged from test_agent_usage.py ---
"""Handler-level malformed-handle regression; pure shape cases live in test_agent_input.py."""

import json
from pathlib import Path

from subagents_helpers import SRC, run_node


def test_malformed_handle_never_dispatches_control(tmp_path: Path) -> None:
    report = run_node(f'''
      import assert from 'node:assert/strict';
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      let effects=0;
      const options={{cwd:process.env.PI_TEST_CWD,spawn:()=>{{effects++;return {{pid:7}};}},
        prompt:async()=>{{effects++;return true;}},terminate:async()=>{{effects++;return {{outcome:'closed'}};}}}};
      for(const [operation,request] of [['stop',{{}}],
        ['input',{{delivery:'next',prompt:'Next'}}],['input',{{delivery:'steer',prompt:'Next'}}]]){{
        const result=await executeChildIntent({{operation,session:'reviewer:opaque',...request}},options);
        assert.equal(result.structuredContent.ok,false);assert.match(result.content[0].text,/Invalid session handle/);
        assert.equal(result.structuredContent.operation,operation,'a malformed handle never relabels its operation');
      }}
      assert.equal(effects,0);console.log(JSON.stringify({{ok:true}}));
    ''', env_overrides={"PI_TEST_CWD": str(tmp_path), "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    assert report["ok"] is True


# --- Merged from test_agent_input.py ---
"""Five equivalence-class checks for the pure input boundary.

Each test uses one isolated Node process. No role discovery or runtime child runs.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
MODULE = (PACKAGE / "src" / "agent-input.ts").as_uri()
NODE = shutil.which("node")

_m4_PREAMBLE = """
import assert from 'node:assert/strict';
const session='session:Reviewer-1:opaque-incarnation';
const bases={start:{operation:'start',name:'reviewer'},input:{operation:'input',delivery:'next',session,prompt:'Continue'},
  steer:{operation:'input',delivery:'steer',session,prompt:'Steer'},
  stop:{operation:'stop',session},list:{operation:'list'}};
const allowed={start:['operation','name','prompt','description','role_prompt','tools','model','fork'],
  input:['operation','session','prompt','delivery'],steer:['operation','session','prompt','delivery'],
  stop:['operation','session'],list:['operation','offset','limit']};
const refused=(input,field)=>{
  const result=validate(input);
  assert.equal(result.ok,false,JSON.stringify(input,(_key,value)=>typeof value==='bigint'?String(value):value));
  assert.equal(typeof result.error,'string');assert.ok(result.error.trim());
  if(field)assert.ok(result.error.includes(field),result.error);
  return result;
};
"""


def _m4_run(script: str, root: Path) -> None:
    assert NODE is not None, "Node is required; no runtime installation occurs"
    env = {"PATH": f"{Path(NODE).parent}{os.pathsep}{os.defpath}", "HOME": str(root),
           "PI_CODING_AGENT_DIR": str(root / "agent"), "XDG_CONFIG_HOME": str(root / "config"),
           "XDG_CACHE_HOME": str(root / "cache")}
    result = subprocess.run([NODE, "--input-type=module", "--eval",
                             f"import {{validateAgentInput as validate}} from {json.dumps(MODULE)};\n" + _m4_PREAMBLE + script],
                            cwd=root, env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_object_operation_and_field_boundaries(tmp_path: Path) -> None:
    _m4_run("""
      for(const input of [undefined,null,[],['start'],'',false,0,1n,Symbol('input'),()=>({})])refused(input);
      for(const value of [undefined,null,false,0,[],{},'', 'Start',' start ','delegate']){
        const result=refused({operation:value,name:'reviewer'},'operation');
        for(const verb of [...new Set(Object.values(bases).map((base)=>base.operation))])assert.ok(result.error.includes(verb));
      }
      const values={name:'reader',prompt:'Input',description:'Purpose',role_prompt:'Rules',tools:['read'],
        model:'provider/model',fork:true,session,offset:0,limit:20};
      for(const [operation,base] of Object.entries(bases)){
        for(const [field,value] of Object.entries(values))if(!allowed[operation].includes(field)){
          refused({...base,[field]:value},field);refused({...base,[field]:undefined},field);
        }
        for(const field of ['definition','persistent','memory','worktree','authorization','__proto__'])
          for(const value of [true,false,undefined])refused({...base,[field]:value},field);
        for(const field of allowed[operation])refused({...base,[field]:undefined},field);
        refused({...base,[Symbol('unknown')]:true});
        refused(Object.defineProperty({...base},'hidden',{value:undefined}),'hidden');
      }
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_start_defaults_identifier_classes_and_authored_bytes(tmp_path: Path) -> None:
    _m4_run(r"""
      for(const input of [{prompt:'Run'},{name:'reviewer'},{name:'reviewer',fork:false},{name:'reviewer',fork:true}])
        assert.deepEqual(validate(input),{ok:true,value:{...input,operation:'start'}});
      for(const input of [{},{description:'Purpose'},{role_prompt:'Rules'},{tools:[]},{model:'p/m'},{fork:true}])refused(input);
      for(const name of ['a','Z','Reviewer.1_-','A'+'1'.repeat(63),'  Reviewer.1_-\t'])
        assert.equal(validate({name}).value.name,name.trim());
      for(const name of ['', ' \t\n','1first','_first','a/b','a\\b','../escape','a b','éclair','a\nb','A'.repeat(65)])refused({name,prompt:'Run'},'name');
      for(const field of ['name','prompt','description','role_prompt','model','session']){
        const base=field==='session'?bases.inspect:bases.start;
        for(const value of [null,false,0,[],{},new String('value'),1n])refused({...base,[field]:value},field);
      }
      for(const field of ['prompt','role_prompt','description'])for(const value of ['', ' ', '\t\r\n','\u00a0\u2003'])
        refused({name:'reviewer',[field]:value},field);
      for(const model of ['', ' \t','p\nm','p\rm','p/m\n','\rp/m'])refused({name:'reviewer',model},'model');
      const authored=' \tfirst café 漢字\r\n\n  second λ\t \n';
      const input={prompt:authored,role_prompt:authored,description:authored};
      assert.deepEqual(validate(input),{ok:true,value:{...input,operation:'start'}});
      for(const delivery of ['next','steer'])assert.equal(validate({operation:'input',delivery,session,prompt:authored}).value.prompt,authored);
      const trimmed=validate({name:' reviewer ',model:' p/m ',tools:[' read ']});
      assert.deepEqual(trimmed.value,{operation:'start',name:'reviewer',model:'p/m',tools:['read']});
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_tool_grants_boolean_choice_and_input_immutability(tmp_path: Path) -> None:
    _m4_run(r"""
      for(const tools of [null,false,1,'read',{0:'read',length:1},new Set(['read'])])refused({name:'reviewer',tools},'tools');
      for(const value of [undefined,null,false,0,[],{},'', ' \t\r\n',new String('read')])
        refused({name:'reviewer',tools:['read',value,'write']},'tools');
      for(const tools of [new Array(1),['read',,'write']])refused({name:'reviewer',tools},'tools');
      for(const tools of [[],['read','read'],['agent_memory','unknown_tool']])
        assert.deepEqual(validate({name:'reviewer',tools}).value.tools,tools);
      for(const fork of [null,0,1,'true',[],{},new Boolean(true)])refused({name:'reviewer',fork},'fork');
      const tools=Object.freeze([' read ','read']);const input=Object.freeze({prompt:' \nRun\t ',tools,fork:false});
      const result=validate(input);assert.equal(result.ok,true);result.value.tools.push('write');
      assert.deepEqual(input.tools,[' read ','read']);assert.equal(input.prompt,' \nRun\t ');
      assert.notEqual(result.value.tools,tools);
      assert.deepEqual(validate(Object.assign(Object.create(null),{operation:'list'})),{ok:true,value:{operation:'list',offset:0,limit:20}});
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_exact_handles_and_input_requirements(tmp_path: Path) -> None:
    _m4_run(r"""
      for(const operation of ['input','steer','stop']){
        const base=bases[operation];
        for(const handle of [session,'session:a:1','session:'+'A'.repeat(64)+':not-a-uuid'])
          assert.deepEqual(validate({...base,session:' '+handle+'\t'}),{ok:true,value:{...base,session:handle}});
        for(const handle of ['', ' \t\n','reviewer','reviewer:id','session:reviewer','session::id','session:reviewer:',
          'session:reviewer:id:extra','session:1bad:id','session:bad name:id','session:reviewer:bad id','session:reviewer:bad\nid','session:'+'A'.repeat(65)+':id']){
          const result=refused({...base,session:handle},'session');assert.ok(result.error.includes('session: prefix'));
        }
        const {session:_removed,...missing}=base;
        assert.ok(refused(missing,'session').error.includes('session:<name>:<incarnation>'));
        assert.ok(refused({...missing,name:'reviewer'},'name').error.includes('session: prefix'));
      }
      for(const operation of ['input','steer'])for(const prompt of ['', ' \t\n',null,undefined,false,0,[],{}])
        refused({...bases[operation],prompt},'prompt');
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_pagination_defaults_and_invalid_ranges(tmp_path: Path) -> None:
    _m4_run("""
      for(const page of [{},{offset:0},{offset:123},{offset:Number.MAX_SAFE_INTEGER},{limit:1},{limit:50},{offset:123,limit:50}])
        assert.deepEqual(validate({operation:'list',...page}),{ok:true,value:{operation:'list',offset:0,limit:20,...page}});
      for(const field of ['offset','limit']){
        const ranges=field==='offset'?[-1,0.5,Number.MAX_SAFE_INTEGER+1,1e20]:[-1,0,0.5,50.5,51];
        for(const value of [...ranges,undefined,null,false,'1',[],{},NaN,Infinity,1n,new Number(1)])refused({operation:'list',[field]:value},field);
      }
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


# --- Merged from test_agent_output.py ---
"""Typed bounded management projections; final answers stay outside this module."""

from pathlib import Path

from subagents_helpers import run_node

_m5_PREAMBLE = """
import assert from 'node:assert/strict';
import {Value} from 'typebox/value';
import * as output from './src/agent-output.ts';
const valid=result=>assert.ok(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,result.structuredContent),
  JSON.stringify([...Value.Errors(output.AGENT_TOOL_OUTPUT_SCHEMA,result.structuredContent)]));
const bounded=result=>{
  assert.ok(Buffer.byteLength(result.content[0].text)<=16384);
  assert.ok(result.content[0].text.split(/\\r\\n|\\r|\\n/).length<=200);
  assert.ok(Buffer.byteLength(JSON.stringify(result.details))<=32768);
  assert.ok(Buffer.byteLength(JSON.stringify(result.structuredContent))<=32768);valid(result);
};
const view=(i=0)=>({name:`reader-${i}`,session:`session:reader-${i}:exact-${i}`,status:'stopped',scope:'session',tools:['read'],sequenceEnded:true});
"""


def _m5_run(script: str, tmp_path: Path) -> None:
    result = run_node(_m5_PREAMBLE + script,env_overrides={
        'HOME':str(tmp_path),'PI_CODING_AGENT_DIR':str(tmp_path/'agent'),'PI_TEST_CWD':str(tmp_path),
    })
    assert result['ok'] is True


def test_unicode_bytes_and_lines_include_visible_marker(tmp_path: Path) -> None:
    _m5_run("""
      for(const raw of ['证据'.repeat(30000),'𐐀'.repeat(20000),'line\\n'.repeat(2000),'x'.repeat(20000)]){
        const preview=output.boundedToolText(raw);assert.ok(preview.truncation);
        assert.ok(Buffer.byteLength(preview.text)<=16384);assert.ok(preview.text.split('\\n').length<=200);
        assert.equal(preview.truncation.originalBytes,Buffer.byteLength(raw));
        assert.equal(preview.truncation.outputBytes,Buffer.byteLength(preview.text));
        assert.ok(preview.text.endsWith(preview.truncation.marker));assert.ok(!preview.text.includes('�'));
      }
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_schema_rejects_missing_handles_and_mismatched_outcomes(tmp_path: Path) -> None:
    _m5_run("""
      const base={ok:true,operation:'start',outcome:'started',state:'working',nextActor:'runtime',prompted:true};
      assert.deepEqual(output.CHILD_OPERATIONS,['start','input','list','stop']);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,base),false);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{...base,name:'r',session:'session:r:s'}),true);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{...base,operation:'list',outcome:'stopped'}),false);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{ok:false,operation:'input',outcome:'error',state:'unknown',nextActor:'caller'}),false);
      const failure=output.createAgentFailure('invalid-bogus','invalid-action','wrong action');bounded(failure);
      assert.equal(failure.structuredContent.requestedOperation,'invalid-bogus');assert.equal(failure.structuredContent.operation,'invalid');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_large_roster_record_retains_raw_state_and_idempotent_diagnostic(tmp_path: Path) -> None:
    _m5_run("""
      const raw={...view(),liveText:'证据\\n'.repeat(10000),error:'\\u001b[31m'+ 'e'.repeat(20000)};
      const before=JSON.stringify(raw);const result=output.createAgentListPage([raw],[]);bounded(result);
      assert.equal(result.structuredContent.state,'read-only');assert.equal(result.structuredContent.nextActor,'caller');
      const listed=result.details.sessions[0];assert.ok(listed.truncation.fields.length>=1);
      // A roster entry is a status summary, so it never carries the child's
      // output; the diagnostic beside it is bounded rather than dropped with it.
      assert.equal(listed.liveText,undefined);
      assert.ok(result.content[0].text.includes(listed.error));
      assert.equal(JSON.stringify(raw),before);
      const repeated=output.createAgentResult(result.content[0].text,result.structuredContent);bounded(repeated);
      assert.deepEqual(repeated.structuredContent,result.structuredContent);
      assert.equal(listed.error,'e'.repeat(1000)+'… [diagnostic truncated]');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_pages_across_sessions_and_definitions_without_result_bodies(tmp_path: Path) -> None:
    _m5_run("""
      const sessions=Array.from({length:72},(_,i)=>({...view(i),liveText:'x'.repeat(16000),error:'e'.repeat(20000)}));
      const definitions=Array.from({length:13},(_,i)=>({name:`saved-${i}`,status:'offline',scope:'user',description:'d'.repeat(10000),tools:[]}));
      const before=JSON.stringify({sessions,definitions});const seen=[];let offset=0;
      do{
        const result=output.createAgentListPage(sessions,definitions,{offset,limit:50});bounded(result);
        assert.equal(result.structuredContent.total,85);assert.equal(result.structuredContent.count,72);
        for(const item of [...result.details.agents,...result.details.definitions]){
          assert.ok(!seen.includes(item.name));seen.push(item.name);assert.equal(item.liveText,undefined);
        }
        assert.equal(result.details.page.returned,result.details.sessions.length+result.details.definitions.length);
        offset=result.details.page.nextOffset;
      }while(offset!==undefined);
      assert.equal(seen.length,85);assert.equal(JSON.stringify({sessions,definitions}),before);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_untrusted_truncation_metadata_cannot_disable_the_preview_budget(tmp_path: Path) -> None:
    _m5_run("""
      const raw={...view(),liveText:'x'.repeat(12000),error:'e'.repeat(2000),truncation:{omittedFields:[],fields:[
        {field:'liveText',truncated:true,reason:'bytes',originalBytes:12000,originalLines:1,outputBytes:1,outputLines:1,marker:'already bounded'},
        {field:'error',truncated:true,reason:'diagnostic',originalBytes:2000,originalLines:1,outputBytes:1,outputLines:1,marker:'already bounded'}]}};
      const before=JSON.stringify(raw);const result=output.createAgentListPage([raw],[]);bounded(result);
      const listed=result.details.sessions[0];
      // A forged "already bounded" claim restores neither field: the roster omits
      // output outright, and the diagnostic is bounded by the real budget.
      assert.equal(listed.liveText,undefined);
      assert.ok(listed.truncation.omittedFields.includes('liveText'));
      assert.ok(listed.truncation.fields.some(field=>field.field==='liveText'&&field.reason==='summary'));
      assert.ok(listed.error.length<=1024);assert.ok(listed.error.includes('diagnostic truncated'));
      assert.equal(JSON.stringify(raw),before);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_required_input_preview_cannot_be_removed_to_fake_a_valid_success(tmp_path: Path) -> None:
    _m5_run("""
      const raw={operation:'input',delivery:'next',ok:true,outcome:'prompted',name:'reader',session:'session:reader:exact',
        state:'working',nextActor:'runtime',prompt:'x'.repeat(6000),prompted:true,grant:['g'.repeat(31000)]};
      const result=output.createAgentResult('Input accepted',raw);bounded(result);
      assert.ok(result.structuredContent.ok?typeof result.structuredContent.prompt==='string':result.structuredContent.code==='output-limit');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_failure_and_exact_authority_limit_are_not_process_outcomes(tmp_path: Path) -> None:
    _m5_run("""
      const error=output.createAgentFailure('input','delivery-failed','\\u001b[31m'+ '证'.repeat(100000),
        {session:'session:reader:exact',state:'starting',dispatched:true,controlOutcome:'uncertain',pendingIntent:'input',nextActor:'caller'});
      bounded(error);assert.equal(error.structuredContent.controlOutcome,'uncertain');
      assert.equal(error.structuredContent.operation,'input');
      assert.equal(error.structuredContent.pendingIntent,'input');assert.ok(!error.content[0].text.includes('\\u001b'));
      const raw={...view(),assignment:{id:'task','kind':'task',resources:['x'.repeat(50000)]}};
      const before=JSON.stringify(raw);const limit=output.createAgentListPage([raw],[]);bounded(limit);
      assert.equal(limit.structuredContent.code,'output-limit');assert.equal(limit.structuredContent.session,raw.session);
      assert.ok(limit.structuredContent.limit.omittedFields.includes('assignment'));assert.equal(JSON.stringify(raw),before);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


# --- Merged from test_agent_structured_controls.py ---
"""Observed state, pending intent and failure codes never imply another outcome."""

from pathlib import Path

import pytest

from resident_support import run


def test_immediate_settled_answer_has_no_invented_pending_result(tmp_path: Path) -> None:
    run("""
      const result=await call({name:"coalesced-machine",prompt:"Run",tools:[]},{spawn:options=>{
        spawns.push(options);options.onUpdate({text:"2",turns:1,finalResponse:true,answerComplete:true});
        return {pid:42,accepted:Promise.resolve(true)};
      }});
      assert.equal(result.structuredContent.ok,true);assert.equal(result.structuredContent.state,"idle");
      assert.equal(result.structuredContent.nextActor,"caller");assert.equal(result.structuredContent.pendingIntent,undefined);
      assert.equal(notices.length,1);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


@pytest.mark.parametrize("kind", ["rejected", "uncertain"])
def test_control_failure_distinguishes_rejection_from_uncertainty(tmp_path: Path, kind: str) -> None:
    run("""
      const started=await call({name:"control-machine",prompt:"First",tools:[]},{prompt:async()=>{
        if(KIND==="uncertain")throw new Error("No ACK");return false;
      }});final(0,"2");
      const result=await call({operation:"input",delivery:"next",session:started.details.session,prompt:"Next"});
      assert.equal(result.isError,true);assert.equal(result.structuredContent.operation,"input");
      assert.equal(result.structuredContent.session,started.details.session);assert.equal(result.structuredContent.dispatched,true);
      assert.equal(result.structuredContent.code,KIND==="uncertain"?"delivery-failed":"input-rejected");
      assert.equal(result.structuredContent.controlOutcome,KIND);
      assert.equal(result.structuredContent.pendingIntent,KIND==="uncertain"?"input":undefined);
      assert.equal(result.structuredContent.state,KIND==="uncertain"?"starting":"idle");
      assert.equal(result.structuredContent.nextActor,"caller");console.log(JSON.stringify({ok:true}));
    """.replace("KIND",f'"{kind}"'),tmp_path)


def test_start_failure_keeps_its_exact_stopped_record_in_machine_data(tmp_path: Path) -> None:
    run("""
      const result=await call({name:"failed-machine",prompt:"Run",tools:[]},{spawn:()=>({error:"LOCAL_SPAWN_FAILURE"})});
      assert.equal(result.isError,true);assert.equal(result.structuredContent.code,"spawn-failed");
      assert.equal(result.structuredContent.operation,"start");assert.equal(result.structuredContent.state,"stopped");
      assert.equal(result.structuredContent.controlOutcome,"rejected");
      const page=await call({ operation:"list" });
      const stopped=page.details.sessions.find((row)=>row.session===result.structuredContent.session);
      assert.equal(page.details.ok,true);assert.ok(stopped,"the failed start keeps its exact stopped record");
      assert.equal(stopped.error,"LOCAL_SPAWN_FAILURE");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


# --- Merged from test_agent_contract_integration.py ---
"""Public handler enforces the operation contract and machine output budget."""

from pathlib import Path

from resident_support import run


def test_exported_handler_refuses_invalid_types_and_misplaced_fields_before_effects(tmp_path: Path) -> None:
    run("""
      const invalid=[null,[],{operation:true,name:"must-not-start"},{operation:""},{name:"bad-tools",tools:["read",7]},
        {name:"bad-fork",fork:"true"},{operation:"list",prompt:"ignored"},{operation:"list",tools:["bash"]},
        { operation:"list", session:"session:none:exact",prompt:"ignored"},
        {operation:"stop",session:"session:none:exact",tools:["bash"]},
        {operation:"input",delivery:"next",session:"session:none:exact",prompt:"Run",model:"fake/model"}];
      for(const input of invalid){
        const out=await call(input);assert.equal(out.details.ok,false,JSON.stringify(input));
        assert.equal(out.isError,true);
      }
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],[0,0,0,0,0]);
      assert.deepEqual(roster.listAgents(),[]);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_validation_failure_keeps_known_operation_without_guessing_an_invalid_start(tmp_path: Path) -> None:
    run("""
      const list=await call({operation:"list",prompt:"misplaced"});
      const start=await call({name:"invalid",tools:[7]});
      const wrong=await call({operation:"nonsense",name:"never"});
      assert.equal(list.structuredContent.operation,"list");assert.equal(start.structuredContent.operation,"start");
      assert.equal(wrong.structuredContent.operation,"invalid");
      assert.equal(wrong.structuredContent.requestedOperation,"nonsense");
      assert.deepEqual(roster.listAgents(),[]);assert.equal(spawns.length,0);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_handler_preserves_authored_prompt_and_role_bytes(tmp_path: Path) -> None:
    run("""
      const prompt="  user input\\n\\n";const role="  standing role\\n";const description="  role purpose  ";
      const start=await call({name:"authored",prompt,role_prompt:role,description,tools:[]});
      assert.equal(start.details.ok,true);assert.equal(start.details.prompt,prompt);
      assert.ok(spawns[0].description.endsWith(prompt));
      assert.ok(spawns[0].description.includes(role));
      const {resolveAgent}=await import("file://"+process.cwd()+"/src/agents.ts");
      assert.equal(resolveAgent("authored",cwd).prompt,role,"session role registry must retain authored instructions");
      assert.equal(resolveAgent("authored",cwd).description,description);
      final(0,"2");const input="  next input\\n";
      const sent=await call({operation:"input",delivery:"next",session:start.details.session,prompt:input});
      assert.equal(sent.details.ok,true);assert.equal(prompts[0].message,input);assert.equal(sent.details.prompt,input);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_all_operation_results_are_machine_readable_and_schema_valid(tmp_path: Path) -> None:
    run("""
      const {registerIntentTools}=await import("file://"+process.cwd()+"/src/intent-tools.ts");
      const {Value}=await import("typebox/value");
      const intentOptions={cwd,parentSessionId:"resident-parent",leaderModel:()=>"test/parent",thinking:()=>"low",
        spawn:input=>{spawns.push(input);return {pid:42,readiness:Promise.resolve(ready)}},
        prompt:async(name,message)=>{prompts.push({name,message});return accepted;},
        steer:(name,message)=>{steers.push({name,message});return steerAccepted;},
        terminate:async()=>({outcome:"closed"}),
        workspace:input=>{workspaces.push(input);return {cwd:input.cwd,
          workspacePath:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/workspace",
          sessionDir:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/projects/test/session",reused:false};},
        deliverSessionResult:notice=>notices.push(notice)};
      const tools=[];registerIntentTools({registerTool:tool=>tools.push(tool)},intentOptions);
      const tool=name=>{const found=tools.find(candidate=>candidate.name===name);assert.ok(found,`the intent family registers ${name}`);return found;};
      const ctx={cwd};const run=(name,params)=>tool(name).execute(name,params,undefined,undefined,ctx);
      const start=await run("agent_start",{label:"machine",prompt:"First",tools:[]});final(0,"2");
      const listed=await run("agent_list",{});
      const sent=await run("agent_input",{session:start.details.session,prompt:"Second",delivery:"next"});
      const steered=await run("agent_input",{session:start.details.session,prompt:"Only number",delivery:"steer"});
      final(0,"3");const stopped=await run("agent_stop",{session:start.details.session});
      const failed=await run("agent_input",{session:"session:missing:exact",prompt:"None",delivery:"next"});
      for(const [name,result] of [["agent_start",start],["agent_list",listed],
        ["agent_input",sent],["agent_input",steered],["agent_stop",stopped],["agent_input",failed]]){
        const definition=tool(name);assert.ok(definition.outputSchema,"data-returning tools must declare outputSchema");
        assert.ok(result.structuredContent,"structured data must reach programmatic callers");
        assert.ok(Value.Check(definition.outputSchema,result.structuredContent),JSON.stringify([...Value.Errors(definition.outputSchema,result.structuredContent)]));
        assert.equal(result.structuredContent.ok,result.details.ok);
        assert.equal(result.structuredContent.operation,result.details.operation);
        assert.equal(result.structuredContent.operation,name,"the receipt carries the operation that ran");
        assert.equal(result.structuredContent.disposition,result.details.disposition);
        assert.equal(result.structuredContent.version,1);
      }
      assert.equal(start.structuredContent.nextActor,"runtime");
      assert.equal(start.structuredContent.disposition,"started");
      assert.equal(listed.structuredContent.disposition,"listed");
      assert.equal(sent.structuredContent.disposition,"started");
      assert.equal(steered.structuredContent.disposition,"steered");
      assert.equal(stopped.structuredContent.state,"stopped");
      assert.equal(stopped.structuredContent.disposition,"stopped");
      assert.equal(failed.structuredContent.nextActor,"caller");
      assert.equal(failed.structuredContent.disposition,"rejected");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_list_pages_and_tool_failure_have_aggregate_byte_budgets(tmp_path: Path) -> None:
    run("""
      for(let i=0;i<75;i++)roster.registerAgent({name:`retained-${i}`,role:"diagnostic",spawnId:`incarnation-${i}`,
        pid:0,status:"stopped",liveText:"证据".repeat(20000),error:"issue".repeat(30000),createdAt:i,updatedAt:i});
      const before=JSON.stringify(roster.listAgents());const seen=[];let offset=0;
      do {
        const page=await call({operation:"list",offset,limit:50});
        assert.equal(page.details.ok,true);assert.ok(Buffer.byteLength(page.content[0].text)<=16*1024);
        assert.ok(page.content[0].text.split("\\n").length<=200);
        assert.ok(Buffer.byteLength(JSON.stringify(page.details))<=32*1024);
        assert.ok(Buffer.byteLength(JSON.stringify(page.structuredContent))<=32*1024);
        for(const entry of page.details.agents){assert.ok(!seen.includes(entry.session));seen.push(entry.session);}
        assert.equal(page.details.count,75);assert.ok(page.details.page);
        offset=page.details.page.nextOffset;
      }while(offset!==undefined);
      assert.equal(seen.length,75);assert.equal(JSON.stringify(roster.listAgents()),before);
      const out=await call({name:"bounded-failure",prompt:"Run",tools:[]},{spawn:()=>({error:"\\u001b[31m"+"证".repeat(100000)})});
      assert.equal(out.isError,true);assert.ok(Buffer.byteLength(out.content[0].text)<=16*1024);
      assert.ok(Buffer.byteLength(JSON.stringify(out.details))<=32*1024);
      assert.ok(out.content[0].text.includes("truncated"));
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


# --- Merged from test_agent_contract_reachability.py ---
"""Observable contract for the startup reachability rules in features/intent-tools.feature."""

import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_node

_m8_ENTRY = (PACKAGE / "index.ts").as_uri()
INTENT_TOOLS = (SRC / "intent-tools.ts").as_uri()

_m8_PREAMBLE = f"""
import assert from 'node:assert/strict';
import {{ stripVTControlCharacters }} from 'node:util';
import piSubagentsExtension from {json.dumps(_m8_ENTRY)};
import {{ executeIntentTool, INTENT_TOOL_SCHEMAS }} from {json.dumps(INTENT_TOOLS)};

const registered = [];
const pi = {{ registerTool: (tool) => registered.push(tool), registerMessageRenderer() {{}}, on() {{}}, events: {{ emit() {{}} }} }};
piSubagentsExtension(pi);
const intentTools = new Map(registered.map((tool) => [tool.name, tool]));

const spawns = [];
const options = {{
  cwd: process.env.PI_TEST_CWD,
  spawn: (value) => {{ spawns.push(value); return {{ pid: 42, accepted: Promise.resolve(true), readiness: Promise.resolve(true) }}; }},
  prompt: async () => true,
  steer: async () => true,
  terminate: async () => ({{ outcome: 'closed' }}),
  deliverSessionResult: () => {{}},
}};
const call = async (name, args) => (await executeIntentTool(name, args, options)).structuredContent;
const {{ Check }} = await import('typebox/value');
"""


def _m8_run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(_m8_PREAMBLE + script, env_overrides={
        "PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "HOME": str(tmp_path),
    })


def test_an_empty_identity_is_a_temporary_role(tmp_path: Path) -> None:
    """A caller that names an identity with no value gets a temporary child.

    The extension already reads an empty identity as absent, so the declared
    schema accepts what the extension accepts instead of refusing a call the
    product itself would have served.
    """
    result = _m8_run("""
      const empty = await call('agent_start', { identity: '', prompt: 'FIRST', instructions: 'TEMP ROLE' });
      const absent = await call('agent_start', { prompt: 'SECOND' });
      console.log(JSON.stringify({
        declared: Check(INTENT_TOOL_SCHEMAS.agent_start, { prompt: 'THIRD', identity: '' }),
        empty: { ok: empty.ok, name: empty.name, scope: empty.scope, identity: empty.identity ?? null },
        absent: { ok: absent.ok, scope: absent.scope },
        spawns: spawns.map((value) => ({ description: value.description ?? null, role: value.env?.PI_SUBAGENT_ROLE ?? null })),
      }));
    """, tmp_path)
    assert result["declared"] is True, "the schema accepts an identity field with no value"
    assert result["empty"]["ok"] is True
    assert result["empty"]["scope"] == "session"
    assert result["empty"]["identity"] is None, "an empty identity is not an identity"
    assert result["empty"]["name"] != "", "a temporary child never carries an empty name"
    assert len(result["spawns"]) == 2
    assert result["spawns"][0]["description"], "a temporary child still carries the role half it was given"
    assert result["spawns"][0]["role"] is None, "a temporary child carries no saved identity"


def test_the_tools_parameter_names_every_grantable_id(tmp_path: Path) -> None:
    """The description is the only contract a caller reads before spending a call.

    The ids a child accepts are a fixed set, and a project-extension tool is not
    in it. Both facts belong in the parameter description, because a refused call
    is the only other place they appear.
    """
    result = _m8_run("""
      const description = INTENT_TOOL_SCHEMAS.agent_start.properties.tools.description;
      console.log(JSON.stringify({
        missing: ['read','bash','edit','write','grep','find','ls','powershell','agent_memory'].filter((id) => !new RegExp(`\\\\b${id}\\\\b`).test(description)),
        child: /bare pi process|child process/i.test(description),
        extension: /extension|MCP/i.test(description),
      }));
    """, tmp_path)
    assert result["missing"] == [], "every grantable id is named"
    assert result["child"] is True
    assert result["extension"] is True


def test_an_empty_definition_list_says_where_an_identity_lives(tmp_path: Path) -> None:
    """Zero saved identities is a state the caller has to act on.

    The row names the project-local path a repository identity uses and states
    that a temporary role needs no file, so the first reachable answer is not the
    user-scope path under the agent home.
    """
    result = _m8_run("""
      const listed = await executeIntentTool('agent_list', {}, options);
      const component = intentTools.get('agent_list').renderResult(
        { content: listed.content, details: listed.details },
        { expanded: true, isPartial: false },
        { fg: (_n, text) => text, bg: (_n, text) => text, bold: (text) => text },
        { args: {}, toolCallId: 'empty-page', isError: false },
      );
      console.log(JSON.stringify({ rows: component.render(120).map(stripVTControlCharacters) }));
    """, tmp_path)
    text = "\n".join(str(row) for row in result["rows"])
    assert ".pi/agents/" in text, f"the project-local identity path is named:\n{text}"
    assert "temporary" in text.lower()


# --- Merged from test_tool_activation.py ---
"""Activation tested through the real package entry and a native session tree."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, run_node
_m9_ENTRY = (PACKAGE / "index.ts").as_uri()
_m9_PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import extension from {json.dumps(_m9_ENTRY)};
const family=['agent_start','agent_input','agent_stop','agent_list'];
const registered = [], handlers = new Map();
let active = ["read",...family,"subagents_enable"];
const pi = {{
  registerTool: t => registered.push(t),
  registerMessageRenderer() {{}},
  on: (event,h) => {{ const list=handlers.get(event)??[]; list.push(h); handlers.set(event,list); }},
  events: {{emit(){{}}}},
  getAllTools: () => registered,
  getActiveTools: () => active,
  setActiveTools: next => {{active=next;}},
}};
extension(pi);
const sessionManager=SessionManager.inMemory();
const ctx={{sessionManager,model:{{api:"anthropic-messages",compat:{{supportsMidConvoSystemMessages:true,supportsMidConvoToolChanges:true}}}}}};
const emit=async event=>{{for(const h of handlers.get(event)??[])await h({{}},ctx);}};
"""

def _m9_run(script: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="subagent-activation-") as directory:
        home = Path(directory)
        return run_node(_m9_PREAMBLE + script, env_overrides={
            **{key: "" for key in os.environ if key.startswith("PI_")},
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "PI_CODING_AGENT_DIR": str(home / "agent"),
            "PI_CODING_AGENT_SESSION_DIR": str(home / "sessions"),
            "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        })


def test_native_pi_activation_preserves_the_transcript_prefix(tmp_path: Path) -> None:
    # The native probe must run with a controlled process environment. Inheriting
    # every non-PI variable can leak NODE_OPTIONS, provider credentials, or user
    # config into what is meant to be an isolated transcript/activation check.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
    }
    result = subprocess.run(["node", str(PACKAGE / "tests" / "activation-transcript-fixture.ts")],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"prefixPreserved":true' in result.stdout


def test_compatible_fresh_session_loads_only_small_loader() -> None:
    result=_m9_run("""
      await emit("session_start");
      const loader=registered.find(t=>t.name==="subagents_enable");
      console.log(JSON.stringify({active,loader:!!loader,properties:loader?Object.keys(loader.parameters.properties):null}));
    """)
    assert result == {"active":["read","subagents_enable"],"loader":True,"properties":[]}


def test_provider_addition_flags_are_transport_specific() -> None:
    result=_m9_run("""
      const cases=[
        ["openai-completions",{supportsMidConvoSystemMessages:true,supportsMidConvoToolAdditions:true}],
        ["openai-responses",{supportsMidConvoSystemMessages:true,supportsAdditionalTools:true}],
        ["openai-codex-responses",{supportsMidConvoSystemMessages:true,supportsToolSearch:true}],
        ["openai-responses",{supportsToolSelection:true}],
        ["anthropic-messages",{supportsMidConvoToolChanges:true}],
      ];
      const outcomes=[];
      for(const [api,compat] of cases){ctx.model={api,compat};active=["read",...family,"subagents_enable"];await emit("session_start");outcomes.push([...active]);}
      console.log(JSON.stringify({outcomes}));
    """)
    assert result["outcomes"] == [["read","subagents_enable"]]*3 + [["read","agent_start","agent_input","agent_stop","agent_list"]]*2


def test_restoring_lazy_session_without_native_system_records_keeps_loader() -> None:
    result=_m9_run("""
      await emit("session_start");
      const recorded=active.slice();
      sessionManager.appendMessage({role:"user",timestamp:1,content:"Inspect"});
      await emit("session_start");
      console.log(JSON.stringify({recorded,active}));
    """)
    assert result["recorded"] == ["read","subagents_enable"]
    assert result["active"] == result["recorded"]


def test_unrelated_tool_delta_does_not_remove_subagent_entrypoints() -> None:
    result=_m9_run("""
      await emit("session_start");
      sessionManager.appendMessage({role:"system",timestamp:1,content:"",toolsAdded:[{name:"other",description:"other",parameters:{type:"object"}}]});
      await emit("session_tree");
      console.log(JSON.stringify({active}));
    """)
    assert result["active"] == ["read","subagents_enable"]


def test_loader_enables_agent_without_launching() -> None:
    result=_m9_run("""
      await emit("session_start");
      const loader=registered.find(t=>t.name==="subagents_enable");
      const result=loader?await loader.execute("call",{},undefined,undefined,ctx):null;
      console.log(JSON.stringify({active,enabled:result?.details.enabled??null}));
    """)
    assert not {"agent", "agent_inspect"} & set(result["active"]), "a retired tool is never selected"
    assert result["enabled"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]


def test_incompatible_or_unknown_provider_stays_eager() -> None:
    result=_m9_run("""
      ctx.model={api:"openai-completions",compat:{supportsMidConvoSystemMessages:true}};
      await emit("session_start");
      console.log(JSON.stringify({active}));
    """)
    assert result["active"] == ["read","agent_start","agent_input","agent_stop","agent_list"]


@pytest.mark.parametrize("recorded_name", ["agent", "agent_inspect"])
def test_native_branch_tool_selection_restores_without_model_churn(recorded_name: str) -> None:
    # Every retired name a host may still have recorded keeps its branch's work and
    # receives the whole intent family, so the removal moves delegation instead of
    # taking it away.
    result=_m9_run(f"""
      sessionManager.appendMessage({{role:"system",timestamp:1,content:"",toolsAdded:[{{name:{json.dumps(recorded_name)},description:"x",parameters:{{type:"object",properties:{{}}}}}}],toolsRemoved:[]}});
      await emit("session_start");
      const before=[...active];
      ctx.model={{api:"unknown"}};
      await emit("model_select");
      console.log(JSON.stringify({{active,before,recorded:{json.dumps(recorded_name)}}}));
    """)
    assert result["active"] == ["read","agent_start","agent_input","agent_stop","agent_list"], "a recorded retired name moves to the intent family"
    assert result["recorded"] not in result["active"], "the retired name is scrubbed, not restored"
    assert result["before"] == result["active"], "model_select never churns the selection"


def test_loader_has_short_selection_only_help_annotations_and_typed_schema() -> None:
    result = _m9_run('''
      const loader = registered.find(tool => tool.name === "subagents_enable");
      console.log(JSON.stringify({ description: loader.description, snippet: loader.promptSnippet,
        guidelines: loader.promptGuidelines, parameters: loader.parameters,
        annotations: loader.annotations, outputSchema: loader.outputSchema ?? null }));
    ''')
    assert len(result["description"]) <= 160 and len(result["snippet"]) <= 120
    for text in (result["description"], result["snippet"]):
        assert "agent" in text and "child" in text
    assert "selection" in result["description"].lower() and "authorization" in result["description"].lower()
    guidelines = " ".join(result["guidelines"]).lower()
    assert "user" in guidelines and "instructions" in guidelines and "authorization" in guidelines
    assert "complexity alone" in guidelines
    assert result["parameters"] == {"type": "object", "properties": {}, "additionalProperties": False}
    assert result["annotations"] == {
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    }
    assert result["outputSchema"] is not None


def test_loader_success_and_returned_errors_match_output_schema_and_keep_details() -> None:
    result = _m9_run('''
      const { Check } = await import("typebox/value");
      await emit("session_start");
      const loader = registered.find(tool => tool.name === "subagents_enable");
      const success = await loader.execute("success", {}, undefined, undefined, ctx);
      const repeated = await loader.execute("repeat", {}, undefined, undefined, ctx);
      const available = pi.getAllTools;
      pi.getAllTools = () => registered.filter(tool => tool.name !== "agent_start");
      const unavailable = await loader.execute("excluded", {}, undefined, undefined, ctx);
      pi.getAllTools = available;
      pi.setActiveTools = () => { throw new Error("fixture selection failure"); };
      const failure = await loader.execute("failure", {}, undefined, undefined, ctx);
      pi.setActiveTools = next => { active = next.filter(name => name !== "agent_input"); };
      const ignored = await loader.execute("ignored", {}, undefined, undefined, ctx);
      const receipts = [success, repeated, unavailable, failure, ignored];
      console.log(JSON.stringify({ receipts, valid: receipts.map(receipt => !!loader.outputSchema && Check(loader.outputSchema, receipt.structuredContent)) }));
    ''')
    assert result["valid"] == [True] * 5
    for index, receipt in enumerate(result["receipts"]):
        data = receipt["structuredContent"]
        assert data == receipt["details"]
        assert data["childStarted"] is False
        if index < 2:
            assert data == {"outcome": "enabled", "enabled": ["agent_start", "agent_input", "agent_stop", "agent_list"], "childStarted": False}
            assert receipt.get("isError", False) is False
        else:
            assert receipt["isError"] is True and data["outcome"] == "refused"
            assert data["code"] == ("unavailable" if index == 2 else "activation-failed")
            assert data["unavailable" if index == 2 else "missing"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]
            assert data["error"]


def test_loader_bounds_native_failure_without_mutating_original_diagnostic() -> None:
    result = _m9_run(r'''
      const { Check } = await import("typebox/value");
      const loader = registered.find(tool => tool.name === "subagents_enable");
      const diagnostic = "\x1b[31mfixture\x1b[0m\x1b]0;private-title\x07\x00 " + "长".repeat(3000);
      const original = new Error(diagnostic);
      pi.setActiveTools = () => { throw original; };
      const selection = await loader.execute("selection", {}, undefined, undefined, ctx);
      pi.getAllTools = () => { throw original; };
      const availability = await loader.execute("availability", {}, undefined, undefined, ctx);
      const receipts = [selection, availability];
      console.log(JSON.stringify({ receipts, valid: receipts.map(receipt => !!loader.outputSchema && Check(loader.outputSchema, receipt.structuredContent)),
        originalUnchanged: original.message === diagnostic, originalLength: original.message.length }));
    ''')
    assert result["valid"] == [True, True]
    assert result["originalUnchanged"] is True and result["originalLength"] > 3000
    for receipt in result["receipts"]:
        assert receipt["isError"] is True
        data = receipt["structuredContent"]
        assert data == receipt["details"] and data["code"] == "activation-failed"
        assert data["childStarted"] is False and data["missing"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]
        assert len(data["error"]) <= 1024 and data["error"].endswith("… [diagnostic truncated]")
        assert receipt["content"][0]["text"] == data["error"]
        for text in (data["error"], receipt["content"][0]["text"]):
            assert "\x1b" not in text and "\x07" not in text and "\x00" not in text
            assert "private-title" not in text


def test_native_branch_selection_removals_do_not_leak_between_branches() -> None:
    result = _m9_run('''
      const definition = name => ({ name, description: name, parameters: { type: "object", properties: {} } });
      sessionManager.appendMessage({ role: "system", timestamp: 1, content: "",
        toolsAdded: [definition("subagents_enable"), definition("read")], toolsRemoved: [] });
      const base = sessionManager.getLeafId();
      sessionManager.appendMessage({ role: "system", timestamp: 2, content: "",
        toolsAdded: [definition("agent_start"), definition("agent_input"), definition("agent_stop"), definition("agent_list")], toolsRemoved: [definition("subagents_enable")] });
      const enabledBranch = sessionManager.getLeafId();
      await emit("session_tree");
      const enabled = [...active];
      sessionManager.branch(base);
      sessionManager.appendMessage({ role: "system", timestamp: 3, content: "",
        toolsAdded: [], toolsRemoved: [definition("subagents_enable")] });
      await emit("session_tree");
      const removed = [...active];
      sessionManager.branch(base);
      await emit("session_tree");
      const lazy = [...active];
      sessionManager.branch(enabledBranch);
      ctx.model = { api: "unknown" };
      await emit("session_tree");
      console.log(JSON.stringify({ enabled, removed, lazy, restored: active }));
    ''')
    assert result == {
        "enabled": ["read", "agent_start", "agent_input", "agent_stop", "agent_list"],
        "removed": ["read"],
        "lazy": ["read", "subagents_enable"], "restored": ["read", "agent_start", "agent_input", "agent_stop", "agent_list"],
    }


def test_activation_respects_excluded_entrypoints_on_restore_and_call() -> None:
    result = _m9_run('''
      const loader = registered.find(tool => tool.name === "subagents_enable");
      pi.getAllTools = () => registered.filter(tool => tool.name !== "agent_start");
      await emit("session_start");
      const noAgent = [...active];
      const refusal = await loader.execute("excluded", {}, undefined, undefined, ctx);
      const afterRefusal = [...active];
      pi.getAllTools = () => registered.filter(tool => tool.name !== "subagents_enable");
      active = ["read", "agent_start", "agent_input", "agent_stop", "agent_list", "subagents_enable"];
      await emit("session_tree");
      console.log(JSON.stringify({ noAgent, afterRefusal, noLoader: active, refusal }));
    ''')
    assert result["noAgent"] == result["afterRefusal"] == ["read"]
    assert result["noLoader"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["refusal"]["isError"] is True
    assert result["refusal"]["details"]["unavailable"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]


def test_retired_names_are_scrubbed_from_a_host_selection() -> None:
    """A host that still carries a retired name must not keep it on the wire. Such a
    name is outside the family filter, so only the retired-tool scrub removes it, and
    the family still activates on a transport that cannot add tools mid-conversation."""
    result=_m9_run("""
      const retired=["agent","agent_inspect"];
      active=["read",...retired,"subagents_enable"];
      await emit("session_start");
      const lazy=[...active];
      ctx.model={api:"unknown"};
      active=["read",...retired,"subagents_enable"];
      await emit("session_start");
      console.log(JSON.stringify({lazy,eager:active}));
    """)
    assert result["lazy"] == ["read","subagents_enable"], "an anchored transport keeps the family behind the loader"
    assert result["eager"] == ["read","agent_start","agent_input","agent_stop","agent_list"], "an eager transport serves the family with no retired name"


# --- Merged from test_docker_minimal_token.py ---
"""Grading never upgrades an incomplete compact study into a pass."""
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/minimal.py"
SPEC = importlib.util.spec_from_file_location("docker_minimal_grade", LOCATION)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def fixture(root: Path, *, complete: bool, reasoning: bool, errors: int = 0, tokens: bool = True) -> dict:
    study = {"model": "magpie-hy4/hunyuan-eval/hy4-dev", "piVersion": "1.5.0",
        "completed": complete, "finalRoster": [{"name": "resident", "status": "stopped"}],
        "temporary": {"first": {"kind": "result", "text": "FIRST_OK", "usage": {"input": 1, "output": 1, "totalTokens": 2}},
            "second": {"kind": "result", "text": "SECOND_OK"}, "idle": "idle",
            "stop": {"ok": True}, "stale": {"ok": False}},
        "saved": {"started": {"ok": True}, "notice": {"kind": "result"},
            "restart": {"notice": {"kind": "result"}}},
        "invalidIdentity": {"ok": False}, "identityWithInstructions": {"ok": False},
        "readonly": {"notice": {"kind": "result"}, "proposals": ["candidate.md"]},
        "writer": {"first": {"kind": "result"}, "second": {"kind": "result"},
            "memoryFiles": [{"file": "contract.md", "body": "entry"}]}}
    notices = [study["temporary"]["first"]]
    receipts = [{"name": name} for name in ("agent_start", "agent_input", "agent_stop", "agent_list")]
    (root / "study.json").write_text(json.dumps(study))
    (root / "notices.jsonl").write_text("\n".join(json.dumps(n) for n in notices) + "\n")
    (root / "receipts.json").write_text(json.dumps(receipts))
    (root / "spawns.json").write_text("[]")
    (root / "child-1.jsonl").write_text("\n".join(json.dumps(event) for event in (
        {"event": "system", "memory": "index"},
        {"event": "result", "tool": "agent_memory", "id": "a", "error": True},
        {"event": "result", "tool": "agent_memory", "id": "b", "error": False})) + "\n")
    (root / "parent-tui.json").write_text(json.dumps({"markerObserved": True,
        "expandRepaintObserved": True, "resizeRepaintObserved": True}))
    metadata = {"requests": 1, "transportErrors": errors,
        "modelObservations": [{"reasoningEffortOnWire": "none" if reasoning else "low", "toolCount": 0}]}
    return metadata


def test_compact_study_passes_only_with_all_contracts_and_reasoning_off(tmp_path: Path) -> None:
    metadata = fixture(tmp_path, complete=True, reasoning=True)
    assert GRADER.grade(tmp_path, metadata)["passed"] is True


def test_missing_completion_reasoning_or_transport_health_fails_grading(tmp_path: Path) -> None:
    for complete, reasoning, errors in ((False, True, 0), (True, False, 0), (True, True, 1)):
        root = tmp_path / f"case-{complete}-{reasoning}-{errors}"
        root.mkdir()
        metadata = fixture(root, complete=complete, reasoning=reasoning, errors=errors)
        graded = GRADER.grade(root, metadata)
        assert graded["passed"] is False, (complete, reasoning, errors)
        failed = [name for name, passed in graded["checks"].items() if not passed]
        assert failed


def test_unpriced_result_notice_never_counts_as_measured_tokens(tmp_path: Path) -> None:
    metadata = fixture(tmp_path, complete=True, reasoning=True)
    (tmp_path / "notices.jsonl").write_text(json.dumps({"kind": "result", "text": "FIRST_OK"}) + "\n")
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["checks"]["tokenUsageObserved"] is False
    assert graded["passed"] is False

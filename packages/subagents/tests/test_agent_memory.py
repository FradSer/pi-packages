"""Disk identity Memory contract, exercised with isolated HOME and Pi config.

Contract: packages/subagents/features/agent-memory.feature
All fixtures are private temporary data; no real Agent record is read or written.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, run_node

MEMORY = (PACKAGE / "src" / "memory.ts").as_uri()
AGENTS = (PACKAGE / "src" / "agents.ts").as_uri()
EXTENSION = (PACKAGE / "src" / "agent-extension.ts").as_uri()


def run(
    script: str,
    tmp_path: Path,
    *,
    module_mocks: bool = False,
    extension_prelude: str = "",
    **env: str,
) -> dict[str, object]:
    home = tmp_path / "isolated-home"
    home.mkdir(exist_ok=True)
    return run_node(
        f'''\
        import * as sa from "{MEMORY}";
        const loadAgents = () => import("{AGENTS}");
        import fs from "node:fs";
        import path from "node:path";
        {extension_prelude}
        const {{ default: subagentExtension }} = await import("{EXTENSION}");
        {script}
        ''',
        module_mocks=module_mocks,
        env_overrides={
            **{key: "" for key in os.environ if key.startswith("PI_")},
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "PI_CODING_AGENT_DIR": str(tmp_path),
            "PI_CODING_AGENT_SESSION_DIR": str(tmp_path / "sessions"),
            "PI_SUBAGENT_ROLE": "",
            "PI_SUBAGENT_TOOLS": "",
            "PI_SUBAGENT_DEFINITION": "",
            "PI_SUBAGENT_SCOPE": "",
            "PI_SUBAGENT_PROJECT_CWD": "",
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            **env,
        },
    )


def seed_entry(root: Path, name: str, description: str, body: str = "body") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: capability\n---\n\n{body}\n",
        encoding="utf-8",
    )


def seed_identity(home: Path, name: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "agent.md").write_text(
        f"---\nname: {name}\ndescription: Review scoped evidence.\ntools: read, grep\n---\nReview evidence and limits.\n",
        encoding="utf-8",
    )


def seed_state(home: Path, name: str) -> dict[str, object]:
    home.mkdir(parents=True, exist_ok=True)
    state = {
        "version": 1,
        "name": name,
        "createdAt": "2026-01-02T03:04:05.000Z",
        "lastProject": "/fixture/project",
        "memoryEntryCount": 0,
        "extensionData": {"keep": "unchanged"},
    }
    (home / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return state


# Rule: Memory lives inside the identity's private data home.


def test_memory_root_is_private_nested_and_resolution_is_read_only(tmp_path: Path) -> None:
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        let traversal = "";
        try { sa.agentMemoryRoot("../../etc"); } catch (error) { traversal = error.message; }
        console.log(JSON.stringify({ root, exists: fs.existsSync(root), traversal }));
        ''',
        tmp_path,
    )
    assert result["root"] == str(tmp_path / "agents" / "reviewer" / "memory")
    assert result["exists"] is False, "path resolution must not provision durable data"
    assert "Invalid agent name" in str(result["traversal"])


def test_discovery_includes_only_canonical_durable_homes_with_memory(tmp_path: Path) -> None:
    base = tmp_path / "agents"
    for name in ("reviewer", "builder", "without-memory"):
        seed_identity(base / name, name)
    for name in ("reviewer", "builder", "project-only", "temporary", "malformed", "wrong-name", "legacy", "unbound-state"):
        (base / name / "memory").mkdir(parents=True, exist_ok=True)
    state = seed_state(base / "project-only", "project-only")
    project = tmp_path / "known-project"
    seed_identity(project / ".pi" / "agents" / "project-only", "project-only")
    (base / "project-only" / "state.json").write_text(json.dumps({**state, "lastProject": str(project)}), encoding="utf-8")
    seed_state(base / "unbound-state", "unbound-state")
    (base / "malformed" / "agent.md").write_text("not a definition", encoding="utf-8")
    (base / "malformed" / "state.json").write_text("{}", encoding="utf-8")
    seed_identity(base / "wrong-name", "different-name")
    (base / "legacy" / "lesson.md").write_text("Legacy entries are not canonical.", encoding="utf-8")
    (base / "legacy.md").write_text("---\nname: legacy\n---\nOld definition.\n", encoding="utf-8")
    result = run(
        '''
        const snapshot = fs.readdirSync(path.join(process.env.PI_CODING_AGENT_DIR, "agents"), { recursive: true }).sort();
        const roots = sa.listAgentMemoryRoots();
        const after = fs.readdirSync(path.join(process.env.PI_CODING_AGENT_DIR, "agents"), { recursive: true }).sort();
        const agents = await loadAgents();
        const identity = agents.resolveAgent("project-only", path.join(process.env.HOME, "empty-project"));
        console.log(JSON.stringify({ roots, unchanged: JSON.stringify(snapshot) === JSON.stringify(after), stateIsNotIdentity: !identity }));
        ''',
        tmp_path,
    )
    assert result["roots"] == [str(base / name / "memory") for name in ("builder", "project-only", "reviewer")]
    assert result["unchanged"] is True
    assert result["stateIsNotIdentity"] is True


def test_discovery_ignores_symlinked_homes_and_memory_escapes(tmp_path: Path) -> None:
    base = tmp_path / "agents"
    seed_identity(base / "safe", "safe")
    (base / "safe" / "memory").mkdir()
    seed_identity(base / "escape", "escape")
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "escape" / "memory").symlink_to(outside, target_is_directory=True)
    (base / "alias").symlink_to(base / "safe", target_is_directory=True)
    result = run("console.log(JSON.stringify({ roots: sa.listAgentMemoryRoots() }));", tmp_path)
    assert result["roots"] == [str(base / "safe" / "memory")]


def test_a_symlinked_agent_directory_is_usable_but_entry_and_proposal_escapes_are_refused(tmp_path: Path) -> None:
    real = tmp_path / "real-config"
    root = real / "agents" / "reviewer" / "memory"
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped_entry = outside / "lesson.md"
    escaped_entry.write_text("UNCHANGED", encoding="utf-8")
    (root / "escape.md").symlink_to(escaped_entry)
    (root / "proposals").symlink_to(outside, target_is_directory=True)
    linked = tmp_path / "linked-config"
    linked.symlink_to(real, target_is_directory=True)
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const entry = { description: "d", body: "b" };
        const appended = sa.appendMemoryEntry(root, { ...entry, name: "lesson" }, { writable: true });
        const escaped = sa.appendMemoryEntry(root, { ...entry, name: "escape" }, { writable: true });
        const proposal = sa.writeMemoryProposal(root, { title: "T", capability: "c", applicability: "a", limits: "l" });
        console.log(JSON.stringify({ appended, escaped, proposal, entries: sa.readMemoryEntries(root).map(entry => entry.name) }));
        ''',
        tmp_path,
        PI_CODING_AGENT_DIR=str(linked),
    )
    assert result["appended"]["ok"] is True
    assert result["escaped"]["ok"] is False and "outside" in result["escaped"]["error"]
    assert result["proposal"]["ok"] is False and "outside" in result["proposal"]["error"]
    assert result["entries"] == ["lesson"]
    assert escaped_entry.read_text(encoding="utf-8") == "UNCHANGED"
    assert len(list(outside.iterdir())) == 1


def test_dangling_entry_symlink_cannot_create_an_outside_file(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    root.mkdir(parents=True)
    outside = tmp_path / "outside-entry.md"
    (root / "escape.md").symlink_to(outside)
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const append = sa.appendMemoryEntry(root, { name: "escape", description: "d", body: "b" }, { writable: true });
        console.log(JSON.stringify({ append }));
        ''',
        tmp_path,
    )
    assert result["append"]["ok"] is False
    assert not outside.exists()
    assert (root / "escape.md").is_symlink()


def test_first_append_under_symlinked_config_can_create_nested_memory(tmp_path: Path) -> None:
    real = tmp_path / "real-config"
    real.mkdir()
    linked = tmp_path / "linked-config"
    linked.symlink_to(real, target_is_directory=True)
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const append = sa.appendMemoryEntry(root, { name: "first", description: "First cue.", body: "First method." }, { writable: true });
        console.log(JSON.stringify({ append, exists: fs.existsSync(path.join(root, "first.md")) }));
        ''',
        tmp_path,
        PI_CODING_AGENT_DIR=str(linked),
    )
    assert result["append"]["ok"] is True and result["exists"] is True


# Rule: Both injected and saved indexes obey the UTF-8 byte budget.


def test_block_lists_entries_without_bodies_or_the_definition(tmp_path: Path) -> None:
    home = tmp_path / "agents" / "reviewer"
    seed_identity(home, "reviewer")
    root = home / "memory"
    secret_body = "BODY_MARKER_do_not_inject"
    seed_entry(root, "bisect-flaky-tests", "Use when a test passes alone but fails in a suite.", secret_body)
    seed_entry(root, "review-evidence", "Use when judging whether a finding carries evidence.")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read", "bash"] });
        console.log(JSON.stringify(block));
        ''',
        tmp_path,
    )
    text = str(result["text"])
    assert "bisect-flaky-tests.md" in text and "review-evidence.md" in text
    assert "Use when a test passes alone" in text
    assert "agent.md" not in text and secret_body not in text
    assert text.count(str(result["root"])) == 1
    assert "untrusted reference data" in text
    assert result["writable"] is True and result["omitted"] == 0


def test_index_descriptions_are_sanitized_single_line_reference_data(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_entry(root, "cue", "Use when \x1b[31mcolored\x1b[0m \x1b]0;terminal-title\x07\x00 cue applies.")
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"] });
        sa.writeMemoryIndexFile(root);
        console.log(JSON.stringify({ block: block.text, index: fs.readFileSync(path.join(root, "MEMORY.md"), "utf-8") }));
        ''',
        tmp_path,
    )
    for text in (result["block"], result["index"]):
        assert "Use when colored cue applies." in text
        assert "\x1b" not in text and "\x00" not in text and "\x07" not in text
        assert "terminal-title" not in text


def test_a_long_description_is_shortened_visibly(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_entry(root, "verbose", "长" * 900)
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"], budgetBytes: 1600 });
        console.log(JSON.stringify({ ...block, bytes: Buffer.byteLength(block.text) }));
        ''',
        tmp_path,
    )
    assert "verbose.md" in result["text"] and "…" in result["text"]
    assert "长" * 900 not in result["text"]
    assert result["bytes"] <= 1600


def test_complete_index_and_block_include_notices_inside_the_byte_budget(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    # Filenames alone must exceed 8 KiB; long descriptions alone may be clipped
    # while still listing every entry, which is permitted by the contract.
    for index in range(600):
        seed_entry(root, f"entry-{index:03d}", "Use when 判断复杂条件. " * 40)
    result = run(
        f'''
        const root = sa.agentMemoryRoot("reviewer");
        const cases = [0, 64, 900, 8192].map(budget => {{
          const index = sa.buildMemoryIndex(root, budget);
          const block = sa.buildAgentMemoryBlock({{ agentName: "reviewer", tools: ["read"], budgetBytes: budget }});
          return {{budget,indexBytes: Buffer.byteLength(index.lines.join("\\n")),
            blockBytes: Buffer.byteLength(block.text),index,block}};
        }});
        console.log(JSON.stringify({{cases}}));
        ''',
        tmp_path,
    )
    for case in result["cases"]:
        budget = case["budget"]
        assert case["indexBytes"] <= budget and case["blockBytes"] <= budget
        assert case["index"]["shown"] + case["index"]["omitted"] == 600
        if budget >= 900:
            assert case["block"]["omitted"] > 0
            assert "omitted for budget" in case["block"]["text"]
            assert "authoritative" in case["block"]["text"] and "may be stale" in case["block"]["text"]
        else:
            assert case["block"]["text"] == "", "do not inject partial guidance"


def test_saved_memory_index_is_bounded_and_regenerated_after_append(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    for index in range(600):
        seed_entry(root, f"entry-{index:03d}", "多字节描述 " * 160)
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const append = sa.appendMemoryEntry(root, { name: "new-lesson", description: "Use when verifying byte bounds.", body: "Check complete UTF-8 bytes." }, { writable: true });
        const index = fs.readFileSync(path.join(root, "MEMORY.md"), "utf-8");
        console.log(JSON.stringify({ append, bytes: Buffer.byteLength(index), index, cap: sa.MEMORY_INDEX_BUDGET_BYTES }));
        ''',
        tmp_path,
    )
    assert result["append"]["ok"] is True
    assert result["bytes"] <= result["cap"] == 8192
    assert "omitted for budget" in result["index"]
    assert (root / "new-lesson.md").exists(), "the complete entry remains authoritative even if omitted"


def test_no_folder_or_no_entries_means_no_block_and_no_provisioning(tmp_path: Path) -> None:
    (tmp_path / "agents" / "empty" / "memory").mkdir(parents=True)
    result = run(
        '''
        const absent = sa.buildAgentMemoryBlock({ agentName: "absent", tools: ["write"] });
        const empty = sa.buildAgentMemoryBlock({ agentName: "empty", tools: ["read"] });
        console.log(JSON.stringify({ absent: absent.text, empty: empty.text, created: fs.existsSync(absent.root) }));
        ''',
        tmp_path,
    )
    assert result == {"absent": "", "empty": "", "created": False}


# Rule: Appending follows the effective write grant.


def test_read_only_agent_cannot_append(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_entry(root, "existing", "Use when needed.")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read", "grep"] });
        const append = sa.appendMemoryEntry(block.root, { name: "sneaky", description: "d", body: "b" }, { writable: block.writable });
        console.log(JSON.stringify({ block, append }));
        ''',
        tmp_path,
    )
    assert result["block"]["writable"] is False
    assert result["append"]["ok"] is False and "read-only" in result["append"]["error"]
    assert "read-only" in result["block"]["text"]
    assert not (root / "sneaky.md").exists()


def test_append_updates_only_memory_entry_count_in_existing_state(tmp_path: Path) -> None:
    home = tmp_path / "agents" / "reviewer"
    original = seed_state(home, "reviewer")
    root = home / "memory"
    seed_entry(root, "existing", "Use when needed.")
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const entry = { name: "bisect-flaky", description: "Use when a test passes alone.", body: "Bisect with --last-failed." };
        const first = sa.appendMemoryEntry(root, entry, { writable: true });
        const second = sa.appendMemoryEntry(root, { ...entry, body: "Updated method and limits." }, { writable: true });
        const proposal = sa.writeMemoryProposal(root, { title: "Candidate", capability: "c", applicability: "a", limits: "l" });
        const state = JSON.parse(fs.readFileSync(path.join(root, "..", "state.json"), "utf-8"));
        console.log(JSON.stringify({ first, second, proposal, state, index: fs.readFileSync(path.join(root, "MEMORY.md"), "utf-8") }));
        ''',
        tmp_path,
    )
    assert all(result[key]["ok"] is True for key in ("first", "second", "proposal"))
    assert result["state"] == {**original, "memoryEntryCount": 2}
    assert "existing.md" in result["index"] and "bisect-flaky.md" in result["index"]
    assert "Candidate" not in result["index"]
    assert not list(home.glob("*.tmp")), "atomic replacement leaves no temporary state files"


def test_shared_existing_state_updater_preserves_unknown_fields_and_creation_time(tmp_path: Path) -> None:
    home = tmp_path / "agents" / "reviewer"
    original = seed_state(home, "reviewer")
    result = run(
        '''
        const supported = typeof sa.updateExistingAgentHomeState === "function" && typeof sa.readAgentHomeState === "function";
        if (!supported) { console.log(JSON.stringify({ supported })); }
        else {
          const updated = sa.updateExistingAgentHomeState("reviewer", state => ({ ...state, lastProject: "/next-project", memoryEntryCount: 3 }));
          const latest = sa.readAgentHomeState("reviewer");
          const missing = sa.updateExistingAgentHomeState("absent", state => ({ ...state, memoryEntryCount: 5 }));
          console.log(JSON.stringify({ supported, updated, latest, missing: missing ?? null, created: fs.existsSync(path.join(process.env.PI_CODING_AGENT_DIR, "agents", "absent")) }));
        }
        ''',
        tmp_path,
    )
    assert result["supported"] is True, "storage and child must share one updater"
    expected = {**original, "lastProject": "/next-project", "memoryEntryCount": 3}
    assert result["updated"] == result["latest"] == expected
    assert result["missing"] is None and result["created"] is False
    assert not (home / "state.json.lock").exists()
    assert not list(home.glob("*.tmp"))


@pytest.mark.parametrize("unsafe", ["malformed", "state-symlink", "tmp-symlink", "occupied-lock"])
def test_existing_state_updater_refuses_unsafe_state_without_rewriting(tmp_path: Path, unsafe: str) -> None:
    home = tmp_path / "agents" / "reviewer"
    original = seed_state(home, "reviewer")
    state_file = home / "state.json"
    outside = tmp_path / "outside-state.json"
    outside.write_text(json.dumps(original), encoding="utf-8")
    if unsafe == "malformed":
        state_file.write_text("{}", encoding="utf-8")
    elif unsafe == "state-symlink":
        state_file.unlink()
        state_file.symlink_to(outside)
    elif unsafe == "occupied-lock":
        (home / "state.json.lock").write_text("owned-by-someone-else", encoding="utf-8")
    before = state_file.read_bytes()
    result = run(
        f'''
        const supported = typeof sa.updateExistingAgentHomeState === "function";
        let error = "";
        if (supported) {{
          if ({json.dumps(unsafe)} === "tmp-symlink") fs.symlinkSync({str(outside)!r}, path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer", `state.json.${{process.pid}}.tmp`));
          try {{ sa.updateExistingAgentHomeState("reviewer", state => ({{ ...state, memoryEntryCount: 7 }})); }} catch (caught) {{ error = caught.message; }}
        }}
        console.log(JSON.stringify({{ supported, error }}));
        ''',
        tmp_path,
    )
    assert result["supported"] is True
    assert result["error"], "unsafe paths/state and locks must fail explicitly"
    assert state_file.read_bytes() == before and outside.read_text(encoding="utf-8") == json.dumps(original)
    if unsafe == "occupied-lock":
        assert (home / "state.json.lock").read_text(encoding="utf-8") == "owned-by-someone-else"
    else:
        assert not (home / "state.json.lock").exists()


def test_atomic_state_updates_serialize_two_real_processes(tmp_path: Path) -> None:
    home = tmp_path / "agents" / "reviewer"
    original = seed_state(home, "reviewer")
    isolated_home = tmp_path / "process-home"
    isolated_home.mkdir()
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({"HOME": str(isolated_home), "PI_CODING_AGENT_DIR": str(tmp_path), "PI_OFFLINE": "1"})
    ready = tmp_path / "update-held"
    script_a = f'''
    import * as sa from "{MEMORY}";
    import fs from "node:fs";
    if (typeof sa.updateExistingAgentHomeState !== "function") {{ fs.writeFileSync({str(ready)!r}, "unsupported"); process.exit(2); }}
    const pause = new Int32Array(new SharedArrayBuffer(4));
    sa.updateExistingAgentHomeState("reviewer", state => {{
      fs.writeFileSync({str(ready)!r}, "locked");
      Atomics.wait(pause, 0, 0, 200);
      return {{ ...state, lastProject: "/parent-project" }};
    }});
    '''
    script_b = f'''
    import * as sa from "{MEMORY}";
    if (typeof sa.updateExistingAgentHomeState !== "function") process.exit(2);
    sa.updateExistingAgentHomeState("reviewer", state => ({{ ...state, memoryEntryCount: 4 }}));
    '''
    first = subprocess.Popen(["node", "--input-type=module", "--eval", script_a], cwd=PACKAGE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline and first.poll() is None:
            time.sleep(0.01)
        assert ready.exists() and ready.read_text(encoding="utf-8") == "locked", "RED: shared updater is missing"
        second = subprocess.run(["node", "--input-type=module", "--eval", script_b], cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=15)
        stdout, stderr = first.communicate(timeout=15)
        assert first.returncode == second.returncode == 0, stdout + stderr + second.stderr
    finally:
        if first.poll() is None:
            first.terminate()
            first.communicate(timeout=5)
    assert json.loads((home / "state.json").read_text(encoding="utf-8")) == {**original, "lastProject": "/parent-project", "memoryEntryCount": 4}
    assert not (home / "state.json.lock").exists()


def test_append_does_not_invent_state_or_identity(tmp_path: Path) -> None:
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const append = sa.appendMemoryEntry(root, { name: "lesson", description: "d", body: "b" }, { writable: true });
        console.log(JSON.stringify({ append, state: fs.existsSync(path.join(root, "..", "state.json")), identity: fs.existsSync(path.join(root, "..", "agent.md")) }));
        ''',
        tmp_path,
    )
    assert result["append"]["ok"] is True
    assert result["state"] is False and result["identity"] is False


def test_shell_and_mutating_tools_are_write_capable(tmp_path: Path) -> None:
    result = run(
        '''
        console.log(JSON.stringify({
          bash: sa.isMemoryWritable(["read", "bash"]), powershell: sa.isMemoryWritable(["powershell"]),
          edit: sa.isMemoryWritable(["edit"]), write: sa.isMemoryWritable(["write"]),
          readOnly: sa.isMemoryWritable(["read", "grep", "find", "ls"]),
          none: sa.isMemoryWritable([]), missing: sa.isMemoryWritable(undefined),
        }));
        ''',
        tmp_path,
    )
    assert result == {"bash": True, "powershell": True, "edit": True, "write": True, "readOnly": False, "none": False, "missing": False}


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"name": "../../../escape", "description": "d", "body": "b"}, "Invalid memory entry name"),
        ({"name": "memory", "description": "d", "body": "b"}, "reserved"),
        ({"name": "nodesc", "description": "  ", "body": "b"}, "description"),
        ({"name": "big", "description": "d", "body": "长" * 6000}, "cap"),
    ],
)
def test_invalid_entries_are_refused_without_writes(tmp_path: Path, entry: dict[str, str], message: str) -> None:
    result = run(
        f'''
        const root = sa.agentMemoryRoot("reviewer");
        const append = sa.appendMemoryEntry(root, {json.dumps(entry)}, {{ writable: true }});
        console.log(JSON.stringify({{ append, created: fs.existsSync(root) }}));
        ''',
        tmp_path,
    )
    assert result["append"]["ok"] is False and message in result["append"]["error"]
    assert result["created"] is False


# Rule: Proposals remain unaccepted evidence.


def test_proposals_are_recorded_but_not_entries_or_accepted_memory(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_entry(root, "existing", "Use when needed.")
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const proposal = sa.writeMemoryProposal(root, { title: "Bisect flaky suites", capability: "Bisect by last-failed set.", applicability: "A test passes alone.", limits: "Deterministic ordering.", evidence: "A fixture run." });
        const text = proposal.ok ? fs.readFileSync(proposal.file, "utf-8") : "";
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"] });
        console.log(JSON.stringify({ proposal, text, index: block.text, entries: sa.readMemoryEntries(root).map(entry => entry.name) }));
        ''',
        tmp_path,
    )
    assert result["proposal"]["ok"] is True
    assert Path(result["proposal"]["file"]).parent == root / "proposals"
    assert "status: proposed" in result["text"]
    assert "Bisect flaky suites" not in result["index"]
    assert result["entries"] == ["existing"]


EXTENSION_PROBE = '''
const handlers = new Map();
const registered = [];
subagentExtension({
  on: (event, handler) => { handlers.set(event, handler); },
  registerTool: (tool) => registered.push(tool),
});
'''


def test_child_extension_needs_no_memory_opt_in_and_refreshes_each_input(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_identity(root.parent, "reviewer")
    seed_entry(root, "existing", "Use when needed.")
    result = run(
        EXTENSION_PROBE
        + '''
        const before = handlers.get("before_agent_start");
        const initialOptions = { sections: {}, promptGuidelines: [] };
        await before({ systemPrompt: "BASE", systemPromptOptions: initialOptions });
        const tool = registered.find(tool => tool.name === "agent_memory");
        const append = tool ? await tool.execute("call", { action: "append", name: "fresh", description: "Use after learning.", body: "A fresh capability." }) : undefined;
        const nextOptions = { sections: {}, promptGuidelines: [] };
        await before({ systemPrompt: "BASE", systemPromptOptions: nextOptions });
        console.log(JSON.stringify({ names: registered.map(tool => tool.name), initial: initialOptions.sections.agent_memory ?? "", next: nextOptions.sections.agent_memory ?? "", append }));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="read,write,agent_memory",
        PI_SUBAGENT_DEFINITION=str(root.parent / "agent.md"),
        PI_SUBAGENT_SCOPE="user",
    )
    assert result["names"] == ["agent_memory"], "the durable contribution is not an opt-in"
    assert "existing.md" in result["initial"]
    assert result["append"]["details"]["outcome"] == "recorded"
    assert "fresh.md" not in result["initial"] and "fresh.md" in result["next"]


def test_child_heading_and_complete_memory_contribution_fit_eight_kib(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer" / "memory"
    seed_identity(root.parent, "reviewer")
    for index in range(600):
        seed_entry(root, f"entry-{index:03d}", "a" * 160)
    result = run(
        EXTENSION_PROBE
        + '''
        const before = handlers.get("before_agent_start");
        const options = { sections: {}, promptGuidelines: [] };
        await before({ systemPrompt: "BASE", systemPromptOptions: options });
        const contribution = options.sections.agent_memory ?? "";
        console.log(JSON.stringify({ contribution, bytes: Buffer.byteLength(contribution) }));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="read,agent_memory",
        PI_SUBAGENT_DEFINITION=str(root.parent / "agent.md"),
        PI_SUBAGENT_SCOPE="user",
    )
    assert "=== AGENT MEMORY (reviewer) ===" in result["contribution"]
    assert "omitted for budget" in result["contribution"]
    assert result["bytes"] <= 8192, "the child heading is part of the injected budget too"


def test_empty_durable_child_registers_refresh_handler_and_memory_tool(tmp_path: Path) -> None:
    definition = tmp_path / "agents" / "reviewer" / "agent.md"
    seed_identity(definition.parent, "reviewer")
    result = run(
        EXTENSION_PROBE
        + '''
        const before = handlers.get("before_agent_start");
        const options = { sections: { agent_memory: "stale section" }, promptGuidelines: [] };
        const initial = before ? await before({ systemPrompt: "BASE", systemPromptOptions: options }) : undefined;
        if ("agent_memory" in options.sections) throw new Error("Empty memory must remove its section");
        const root = sa.agentMemoryRoot("reviewer");
        const createdByLoad = fs.existsSync(root);
        sa.appendMemoryEntry(root, { name: "new-entry", description: "New cue.", body: "New method." }, { writable: true });
        await before({ systemPrompt: "BASE", systemPromptOptions: options });
        console.log(JSON.stringify({ handlers: [...handlers.keys()], tools: registered.map(tool => tool.name), initial: initial ?? null, createdByLoad, next: options.sections.agent_memory ?? "" }));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="read",
        PI_SUBAGENT_DEFINITION=str(definition),
        PI_SUBAGENT_SCOPE="user",
    )
    assert result["handlers"] == ["before_agent_start"] and result["tools"] == ["agent_memory"]
    assert result["initial"] is None and result["createdByLoad"] is False
    assert "new-entry.md" in result["next"]


def test_read_only_child_refuses_append_but_can_record_unaccepted_proposal(tmp_path: Path) -> None:
    definition = tmp_path / "agents" / "reviewer" / "agent.md"
    seed_identity(definition.parent, "reviewer")
    result = run(
        EXTENSION_PROBE
        + '''
        const tool = registered.find(tool => tool.name === "agent_memory");
        const append = tool ? await tool.execute("a", { action: "append", name: "lesson", description: "d", body: "b" }) : undefined;
        const proposal = tool ? await tool.execute("p", { action: "propose", title: "Candidate", body: "Capability.", applicability: "Scope.", limits: "Limits." }) : undefined;
        console.log(JSON.stringify({ append, proposal, entries: sa.readMemoryEntries(sa.agentMemoryRoot("reviewer")) }));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="read,grep,agent_memory",
        PI_SUBAGENT_DEFINITION=str(definition),
        PI_SUBAGENT_SCOPE="user",
    )
    assert result["append"]["isError"] is True and "read-only" in result["append"]["content"][0]["text"]
    assert result["proposal"]["details"]["outcome"] == "recorded"
    assert "separate decisions" in result["proposal"]["content"][0]["text"]
    assert result["entries"] == []


def test_ambient_or_temporary_execution_registers_no_memory(tmp_path: Path) -> None:
    result = run(
        EXTENSION_PROBE
        + '''
        console.log(JSON.stringify({ tools: registered.length, handlers: handlers.size, created: fs.existsSync(path.join(process.env.PI_CODING_AGENT_DIR, "agents")) }));
        ''',
        tmp_path,
        PI_SUBAGENT_TOOLS="write,agent_memory",
    )
    assert result == {"tools": 0, "handlers": 0, "created": False}


@pytest.mark.parametrize("scope", ["user", "project", "project-local"])
def test_every_canonical_disk_scope_has_memory_without_frontmatter_opt_in(tmp_path: Path, scope: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = (
        tmp_path / "agents" / "reviewer"
        if scope == "user"
        else project / ".pi" / "agents" / ("reviewer.local" if scope == "project-local" else "reviewer")
    )
    seed_identity(home, "reviewer")
    result = run(
        EXTENSION_PROBE
        + f'''
        const agents = await loadAgents();
        const found = agents.discoverAgents({str(project)!r}).get("reviewer");
        console.log(JSON.stringify({{ found: found ? {{ scope: found.scope, source: found.source }} : null, tools: registered.map(tool => tool.name), created: fs.existsSync(sa.agentMemoryRoot("reviewer")) }}));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="read,grep,agent_memory",
        PI_SUBAGENT_DEFINITION=str(home / "agent.md"),
        PI_SUBAGENT_SCOPE=scope,
        PI_SUBAGENT_PROJECT_CWD=str(project),
    )
    assert result["found"] is not None, "valid canonical agent.md must be discoverable"
    assert result["found"]["scope"] == scope and result["found"]["source"] == str(home / "agent.md")
    assert result["tools"] == ["agent_memory"], "Memory follows the disk child contribution, not a definition field"
    assert result["created"] is False, "read-only discovery and contribution loading do not provision data"


def test_arbitrary_role_and_data_state_do_not_enable_memory(tmp_path: Path) -> None:
    home = tmp_path / "agents" / "unbound"
    seed_state(home, "unbound")
    seed_entry(home / "memory", "existing", "A data folder is not identity.")
    result = run(
        EXTENSION_PROBE
        + '''
        console.log(JSON.stringify({ tools: registered.length, handlers: handlers.size }));
        ''',
        tmp_path,
        PI_SUBAGENT_ROLE="unbound",
        PI_SUBAGENT_TOOLS="write,agent_memory",
    )
    assert result == {"tools": 0, "handlers": 0}
    assert not (home / "agent.md").exists()


@pytest.mark.parametrize("invalid", ["wrong-name", "wrong-scope", "relative", "legacy", "symlink", "hardlink"])
def test_child_binding_rejects_invalid_disk_source(tmp_path: Path, invalid: str) -> None:
    home = tmp_path / "agents" / "reviewer"
    seed_identity(home, "reviewer")
    source = home / "agent.md"
    scope = "user"
    if invalid == "wrong-name":
        seed_identity(home, "different-name")
    elif invalid == "wrong-scope":
        scope = "project"
    elif invalid == "relative":
        source = Path("agent.md")
    elif invalid == "legacy":
        source = tmp_path / "agents" / "reviewer.md"
        source.write_bytes((home / "agent.md").read_bytes())
    elif invalid == "symlink":
        target = tmp_path / "outside.md"
        target.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(target)
    elif invalid == "hardlink":
        os.link(source, tmp_path / "outside.md")
    result = run(
        EXTENSION_PROBE + 'console.log(JSON.stringify({ tools: registered.length, handlers: handlers.size }));',
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS="write,agent_memory",
        PI_SUBAGENT_DEFINITION=str(source),
        PI_SUBAGENT_SCOPE=scope,
        PI_SUBAGENT_PROJECT_CWD=str(tmp_path / "project"),
    )
    assert result == {"tools": 0, "handlers": 0}


def test_session_role_has_no_memory_or_durable_home(tmp_path: Path) -> None:
    result = run(
        '''
        const agents = await loadAgents();
        const role = agents.registerSessionAgent({ name: "temporary", description: "d", tools: ["read"], prompt: "p" });
        agents.clearSessionAgents();
        console.log(JSON.stringify({ scope: role.scope, hasMemorySwitch: "memory" in role, durable: role.scope !== "session" && Boolean(role.source), created: fs.existsSync(sa.agentMemoryRoot("temporary")) }));
        ''',
        tmp_path,
    )
    assert result == {"scope": "session", "hasMemorySwitch": False, "durable": False, "created": False}


# Rule: Child tools describe and return their actual local write effects.


def run_child_tool(
    script: str,
    tmp_path: Path,
    *,
    tools: str = "read,write,agent_memory",
    extension_prelude: str = "",
    module_mocks: bool = False,
) -> dict[str, object]:
    definition = tmp_path / "agents" / "reviewer" / "agent.md"
    seed_identity(definition.parent, "reviewer")
    return run(
        EXTENSION_PROBE
        + '''
        const tool = registered.find(tool => tool.name === "agent_memory");
        const { Check } = await import("typebox/value");
        const validates = result => !!tool.outputSchema && Check(tool.outputSchema, result.structuredContent);
        '''
        + script,
        tmp_path,
        PI_SUBAGENT_ROLE="reviewer",
        PI_SUBAGENT_TOOLS=tools,
        PI_SUBAGENT_DEFINITION=str(definition),
        PI_SUBAGENT_SCOPE="user",
        extension_prelude=extension_prelude,
        module_mocks=module_mocks,
    )


def test_memory_tool_has_short_honest_help_flat_schema_and_write_annotations(tmp_path: Path) -> None:
    result = run_child_tool(
        '''
        console.log(JSON.stringify({
          description: tool.description, snippet: tool.promptSnippet,
          guidelines: tool.promptGuidelines, parameters: tool.parameters,
          annotations: tool.annotations, outputSchema: tool.outputSchema ?? null,
        }));
        ''',
        tmp_path,
    )
    description = result["description"].lower()
    snippet = result["snippet"].lower()
    assert len(description) <= 180 and len(snippet) <= 120
    for text in (description, snippet):
        assert "replac" in text and "creat" in text
        assert "candidate" in text and "unaccepted" in text
        assert "never merg" in text
    guidelines = " ".join(result["guidelines"]).lower()
    assert "project memory" in guidelines and "controlled proposal exception" in guidelines
    assert "read-only execution" in guidelines and "read-only disk" in guidelines
    params = result["parameters"]
    assert params["type"] == "object" and params["required"] == ["action"]
    assert params["additionalProperties"] is False
    assert "oneOf" not in params and "anyOf" not in params
    assert params["properties"]["action"]["enum"] == ["append", "propose"], "no new overwrite verb"
    action_help = params["properties"]["action"]["description"].lower()
    assert "replac" in action_help and "candidate" in action_help and "never merg" in action_help
    assert "append" in params["properties"]["name"]["description"].lower()
    assert "propos" in params["properties"]["name"]["description"].lower()
    assert "append" in params["properties"]["description"]["description"].lower()
    assert "propos" in params["properties"]["description"]["description"].lower()
    assert result["annotations"] == {
        "readOnlyHint": False, "destructiveHint": True,
        "idempotentHint": False, "openWorldHint": False,
    }
    assert result["outputSchema"] is not None


def test_memory_tool_append_still_replaces_same_name_with_typed_receipts(tmp_path: Path) -> None:
    result = run_child_tool(
        '''
        const first = await tool.execute("first", { action: "append", name: "lesson", description: "First cue.", body: "First method." });
        const second = await tool.execute("second", { action: "append", name: "lesson", description: "Updated cue.", body: "Updated method." });
        const root = sa.agentMemoryRoot("reviewer");
        console.log(JSON.stringify({ first, second, valid: [first, second].map(validates),
          entries: sa.readMemoryEntries(root), index: fs.readFileSync(path.join(root, "MEMORY.md"), "utf-8") }));
        ''',
        tmp_path,
    )
    assert result["valid"] == [True, True]
    assert result["entries"] == [{"name": "lesson", "description": "Updated cue.", "body": "Updated method."}]
    assert result["index"].count("lesson.md") == 1
    for key in ("first", "second"):
        receipt = result[key]
        data = receipt["structuredContent"]
        assert data == receipt["details"]
        assert data == {
            "outcome": "recorded", "action": "append",
            "file": str(tmp_path / "agents" / "reviewer" / "memory" / "lesson.md"),
            "effect": "created-or-replaced",
        }
        assert receipt.get("isError", False) is False
        text = receipt["content"][0]["text"].lower()
        assert "created or replaced" in text and "index" in text


@pytest.mark.parametrize(
    ("params", "title", "applicability", "evidence"),
    [
        ({"action": "propose", "body": "Candidate method."}, "proposal", "", ""),
        ({"action": "propose", "name": "fallback-name", "description": "Fallback applicability.", "body": "Candidate method."}, "fallback-name", "Fallback applicability.", ""),
        ({"action": "propose", "title": " Preferred title ", "name": "fallback-name", "description": "ignored fallback", "body": "Candidate method.", "applicability": " Explicit scope. ", "limits": " Scope limits. ", "evidence": " Fixture evidence. "}, "Preferred title", "Explicit scope.", "Fixture evidence."),
        ({"action": "propose", "title": " ", "name": "fallback-name", "description": "not selected", "body": "Candidate method.", "applicability": ""}, "fallback-name", "", ""),
    ],
)
def test_read_only_proposal_writes_candidate_and_preserves_optional_fallbacks(
    tmp_path: Path, params: dict[str, str], title: str, applicability: str, evidence: str,
) -> None:
    result = run_child_tool(
        f'''
        const receipt = await tool.execute("proposal", {json.dumps(params)});
        const root = sa.agentMemoryRoot("reviewer");
        const files = fs.readdirSync(path.join(root, "proposals"));
        console.log(JSON.stringify({{ receipt, valid: validates(receipt), files,
          text: fs.readFileSync(path.join(root, "proposals", files[0]), "utf-8"),
          entries: sa.readMemoryEntries(root), index: fs.existsSync(path.join(root, "MEMORY.md")) }}));
        ''',
        tmp_path,
        tools="read,grep,agent_memory",
    )
    receipt = result["receipt"]
    assert result["valid"] is True
    assert receipt["structuredContent"] == receipt["details"]
    data = receipt["structuredContent"]
    assert data == {
        "outcome": "recorded", "action": "propose", "effect": "candidate-written",
        "file": str(tmp_path / "agents" / "reviewer" / "memory" / "proposals" / result["files"][0]),
        "accepted": False, "merged": False,
    }
    assert f"title: {title}\n" in result["text"] and "status: proposed" in result["text"]
    assert f"## Applicability\n\n{applicability}\n" in result["text"]
    if evidence:
        assert f"## Evidence\n\n{evidence}\n" in result["text"]
    assert result["entries"] == [] and result["index"] is False
    text = receipt["content"][0]["text"].lower()
    assert "candidate" in text and "unaccepted" in text and "never merged" in text
    assert "separate decisions" in text


def test_memory_tool_refuses_wrong_fields_types_and_empty_required_strings_before_writes(tmp_path: Path) -> None:
    append = {"action": "append", "name": "lesson", "description": "A cue.", "body": "A method."}
    propose = {"action": "propose", "body": "A candidate."}
    invalid: list[object] = [None, [], "append", {}, {"action": True}, {"action": 1}, {"action": "replace", "body": "b"}]
    for field in ("name", "description", "body"):
        invalid.extend([{key: value for key, value in append.items() if key != field}, {**append, field: ""}, {**append, field: " \r\n "}])
    for value in (True, 12, [], {}, None):
        for field in ("name", "description", "body"):
            invalid.append({**append, field: value})
        for field in ("body", "title", "name", "description", "applicability", "limits", "evidence"):
            invalid.append({**propose, field: value})
    for field in ("title", "applicability", "limits", "evidence", "authorization"):
        invalid.append({**append, field: "misplaced"})
    invalid.extend([{"action": "propose"}, {**propose, "body": ""}, {**propose, "body": " \r\n "}, {**propose, "authorization": "yes"}])
    result = run_child_tool(
        f'''
        const cases = {json.dumps(invalid)};
        const receipts = [];
        for (const params of cases) receipts.push(await tool.execute("invalid", params));
        console.log(JSON.stringify({{ receipts, valid: receipts.map(validates), cases,
          created: fs.existsSync(sa.agentMemoryRoot("reviewer")) }}));
        ''',
        tmp_path,
    )
    assert result["cases"] == invalid, "validation must not rewrite the authored inputs"
    assert result["created"] is False
    assert all(result["valid"])
    for params, receipt in zip(invalid, result["receipts"], strict=True):
        assert receipt["isError"] is True, params
        assert receipt["structuredContent"] == receipt["details"]
        assert receipt["structuredContent"]["outcome"] == "refused"
        assert receipt["structuredContent"]["code"] == "invalid-arguments"
        assert receipt["structuredContent"]["error"]
        assert "[object Object]" not in receipt["content"][0]["text"]


def test_memory_tool_read_only_append_refusal_describes_controlled_proposal_write(tmp_path: Path) -> None:
    result = run_child_tool(
        '''
        const receipt = await tool.execute("readonly", { action: "append", name: "lesson", description: "A cue.", body: "A method." });
        console.log(JSON.stringify({ receipt, valid: validates(receipt), created: fs.existsSync(sa.agentMemoryRoot("reviewer")) }));
        ''',
        tmp_path,
        tools="read,grep,agent_memory",
    )
    receipt = result["receipt"]
    assert result["valid"] is True and result["created"] is False
    assert receipt["isError"] is True
    assert receipt["structuredContent"] == receipt["details"]
    assert receipt["structuredContent"]["code"] == "read-only-grant"
    text = receipt["content"][0]["text"].lower()
    assert "create or replace" in text and "read-only execution" in text
    assert "controlled proposal exception" in text and "writes" in text and "candidate" in text
    assert "never merged" in text


@pytest.mark.parametrize("action", ["append", "propose"])
def test_already_aborted_memory_tool_refuses_before_write(tmp_path: Path, action: str) -> None:
    result = run_child_tool(
        f'''
        const params = {{ action: {json.dumps(action)}, body: "Authored method." }};
        if (params.action === "append") Object.assign(params, {{ name: "lesson", description: "A cue." }});
        const controller = new AbortController();
        controller.abort(new Error("fixture cancellation"));
        const receipt = await tool.execute("aborted", params, controller.signal);
        console.log(JSON.stringify({{ receipt, valid: validates(receipt), created: fs.existsSync(sa.agentMemoryRoot("reviewer")) }}));
        ''',
        tmp_path,
    )
    receipt = result["receipt"]
    assert result["valid"] is True and result["created"] is False
    assert receipt["isError"] is True
    assert receipt["structuredContent"] == receipt["details"]
    assert receipt["structuredContent"]["action"] == action
    assert receipt["structuredContent"]["code"] == "aborted"


def test_memory_tool_preserves_authored_body_bytes_at_library_boundary(tmp_path: Path) -> None:
    prelude = f'''
    const {{ mock }} = await import("node:test");
    const captured = [];
    mock.module("{MEMORY}", {{ namedExports: {{ ...sa,
      appendMemoryEntry(root, entry, options) {{ captured.push({{ action: "append", entry, options }}); return {{ ok: true, file: path.join(root, "lesson.md") }}; }},
      writeMemoryProposal(root, proposal) {{ captured.push({{ action: "propose", proposal }}); return {{ ok: true, file: path.join(root, "proposals", "candidate.md") }}; }},
    }} }});
    '''
    result = run_child_tool(
        r'''
        const body = " \r\n  authored capability\t\r\n\r\n  ";
        const append = await tool.execute("append", { action: "append", name: " lesson ", description: " A cue. ", body });
        const proposal = await tool.execute("propose", { action: "propose", title: " Candidate ", body });
        console.log(JSON.stringify({ body, captured, valid: [append, proposal].map(validates), created: fs.existsSync(sa.agentMemoryRoot("reviewer")) }));
        ''',
        tmp_path,
        extension_prelude=prelude,
        module_mocks=True,
    )
    assert result["valid"] == [True, True]
    assert result["body"] == " \r\n  authored capability\t\r\n\r\n  "
    assert result["captured"][0]["entry"] == {"name": "lesson", "description": "A cue.", "body": result["body"]}
    assert result["captured"][1]["proposal"]["capability"] == result["body"]
    assert result["created"] is False, "only the library seam is mocked; no real Memory writes"


@pytest.mark.parametrize("failure", ["returned", "thrown"])
def test_memory_tool_bounds_returned_and_thrown_failures_without_mutating_source(tmp_path: Path, failure: str) -> None:
    prelude = f'''
    const {{ mock }} = await import("node:test");
    const diagnostic = "\\x1b[31mfixture\\x1b[0m\\x1b]0;private-title\\x07\\x00 " + "长".repeat(3000);
    const original = diagnostic;
    const fail = () => {{
      if ({json.dumps(failure)} === "thrown") throw new Error(diagnostic);
      return {{ ok: false, error: diagnostic }};
    }};
    mock.module("{MEMORY}", {{ namedExports: {{ ...sa, appendMemoryEntry: fail, writeMemoryProposal: fail }} }});
    '''
    result = run_child_tool(
        '''
        const receipts = [
          await tool.execute("append", { action: "append", name: "lesson", description: "A cue.", body: "A method." }),
          await tool.execute("propose", { action: "propose", body: "A candidate." }),
          await tool.execute("invalid", { action: "append", name: "lesson", description: "A cue.", body: "A method.", [diagnostic]: "misplaced" }),
        ];
        console.log(JSON.stringify({ receipts, valid: receipts.map(validates), originalUnchanged: diagnostic === original, originalLength: original.length }));
        ''',
        tmp_path,
        extension_prelude=prelude,
        module_mocks=True,
    )
    assert result["originalUnchanged"] is True and result["originalLength"] > 3000
    assert result["valid"] == [True, True, True]
    for index, receipt in enumerate(result["receipts"]):
        assert receipt["isError"] is True
        assert receipt["structuredContent"] == receipt["details"]
        data = receipt["structuredContent"]
        assert data["code"] == ("write-failed" if index < 2 else "invalid-arguments")
        assert len(data["error"]) <= 1024 and data["error"].endswith("… [diagnostic truncated]")
        assert receipt["content"][0]["text"] == f'REFUSED · {data["error"]}'
        for text in (receipt["content"][0]["text"], data["error"]):
            assert "\x1b" not in text and "\x00" not in text and "\x07" not in text
            assert "private-title" not in text

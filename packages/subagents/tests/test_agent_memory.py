"""Agent Memory: a persisted Agent's own capability record.

Contract: packages/subagents/features/agent-memory.feature

`PI_CODING_AGENT_DIR` is redirected to a temporary directory in every case,
because Agent Memory has exactly one home at user scope and a test must never
touch a real Agent's record.
"""

from __future__ import annotations

from pathlib import Path

from subagents_helpers import PACKAGE, run_node

SUBAGENTS = (PACKAGE / "index.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f'''\
        import * as sa from "{SUBAGENTS}";
        {script}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def seed_entry(root: Path, name: str, description: str, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: capability\n---\n\n{body}\n",
        encoding="utf-8",
    )


# ── Rule: the folder is the Agent's own and only at user scope ──


def test_memory_root_is_user_scoped_and_traversal_is_refused(tmp_path: Path) -> None:
    project = tmp_path / "some-project"
    project.mkdir()
    result = run(
        f'''
        const root = sa.agentMemoryRoot("reviewer");
        let traversal = "";
        try {{ sa.agentMemoryRoot("../../etc"); }} catch (error) {{ traversal = error.message; }}
        console.log(JSON.stringify({{
          root,
          agentDir: process.env.PI_CODING_AGENT_DIR,
          exact: root === process.env.PI_CODING_AGENT_DIR + "/agents/reviewer",
          // The project-local form must never be used: a project-scoped capability
          // folder cannot serve a cross-project Agent.
          projectScoped: root.includes(".pi/agents"),
          outsideProject: !root.startsWith({str(project)!r}),
          traversal,
        }}));
        ''',
        tmp_path,
    )
    assert result["exact"] is True, "Agent Memory has exactly one home, at user scope"
    assert result["projectScoped"] is False, "no project-local Agent Memory folder"
    assert result["outsideProject"] is True
    assert str(result["root"]).startswith(str(result["agentDir"]))
    assert "Invalid agent name" in str(result["traversal"])


def test_existing_roots_are_discoverable_in_stable_order(tmp_path: Path) -> None:
    (tmp_path / "agents" / "reviewer").mkdir(parents=True)
    (tmp_path / "agents" / "builder").mkdir(parents=True)
    (tmp_path / "agents" / "plain.md").write_text("---\nname: plain\n---\nbody\n", encoding="utf-8")
    result = run(
        '''
        const roots = sa.listAgentMemoryRoots();
        console.log(JSON.stringify({ roots, sorted: JSON.stringify(roots) === JSON.stringify([...roots].sort()) }));
        ''',
        tmp_path,
    )
    names = [str(root).rsplit("/", 1)[-1] for root in result["roots"]]
    assert names == ["builder", "reviewer"], "definition files are not memory folders"
    assert result["sorted"] is True


# ── Rule: injection carries an index, never bodies ──


def test_block_lists_entries_without_bodies(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    secret_body = "BODY_MARKER_do_not_inject"
    seed_entry(root, "bisect-flaky-tests", "Use when a test passes alone but fails in a suite.", secret_body)
    seed_entry(root, "review-evidence", "Use when judging whether a finding carries evidence.", "Another body.")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read", "bash"] });
        console.log(JSON.stringify({
          text: block.text,
          writable: block.writable,
          omitted: block.omitted,
          root: block.root,
        }));
        ''',
        tmp_path,
    )
    text = str(result["text"])
    assert "bisect-flaky-tests.md" in text and "review-evidence.md" in text
    assert "Use when a test passes alone" in text, "the description is the relevance cue"
    assert secret_body not in text, "no entry body may be injected (ADR-0003)"
    assert text.count(str(result["root"])) == 1, "the root is declared once, not per entry"
    assert "untrusted reference data" in text
    assert result["writable"] is True, "a bash grant is write-capable"
    assert result["omitted"] == 0


def test_a_long_description_is_shortened_visibly(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    seed_entry(root, "verbose", "x" * 900, "body")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"], budgetBytes: 700 });
        console.log(JSON.stringify({ text: block.text, omitted: block.omitted }));
        ''',
        tmp_path,
    )
    text = str(result["text"])
    assert "verbose.md" in text, "a shortened entry is still listed"
    assert "…" in text, "the shortening must be marked, not presented as complete"
    assert "x" * 900 not in text


def test_entries_beyond_the_budget_are_counted(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    for index in range(40):
        seed_entry(root, f"entry-{index:02d}", f"Use when case {index} applies.", "body")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"], budgetBytes: 900 });
        console.log(JSON.stringify({ text: block.text, omitted: block.omitted }));
        ''',
        tmp_path,
    )
    assert int(str(result["omitted"])) > 0, "an entry that cannot be listed is counted, not lost"
    text = str(result["text"])
    assert "omitted for budget" in text
    assert "authoritative" in text and "may be stale" in text


def test_no_folder_means_no_block(tmp_path: Path) -> None:
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "absent", tools: ["read", "write"] });
        console.log(JSON.stringify({ text: block.text, writable: block.writable }));
        ''',
        tmp_path,
    )
    assert result["text"] == "", "the absence of a block is how 'no Agent Memory' is expressed"


# ── Rule: writing is gated by the tool grant ──


def test_read_only_agent_cannot_append(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    seed_entry(root, "existing", "Use when needed.", "body")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read", "grep"] });
        const append = sa.appendMemoryEntry(block.root,
          { name: "sneaky", description: "d", body: "b" }, { writable: block.writable });
        console.log(JSON.stringify({ writable: block.writable, append, readOnlyTold: block.text.includes("read-only") }));
        ''',
        tmp_path,
    )
    assert result["writable"] is False
    append = result["append"]
    assert isinstance(append, dict) and append["ok"] is False
    assert "read-only" in str(append["error"])
    assert result["readOnlyTold"] is True, "the block must say so rather than just refusing later"
    assert not (root / "sneaky.md").exists()


def test_write_capable_agent_appends_and_the_index_follows(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    seed_entry(root, "existing", "Use when needed.", "body")
    result = run(
        '''
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["write"] });
        const append = sa.appendMemoryEntry(block.root,
          { name: "bisect-flaky", description: "Use when a test passes alone.", body: "Bisect with --last-failed." },
          { writable: block.writable });
        const after = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["write"] });
        console.log(JSON.stringify({ append, listed: after.text.includes("bisect-flaky.md") }));
        ''',
        tmp_path,
    )
    append = result["append"]
    assert isinstance(append, dict) and append["ok"] is True
    assert (root / "bisect-flaky.md").exists()
    assert result["listed"] is True, "a later session sees it without reloading anything"
    index = (root / "MEMORY.md").read_text(encoding="utf-8")
    assert "bisect-flaky.md" in index and "existing.md" in index, "the index is derived from the folder"


def test_bash_counts_as_write_capable(tmp_path: Path) -> None:
    result = run(
        '''
        console.log(JSON.stringify({
          bash: sa.isMemoryWritable(["read", "bash"]),
          powershell: sa.isMemoryWritable(["read", "powershell"]),
          edit: sa.isMemoryWritable(["edit"]),
          readOnly: sa.isMemoryWritable(["read", "grep", "find", "ls"]),
          none: sa.isMemoryWritable([]),
          undefined: sa.isMemoryWritable(undefined),
        }));
        ''',
        tmp_path,
    )
    assert result["bash"] is True and result["powershell"] is True and result["edit"] is True
    assert result["readOnly"] is False, "a shell can write, so bash is not read-only"
    assert result["none"] is False and result["undefined"] is False


def test_entry_name_traversal_oversize_and_missing_description_are_refused(tmp_path: Path) -> None:
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const traversal = sa.appendMemoryEntry(root,
          { name: "../../../escape", description: "d", body: "b" }, { writable: true });
        const oversized = sa.appendMemoryEntry(root,
          { name: "big", description: "d", body: "y".repeat(sa.MEMORY_ENTRY_MAX_BYTES + 10) }, { writable: true });
        const noDescription = sa.appendMemoryEntry(root,
          { name: "nodesc", description: "  ", body: "b" }, { writable: true });
        console.log(JSON.stringify({ traversal, oversized, noDescription }));
        ''',
        tmp_path,
    )
    # A traversal name is refused at the naming gate, before path containment is
    # even consulted: the first check that can reject it does. Both gates exist;
    # asserting the refusal and the absence of an escaped file is the property.
    refusals = {
        "traversal": ("Invalid memory entry name", "outside the Agent Memory folder"),
        "oversized": ("cap",),
        "noDescription": ("description",),
    }
    for key, needles in refusals.items():
        outcome = result[key]
        assert isinstance(outcome, dict) and outcome["ok"] is False, key
        assert any(needle in str(outcome["error"]) for needle in needles), f"{key}: {outcome['error']}"
    assert not (tmp_path / "escape.md").exists()
    assert not list(tmp_path.glob("escape.md")), "nothing may be written outside the memory root"


# ── Rule: a generalizing lesson is proposed, not merged ──


def test_proposals_are_recorded_and_are_not_entries(tmp_path: Path) -> None:
    root = tmp_path / "agents" / "reviewer"
    seed_entry(root, "existing", "Use when needed.", "body")
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const proposed = sa.writeMemoryProposal(root, {
          title: "Bisect flaky suites",
          capability: "Bisect by last-failed set rather than by file order.",
          applicability: "Suites where a test passes alone.",
          limits: "Assumes deterministic ordering within a file.",
          evidence: "Two runs on project X.",
        });
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"] });
        console.log(JSON.stringify({
          proposed,
          inIndex: block.text.includes("Bisect flaky suites"),
          proposalIsNotAnEntry: block.text.includes("proposals/"),
        }));
        ''',
        tmp_path,
    )
    proposed = result["proposed"]
    assert isinstance(proposed, dict) and proposed["ok"] is True
    assert (root / "proposals").is_dir()
    assert len(list((root / "proposals").glob("*.md"))) == 1
    assert result["inIndex"] is False, "a proposal is not memory and must not appear in the index"


def test_read_only_agent_may_still_propose(tmp_path: Path) -> None:
    result = run(
        '''
        const root = sa.agentMemoryRoot("reviewer");
        const block = sa.buildAgentMemoryBlock({ agentName: "reviewer", tools: ["read"] });
        const proposed = sa.writeMemoryProposal(root, {
          title: "t", capability: "c", applicability: "a", limits: "l",
        });
        console.log(JSON.stringify({ writable: block.writable, proposed }));
        ''',
        tmp_path,
    )
    assert result["writable"] is False
    assert result["proposed"]["ok"] is True, "proposing is reporting, not writing memory"


# ── Rule: a Temporary Agent owns no Agent Memory ──


def test_session_scoped_definition_never_gets_memory(tmp_path: Path) -> None:
    result = run(
        '''
        const registered = sa.registerSessionAgent({
          name: "temp-agent", description: "d", tools: ["read"], prompt: "p", memory: true,
        });
        sa.clearSessionAgents();
        console.log(JSON.stringify({ memory: registered.memory, scope: registered.scope, isolation: registered.isolation }));
        ''',
        tmp_path,
    )
    assert result["memory"] is False, "a Temporary Agent owns no Agent Memory, whatever it asked for"
    assert result["scope"] == "session"


def test_persisted_definition_opts_in_explicitly(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    agents.mkdir(parents=True)
    (agents / "with-memory.md").write_text(
        "---\nname: with-memory\ndescription: d\ntools: read, bash\nmemory: true\n---\nRole body.\n",
        encoding="utf-8",
    )
    (agents / "without-memory.md").write_text(
        "---\nname: without-memory\ndescription: d\ntools: read\n---\nRole body.\n",
        encoding="utf-8",
    )
    (agents / "shared.md").write_text(
        "---\nname: shared\ndescription: d\ntools: read\nworktree: false\n---\nRole body.\n",
        encoding="utf-8",
    )
    result = run(
        '''
        const found = sa.discoverAgents();
        const pick = (name) => {
          const agent = found.get(name);
          return agent ? { memory: agent.memory, isolation: agent.isolation, worktree: agent.worktree } : null;
        };
        console.log(JSON.stringify({
          withMemory: pick("with-memory"),
          withoutMemory: pick("without-memory"),
          shared: pick("shared"),
          defaultIsolated: pick("without-memory").isolation,
        }));
        ''',
        tmp_path,
    )
    assert result["withMemory"] == {"memory": True, "isolation": "isolated", "worktree": True}
    assert result["withoutMemory"]["memory"] is False, "absent means no memory folder"
    assert result["shared"] == {"memory": False, "isolation": "shared", "worktree": False}
    assert result["defaultIsolated"] == "isolated", (
        "isolation is the default: a durable per-Agent workspace is what makes Pi's "
        "per-working-directory session storage usable as working memory"
    )

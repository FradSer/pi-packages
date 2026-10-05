"""Regression contracts for private storage write boundaries.

Contract: features/storage-hardening.feature. Every case uses an isolated
agent directory and a real Node filesystem call; no user configuration is
read or written.
"""

from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, run_node

MEMORY = (PACKAGE / "src" / "memory.ts").as_uri()
AGENTS = (PACKAGE / "src" / "agents.ts").as_uri()
MIGRATION = (PACKAGE / "src" / "migration.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    project = tmp_path / "project"
    project.mkdir()
    return run_node(
        f'''import * as memory from {json.dumps(MEMORY)};
        import * as agents from {json.dumps(AGENTS)};
        import * as migration from {json.dumps(MIGRATION)};
        import fs from "node:fs";
        import path from "node:path";
        const root = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer", "memory");
        const put = (file, body) => {{ fs.mkdirSync(path.dirname(file), {{ recursive: true }}); fs.writeFileSync(file, body); }};
        {script}''',
        env_overrides={
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
            "PI_TEST_CWD": str(project),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
        },
    )


def test_hard_linked_entry_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside.md");
      put(outside, "OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "lesson.md"));
      const append = memory.appendMemoryEntry(root, { name: "lesson", description: "d", body: "NEW" }, { writable: true });
      console.log(JSON.stringify({ append, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["append"]["ok"] is False
    assert result["outside"] == "OUTSIDE"
    assert result["links"] == 2


def test_hard_linked_index_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-index.md");
      put(outside, "INDEX OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "MEMORY.md"));
      const error = (() => { try { memory.writeMemoryIndexFile(root); return ""; } catch (e) { return e.message; } })();
      console.log(JSON.stringify({ error, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["error"]
    assert result["outside"] == "INDEX OUTSIDE"
    assert result["links"] == 2


def test_append_preflights_a_hard_linked_index_before_creating_entry(tmp_path: Path) -> None:
    result = run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-index.md");
      put(outside, "INDEX OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "MEMORY.md"));
      const append = memory.appendMemoryEntry(root, { name: "lesson", description: "d", body: "NEW" }, { writable: true });
      console.log(JSON.stringify({ append, entry: fs.existsSync(path.join(root, "lesson.md")), outside: fs.readFileSync(outside, "utf8") }));
    ''', tmp_path)
    assert result["append"]["ok"] is False
    assert result["entry"] is False
    assert result["outside"] == "INDEX OUTSIDE"


def test_same_title_proposals_survive_same_millisecond(tmp_path: Path) -> None:
    result = run('''
      const clock = Date.now; Date.now = () => 1700000000000;
      let first, second;
      try {
        first = memory.writeMemoryProposal(root, { title: "Same title", capability: "ONE", applicability: "a", limits: "l" });
        second = memory.writeMemoryProposal(root, { title: "Same title", capability: "TWO", applicability: "a", limits: "l" });
      } finally { Date.now = clock; }
      const files = fs.readdirSync(path.join(root, "proposals")).sort();
      console.log(JSON.stringify({ first, second, files, contents: files.map(name => fs.readFileSync(path.join(root, "proposals", name), "utf8")) }));
    ''', tmp_path)
    assert result["first"]["ok"] is True and result["second"]["ok"] is True
    assert len(result["files"]) == 2
    assert any("ONE" in body for body in result["contents"])
    assert any("TWO" in body for body in result["contents"])


def test_hard_linked_definition_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-agent.md");
      put(outside, "OUTSIDE DEFINITION");
      const destination = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer", "agent.md");
      fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.linkSync(outside, destination);
      const error = (() => { try { agents.persistAgentDefinition({ name: "reviewer", description: "d", tools: [], prompt: "p" }, "user"); return ""; } catch (e) { return e.message; } })();
      console.log(JSON.stringify({ error, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["error"]
    assert result["outside"] == "OUTSIDE DEFINITION"
    assert result["links"] == 2


def test_migration_refuses_hard_linked_legacy_source(tmp_path: Path) -> None:
    result = run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-memory.md");
      put(outside, "OUTSIDE MEMORY");
      const sourceRoot = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer");
      put(path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer.md"), "---\\nname: reviewer\\ndescription: d\\ntools: read\\n---\\nROLE\\n");
      fs.mkdirSync(sourceRoot, { recursive: true }); fs.linkSync(outside, path.join(sourceRoot, "lesson.md"));
      const plan = migration.planAgentMigration({ agentName: "reviewer", scope: "user", cwd: process.env.PI_TEST_CWD });
      console.log(JSON.stringify({ status: plan.status, blocked: plan.blocked, outside: fs.readFileSync(outside, "utf8"), canonical: fs.existsSync(path.join(sourceRoot, "memory", "lesson.md")) }));
    ''', tmp_path)
    assert result["status"] == "blocked"
    assert result["outside"] == "OUTSIDE MEMORY"
    assert result["canonical"] is False
    assert any("linked" in block["message"].lower() for block in result["blocked"])


def test_oversized_proposal_is_refused_before_any_write(tmp_path: Path) -> None:
    result = run('''
      const proposal = memory.writeMemoryProposal(root, {
        title: "Too large", capability: "x".repeat(memory.MEMORY_ENTRY_MAX_BYTES),
        applicability: "a", limits: "l", evidence: "e",
      });
      console.log(JSON.stringify({ proposal, root: fs.existsSync(root), proposals: fs.existsSync(path.join(root, "proposals")) }));
    ''', tmp_path)
    assert result["proposal"]["ok"] is False
    assert "cap" in result["proposal"]["error"].lower()
    assert result["root"] is False and result["proposals"] is False


def test_exact_utf8_proposal_budget_preserves_complete_bytes(tmp_path: Path) -> None:
    result = run('''
      const RealDate = Date; const fixed = RealDate.parse("2026-01-01T00:00:00.000Z");
      class FixedDate extends RealDate { constructor(...args) { super(args.length ? args[0] : fixed); } static now() { return fixed; } }
      globalThis.Date = FixedDate;
      const title = "Boundary", applicability = "when", limits = "limits";
      const build = capability => ["---", `title: ${title}`, "status: proposed", `created: ${new Date().toISOString()}`, "---", "", "## Capability", "", capability, "", "## Applicability", "", applicability, "", "## Limits", "", limits, ""].join("\\n");
      const budget = memory.MEMORY_ENTRY_MAX_BYTES; const emptyBytes = Buffer.byteLength(build(""), "utf8");
      const remaining = budget - emptyBytes; const multibyte = "界".repeat(Math.floor(remaining / 3)) + "x".repeat(remaining % 3);
      const expected = build(multibyte); const proposal = memory.writeMemoryProposal(root, { title, capability: multibyte, applicability, limits });
      const file = proposal.ok ? fs.readFileSync(proposal.file, "utf8") : "";
      console.log(JSON.stringify({ proposal, bytes: Buffer.byteLength(file, "utf8"), exact: file === expected, tail: file.slice(-12) }));
    ''', tmp_path)
    assert result["proposal"]["ok"] is True
    assert result["bytes"] == 16 * 1024
    assert result["exact"] is True
    assert result["tail"].endswith("limits\n")

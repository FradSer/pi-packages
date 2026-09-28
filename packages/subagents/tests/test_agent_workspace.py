"""Durable per-Agent workspaces.

Contract: packages/subagents/features/agent-workspace.feature

The property that matters most is durability. Pi groups sessions by working
directory, so a workspace that changes or disappears per task orphans that Agent's
working memory every attempt. These tests assert the path is stable, that a second
attempt reuses it, and that completion never removes it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from subagents_helpers import PACKAGE, run_node

SUBAGENTS = (PACKAGE / "index.ts").as_uri()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "agent@example.test"),
        ("config", "user.name", "agent"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], capture_output=True, text=True, check=True)
    return repo


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f'''\
        import * as sa from "{SUBAGENTS}";
        {script}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent-dir")},
    )


# ── Rule: the workspace is durable and stable per Agent and project ──


def test_workspace_path_is_stable_and_scoped(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run(
        f'''
        const cwd = {str(repo)!r};
        const first = sa.agentWorkspacePath("reviewer", cwd);
        const again = sa.agentWorkspacePath("reviewer", cwd);
        console.log(JSON.stringify({{
          first,
          stable: first === again,
          underAgentDir: first.startsWith(process.env.PI_CODING_AGENT_DIR),
          inWorkspaces: first.includes("/workspaces/reviewer/"),
          // A different Agent gets a different home, and so does a different project.
          otherAgent: sa.agentWorkspacePath("builder", cwd) !== first,
          otherProject: sa.agentWorkspacePath("reviewer", {str(tmp_path)!r}) !== first,
          // The workspace is not inside the checkout: durable state does not
          // belong in a working tree.
          outsideRepo: !first.startsWith(cwd),
        }}));
        ''',
        tmp_path,
    )
    assert result["stable"] is True, "a changing path would orphan the Pi session group"
    assert result["underAgentDir"] is True
    assert result["inWorkspaces"] is True
    assert result["otherAgent"] is True and result["otherProject"] is True
    assert result["outsideRepo"] is True


def test_first_attempt_creates_and_second_reuses(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run(
        f'''
        const cwd = {str(repo)!r};
        const first = sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd, isolation: "isolated" }});
        const second = sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd, isolation: "isolated" }});
        console.log(JSON.stringify({{ first, second }}));
        ''',
        tmp_path,
    )
    first, second = result["first"], result["second"]
    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["isolation"] == "worktree" and first["reused"] is False
    assert first["branch"] == "agent/reviewer", "a durable branch gives the workspace continuity"
    assert Path(str(first["cwd"])).is_dir()
    assert second["reused"] is True, "the second attempt must reuse the same workspace"
    assert second["cwd"] == first["cwd"], "reuse is what preserves the Pi session group"


def test_shared_isolation_and_non_repository_fall_back_with_a_reason(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    result = run(
        f'''
        console.log(JSON.stringify({{
          shared: sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd: {str(repo)!r}, isolation: "shared" }}),
          notRepo: sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd: {str(plain)!r}, isolation: "isolated" }}),
        }}));
        ''',
        tmp_path,
    )
    shared = result["shared"]
    assert isinstance(shared, dict)
    assert shared["isolation"] == "none" and shared["cwd"] == str(repo)
    not_repo = result["notRepo"]
    assert isinstance(not_repo, dict)
    assert not_repo["isolation"] == "none"
    assert "not a git repository" in str(not_repo["reason"]), (
        "falling back must say so rather than pretending the child is isolated"
    )


# ── Rule: completion preserves, only release removes ──


def test_preserve_commits_and_keeps_the_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run(
        f'''
        const cwd = {str(repo)!r};
        const ws = sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd, isolation: "isolated" }});
        const out = ws.cwd + "/output.txt";
        const {{ writeFileSync }} = await import("node:fs");
        writeFileSync(out, "attempt one\\n");
        const preserved = sa.preserveAgentWorkspace({{ agentName: "reviewer", cwd: ws.cwd }});
        const stillThere = await import("node:fs").then((fs) => fs.existsSync(ws.cwd));
        console.log(JSON.stringify({{ ws, preserved, stillThere, branch: preserved.branch }}));
        ''',
        tmp_path,
    )
    preserved = result["preserved"]
    assert isinstance(preserved, dict) and preserved["ok"] is True
    assert preserved["committed"] is True, "an interrupted attempt must still leave its work on the branch"
    assert result["stillThere"] is True, "completion never removes a durable workspace"
    workspace_cwd = str(result["ws"]["cwd"]) if isinstance(result["ws"], dict) else ""
    assert Path(workspace_cwd).is_dir()
    commits = git(Path(workspace_cwd), "log", "--oneline", "-1")
    assert "preserve attempt output" in commits


def test_preserve_on_a_clean_workspace_commits_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run(
        f'''
        const ws = sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd: {str(repo)!r}, isolation: "isolated" }});
        console.log(JSON.stringify(sa.preserveAgentWorkspace({{ agentName: "reviewer", cwd: ws.cwd }})));
        ''',
        tmp_path,
    )
    assert result["ok"] is True
    assert result["committed"] is False, "a clean tree is not an error and needs no commit"


def test_release_removes_only_on_explicit_request(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run(
        f'''
        const cwd = {str(repo)!r};
        const ws = sa.ensureAgentWorkspace({{ agentName: "reviewer", cwd, isolation: "isolated" }});
        const released = sa.releaseAgentWorkspace({{ agentName: "reviewer", cwd }});
        const fs = await import("node:fs");
        console.log(JSON.stringify({{ ws, released, gone: !fs.existsSync(ws.cwd) }}));
        ''',
        tmp_path,
    )
    assert result["released"]["ok"] is True
    assert result["gone"] is True, "an explicit release removes the workspace"
    # The branch survives, so preserved work stays retrievable.
    branches = git(repo, "branch", "--list", "agent/reviewer")
    assert "agent/reviewer" in branches


def test_a_failed_spawn_never_removes_a_reused_workspace() -> None:
    """Asserted on the consumer's guard rather than by spawning: `discardWorkspaceQuietly`
    must skip any workspace it did not create."""
    source = (PACKAGE.parent / "agent-teams" / "src" / "team-machine.ts").read_text(encoding="utf-8")
    assert "workspace.reused" in source, "the guard must test whether this spawn created the workspace"
    assert "function discardWorkspaceQuietly(name: string, workspace: AgentWorkspace | undefined)" in source
    body = source.split("function discardWorkspaceQuietly", 1)[1].split("\n}", 1)[0]
    assert "if (!workspace || workspace.isolation !== \"worktree\" || workspace.reused) return;" in body

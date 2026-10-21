"""Scenarios of features/codemode-skill-tools.feature.

Given routed leaf skills, When Pi loads the extension or a skill tool is called,
Then the model reaches a leaf skill through codemode search and call, and keeps
the routing-suggestion fallback while codemode is unavailable.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from test_skill_router import (
    PACKAGE,
    exposed_root,
    gateway_root,
    git,
    installed_collection,
    run_harness,
    source_repo,
    write_skill,
)

PREFIX = "skill_router__"


def sanitize(value: str) -> str:
    """Every character outside [A-Za-z0-9_] becomes `_`, as MCP tool names do."""
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def tool_name(collection_id: str, skill: str) -> str:
    """The registered name of one routed leaf skill."""
    return f"{PREFIX}{sanitize(collection_id)}__{sanitize(skill)}"


def skill_tools(agent_dir: Path) -> list[dict[str, object]]:
    result = run_harness(agent_dir, "tools")
    assert result["ok"] is True, result
    return [tool for tool in result["tools"] if tool["name"] != "codemode"]


def tool_names(agent_dir: Path) -> list[str]:
    return sorted(str(tool["name"]) for tool in skill_tools(agent_dir))


def test_each_routed_leaf_skill_is_registered_as_a_codemode_tool(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    tools = skill_tools(agent_dir)
    assert sorted(tool["name"] for tool in tools) == sorted(
        [tool_name(collection_id, "bug-diagnosis"), tool_name(collection_id, "code-review")]
    )
    for tool in tools:
        assert tool["exposure"] == "codemode"
        assert tool["parameterKeys"] == []
        assert tool["promptGuidelines"], tool
        assert tool["reachesTools"] is False, tool


def test_a_disabled_collection_registers_no_skill_tool(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    assert run_harness(agent_dir, "toggle", collection_id, "off")["ok"] is True
    assert skill_tools(agent_dir) == []
    assert run_harness(agent_dir, "menu-registered")["command"] is True


def test_a_collection_is_one_search_namespace(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    gateway = (gateway_root(agent_dir, collection_id) / "SKILL.md").read_text(encoding="utf-8")
    namespaces = {str(tool["namespace"]["name"]) for tool in skill_tools(agent_dir)}
    assert namespaces == {f"{PREFIX}{sanitize(collection_id)}"}
    for tool in skill_tools(agent_dir):
        namespace = tool["namespace"]
        assert collection_id in namespace["aliases"]
        assert namespace["description"] == "Expert workflows spanning bug diagnosis and code review."
        assert namespace["instructions"] == gateway


def test_skill_tool_description_carries_summary_and_upstream_description(tmp_path: Path) -> None:
    repo = tmp_path / "trigger-description"
    write_skill(
        repo,
        "skills/flaky-tests",
        "flaky-tests",
        "When the user wants to debug a failing test. Also use when a stack trace or a flaky suite is involved.",
    )
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(repo))
    assert added["ok"] is True, added
    [tool] = skill_tools(agent_dir)
    description = str(tool["description"])
    assert description.startswith("Debug a failing test.")
    assert "Also use when a stack trace or a flaky suite is involved." in description
    assert "leaves/" not in description
    assert "exposed" not in description
    assert "synced from" not in description


def test_skill_tool_description_never_repeats_the_upstream_description(tmp_path: Path, source_repo: Path) -> None:
    """Given an upstream description whose first sentence is the summary, When
    the extension loads, Then the searchable text is not duplicated."""
    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(source_repo))
    assert added["ok"] is True, added
    [tool] = [tool for tool in skill_tools(agent_dir) if tool["name"] == tool_name("upstream", "bug-diagnosis")]
    assert tool["description"] == "Diagnose tricky bugs systematically"


def test_calling_a_skill_tool_returns_instructions_and_directory(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    name = tool_name(collection_id, "bug-diagnosis")
    skill_file = exposed_root(agent_dir, collection_id) / "leaves" / "bug-diagnosis" / "SKILL.md"

    result = run_harness(agent_dir, "call", name)
    assert result["ok"] is True, result
    assert result["isError"] is False, result
    structured = result["structuredContent"]
    assert structured["ok"] is True
    assert structured["collection"] == collection_id
    assert structured["skill"] == "bug-diagnosis"
    assert structured["tool"] == name
    assert structured["directory"] == str(skill_file.parent)
    assert structured["skillFile"] == str(skill_file)
    assert structured["truncated"] is False
    assert structured["body"] == skill_file.read_text(encoding="utf-8")
    assert result["text"] == structured["body"]
    assert "# bug-diagnosis" in result["text"]
    assert "Follow the workflow." in result["text"]


def test_oversized_body_is_truncated_with_a_pointer_to_its_file(tmp_path: Path) -> None:
    repo = tmp_path / "huge-skill"
    skill_dir = repo / "skills" / "huge"
    skill_dir.mkdir(parents=True)
    body = "Follow these steps carefully and re-check each one.\n" * 700
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: huge\ndescription: Apply a very long workflow\n---\n\n{body}",
        encoding="utf-8",
    )
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(repo))
    assert added["ok"] is True, added
    collection_id = str(added["id"])
    skill_file = exposed_root(agent_dir, collection_id) / "leaves" / "huge" / "SKILL.md"
    complete = skill_file.read_text(encoding="utf-8")
    assert len(complete) > 20000

    result = run_harness(agent_dir, "call", tool_name(collection_id, "huge"))
    assert result["ok"] is True, result
    structured = result["structuredContent"]
    assert structured["truncated"] is True
    # The bound is exact: the instructions stop at 20000 characters and only the
    # truncation note follows them.
    assert structured["body"].startswith(complete[:20000])
    # The note pins the bound exactly: a bound of 25000 would report a different
    # omitted count, so this fails when the bound moves.
    assert f"\u2026{len(complete) - 20000} chars truncated\u2026" in structured["body"]
    assert str(skill_file) in structured["body"]


def test_skill_tool_refuses_content_outside_the_exposed_tree(installed_collection, tmp_path: Path) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    leaf = exposed_root(agent_dir, collection_id) / "leaves" / "bug-diagnosis" / "SKILL.md"
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: bug-diagnosis\ndescription: outside\n---\n\nSECRET OUTSIDE CONTENT\n", encoding="utf-8")
    leaf.unlink()
    leaf.symlink_to(outside)

    result = run_harness(agent_dir, "call", tool_name(collection_id, "bug-diagnosis"))
    assert result["ok"] is True, result
    assert result["isError"] is True, result
    assert "SECRET OUTSIDE CONTENT" not in result["text"]
    assert result["structuredContent"]["ok"] is False
    assert result["structuredContent"]["error"]


def test_removed_collection_cannot_still_serve_a_skill(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "call-after-remove", tool_name(collection_id, "bug-diagnosis"), collection_id)
    assert result["ok"] is True, result
    assert result["isError"] is True, result
    assert collection_id in str(result["structuredContent"]["error"])


def test_codemode_availability_selects_the_tools_channel(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    routed = run_harness(agent_dir, "route", "please diagnose this bug", "--codemode", "active")
    assert routed["ok"] is True, routed
    assert "skill_router" not in routed["sections"], routed["sections"]
    assert routed["systemPrompt"] == "base system prompt"
    assert run_harness(agent_dir, "tools", "--codemode", "active")["activeTools"] == ["codemode"]
    assert tool_name(collection_id, "bug-diagnosis") in tool_names(agent_dir)


def test_an_allowlist_that_hides_the_skill_tools_keeps_the_fallback(installed_collection) -> None:
    """Given codemode is active but the session's tool allowlist removed the
    skill tools, When a prompt matches a route, Then the routing suggestion is
    added, because a codemode call could not reach the tool."""
    agent_dir = installed_collection["agent_dir"]
    routed = run_harness(
        agent_dir,
        "route",
        "please diagnose this bug",
        "--codemode",
        "active",
        "--tool-allowlist",
        "read,codemode",
    )
    assert routed["ok"] is True, routed
    assert "bug-diagnosis" in routed["sections"]["skill_router"]
    tools = run_harness(agent_dir, "tools", "--codemode", "active", "--tool-allowlist", "read,codemode")
    assert tools["sessionTools"] == ["codemode"]


def test_a_codemode_that_reaches_nothing_keeps_the_fallback(installed_collection) -> None:
    """Given codemode is active and declares reachesTools but names nothing it
    reaches, When a prompt matches a route, Then the routing suggestion is added:
    the declaration alone must not suppress the only working path."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    tools = run_harness(agent_dir, "tools", "--codemode", "misdeclared")
    assert tools["activeTools"] == ["codemode"]
    assert tool_name(collection_id, "bug-diagnosis") in tools["sessionTools"]
    routed = run_harness(agent_dir, "route", "please diagnose this bug", "--codemode", "misdeclared")
    assert routed["ok"] is True, routed
    assert "bug-diagnosis" in routed["sections"]["skill_router"]


def test_a_codemode_that_fails_to_answer_keeps_the_fallback(installed_collection) -> None:
    """Given the registered codemode throws when asked what it reaches, When a
    prompt matches a route, Then the turn keeps its only working path."""
    agent_dir = installed_collection["agent_dir"]
    tools = run_harness(agent_dir, "tools", "--codemode", "throwing")
    assert tools["activeTools"] == ["codemode"]
    routed = run_harness(agent_dir, "route", "please diagnose this bug", "--codemode", "throwing")
    assert routed["ok"] is True, routed
    assert "bug-diagnosis" in routed["sections"]["skill_router"]


def test_registered_but_inactive_codemode_keeps_the_fallback(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    routed = run_harness(agent_dir, "route", "please diagnose this bug", "--codemode", "registered")
    assert routed["ok"] is True, routed
    guidance = routed["sections"]["skill_router"]
    assert "bug-diagnosis" in guidance
    assert "bug-diagnosis" in routed["systemPrompt"]


def test_session_without_codemode_keeps_the_fallback(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["ok"] is True, routed
    assert "bug-diagnosis" in routed["sections"]["skill_router"]


def test_gateway_names_each_workflows_skill_tool(installed_collection) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    gateway = (gateway_root(agent_dir, collection_id) / "SKILL.md").read_text(encoding="utf-8")
    assert tool_name(collection_id, "bug-diagnosis") in gateway
    assert tool_name(collection_id, "code-review") in gateway
    assert "../leaves/bug-diagnosis/SKILL.md" in gateway
    assert "- `bug-diagnosis` — Diagnose tricky bugs systematically." in gateway


def make_repo(path: Path, skill: str, description: str) -> Path:
    """A one-skill upstream repository with its own commit."""
    write_skill(path, f"skills/{skill}", skill, description)
    git(path, "init", "-q", "-b", "main")
    git(path, "add", "-A")
    git(path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return path


def test_a_partially_hidden_tool_set_offers_the_fallback_for_the_hidden_skill(installed_collection) -> None:
    """Given the allowlist kept one routed skill's tool and removed the other,
    When a prompt matches the removed skill, Then the routing suggestion is
    added: the surviving sibling tool must not stand in for it."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    allowlist = f"read,codemode,{tool_name(collection_id, 'code-review')}"
    routed = run_harness(
        agent_dir, "route", "please diagnose this bug", "--codemode", "active", "--tool-allowlist", allowlist
    )
    assert routed["ok"] is True, routed
    assert "bug-diagnosis" in routed["sections"]["skill_router"]
    tools = run_harness(agent_dir, "tools", "--codemode", "active", "--tool-allowlist", allowlist)
    assert tool_name(collection_id, "bug-diagnosis") not in tools["sessionTools"]
    assert tool_name(collection_id, "code-review") in tools["sessionTools"]


def test_installing_a_collection_applies_its_skill_tools_immediately(tmp_path: Path, source_repo: Path) -> None:
    """Given the user installs a collection through the menu, When the flow
    finishes, Then its skill tools exist in that same session, without a reload."""
    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "menu-add", str(source_repo))
    assert added["ok"] is True, added
    exposed = {item["name"]: item["exposure"] for item in added["registered"]}
    assert exposed[tool_name("upstream", "bug-diagnosis")] == "codemode"
    assert exposed[tool_name("upstream", "code-review")] == "codemode"


def test_a_refresh_updates_an_existing_tools_searchable_text(installed_collection) -> None:
    """Given a collection's capability summary is edited while the session is
    live, When the tools are refreshed, Then the existing skill tools carry the new
    namespace description and gateway instructions rather than the old ones."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "refresh", "--describe", collection_id, "Rewritten capability summary.")
    assert result["ok"] is True, result
    [tool] = [item for item in result["registered"] if item["name"] == tool_name(collection_id, "bug-diagnosis")]
    assert tool["exposure"] == "codemode"
    assert tool["namespaceDescription"] == "Rewritten capability summary."
    assert 'description: "Rewritten capability summary."' in tool["instructions"]


def test_a_refresh_withdraws_the_tools_of_a_removed_collection(installed_collection) -> None:
    """Given a collection is removed while the session is live, When the tools are
    refreshed, Then its skill tools are hidden and the command still exists."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "refresh", "--remove", collection_id)
    assert result["ok"] is True, result
    exposures = {item["name"]: item["exposure"] for item in result["registered"]}
    assert exposures[tool_name(collection_id, "bug-diagnosis")] == "hidden"
    assert exposures[tool_name(collection_id, "code-review")] == "hidden"
    assert run_harness(agent_dir, "menu-registered")["command"] is True


def test_a_refresh_withdraws_the_tools_of_a_disabled_collection(installed_collection) -> None:
    """Given a collection is disabled while the session is live, When the tools are
    refreshed, Then its skill tools are hidden rather than removed."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "refresh", "--disable", collection_id)
    assert result["ok"] is True, result
    exposures = {item["name"]: item["exposure"] for item in result["registered"]}
    assert exposures[tool_name(collection_id, "bug-diagnosis")] == "hidden"
    assert exposures[tool_name(collection_id, "code-review")] == "hidden"


def test_a_collection_added_after_load_keeps_the_fallback(tmp_path: Path) -> None:
    """Given one collection registered its skill tools, When another collection is
    added while the session is live and a prompt matches it, Then the routing
    suggestion is added, because the new collection has no tools until /reload."""
    first = make_repo(tmp_path / "first-source", "bug-diagnosis", "Diagnose tricky bugs systematically")
    second = make_repo(
        tmp_path / "second-source",
        "seo-audit",
        "When the user wants to audit, review, or diagnose SEO issues.",
    )
    agent_dir = tmp_path / "agent"
    assert run_harness(agent_dir, "add", str(first))["ok"] is True

    routed = run_harness(
        agent_dir, "route-after-add", str(second), "please audit the SEO of this page", "--codemode", "active"
    )
    assert routed["ok"] is True, routed
    assert "seo-audit" in routed["sections"]["skill_router"]
    assert "skill_router__first_source__bug_diagnosis" in routed["registered"]
    assert not any("second_source" in name for name in routed["registered"])
    assert routed["added"] == "second-source"


def test_a_symlinked_exposed_directory_refuses_the_call(installed_collection, tmp_path: Path) -> None:
    """Given the router's exposed directory is replaced by a symlink to an
    outside tree, When the skill tool is called, Then the call is refused."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    evil = tmp_path / "evil" / "collections" / collection_id / "leaves" / "bug-diagnosis"
    evil.mkdir(parents=True)
    (evil / "SKILL.md").write_text(
        "---\nname: bug-diagnosis\ndescription: hijacked\n---\n\nSECRET HIJACKED CONTENT\n", encoding="utf-8"
    )
    exposed = agent_dir / "skill-router" / "exposed"
    exposed.rename(agent_dir / "skill-router" / "exposed-real")
    exposed.symlink_to(tmp_path / "evil")

    result = run_harness(agent_dir, "call", tool_name(collection_id, "bug-diagnosis"))
    assert result["ok"] is True, result
    assert result["isError"] is True, result
    assert "SECRET HIJACKED CONTENT" not in result["text"]
    assert result["structuredContent"]["ok"] is False


def test_a_body_cut_at_the_bound_never_splits_a_surrogate_pair(tmp_path: Path) -> None:
    """Given the cut lands on a surrogate pair, When the skill tool is called,
    Then the body is valid text with no half pair."""
    repo = tmp_path / "surrogate-skill"
    skill_dir = repo / "skills" / "pairs"
    skill_dir.mkdir(parents=True)
    # The astral character's high surrogate lands exactly at the bound, so a cut
    # at 20000 would return half a pair. The source already carries
    # `disable-model-invocation`, so materialization rewrites the frontmatter to
    # the identical text and the bound keeps the same offset.
    frontmatter = (
        "---\nname: pairs\ndescription: Apply a body with an astral character\n"
        "disable-model-invocation: true\n---\n\n"
    )
    content = f"{frontmatter}{'A' * (19999 - len(frontmatter))}\U0001F600{'B' * 50}"
    assert content[19999] == "\U0001F600", "the pair must straddle the bound"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(repo))
    assert added["ok"] is True, added
    skill_file = exposed_root(agent_dir, str(added["id"])) / "leaves" / "pairs" / "SKILL.md"
    assert skill_file.read_text(encoding="utf-8") == content, "materialization must keep the offsets"
    result = run_harness(agent_dir, "call", tool_name(str(added["id"]), "pairs"))
    assert result["ok"] is True, result
    structured = result["structuredContent"]
    assert structured["truncated"] is True
    body = structured["body"]
    assert body.startswith(content[:19999])
    assert "\U0001F600" not in body
    assert str(skill_file) in body
    body.encode("utf-8")  # a lone surrogate would raise instead


def test_a_deleted_clone_degrades_to_the_workflow_summary(installed_collection) -> None:
    """Given the cached clone is gone, When the extension loads, Then the
    searchable text is the workflow summary alone and the call still serves the
    materialized instructions."""
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    for entry in (agent_dir / "skill-router" / "cache").iterdir():
        shutil.rmtree(entry)
    [tool] = [item for item in skill_tools(agent_dir) if item["name"] == tool_name(collection_id, "bug-diagnosis")]
    assert tool["description"] == "Diagnose tricky bugs systematically."
    assert tool["namespace"]["instructions"]

    result = run_harness(agent_dir, "call", tool_name(collection_id, "bug-diagnosis"))
    assert result["ok"] is True, result
    assert result["isError"] is False, result
    assert "# bug-diagnosis" in result["text"]


def test_feature_file_lists_the_tool_channel_scenarios() -> None:
    feature = (PACKAGE / "features" / "codemode-skill-tools.feature").read_text(encoding="utf-8")
    for title in (
        "Each routed leaf skill is registered as a codemode tool",
        "A disabled collection registers no skill tool",
        "A collection is one search namespace",
        "A skill tool is searchable by its summary and its upstream description",
        "The searchable text never repeats the upstream description",
        "Calling a skill tool returns instructions and the skill directory",
        "An oversized skill body is truncated with a pointer to its file",
        "A skill tool refuses content outside the exposed tree",
        "A removed collection cannot still serve a skill",
        "Codemode availability selects the tools channel",
        "An allowlist that hides the skill tools keeps the fallback",
        "A codemode that reaches nothing keeps the fallback",
        "A codemode that fails to answer keeps the fallback",
        "A registered but inactive codemode keeps the fallback",
        "A partially hidden tool set offers the fallback for the hidden skill",
        "Installing a collection applies its skill tools immediately",
        "A refresh updates an existing tool's searchable text",
        "Removing a collection withdraws its skill tools",
        "Disabling a collection withdraws its skill tools",
        "A collection added after the extension loaded keeps the fallback",
        "A symlinked exposed directory refuses the call",
        "A deleted clone degrades to the workflow summary",
        "A body cut at the bound never splits a surrogate pair",
        "A session without codemode keeps the fallback",
        "The gateway names each workflow's skill tool",
    ):
        assert title in feature

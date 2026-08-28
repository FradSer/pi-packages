from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_harness(agent_dir: Path, *args: str, timeout: int = 120) -> dict[str, object]:
    completed = subprocess.run(
        ["npx", "tsx", str(PACKAGE / "tests" / "router_harness.ts"), *args],
        cwd=REPO,
        env={**os.environ, "PI_CODING_AGENT_DIR": str(agent_dir)},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def write_skill(repo: Path, rel_dir: str, name: str, description: str, extra_file: bool = False) -> None:
    skill_dir = repo / rel_dir
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nFollow the workflow.\n",
        encoding="utf-8",
    )
    if extra_file:
        (skill_dir / "references").mkdir(exist_ok=True)
        (skill_dir / "references" / "notes.md").write_text("# Notes\n", encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    write_skill(repo, "skills/bug-diagnosis", "bug-diagnosis", "Diagnose tricky bugs systematically", extra_file=True)
    write_skill(repo, "skills/code-review", "code-review", "Review code changes carefully")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


@pytest.fixture
def installed_collection(tmp_path: Path, source_repo: Path) -> dict[str, object]:
    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp")
    assert result["ok"] is True, result
    return {"agent_dir": agent_dir, "add": result}


def exposed_root(agent_dir: Path, collection_id: str) -> Path:
    return agent_dir / "skill-router" / "exposed" / collection_id


def read_registry(agent_dir: Path) -> dict[str, object]:
    registry_file = agent_dir / "skill-router" / "collections.json"
    if not registry_file.exists():
        return {"collections": []}
    return json.loads(registry_file.read_text(encoding="utf-8"))


def test_manifest_declares_extension_only_and_no_packaged_skills() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "pi-skill-router"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert "skills" not in manifest["pi"]
    assert not (PACKAGE / "skills").exists()
    assert not (PACKAGE / "tools").exists()
    assert f"**Package version:** {manifest['version']}" in (PACKAGE / "README.md").read_text(encoding="utf-8")


def test_add_collection_materializes_wrapped_skills(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp")
    assert result["ok"] is True, result
    collection_id = str(result["id"])

    cache = agent_dir / "skill-router" / "cache"
    assert any(cache.iterdir()), "repository must be cloned into the router cache"

    exposed = exposed_root(agent_dir, collection_id)
    leaf = exposed / "mp-bug-diagnosis" / "SKILL.md"
    assert leaf.is_file()
    frontmatter = leaf.read_text(encoding="utf-8").split("---", 2)[1]
    assert re.search(r"(?m)^name: mp-bug-diagnosis$", frontmatter)
    assert "disable-model-invocation: true" in frontmatter
    assert "Diagnose tricky bugs systematically" in frontmatter
    assert (exposed / "mp-bug-diagnosis" / "references" / "notes.md").is_file()
    assert (exposed / "mp-code-review" / "SKILL.md").is_file()

    gateway = (exposed / collection_id / "SKILL.md").read_text(encoding="utf-8")
    gateway_frontmatter = gateway.split("---", 2)[1]
    assert re.search(rf"(?m)^name: {re.escape(collection_id)}$", gateway_frontmatter)
    assert "disable-model-invocation: true" not in gateway_frontmatter
    assert "mp-bug-diagnosis" in gateway
    assert "mp-code-review" in gateway

    registry = read_registry(agent_dir)
    [entry] = registry["collections"]
    assert entry["id"] == collection_id
    assert entry["prefix"] == "mp"
    assert entry["enabled"] is True
    assert entry["source"]["repo"] == str(source_repo)
    assert {route["skill"] for route in entry["routes"]} == {"bug-diagnosis", "code-review"}
    for route in entry["routes"]:
        assert route["terms"], "routes must carry derived routing terms"
        assert route["path"], "routes must record the upstream skill path"


def test_add_with_subset_selection_materializes_only_selected(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp", "--skills", "bug-diagnosis")
    assert result["ok"] is True, result
    exposed = exposed_root(agent_dir, str(result["id"]))
    assert (exposed / "mp-bug-diagnosis" / "SKILL.md").is_file()
    assert not (exposed / "mp-code-review").exists()
    [entry] = read_registry(agent_dir)["collections"]
    assert [route["skill"] for route in entry["routes"]] == ["bug-diagnosis"]


def test_add_rejects_duplicate_prefix(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    first = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp", "--id", "one")
    assert first["ok"] is True, first
    second = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp", "--id", "two")
    assert second["ok"] is False
    assert "prefix" in str(second["error"]).lower()


def test_resources_discover_returns_exposed_collection(installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "discover")
    assert result["ok"] is True
    assert result["skillPaths"] == [str(exposed_root(agent_dir, collection_id))]
    names = {skill["name"] for skill in result["skills"]}
    assert names == {collection_id, "mp-bug-diagnosis", "mp-code-review"}
    for skill in result["skills"]:
        assert skill["disableModelInvocation"] is (skill["name"] != collection_id)


def test_route_high_confidence_suggests_leaf_with_real_path(installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "route", "please diagnose this bug")
    assert result["ok"] is True
    system_prompt = str(result["systemPrompt"])
    assert "mp-bug-diagnosis" in system_prompt
    assert collection_id in system_prompt
    assert str(exposed_root(agent_dir, collection_id) / "mp-bug-diagnosis" / "SKILL.md") in system_prompt
    assert result["prompt"] == "please diagnose this bug"
    assert result["message"] is None
    assert "<skill name=" not in system_prompt


def test_route_unmatched_prompt_has_no_guidance(installed_collection: dict[str, object]) -> None:
    result = run_harness(installed_collection["agent_dir"], "route", "what is the weather in Tokyo")
    assert result["systemPrompt"] == "base system prompt"


def test_route_explicit_invocations_bypass(installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    slash = run_harness(agent_dir, "route", "/skill:mp-bug-diagnosis investigate this bug")
    assert slash["systemPrompt"] == "base system prompt"
    embedded = run_harness(agent_dir, "route", "please use /skill:mp-bug-diagnosis to investigate this bug")
    assert embedded["systemPrompt"] == "base system prompt"
    punctuated = run_harness(agent_dir, "route", "please use /skill:mp-bug-diagnosis, then investigate this bug")
    assert punctuated["systemPrompt"] == "base system prompt"
    surrounded = run_harness(agent_dir, "route", "please use (/skill:mp-bug-diagnosis) to investigate this bug")
    assert surrounded["systemPrompt"] == "base system prompt"
    expanded = run_harness(agent_dir, "route", '<skill name="mp-bug-diagnosis">diagnose this bug</skill>')
    assert expanded["systemPrompt"] == "base system prompt"
    other_slash = run_harness(agent_dir, "route", "/status: diagnose this bug")
    assert "mp-bug-diagnosis" in str(other_slash["systemPrompt"])


def test_disabled_collection_is_neither_exposed_nor_routed(installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    toggled = run_harness(agent_dir, "toggle", collection_id, "off")
    assert toggled["ok"] is True and toggled["enabled"] is False
    discovered = run_harness(agent_dir, "discover")
    assert discovered["skillPaths"] == []
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"


def test_update_rematerializes_selection_and_ignores_new_skills(
    tmp_path: Path, source_repo: Path, installed_collection: dict[str, object]
) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    write_skill(source_repo, "skills/refactor", "refactor", "Refactor code safely")
    write_skill(source_repo, "skills/bug-diagnosis", "bug-diagnosis", "Diagnose tricky bugs methodically", extra_file=True)
    git(source_repo, "add", "-A")
    git(source_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "more")

    result = run_harness(agent_dir, "update", collection_id)
    assert result["ok"] is True, result
    exposed = exposed_root(agent_dir, collection_id)
    assert not (exposed / "mp-refactor").exists(), "new upstream skills stay unrouted until selected"
    frontmatter = (exposed / "mp-bug-diagnosis" / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    assert "Diagnose tricky bugs methodically" in frontmatter
    [entry] = read_registry(agent_dir)["collections"]
    assert {route["skill"] for route in entry["routes"]} == {"bug-diagnosis", "code-review"}


def test_selection_change_explicitly_adds_upstream_skill(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp", "--skills", "bug-diagnosis")
    assert added["ok"] is True, added
    collection_id = str(added["id"])

    selected = run_harness(agent_dir, "select", collection_id, "bug-diagnosis", "code-review")
    assert selected["ok"] is True, selected
    exposed = exposed_root(agent_dir, collection_id)
    assert (exposed / "mp-code-review" / "SKILL.md").is_file()
    [entry] = read_registry(agent_dir)["collections"]
    assert {route["skill"] for route in entry["routes"]} == {"bug-diagnosis", "code-review"}


def test_remove_deletes_exposed_dir_and_registry_entry(installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    result = run_harness(agent_dir, "remove", collection_id)
    assert result["ok"] is True
    assert not exposed_root(agent_dir, collection_id).exists()
    assert read_registry(agent_dir)["collections"] == []
    discovered = run_harness(agent_dir, "discover")
    assert discovered["skillPaths"] == []


def test_duplicate_upstream_skill_names_fail_materialization(tmp_path: Path) -> None:
    repo = tmp_path / "dupes"
    repo.mkdir()
    write_skill(repo, "a/tools", "same-name", "First copy")
    write_skill(repo, "b/tools", "same-name", "Second copy")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(repo), "--prefix", "zz")
    assert result["ok"] is False
    assert "collision" in str(result["error"]).lower() or "duplicate" in str(result["error"]).lower()
    exposed = agent_dir / "skill-router" / "exposed"
    assert not exposed.exists() or list(exposed.iterdir()) == []
    assert read_registry(agent_dir)["collections"] == []


def test_invalid_registry_entries_fail_closed(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.mkdir(parents=True)
    (root / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "bad-mode",
                        "prefix": "zz",
                        "gateway": "bad-mode",
                        "mode": "auto",
                        "enabled": True,
                        "source": {"repo": str(source_repo), "ref": "main"},
                        "routes": [{"skill": "bug-diagnosis", "path": "skills/bug-diagnosis", "terms": ["bug"]}],
                    },
                    {
                        "id": "dupe-prefix",
                        "prefix": "zz",
                        "gateway": "dupe-prefix",
                        "mode": "suggest",
                        "enabled": True,
                        "source": {"repo": str(source_repo), "ref": "main"},
                        "routes": [{"skill": "bug-diagnosis", "path": "skills/bug-diagnosis", "terms": ["bug"]}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"


def test_menu_command_is_registered(tmp_path: Path) -> None:
    result = run_harness(tmp_path / "agent", "menu-registered")
    assert result == {"ok": True, "command": True}


def test_registry_route_paths_cannot_escape_cache(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.mkdir(parents=True)
    (root / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "evil",
                        "prefix": "zz",
                        "gateway": "evil",
                        "mode": "suggest",
                        "enabled": True,
                        "description": "evil",
                        "source": {"repo": str(source_repo), "url": str(source_repo), "ref": "main", "cacheKey": "x"},
                        "routes": [{"skill": "bug-diagnosis", "path": "../../etc", "terms": ["bug"]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"


def test_crlf_frontmatter_is_wrapped(tmp_path: Path) -> None:
    repo = tmp_path / "crlf"
    skill_dir = repo / "skills" / "crlf-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(
        b"---\r\nname: crlf-skill\r\ndescription: Uses CRLF endings\r\n---\r\n\r\n# crlf\r\n"
    )
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    git(repo, "config", "core.autocrlf", "false")

    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(repo), "--prefix", "zz")
    assert result["ok"] is True, result
    leaf = exposed_root(agent_dir, str(result["id"])) / "zz-crlf-skill" / "SKILL.md"
    content = leaf.read_text(encoding="utf-8")
    frontmatter = content.split("---", 2)[1]
    assert re.search(r"name: zz-crlf-skill", frontmatter)
    assert "disable-model-invocation: true" in frontmatter


def make_repo(path: Path, skill_name: str = "bug-diagnosis", description: str = "Diagnose tricky bugs systematically") -> Path:
    path.mkdir(parents=True)
    write_skill(path, f"skills/{skill_name}", skill_name, description)
    git(path, "init", "-q", "-b", "main")
    git(path, "add", "-A")
    git(path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return path


def test_local_repos_with_same_basename_get_distinct_caches(tmp_path: Path) -> None:
    first = make_repo(tmp_path / "one" / "repo", "bug-diagnosis", "First repo skill")
    second = make_repo(tmp_path / "two" / "repo", "code-review", "Second repo skill")
    agent_dir = tmp_path / "agent"
    added_first = run_harness(agent_dir, "add", str(first), "--prefix", "aa", "--id", "first")
    assert added_first["ok"] is True, added_first
    added_second = run_harness(agent_dir, "add", str(second), "--prefix", "bb", "--id", "second")
    assert added_second["ok"] is True, added_second
    first_leaf = exposed_root(agent_dir, "first") / "aa-bug-diagnosis" / "SKILL.md"
    second_leaf = exposed_root(agent_dir, "second") / "bb-code-review" / "SKILL.md"
    assert "First repo skill" in first_leaf.read_text(encoding="utf-8")
    assert "Second repo skill" in second_leaf.read_text(encoding="utf-8")


def test_symlinked_skill_dir_is_rejected_and_outside_file_untouched(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "SKILL.md"
    target.write_text("---\nname: outside\ndescription: do not touch\n---\n", encoding="utf-8")
    repo = tmp_path / "evil-repo"
    (repo / "skills").mkdir(parents=True)
    (repo / "skills" / "linked").symlink_to(outside, target_is_directory=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(repo), "--prefix", "zz")
    assert result["ok"] is False
    assert "symlink" in str(result["error"]).lower()
    assert target.read_text(encoding="utf-8") == "---\nname: outside\ndescription: do not touch\n---\n"


def test_symlinked_exposed_root_is_rejected(tmp_path: Path, source_repo: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    (root / "exposed").parent.mkdir(parents=True)
    (root / "exposed").symlink_to(outside, target_is_directory=True)

    result = run_harness(agent_dir, "add", str(source_repo), "--prefix", "zz")
    assert result["ok"] is False
    assert "symlink" in str(result["error"]).lower()
    assert list(outside.iterdir()) == []


def test_symlinked_router_root_is_rejected(tmp_path: Path, source_repo: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.parent.mkdir(parents=True)
    root.symlink_to(outside, target_is_directory=True)

    result = run_harness(agent_dir, "add", str(source_repo), "--prefix", "zz")
    assert result["ok"] is False
    assert "symlink" in str(result["error"]).lower()
    assert list(outside.iterdir()) == []


def test_nested_skill_definitions_are_not_exposed_as_leaves(tmp_path: Path) -> None:
    repo = tmp_path / "nested"
    write_skill(repo, "skills/outer", "outer", "Outer skill")
    write_skill(repo, "skills/outer/nested", "nested", "Nested skill")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(repo), "--prefix", "zz", "--skills", "outer")
    assert result["ok"] is True, result
    discovered = run_harness(agent_dir, "discover")
    assert {skill["name"] for skill in discovered["skills"]} == {str(result["id"]), "zz-outer"}


def test_symlinked_git_metadata_and_cache_are_rejected(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(source_repo), "--prefix", "zz")
    assert added["ok"] is True, added
    collection_id = str(added["id"])
    registry = read_registry(agent_dir)
    [entry] = registry["collections"]
    cache = agent_dir / "skill-router" / "cache" / entry["source"]["cacheKey"]
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    (cache / ".git").rename(cache / ".git-real")
    (cache / ".git").symlink_to(outside, target_is_directory=True)
    updated = run_harness(agent_dir, "update", collection_id)
    assert updated["ok"] is False
    selected = run_harness(agent_dir, "select", collection_id, "bug-diagnosis")
    assert selected["ok"] is False
    assert list(outside.iterdir()) == []


def test_external_gitdir_metadata_is_rejected(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", str(source_repo), "--prefix", "zz")
    assert added["ok"] is True, added
    collection_id = str(added["id"])
    [entry] = read_registry(agent_dir)["collections"]
    cache = agent_dir / "skill-router" / "cache" / entry["source"]["cacheKey"]
    outside = tmp_path / "outside-gitdir"
    outside.mkdir()
    (cache / ".git").rename(cache / ".git-real")
    (cache / ".git").write_text(f"gitdir: {outside}\n", encoding="utf-8")
    updated = run_harness(agent_dir, "update", collection_id)
    assert updated["ok"] is False


def test_malicious_cache_key_fails_closed(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.mkdir(parents=True)
    (root / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "evil",
                        "prefix": "zz",
                        "gateway": "evil",
                        "mode": "suggest",
                        "enabled": True,
                        "description": "evil",
                        "source": {"repo": str(source_repo), "url": str(source_repo), "ref": "main", "cacheKey": "../../escape"},
                        "routes": [{"skill": "bug-diagnosis", "path": "skills/bug-diagnosis", "terms": ["bug"]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"
    update = run_harness(agent_dir, "update", "evil")
    assert update["ok"] is False


def test_malicious_git_ref_fails_closed(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.mkdir(parents=True)
    (root / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "evil",
                        "prefix": "zz",
                        "gateway": "evil",
                        "mode": "suggest",
                        "enabled": True,
                        "description": "evil",
                        "source": {"repo": str(source_repo), "url": str(source_repo), "ref": "--upload-pack=touch", "cacheKey": "safe"},
                        "routes": [{"skill": "bug-diagnosis", "path": "skills/bug-diagnosis", "terms": ["bug"]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"
    update = run_harness(agent_dir, "update", "evil")
    assert update["ok"] is False


def test_pinned_tag_ref_survives_update(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "tagged", "bug-diagnosis", "Version one")
    git(repo, "-c", "tag.gpgsign=false", "tag", "v1")
    write_skill(repo, "skills/bug-diagnosis", "bug-diagnosis", "Version two")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "v2")

    agent_dir = tmp_path / "agent"
    added = run_harness(agent_dir, "add", f"{repo}@v1", "--prefix", "zz")
    assert added["ok"] is True, added
    collection_id = str(added["id"])
    leaf = exposed_root(agent_dir, collection_id) / "zz-bug-diagnosis" / "SKILL.md"
    assert "Version one" in leaf.read_text(encoding="utf-8")
    [entry] = read_registry(agent_dir)["collections"]
    assert entry["source"]["ref"] == "v1"

    updated = run_harness(agent_dir, "update", collection_id)
    assert updated["ok"] is True, updated
    assert "Version one" in leaf.read_text(encoding="utf-8"), "update must stay on the pinned tag"


def test_different_refs_use_independent_caches(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "refs", "bug-diagnosis", "Main version")
    git(repo, "-c", "tag.gpgsign=false", "tag", "v1")
    write_skill(repo, "skills/bug-diagnosis", "bug-diagnosis", "Head version")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "head")

    agent_dir = tmp_path / "agent"
    first = run_harness(agent_dir, "add", f"{repo}@v1", "--prefix", "v1", "--id", "tagged")
    assert first["ok"] is True, first
    second = run_harness(agent_dir, "add", str(repo), "--prefix", "hd", "--id", "head")
    assert second["ok"] is True, second
    tagged_leaf = exposed_root(agent_dir, "tagged") / "v1-bug-diagnosis" / "SKILL.md"
    assert "Main version" in tagged_leaf.read_text(encoding="utf-8")
    updated = run_harness(agent_dir, "select", "tagged", "bug-diagnosis")
    assert updated["ok"] is True, updated
    assert "Main version" in tagged_leaf.read_text(encoding="utf-8")
    entries = read_registry(agent_dir)["collections"]
    assert len({entry["source"]["cacheKey"] for entry in entries}) == 2


def test_duplicate_source_ref_is_rejected(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    first = run_harness(agent_dir, "add", str(source_repo), "--prefix", "one", "--id", "one")
    assert first["ok"] is True, first
    second = run_harness(agent_dir, "add", str(source_repo), "--prefix", "two", "--id", "two")
    assert second["ok"] is False
    assert "cache" in str(second["error"]).lower() or "source" in str(second["error"]).lower()
    assert len(read_registry(agent_dir)["collections"]) == 1


def test_update_remaps_moved_skill_path(tmp_path: Path, source_repo: Path, installed_collection: dict[str, object]) -> None:
    agent_dir = installed_collection["agent_dir"]
    collection_id = str(installed_collection["add"]["id"])
    moved = source_repo / "workflows" / "bug-diagnosis"
    moved.parent.mkdir(parents=True)
    (source_repo / "skills" / "bug-diagnosis").rename(moved)
    git(source_repo, "add", "-A")
    git(source_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "move")

    updated = run_harness(agent_dir, "update", collection_id)
    assert updated["ok"] is True, updated
    [entry] = read_registry(agent_dir)["collections"]
    paths = {route["skill"]: route["path"] for route in entry["routes"]}
    assert paths["bug-diagnosis"] == "workflows/bug-diagnosis"
    assert (exposed_root(agent_dir, collection_id) / "mp-bug-diagnosis" / "SKILL.md").is_file()


def test_gateway_cannot_collide_with_leaf_or_other_gateway(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    colliding_leaf = run_harness(
        agent_dir, "add", str(source_repo), "--prefix", "mp", "--gateway", "mp-bug-diagnosis"
    )
    assert colliding_leaf["ok"] is False
    assert "collid" in str(colliding_leaf["error"]).lower() or "gateway" in str(colliding_leaf["error"]).lower()

    first = run_harness(agent_dir, "add", str(source_repo), "--prefix", "mp", "--id", "one", "--gateway", "shared")
    assert first["ok"] is True, first
    second = run_harness(agent_dir, "add", str(source_repo), "--prefix", "bb", "--id", "two", "--gateway", "shared")
    assert second["ok"] is False
    assert "gateway" in str(second["error"]).lower()


def test_duplicate_upstream_names_fail_even_when_selecting_subset(tmp_path: Path) -> None:
    repo = tmp_path / "dupes-subset"
    repo.mkdir()
    write_skill(repo, "a/tools", "same-name", "First copy")
    write_skill(repo, "b/tools", "same-name", "Second copy")
    write_skill(repo, "c/unique", "unique-skill", "Unique")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    agent_dir = tmp_path / "agent"
    result = run_harness(agent_dir, "add", str(repo), "--prefix", "zz", "--skills", "unique-skill")
    assert result["ok"] is False
    assert "duplicate" in str(result["error"]).lower() or "collision" in str(result["error"]).lower()


def test_malformed_enabled_and_duplicate_ids_fail_closed(tmp_path: Path, source_repo: Path) -> None:
    agent_dir = tmp_path / "agent"
    root = agent_dir / "skill-router"
    root.mkdir(parents=True)
    entry = {
        "id": "one",
        "prefix": "zz",
        "gateway": "one",
        "mode": "suggest",
        "description": "x",
        "source": {"repo": str(source_repo), "url": str(source_repo), "ref": "main", "cacheKey": "x"},
        "routes": [{"skill": "bug-diagnosis", "path": "skills/bug-diagnosis", "terms": ["bug"]}],
    }
    (root / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {**entry, "enabled": "false"},
                    {**entry, "id": "one", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    routed = run_harness(agent_dir, "route", "please diagnose this bug")
    assert routed["systemPrompt"] == "base system prompt"


def test_feature_contract_covers_external_hosting() -> None:
    feature = (PACKAGE / "features" / "skill-router.feature").read_text(encoding="utf-8")
    assert "ships no skill content" in feature
    assert "materializes wrapped skills" in feature
    assert "resources_discover" in feature
    assert "Explicit skill invocations are never rerouted" in feature
    assert "re-materializes the preserved selection" in feature
    assert "fail closed" in feature

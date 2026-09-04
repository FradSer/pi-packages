from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
CHECKER = PACKAGE / "scripts" / "check-upstream-sync.mjs"
SELECTION = PACKAGE / "upstream-selection.json"


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(CHECKER), *args],
        cwd=PACKAGE,
        text=True,
        capture_output=True,
    )


def test_selection_records_distinct_upstream_revisions_and_complete_reasons() -> None:
    metadata = json.loads(SELECTION.read_text())
    assert metadata["comparedCommit"] == "6654f6b60cd9d5be8b54c6fafe44346dabeb3b76"
    assert metadata["comparisonTag"] == "v1.2.3"
    assert metadata["resolvedTagCommit"] == "6acc160e4e0cd062dbbbd7a1b26ae92855edf07e"
    assert metadata["latestCheckedCommit"] == "3cca18b368ae95cdbdebbff572ccafa662551015"
    assert len({
        metadata["comparedCommit"],
        metadata["comparisonTag"],
        metadata["resolvedTagCommit"],
        metadata["latestCheckedCommit"],
    }) == 4
    assert all(item["localCatalogId"] for item in metadata["selected"])
    assert all(item["reason"].strip() for item in metadata["excluded"])


def test_checker_validates_local_selection_without_network() -> None:
    result = run_checker()
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["upstreamCompared"] is False
    assert report["selected"] > 0
    assert report["excluded"] > 0


def test_packed_package_includes_sync_metadata_and_checker(tmp_path: Path) -> None:
    output = subprocess.check_output(
        ["pnpm", "--dir", str(PACKAGE), "pack", "--pack-destination", str(tmp_path)],
        text=True,
    )
    tarball = next(Path(part) for part in output.split() if part.endswith(".tgz"))
    with tarfile.open(tarball) as archive:
        names = set(archive.getnames())
    assert "package/UPSTREAM.md" in names
    assert "package/upstream-selection.json" in names
    assert "package/scripts/check-upstream-sync.mjs" in names


def git(upstream: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(upstream), *args], text=True).strip()


def write_upstream_fixture(upstream: Path, metadata: dict[str, object]) -> None:
    subprocess.check_call(["git", "init", "-q", str(upstream)])
    subprocess.check_call(["git", "-C", str(upstream), "config", "user.email", "fixture@example.com"])
    subprocess.check_call(["git", "-C", str(upstream), "config", "user.name", "Fixture"])

    for item in metadata["selected"]:
        source = upstream / item["upstreamPath"]
        source.parent.mkdir(parents=True, exist_ok=True)
        local_body = (PACKAGE / item["localResource"]).read_text()
        disabled = "disable-model-invocation: true\n" if item["upstreamInvocation"] == "user" else ""
        source.write_text(
            f"---\nname: {item['upstreamSkill']}\n{disabled}---\n\n{local_body}"
        )

    for item in metadata["excluded"]:
        source = upstream / item["upstreamPath"]
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"---\nname: {item['upstreamSkill']}\n---\n\nExcluded fixture.\n")

    subprocess.check_call(["git", "-C", str(upstream), "add", "."])
    subprocess.check_call(["git", "-C", str(upstream), "commit", "-qm", "fixture"])
    metadata["comparedCommit"] = git(upstream, "rev-parse", "HEAD")
    subprocess.check_call(["git", "-C", str(upstream), "commit", "--allow-empty", "-qm", "tag target"])
    metadata["resolvedTagCommit"] = git(upstream, "rev-parse", "HEAD")
    subprocess.check_call([
        "git", "-C", str(upstream), "update-ref",
        f"refs/tags/{metadata['comparisonTag']}", metadata["resolvedTagCommit"],
    ])
    subprocess.check_call(["git", "-C", str(upstream), "commit", "--allow-empty", "-qm", "latest"])
    metadata["latestCheckedCommit"] = git(upstream, "rev-parse", "HEAD")


def test_checker_compares_an_already_cloned_upstream_tree(tmp_path: Path) -> None:
    metadata = json.loads(SELECTION.read_text())
    upstream = tmp_path / "skills"
    write_upstream_fixture(upstream, metadata)
    original = SELECTION.read_text()
    SELECTION.write_text(json.dumps(metadata))
    try:
        result = run_checker("--upstream", str(upstream))
    finally:
        SELECTION.write_text(original)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["upstreamCompared"] is True
    assert report["upstreamSkills"] == len(metadata["selected"]) + len(metadata["excluded"])
    assert report["content"]["exact"] == len(metadata["selected"])
    assert report["content"]["adapted"] == 0


def test_checker_rejects_upstream_checkout_at_a_different_head(tmp_path: Path) -> None:
    metadata = json.loads(SELECTION.read_text())
    upstream = tmp_path / "skills"
    write_upstream_fixture(upstream, metadata)
    result = run_checker("--upstream", str(upstream))
    assert result.returncode == 1
    assert "metadata latestCheckedCommit" in result.stderr

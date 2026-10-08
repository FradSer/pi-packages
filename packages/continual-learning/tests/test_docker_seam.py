"""The attribution seam must hand the extension the fixture it writes.

The per-project seam once wrote the fixture into the container configuration but
did not export the environment that points at it, so every arm silently ran the
model's own plan and the pair lost its attribution.
"""
from __future__ import annotations

from pathlib import Path

from docker_experiment import SEAM_ENVIRONMENT, fixed_memory_seam


def test_a_per_project_fixture_is_handed_to_the_extension_and_not_only_written(tmp_path: Path) -> None:
    (tmp_path / "pluggy.json").write_text('[{"name":"a.md"}]', encoding="utf-8")
    contents, environment = fixed_memory_seam(None, str(tmp_path), "pluggy")
    assert contents == '[{"name":"a.md"}]'
    assert environment == ("--env", SEAM_ENVIRONMENT)


def test_a_single_source_still_supplies_the_seam(tmp_path: Path) -> None:
    source = tmp_path / "one.json"
    source.write_text("[]", encoding="utf-8")
    assert fixed_memory_seam(str(source), None, "pluggy") == ("[]", ("--env", SEAM_ENVIRONMENT))


def test_the_directory_wins_over_the_single_source(tmp_path: Path) -> None:
    source = tmp_path / "one.json"
    source.write_text("[]", encoding="utf-8")
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "pluggy.json").write_text('[{"name":"b.md"}]', encoding="utf-8")
    assert fixed_memory_seam(str(source), str(directory), "pluggy")[0] == '[{"name":"b.md"}]'


def test_a_project_with_no_file_supplies_nothing(tmp_path: Path) -> None:
    # A widened cohort must never hand one project another project's quotes.
    (tmp_path / "pluggy.json").write_text("[]", encoding="utf-8")
    assert fixed_memory_seam(None, str(tmp_path), "humanize") == (None, None)
    assert fixed_memory_seam(None, None, "pluggy") == (None, None)
    assert fixed_memory_seam(str(tmp_path / "absent.json"), None, "pluggy") == (None, None)

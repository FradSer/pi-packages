"""Regression: the Harness probe must not crash on a missing project Harness file.

The iniconfig-on arm failed its Harness phase with FileNotFoundError, because the
probe read `.pi/harness.json` even though no Harness rule had been applied. A
missing file means "no rule", and the acceptance gate must report that, not a
probe error.
"""

from __future__ import annotations

import json

import pytest

import live_docker_projects as workflow


def test_missing_harness_file_means_no_rules(tmp_path) -> None:
    # Given a project with no .pi/harness.json, When the probe reads its rules,
    # Then it reports no rules instead of raising FileNotFoundError.
    assert workflow.read_harness_rules(tmp_path) == []


def test_present_harness_file_returns_its_rules(tmp_path) -> None:
    # Given a project Harness file, When the probe reads its rules, Then it
    # returns exactly the recorded rules.
    harness = tmp_path / ".pi"
    harness.mkdir()
    (harness / "harness.json").write_text(json.dumps({"rules": [{"bash": "git push", "action": "block"}]}))
    assert workflow.read_harness_rules(tmp_path) == [{"bash": "git push", "action": "block"}]


def test_malformed_harness_file_still_raises(tmp_path) -> None:
    # Given a malformed project Harness file, When the probe reads its rules,
    # Then the integrity problem still surfaces.
    harness = tmp_path / ".pi"
    harness.mkdir()
    (harness / "harness.json").write_text("{ not json")
    with pytest.raises(json.JSONDecodeError):
        workflow.read_harness_rules(tmp_path)
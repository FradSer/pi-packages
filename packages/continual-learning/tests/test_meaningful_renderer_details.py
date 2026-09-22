from __future__ import annotations

from pathlib import Path

import pytest

from support import run_bun_script

HARNESS = Path(__file__).with_name("meaningful_details_harness.ts")


@pytest.fixture(scope="module")
def rendered() -> dict:
    return run_bun_script(HARNESS, temp_dirs=("PI_CODING_AGENT_DIR",))


@pytest.mark.parametrize(
    ("case", "label"),
    [("policy-blocked", "policy blocked"), ("policy-allowed", "policy allowed"), ("policy-observed", "policy observed")],
)
def test_policy_reason_is_only_in_title_and_explanation_survives(rendered: dict, case: str, label: str) -> None:
    row = rendered[case]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] {label} · {data['reason']}"
    for field in ("policy", "action", "outcome", "tool", "source", "file"):
        assert f"{field} · {data[field]}" in expanded
    assert "\n".join(expanded).count(data["reason"]) == 1
    assert not any(line.startswith("reason ·") for line in expanded)
    collapsed = row["views"]["240"]["collapsed"]
    assert len(collapsed) == 1 and "to expand" in collapsed[0]


@pytest.mark.parametrize("status", ["checked", "observed", "violated", "unsupported", "repair-exhausted"])
def test_check_status_and_detail_stay_in_title_while_evidence_remains(rendered: dict, status: str) -> None:
    row = rendered[f"check-{status}"]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] check {status} · {data['detail']}"
    for field in ("phase", "policy", "path"):
        assert f"{field} · {data[field]}" in expanded
    assert "\n".join(expanded).count(data["detail"]) == 1
    assert not any(line.startswith(("status ·", "detail ·")) for line in expanded)


def test_legacy_guidance_entry_type_still_renders_as_harness_guidance(rendered: dict) -> None:
    current = rendered["skill-rule"]
    legacy = rendered["guidance-legacy-entry"]
    assert legacy["data"] == current["data"]
    assert legacy["views"] == current["views"]
    assert legacy["views"]["240"]["expanded"][0] == "[harness] skill rule · review"


def test_output_check_keeps_phase_and_policy_without_inventing_a_path(rendered: dict) -> None:
    expanded = rendered["check-output"]["views"]["240"]["expanded"]
    assert "phase · output" in expanded and "policy · artifact-evidence" in expanded
    assert not any(line.startswith("path ·") for line in expanded)


@pytest.mark.parametrize(
    ("case", "label", "subject"),
    [
        ("skill-rule", "skill rule", "review"),
        ("skill-prompt", "skill rule", "review"),
        ("text-rule", "text guidance", "project-a-guidance"),
        ("text-incomplete", "text guidance incomplete", "guidance"),
    ],
)
def test_guidance_identity_is_only_in_title_but_prompt_and_provenance_survive(
    rendered: dict, case: str, label: str, subject: str,
) -> None:
    row = rendered[case]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] {label} · {subject}"
    assert f"source · {data['source']}" in expanded
    assert f"file · {data['file']}" in expanded
    assert f"prompt · {data['prompt'].splitlines()[0]}" in expanded
    assert data["prompt"].splitlines()[1] in expanded
    assert not any(line.startswith(("skill ·", "rule ·")) for line in expanded)


@pytest.mark.parametrize(("case", "field"), [("policy-long", "reason"), ("check-long", "detail"), ("guidance-long", "skill")])
def test_narrow_expansion_recovers_subject_without_repeating_a_field(rendered: dict, case: str, field: str) -> None:
    row = rendered[case]
    view = row["views"]["48"]
    assert "to expand" in " ".join(view["collapsed"])
    assert not any(line.startswith(("reason ·", "detail ·", "skill ·")) for line in view["expanded"])
    # Wrapping may split words or preserve a hyphen, so compare non-whitespace text.
    subject = "".join(row["data"][field].split())
    expanded = "".join("".join(view["expanded"]).split())
    assert expanded.count(subject) == 1


@pytest.mark.parametrize("width", [240, 48])
def test_full_guidance_prompt_survives_character_and_detail_line_limits(rendered: dict, width: int) -> None:
    row = rendered["guidance-full-prompt"]
    prompt = row["data"]["prompt"]
    assert len(prompt) > 2000 and len(prompt.splitlines()) > 50
    expanded = "".join("".join(row["views"][str(width)]["expanded"]).split())
    assert "".join(prompt.split()) in expanded
    for field in ("source", "file"):
        assert "".join(f"{field} · {row['data'][field]}".split()) in expanded

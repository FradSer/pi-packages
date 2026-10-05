"""The current public catalog must have real invocation case contracts."""
from pathlib import Path

from real_model_live import load_cases
from type_inventory import inventory


def test_every_supported_public_type_has_a_real_case() -> None:
    report = inventory()
    assert report["missingPublicTypes"] == []
    assert set(report["resourceKinds"]) == {"workflow", "utility", "reference", "asset"}
    assert set(report["invocationModes"]) == {"model", "user", "internal"}
    assert report["transitions"] > report["placements"]


def test_omitted_public_cases_are_reported_as_gaps() -> None:
    root = Path(__file__).parent
    cases = [case for name in ("real-model-cases.json", "developer-journey-cases.json", "expanded-type-cases.json") for case in load_cases(root / name)]
    cases = [case for case in cases if case.get("expectSource") != "research"]
    assert "standalone:research" in inventory(cases)["missingPublicTypes"]

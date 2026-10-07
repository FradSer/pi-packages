"""Evidence grading never upgrades injection or failed generation into capability."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/score.py"
SPEC = importlib.util.spec_from_file_location("docker_memory_score", LOCATION)
assert SPEC is not None and SPEC.loader is not None
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)


def test_unanswered_arm_is_missing_quality_coverage(tmp_path: Path) -> None:
    common = {"withMemory": True, "expected": None, "data": {"name": "reviewer"}}
    study = {"piVersion": "1.0.4", "model": "test", "evaluations": [
        {**common, "case": "unanswered", "notice": {"kind": "unanswered", "text": ""}},
        {**common, "case": "correct", "notice": {"kind": "result", "text": '{"findings": []}'}},
    ]}
    (tmp_path / "study.json").write_text(json.dumps(study))
    (tmp_path / "spawns.json").write_text("[]")
    result = SCORER.score(tmp_path)
    assert result["scores"]["True"] == {"correct": 1, "total": 1, "attempted": 2, "missingCoverage": 1, "falsePositives": 0}
    assert result["evaluations"][0]["missed"] is None


def test_index_injection_without_body_read_is_not_retrieval(tmp_path: Path) -> None:
    body = "A reusable capability body."
    study = {"piVersion": "1.0.4", "model": "test", "memoryFiles": [{"file": "pi-review-boundaries.md", "body": body}], "evaluations": [
        {"case": "safe", "withMemory": True, "expected": None, "data": {"name": "reviewer"}, "notice": {"kind": "result", "text": '```json\n{"findings": []}\n```'}},
    ]}
    (tmp_path / "study.json").write_text(json.dumps(study))
    (tmp_path / "spawns.json").write_text(json.dumps([{"name": "reviewer", "result": {"pid": 42}}]))
    (tmp_path / "child-42.jsonl").write_text(json.dumps({"event": "system", "memory": "Index is present."}) + "\n")
    evaluation = SCORER.score(tmp_path)["evaluations"][0]
    assert evaluation["memoryIndexInjected"] is True
    assert evaluation["fullEntryRead"] is False

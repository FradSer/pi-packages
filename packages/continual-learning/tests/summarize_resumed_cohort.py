"""Summarize one resumed-cohort output root into the six separate measures.

Reads only recorded artifacts. Misrecording and false holds need human judgment,
so those two measures are reported as review input, not as a verdict.

Usage: python3 summarize_resumed_cohort.py <output root>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def memory_items(arm: Path) -> list[dict]:
    """Return each written Memory file with a body hash for manual review."""
    items = []
    for path in sorted(arm.glob("memory/*/MEMORY.md")) + sorted(arm.glob("project/.memory/MEMORY.md")):
        if path.is_file():
            body = path.read_text(encoding="utf-8", errors="replace")
            items.append({
                "path": str(path.relative_to(arm)),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "lines": len(body.splitlines()),
            })
    return items


def arm_summary(arm: Path) -> dict:
    report_path = arm / "report.json"
    if not report_path.is_file():
        return {"arm": arm.name, "status": "missing-report"}
    report = json.loads(report_path.read_text())
    attempts = []
    jev = []
    for receipt in report.get("receipts") or []:
        for attempt in receipt.get("attempts", []):
            attempts.append({
                "phase": attempt.get("phase"),
                "outcome": attempt.get("outcome"),
                "operations": attempt.get("operations"),
                "durationMs": attempt.get("durationMs"),
                "diagnostic": attempt.get("diagnostic"),
                "usage": attempt.get("usage"),
            })
            if isinstance(attempt.get("jev"), dict):
                jev.append(attempt["jev"])
        totals = receipt.get("totals")
        usage_available = receipt.get("usageAvailable")
        cost_available = receipt.get("costAvailable")
    return {
        "arm": arm.name,
        "status": report.get("status"),
        "stage": report.get("stage"),
        "learningSeconds": report.get("learningSeconds"),
        "checks": report.get("checks"),
        "phaseObservations": report.get("phaseObservations"),
        "attempts": attempts,
        "jevJudgments": jev,
        "totals": totals,
        "usageAvailable": usage_available,
        "costAvailable": cost_available,
        "memoryItems": memory_items(arm),
    }


def main() -> None:
    root = Path(sys.argv[1]).expanduser()
    summary = {}
    summary_path = root / "summary.json"
    if summary_path.is_file():
        recorded = json.loads(summary_path.read_text())
        summary = {
            "sourceDigest": recorded.get("sourceDigest"),
            "memoryPolicy": recorded.get("memoryPolicy"),
            "providerRequests": recorded.get("providerRequests"),
            "jevRequests": recorded.get("jevRequests"),
            "jevResponsesWithUsage": recorded.get("jevResponsesWithUsage"),
            "jevUsage": recorded.get("jevUsage"),
            "projects": [(item.get("project"), item.get("status"), item.get("stage"))
                         for item in recorded.get("projects", [])],
        }
    arms = [arm_summary(arm) for arm in sorted(root.glob("*/")) if arm.is_dir()]
    print(json.dumps({"root": str(root), "summary": summary, "arms": arms}, indent=2))


if __name__ == "__main__":
    main()
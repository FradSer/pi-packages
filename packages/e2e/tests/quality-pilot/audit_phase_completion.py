"""Offline completion audit. A successful Pi process is not a completed model task."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def audit_phase(folder: Path, declared_result: dict[str, object] | None = None) -> dict[str, object]:
    result_path = folder / "result.json"
    events_path = folder / "events.jsonl"
    result = json.loads(result_path.read_text())
    # Completion metadata is added by the controller after the engine receipt.
    if declared_result is not None:
        result = {**result, **declared_result}
    errors: list[dict[str, object]] = []
    unparsed = 0
    for number, line in enumerate(events_path.read_text().splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            unparsed += 1
            continue
        message = event.get("message", {})
        if event.get("type") == "message_end" and message.get("stopReason") == "error":
            error = message.get("errorMessage", "")
            errors.append({"line": number, "http400": str(error).startswith("400 ")})
    return {
        "processExitCode": result.get("exitCode"),
        "controllerTransportErrors": result.get("transportErrors"),
        "forwardedRequests": result.get("requests"),
        "reportedComplete": result.get("reportCompleted") is True,
        "modelErrorCount": len(errors),
        "errors": errors,
        "unparsedLines": unparsed,
        "completedWithoutRecordedError": result.get("reportCompleted") is True and not errors and not unparsed,
        "inputHashes": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (result_path, events_path)
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parent / "runs/native-first-20261010"
    output = root / "completion-error-audit.json"
    if output.exists():
        raise SystemExit("Preserve previous audit; choose a new output for a subsequent audit")
    results_path = root / "results.json"
    results = json.loads(results_path.read_text())
    phases = {
        f"{arm}/{phase}": audit_phase(root / arm / phase, results[arm][phase])
        for arm in ("baseline", "e2e") for phase in ("review", "fix")
    }
    output.write_text(json.dumps({
        "phases": phases,
        "controllerResultsSha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "paidRequests": 0,
        "conclusion": "Both fixes ended with recorded HTTP 400 errors; no completed-fix quality comparison.",
        "exactRejectionCause": "Unknown: original proxy did not retain validation rejection metadata.",
    }, ensure_ascii=False, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()

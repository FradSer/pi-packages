"""Explicit paired model-task evaluation; uses provider calls only without --validate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1]
USAGE_KEYS = ("input", "output", "cacheRead", "cacheWrite", "totalTokens")


def validate_suite(suite: dict[str, Any]) -> None:
    if not isinstance(suite, dict) or suite.get("version") != 1:
        raise ValueError("A version 1 task evaluation suite is required")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError("Supply 1..20 held-out tasks")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("Task ids must be non-empty and unique")
        ids.add(case["id"])
        if not isinstance(case.get("prompt"), str) or not 1 <= len(case["prompt"]) <= 8000:
            raise ValueError("Each task needs a bounded prompt")
        for key in ("required", "forbidden"):
            values = case.get(key, [])
            if not isinstance(values, list) or len(values) > 32 or not all(isinstance(value, str) and 0 < len(value) <= 2000 for value in values):
                raise ValueError("Expected answer fragments must be bounded non-empty strings")
        if not case.get("required"):
            raise ValueError("Each task needs an independently specified required answer")
        exact = case.get("exact")
        if exact is not None and (not isinstance(exact, str) or not 0 < len(exact) <= 2000):
            raise ValueError("Exact answers must be bounded non-empty strings")
        read_body = case.get("readBody")
        if read_body is not None:
            if not isinstance(read_body, dict) or set(read_body) != {"path", "required"}:
                raise ValueError("readBody must specify only path and required")
            if not isinstance(read_body["path"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*\.md", read_body["path"]):
                raise ValueError("readBody path must be a Memory filename")
            if not isinstance(read_body["required"], str) or not 1 <= len(read_body["required"]) <= 2000:
                raise ValueError("readBody marker must be a bounded non-empty string")
    for arm in ("baseline", "candidate"):
        config = suite.get(arm)
        if not isinstance(config, dict) or not isinstance(config.get("memories"), dict) or len(config["memories"]) > 128:
            raise ValueError("Each arm needs a bounded memories mapping")
        if set(config) != {"memories"}:
            raise ValueError("Task evaluation arms support only memories; use rule evaluation for Harness")
        for name, text in config["memories"].items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*\.md", name) or name.lower() == "memory.md" or not isinstance(text, str) or len(text.encode()) > 64000:
                raise ValueError("Invalid fixture Memory entry")


def score_case(case: dict[str, Any], answer: str) -> bool:
    if "exact" in case:
        return answer.strip() == case["exact"] and not any(text in answer for text in case.get("forbidden", []))
    return all(text in answer for text in case["required"]) and not any(text in answer for text in case.get("forbidden", []))


def _resolve_native_path(raw_path: str, project_root: Path) -> Path:
    path = Path(raw_path)
    return (path if path.is_absolute() else project_root / path).resolve(strict=False)


def read_body_matches(case: dict[str, Any], read_events: list[dict[str, Any]], memory_root: Path) -> bool:
    requirement = case.get("readBody")
    if requirement is None:
        return True
    project_root = memory_root.parent.resolve(strict=False)
    expected_path = (memory_root / requirement["path"]).resolve(strict=False)
    marker = requirement["required"]
    for event in read_events:
        path = event.get("path")
        if event.get("isError") is not False or not isinstance(path, str):
            continue
        if _resolve_native_path(path, project_root) != expected_path:
            continue
        result = event.get("result")
        try:
            rendered = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        if marker in rendered:
            return True
    return False


def _display_read_paths(read_events: list[dict[str, Any]], project_root: Path) -> list[str]:
    root = project_root.resolve(strict=False)
    paths: list[str] = []
    for event in read_events:
        path = event.get("path")
        if event.get("isError") is not False or not isinstance(path, str):
            continue
        resolved = _resolve_native_path(path, root)
        try:
            paths.append(resolved.relative_to(root).as_posix())
        except ValueError:
            paths.append("<outside-project>")
    return paths


def _snapshot_provider_config(source: Path) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
    temporary = tempfile.TemporaryDirectory(prefix="learning-evaluation-config-")
    snapshot = Path(temporary.name)
    snapshot.chmod(0o700)
    fingerprints: list[dict[str, str]] = []
    for name in ("auth.json", "models.json"):
        source_file = source / name
        if not source_file.exists():
            continue
        resolved_source = source_file.resolve(strict=False)
        if not resolved_source.is_file():
            temporary.cleanup()
            raise ValueError(f"Provider config {name} must be a regular file")
        destination = snapshot / name
        destination.write_bytes(resolved_source.read_bytes())
        destination.chmod(0o600)
        fingerprints.append({"name": name, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    fingerprint = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    return temporary, snapshot, fingerprint


def _read_events(data: bytes) -> list[dict[str, Any]]:
    pending: dict[str, dict[str, Any]] = {}
    completed: list[dict[str, Any]] = []
    for line in data.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(event, dict) or event.get("toolName") != "read":
            continue
        event_type = event.get("type")
        call_id = event.get("toolCallId")
        if event_type == "tool_execution_start":
            args = event.get("args")
            path = args.get("path") if isinstance(args, dict) else None
            record = {"path": path, "isError": None, "result": None}
            if isinstance(call_id, str) and call_id:
                pending[call_id] = record
        elif event_type == "tool_execution_end":
            if not isinstance(call_id, str) or not call_id:
                continue
            record = pending.pop(call_id, None)
            if record is None:
                continue
            record["isError"] = event.get("isError")
            record["result"] = event.get("result")
            completed.append(record)
    return completed


def run_case(case: dict[str, Any], arm: dict[str, Any], model: str, source: Path, *, arm_name: str = "candidate", config_source: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="learning-evaluation-") as raw:
        base = Path(raw)
        project, agent = base / "project", base / "agent"
        project.mkdir(mode=0o700)
        agent.mkdir(mode=0o700)
        config_root = config_source or source
        for name in ("auth.json", "models.json"):
            config_file = config_root / name
            if config_file.is_file():
                shutil.copyfile(config_file, agent / name)
                (agent / name).chmod(0o600)
        (agent / "settings.json").write_text(json.dumps({"packages": []}))
        (agent / "memory").mkdir()
        (agent / "memory" / "settings.json").write_text(json.dumps({"autoMemory": False}))
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        (project / ".memory").mkdir()
        for name, text in arm["memories"].items():
            (project / ".memory" / name).write_text(text)
            (project / ".memory" / name).chmod(0o600)
        started = time.monotonic()
        error: str | None = None
        with (base / "stdout").open("w+b") as stdout, (base / "stderr").open("w+b") as stderr:
            try:
                result = subprocess.run([
                    "pi", "--offline", "--no-extensions", "-e", str(PACKAGE / "index.ts"),
                    "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
                    "--no-session", "--print", "--mode", "json", "--model", model, "--tools", "read", case["prompt"],
                ], cwd=project, env={**os.environ, "PI_CODING_AGENT_DIR": str(agent)}, stdout=stdout, stderr=stderr, timeout=240)
                if result.returncode:
                    error = f"Pi exited with code {result.returncode}"
            except subprocess.TimeoutExpired:
                error = "Task exceeded 240 seconds"
            stdout.seek(0)
            data = stdout.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("Task output exceeded 32 MiB")
        answer = ""
        usage = dict.fromkeys(USAGE_KEYS, 0)
        price = 0.0
        priced = True
        messages = 0
        for line in data.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            message = event.get("message", {})
            if event.get("type") != "message_end" or message.get("role") != "assistant":
                continue
            messages += 1
            content = message.get("content", [])
            if not isinstance(content, list) or any(not isinstance(block, dict) for block in content):
                error = "Assistant response content was malformed"
                continue
            answer = "\n".join(block.get("text", "") for block in content if block.get("type") == "text" and isinstance(block.get("text"), str))
            if message.get("stopReason") in ("error", "aborted"):
                error = "Model task failed or was aborted"
            measured = message.get("usage", {})
            for key in USAGE_KEYS:
                usage[key] += measured.get(key, 0)
            cost = measured.get("cost", {}).get("total")
            priced = priced and isinstance(cost, (int, float)) and (cost > 0 or not any(measured.get(key, 0) for key in USAGE_KEYS))
            if isinstance(cost, (int, float)):
                price += cost
        if messages == 0 and error is None:
            error = "No assistant response"
        read_events = _read_events(data)
        body_read = read_body_matches(case, read_events, project / ".memory") if arm_name == "candidate" else None
        passed = error is None and score_case(case, answer) and (body_read is not False)
        return {"id": case["id"], "passed": passed, "answer": answer[:16000], "error": error,
                "readBodyMatched": body_read, "successfulReadCount": sum(event.get("isError") is False for event in read_events),
                "readPaths": _display_read_paths(read_events, project),
                "durationMs": round((time.monotonic() - started) * 1000), "usage": usage, "cost": price if priced and messages else None}


def evaluate_suite(suite: dict[str, Any], model: str, source: Path) -> dict[str, Any]:
    validate_suite(suite)
    outcomes: dict[str, list[dict[str, Any]]] = {"baseline": [], "candidate": []}
    config_temporary, config_snapshot, config_fingerprint = _snapshot_provider_config(source)
    config_files = [name for name in ("auth.json", "models.json") if (config_snapshot / name).is_file()]
    try:
        for index, case in enumerate(suite["cases"]):
            for arm in (("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")):
                outcomes[arm].append(run_case(case, suite[arm], model, source, arm_name=arm, config_source=config_snapshot))
    finally:
        config_temporary.cleanup()
    summaries = {arm: {"successRate": sum(row["passed"] for row in rows) / len(rows), "executionFailures": sum(row["error"] is not None for row in rows), "durationMs": sum(row["durationMs"] for row in rows),
                       "usage": {key: sum(row["usage"][key] for row in rows) for key in USAGE_KEYS},
                       "cost": sum(row["cost"] for row in rows) if all(row["cost"] is not None for row in rows) else None, "results": rows}
                 for arm, rows in outcomes.items()}
    return {"kind": "paired-learning-task-evaluation", "version": 1, "model": model,
            "suiteDigest": hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest(), **summaries,
            "configSnapshot": {"files": config_files, "fingerprint": config_fingerprint},
            "regressions": [before["id"] for before, after in zip(outcomes["baseline"], outcomes["candidate"]) if before["passed"] and not after["passed"]],
            "scope": "One paired sample per held-out task; validates answer scoring and declared candidate Memory-body read evidence, but does not establish statistical improvement, causal attribution, learning-pipeline persistence, or Bash enforcement."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.suite.stat().st_size > 2_000_000:
        raise ValueError("Suite exceeds 2 MB")
    suite = json.loads(args.suite.read_text())
    validate_suite(suite)
    if args.validate:
        print(json.dumps({"valid": True, "cases": len(suite["cases"])}))
        return
    if args.output and args.output.exists():
        raise ValueError("Refusing to overwrite an existing evaluation report")
    source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
    model = args.model
    if not model:
        config = json.loads((source / "memory.json").read_text())
        model = f"{config['provider']}/{config['model']}"
    report = json.dumps(evaluate_suite(suite, model, source), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as target:
            args.output.chmod(0o600)
            target.write(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()

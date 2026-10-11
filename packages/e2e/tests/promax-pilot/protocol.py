"""Pure sampling and scoring policy; no model or Docker work on import."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

LANGUAGES = ("python", "typescript", "go", "rust")
SEED = "pi-e2e-promax-pilot-v1"


def select_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick two distinct repositories per language without inspecting answers."""
    selected: list[dict[str, Any]] = []
    for language in LANGUAGES:
        seen: set[str] = set()
        candidates = sorted((row for row in rows if row["language"] == language),
                            key=lambda row: hashlib.sha256(f"{SEED}:{row['instance_id']}".encode()).hexdigest())
        for row in candidates:
            if row["repo"] in seen:
                continue
            seen.add(row["repo"])
            selected.append(row)
            if len(seen) == 2:
                break
        if len(seen) != 2:
            raise ValueError(f"Need two distinct repositories for {language}")
    return selected


def public_task(row: dict[str, Any]) -> dict[str, str]:
    """Allow only public instructions, not grading metadata or answer locators."""
    return {key: row[key] for key in ("language", "problem_statement")}


def replace_environment_task(selected: list[dict[str, Any]], rows: list[dict[str, Any]], blocked_id: str,
                             excluded_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Preflight-only fallback: same language, other repository if available."""
    blocked = next(row for row in selected if row["instance_id"] == blocked_id)
    ids = {row["instance_id"] for row in selected} | (excluded_ids or set())
    repositories = {row["repo"] for row in selected}
    candidates = [row for row in rows if row["language"] == blocked["language"]
                  and row["instance_id"] not in ids and row["repo"] != blocked["repo"]]
    candidates.sort(key=lambda row: (row["repo"] in repositories,
                    hashlib.sha256(f"{SEED}:{row['instance_id']}".encode()).hexdigest()))
    if not candidates:
        raise ValueError("No same-language environment replacement")
    return [candidates[0] if row["instance_id"] == blocked_id else row for row in selected]


def grade_succeeded(returncode: int, stdout: str, stderr: str) -> bool:
    """Use the verifier's outcome, never output equality with a failed oracle."""
    combined = stdout + "\n" + stderr
    if returncode != 0 or "OMNIGRIL_TEST_PATCH_APPLY_FAILED=1" in combined:
        return False
    markers = re.findall(r"OMNIGRIL_EXIT_CODE=(\d+)\s*$", combined, re.MULTILINE)
    return bool(markers) and all(marker == "0" for marker in markers)


def gate_eligible(oracle: dict[str, Any], empty: dict[str, Any]) -> bool:
    """Both controls must execute, and the empty run must report test failure."""
    return (oracle.get("passed") is True and empty.get("passed") is False
            and empty.get("reason") == "verifier_finished"
            and bool(empty.get("scriptExitCodes"))
            and any(code != 0 for code in empty["scriptExitCodes"])
            and not empty.get("compilerFailure", False)
            and not empty.get("testPatchApplyFailed", False))


def compiler_failure(stderr: str) -> bool:
    """Compiler crashes are infrastructure; application deadlocks remain failures."""
    return ("internal compiler error" in stderr.lower()
            or ("fatal error:" in stderr and "cmd/compile/internal/" in stderr))


def create_attempt_directory(path: Path) -> None:
    """Refuse reused attempt artifacts, including partially written attempts."""
    path.mkdir(parents=True, exist_ok=False)

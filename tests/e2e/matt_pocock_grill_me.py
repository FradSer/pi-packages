"""Real end-to-end coverage for grill-me through its user entry points.

This is the matt-pocock case in the repository E2E layer. It starts the real Pi
CLI against the package's runtime fixture, so the extension loader, the agent
loop, tool-schema validation, and state persistence are native Pi. The model
transport is deterministic and local; no provider credentials are read.

Two entry points are exercised, because they failed differently:

1. The user entry point. `/matt-pocock` opens the menu, and "Run a standalone
   capability" lists "Grill Me". This path always worked.
2. The model entry point. The model must be able to run grill-me when the user
   asks for it by name. Before `mode: "user-capability"` existed, grill-me was
   absent from the tool schema and from the injected catalog, so a user who said
   "grill me" gave the model nothing to route to.

Both cases must complete. The runner prints one result object and, with
`--output`, records it as JSON.

Usage:
    python3 tests/e2e/matt_pocock_grill_me.py [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_TESTS = ROOT / "packages" / "matt-pocock" / "tests"
sys.path.insert(0, str(PACKAGE_TESTS))

from live_pty import base_env  # noqa: E402
from runtime_live import call, command, isolated_env, read_rows  # noqa: E402

CAPABILITY = "grill-me"
# grill-me requires grilling, so the delivered closure must carry both bodies.
CLOSURE = ("grill-me", "grilling")
RESULTS = Path(__file__).with_name("matt-pocock-grill-me-results.json")


class Rpc:
    """Minimal RPC client over a real Pi process."""

    def __init__(self, pi: str, case_root: Path, evidence: Path, session: Path) -> None:
        case_root.mkdir(parents=True, exist_ok=True)
        self.name = case_root.name
        self.evidence = evidence
        self.session = session
        self.env = isolated_env(case_root, evidence, [])
        self.proc = subprocess.Popen(
            [*command(pi, mode="rpc", session=session)],
            cwd=case_root, env=self.env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert self.proc.stdin and self.proc.stdout
        self.buffer = bytearray()
        self.events: list[dict[str, object]] = []
        self.prompt_number = 0

    def send(self, value: dict[str, object]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write((json.dumps(value) + "\n").encode())
        self.proc.stdin.flush()

    def wait_for(self, predicate, timeout: float = 90) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, _, remainder = self.buffer.partition(b"\n")
                self.buffer = bytearray(remainder)
                if not line:
                    continue
                row = json.loads(line)
                self.events.append(row)
                if predicate(row):
                    return row
            ready, _, _ = select.select([self.proc.stdout], [], [], 0.2)
            if ready:
                chunk = os.read(self.proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                self.buffer.extend(chunk)
            if self.proc.poll() is not None:
                break
        stderr = self.proc.stderr.read().decode(errors="replace") if self.proc.poll() else ""
        raise AssertionError({"case": self.name, "stage": "rpc-event", "exitCode": self.proc.poll(),
                              "events": self.events[-20:], "stderr": stderr[-2000:]})

    def prompt(self, message: str, *, wait_response: bool = True) -> None:
        self.prompt_number += 1
        identifier = f"prompt-{self.prompt_number}"
        self.send({"id": identifier, "type": "prompt", "message": message})
        # A command that opens a menu does not answer until the menu resolves, so the
        # caller drives the menu first and waits for this response afterwards.
        if not wait_response:
            return
        response = self.wait_for(lambda row: row.get("type") == "response" and row.get("id") == identifier)
        assert response.get("success") is True, {"case": self.name, "response": response}

    def select(self, option: str) -> dict[str, object]:
        request = self.wait_for(lambda row: row.get("type") == "extension_ui_request"
                                and row.get("method") == "select")
        choices = request.get("options")
        assert isinstance(choices, list) and all(isinstance(c, str) for c in choices), request
        match = next((c for c in choices if c == option or c.startswith(option)), None)
        assert match is not None, {"requested": option, "choices": choices}
        self.send({"type": "extension_ui_response", "id": request["id"], "value": match})
        return request

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        assert self.proc.returncode == 0, {"case": self.name, "exitCode": self.proc.returncode}


def _strings(value: object) -> list[str]:
    """Every string nested anywhere in a parsed session entry."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    return []


def persisted_sources(session: Path) -> set[str]:
    """Which procedure bodies reached the persisted session.

    The menu path persists a custom procedure message; the gateway path persists a
    tool result. Reading every string in the file covers both without depending on
    which shape carried the body.
    """
    if not session.exists():
        return set()
    blob: list[str] = []
    for line in session.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            blob.extend(_strings(json.loads(line)))
        except json.JSONDecodeError:
            continue
    joined = "\n".join(blob)
    return {name for name in CLOSURE if f'<procedure-source id="{name}"' in joined}


def run_menu_entry_point(pi: str, root: Path) -> dict[str, object]:
    """The user opens /matt-pocock and picks Grill Me from the menu."""
    case_root = root / "menu-entry-point"
    evidence = case_root / "evidence.jsonl"
    session = case_root / "session.jsonl"
    case = Rpc(pi, case_root, evidence, session)
    try:
        case.prompt("/matt-pocock", wait_response=False)
        case.select("Run a standalone capability")
        case.select("Grill Me")
        case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-1")
        case.wait_for(lambda row: row.get("type") == "agent_end")
        rows = read_rows(evidence)
        procedures = [row for row in rows if row.get("kind") == "procedure"]
        assert procedures, {"case": case.name, "rows": rows[-20:]}
        delivered = procedures[-1]
        details = delivered.get("details") or {}
        assert details.get("capability") == CAPABILITY, {"details": details, "rows": rows[-20:]}
        sources = persisted_sources(session)
        assert sources == set(CLOSURE), {"sources": sorted(sources), "session": str(session)}
    finally:
        case.close()
    return {"entryPoint": "menu", "capability": CAPABILITY,
            "deliveredSources": sorted(sources), "status": "completed"}


def run_gateway_entry_point(pi: str, root: Path) -> dict[str, object]:
    """The model runs grill-me because the user asked for it by name."""
    case_root = root / "gateway-entry-point"
    case_root.mkdir(parents=True, exist_ok=True)
    evidence = case_root / "evidence.jsonl"
    session = case_root / "session.jsonl"
    scripted = [
        call("matt_pocock_workflow", mode="user-capability", capability=CAPABILITY),
        # The autonomous mode must keep refusing it, or the upstream
        # disable-model-invocation intent is lost.
        call("matt_pocock_workflow", mode="capability", capability=CAPABILITY),
    ]
    env = isolated_env(case_root, evidence, scripted)
    result = subprocess.run(
        [*command(pi, mode=None, session=session), "--print",
         "Ask the gateway for the grill-me capability, then try it again in autonomous mode."],
        cwd=case_root, env=env, input="", text=True, capture_output=True, timeout=180,
    )
    assert result.returncode == 0, {"stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
    results = [row for row in read_rows(evidence) if row.get("kind") == "tool_result"]
    assert len(results) == len(scripted), {"results": results, "stdout": result.stdout[-1500:]}
    accepted, rejected = results
    assert accepted.get("isError") is not True, accepted
    assert accepted.get("details", {}).get("mode") == "user-capability", accepted
    assert accepted.get("details", {}).get("capability") == CAPABILITY, accepted
    assert rejected.get("isError") is True, rejected
    sources = persisted_sources(session)
    assert sources == set(CLOSURE), {"sources": sorted(sources), "session": str(session)}
    return {"entryPoint": "model-gateway", "mode": "user-capability", "capability": CAPABILITY,
            "autonomousModeRefused": True, "deliveredSources": sorted(sources), "status": "completed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="record the result as JSON")
    args = parser.parse_args()
    pi = shutil.which("pi")
    if not pi:
        print(json.dumps({"status": "blocked", "reason": "Pi CLI is required"}))
        return 2
    with tempfile.TemporaryDirectory(prefix="matt-pocock-grill-me-e2e-") as temporary:
        root = Path(temporary)
        report = {
            "capability": CAPABILITY,
            "closure": list(CLOSURE),
            "cases": [run_menu_entry_point(pi, root), run_gateway_entry_point(pi, root)],
        }
    report["status"] = "completed"
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

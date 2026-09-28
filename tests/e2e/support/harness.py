"""Run a real `pi` process against one install combination.

Everything here is about making "installed alone" mean something. The combination
is resolved from each package's manifest, not from a list written in a test: a
bundle's own entry registers one tool and its *manifest* is what loads the other
two, so a suite that hand-listed the entries would stop proving that the manifest
is what an install relies on.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGES = REPO / "packages"
# The fixture lives inside the package whose dependencies the install resolves
# through, so a bare specifier in it names the same module instance the
# packages themselves use. A fixture elsewhere would register a role in a
# second copy of the registry and watch the first refuse to find it.
E2E = Path(__file__).resolve().parents[1]
FIXTURE = PACKAGES / "agent-teams" / "tests" / "e2e" / "install-fixture.ts"

# The tool the harness uses to ask the host what it actually registered. It is not
# one of the three, so a suite asserting the surface can tell its own probe apart.
PROBE = "e2e_probe"

# Prefix the scripted provider puts on its final answer. Must match scripted.ts.
REPORT_PREFIX = "E2E_REPORT"


def manifest(package: str) -> dict[str, object]:
    return json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))


def loaded_entries(installed: list[str]) -> list[str]:
    """The extension entries a real install of `installed` would load.

    Follows each package's own `pi.extensions` for its own entry, and for a
    bundled dependency resolves the node_modules path back to the local package so
    the suite runs the source this repository actually contains.
    """
    resolved: list[str] = []
    for package in installed:
        declared = manifest(package).get("pi", {}).get("extensions", [])  # type: ignore[union-attr]
        assert declared, f"{package} declares no extension entry"
        assert declared[0] == "./index.ts", f"{package} must load its own root index first"
        for entry in declared:
            if "node_modules" not in entry:
                resolved.append(package)
                continue
            parts = Path(entry).parts
            name = parts[2] if parts[1].startswith("@") else parts[1]
            local = name[3:] if name.startswith("pi-") else name
            assert (PACKAGES / local / "index.ts").is_file(), (
                f"{package} bundles {local}, which has no root index to load"
            )
            assert local not in resolved, f"{package} bundles {local} twice"
            resolved.append(local)
    return resolved


@dataclass
class Run:
    completed: subprocess.CompletedProcess[str]

    @property
    def text(self) -> str:
        return self.completed.stdout + self.completed.stderr

    def report(self) -> dict[str, object]:
        """The transcript-derived report the scripted provider emitted.

        The provider builds it by reading the transcript, so every value in it came
        out of a real tool execution rather than out of the fixture.
        """
        for line in self.completed.stdout.splitlines():
            marker = line.strip()
            if marker.startswith(f"{REPORT_PREFIX} "):
                return json.loads(marker[len(REPORT_PREFIX) + 1:])
        raise AssertionError(
            f"no {REPORT_PREFIX} in the run output; the scripted turn never completed:\n{self.text}"
        )

    def surfaces(self) -> list[str]:
        tools = self.report().get("tools")
        return [str(name) for name in tools] if isinstance(tools, list) else []

    def calls(self) -> list[dict[str, object]]:
        calls = self.report().get("calls")
        return list(calls) if isinstance(calls, list) else []

    def calls_named(self, name: str) -> list[dict[str, object]]:
        return [call for call in self.calls() if call.get("name") == name]

    def call(self, name: str) -> dict[str, object]:
        """The one recorded execution of `name`, or a failure naming what ran."""
        matching = self.calls_named(name)
        if len(matching) != 1:
            ran = [str(call.get("name")) for call in self.calls()]
            raise AssertionError(f"expected exactly one {name} call, saw {ran}")
        return matching[0]

    def details(self, name: str) -> dict[str, object]:
        details = self.call(name).get("details")
        return details if isinstance(details, dict) else {}


def run_install(
    tmp_path: Path,
    installed: list[str],
    *,
    scenario: str = "surface",
    tools: str | None = None,
    prompt: str = "Run the install E2E",
    extra_args: list[str] | None = None,
    host: str | None = None,
    timeout: int = 40,
) -> Run:
    """Start a real `pi` process that is exactly `installed`.

    The process runs in its own session so the suite can reap it as a group. A
    suite that starts a child process must not be able to leak one: the report
    arrives on stdout, and a child the scenario did not stop would otherwise keep
    the session alive past the run and into the next test.
    """
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("the Pi CLI is required for the install E2E suites")

    entries = loaded_entries(installed)
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "settings.json").write_text(
        json.dumps({"theme": "dark", "quietStartup": True}), encoding="utf-8"
    )
    env.update({
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(agent_dir),
        # No network: the scripted provider is the only thing that answers, and a
        # suite that reached out would hang rather than fail loudly.
        "PI_OFFLINE": "1",
        "PI_E2E_AUTH": secrets.token_hex(16),
        "PI_E2E_PACKAGES": ",".join(entries),
        "PI_E2E_SCENARIO": scenario,
        "PI_E2E_PROBE": PROBE,
        # Whether the fixture publishes the coordinator seam, which is what puts a
        # second participant on the board so resource conflicts exist to be refused.
        "PI_E2E_HOST": host or "0",
    })

    command = [
        pi, "--print", "--no-session", "--no-extensions", "--no-skills",
        "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
        "--extension", str(FIXTURE),
        "--provider", "e2e-scripted", "--model", "deterministic", "--thinking", "off",
        # No `--tools` filter by default: the point of the surface assertion is which
        # tools the packages registered, and a filter would make that a fact about
        # this harness rather than about the install.
        *(["--tools", tools] if tools else []),
        prompt,
        *(extra_args or []),
    ]
    process = subprocess.Popen(
        command, cwd=tmp_path, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    lines: list[str] = []
    deadline = time.monotonic() + timeout
    reported = False
    try:
        assert process.stdout is not None
        while time.monotonic() < deadline:
            if process.stdout.closed:
                break
            line = process.stdout.readline()
            if line == "":
                if process.poll() is not None:
                    break
                continue
            lines.append(line)
            if line.strip().startswith(REPORT_PREFIX):
                # The report is the last thing the scripted provider says, so once
                # it is out the run has nothing left to decide.
                reported = True
                break
        process.wait(timeout=max(1.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        pass
    finally:
        _reap(process)
    completed = subprocess.CompletedProcess(command, 0 if reported else (process.returncode or 1), "".join(lines), "")
    return Run(completed)


def _reap(process: subprocess.Popen[str]) -> None:
    """Kill the process group, so a child the scenario did not stop cannot outlive it."""
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    if process.stdout is not None:
        process.stdout.close()

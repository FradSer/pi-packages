"""Run explicitly requested Pi v1 real-model cases in isolated projects.

The default action is deliberately inert: use --list to inspect the case
catalog. A model run requires --case or --all and uses the configured
provider/model without falling back to another provider.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
CASES = Path(__file__).with_name("real-model-cases.json")
PRODUCTION_EXTENSION = ROOT / "packages/matt-pocock/index.ts"
OBSERVER_EXTENSION = Path(__file__).with_name("real-model-observer.ts")
CASE_DEADLINE_SECONDS = 240.0
FIXED_TEST = Path("tests/verify.test.mjs")
DEVELOPER_FIXTURES = frozenset({
    "discount", "cache", "config", "frontend", "api", "authorization", "migration",
    "performance", "localization", "paths", "test-design",
})
SECRET_KEY_NAMES = {"access", "refresh", "key", "token", "apiKey", "api_key"}
UNSAFE_WORDS = re.compile(
    r"\b(approve|approved|confirm|confirmed|delete|destroy|deploy|execute|overwrite|publish|push|remove|send|ship|yes)\b",
    re.IGNORECASE,
)


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"case catalog must be a JSON array: {path}")
    cases: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("every real-model case needs a string id")
        fixture = item.get("fixture")
        if fixture is not None and (not isinstance(fixture, str) or fixture not in DEVELOPER_FIXTURES | {"slop", "scope-creep", "prototype", "merge"}):
            raise ValueError(f"unknown fixture: {fixture}")
        cases.append(item)
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("real-model case ids must be unique")
    return cases


def safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [safe_json(item) for item in value[:40]]
    if isinstance(value, dict):
        return {str(key): safe_json(item) for key, item in list(value.items())[:40]}
    return str(value)


def secret_values(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    found: list[str] = []

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key))
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str) and (key in SECRET_KEY_NAMES or len(item) >= 32):
            found.append(item)

    visit(value)
    return sorted(set(found), key=len, reverse=True)


def redact(text: str, secrets: Iterable[str], limit: int = 4_000, *, tail: bool = True) -> str:
    result = text
    for value in secrets:
        if value:
            result = result.replace(value, "[REDACTED]")
    return result[-limit:] if tail else result[:limit]


def base_env() -> dict[str, str]:
    allowed = {
        "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "COLORTERM", "CI",
        "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "USER", "LOGNAME", "TZ",
        "SYSTEMROOT", "WINDIR", "PATHEXT", "TMPDIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def write_project(project: Path, case: dict[str, Any]) -> None:
    (project / "src").mkdir(parents=True)
    (project / "prototypes").mkdir()
    (project / "docs").mkdir()
    (project / "tests").mkdir()
    (project / ".tmp").mkdir()
    slop = case.get("fixture") == "slop"
    scope_creep = case.get("fixture") == "scope-creep"
    if slop:
        source = (
            "export function calculateTotal(items) {\n"
            "  const normalized = Array.isArray(items) ? items : [];\n"
            "  return Math.round(normalized.reduce((total, item) => total + item.price * item.quantity, 0) * 100) / 100;\n"
            "}\n\n"
            "export function makeReceipt(items) {\n"
            "  return { total: calculateTotal(items), items };\n"
            "}\n"
        )
    elif scope_creep:
        source = (
            "export function calculateTotal(items) {\n"
            "  return Math.round(items.reduce((total, item) => total + item.price * (item.quantity ?? 1), 0) * 100) / 100;\n"
            "}\n\n"
            "export function makeReceipt(items) {\n"
            "  return { total: calculateTotal(items), items };\n"
            "}\n"
        )
    else:
        source = (
            "export function calculateTotal(items) {\n"
            "  return items.reduce((total, item) => total + item.price, 0);\n"
            "}\n\n"
            "export function makeReceipt(items) {\n"
            "  return { total: calculateTotal(items), items };\n"
            "}\n"
        )
    (project / "src/receipt.mjs").write_text(source, encoding="utf-8")
    spec = (
        "# Receipt\n\n"
        "Given each line has a validated price and quantity field, when its total is calculated, then both fields are used.\n"
        "The task scope is quantity multiplication and cent rounding; do not invent a missing-field default.\n"
        if scope_creep else
        "# Receipt\n\n"
        "Given a line with unit price 3 and quantity 2, when its total is calculated, then the result is 6.\n"
        "Given decimal line totals, when the receipt is finalized, then the final total is rounded to cents.\n"
    )
    (project / "SPEC.md").write_text(spec, encoding="utf-8")
    (project / "GLOSSARY.md").write_text(
        "# Glossary\n\n- line item: a price and quantity in a receipt.\n",
        encoding="utf-8",
    )
    (project / "PRIMARY-SOURCE.md").write_text(
        "# Primary source\n\nThe local specification is authoritative for this fixture.\n",
        encoding="utf-8",
    )
    (project / "SESSION_LOG.md").write_text(
        "# Session log\n\n"
        "The previous agent skipped the reproduction and treated an ambiguous quantity sentence as a complete specification.\n"
        "Synthetic fixture excerpt: the quantity case is expected to be RED before the fix; the next agent must record a GREEN result.\n",
        encoding="utf-8",
    )
    (project / "AGENTS.md").write_text(
        "# Fixture rules\n\nWork locally. Do not use network, deployment, publishing, or destructive commands.\n",
        encoding="utf-8",
    )
    (project / "docs/README.md").write_text(
        "# Fixture docs\n\nA small receipt project used by the real-model check.\n",
        encoding="utf-8",
    )
    (project / "package.json").write_text(
        '{"name":"real-model-fixture","private":true,"type":"module"}\n',
        encoding="utf-8",
    )

    # The immutable test is deliberately about source behavior only. Artifact
    # presence and wording are checked by the parent process, so a missing
    # note cannot turn a RED behavior check into a misleading failure (or hide
    # a RED check behind an artifact assertion).
    if case.get("fixture") == "prototype":
        fixed_test = (
            "import test from \"node:test\";\n"
            "import assert from \"node:assert/strict\";\n"
            "import { lineTotal } from \"../prototypes/rounding.mjs\";\n\n"
            "test(\"prototype applies quantity\", () => {\n"
            "  assert.equal(lineTotal(3, 2), 6);\n"
            "});\n\n"
            "test(\"prototype preserves the native decimal multiplication result\", () => {\n"
            "  assert.equal(lineTotal(3.335, 3), Number(3.335 * 3));\n"
            "});\n"
        )
    else:
        fixed_test = (
            "import test from \"node:test\";\n"
            "import assert from \"node:assert/strict\";\n"
            "import { calculateTotal, makeReceipt } from \"../src/receipt.mjs\";\n\n"
            + ("test(\"quantity is applied to each line\", () => {\n"
               "  const items = [{ price: 3, quantity: 2 }, { price: 5, quantity: 1 }];\n"
               "  const total = calculateTotal(items);\n"
               '  assert.equal(total, 11, "receipt total must include quantity");\n'
               '  assert.equal(makeReceipt(items).total, 11, "receipt must expose the fixed total");\n'
               '  assert.deepEqual(makeReceipt(items).items, items, "receipt must preserve its line items");\n'
               "});\n\n"
               "test(\"decimal totals are rounded to cents\", () => {\n"
               "  const rounded = calculateTotal([{ price: 1.006, quantity: 1 }]);\n"
               '  assert.equal(rounded, 1.01, "receipt total must round cents");\n'
               "});\n"
               if case.get("checkTests") else "")
        )
    # Developer journeys supply trusted, checked-in source/spec/acceptance files.
    fixture = case.get("fixture")
    if fixture in DEVELOPER_FIXTURES:
        fixture_root = Path(__file__).with_name("fixtures") / "developer" / fixture
        for file in sorted(fixture_root.rglob("*")):
            if file.is_file():
                destination = project / file.relative_to(fixture_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(file.read_bytes())
        if fixture != "discount":
            (project / "src/receipt.mjs").unlink()
        (project / "docs/README.md").write_text(f"# Developer fixture: {fixture}\n\nRead SPEC.md for the task contract.\n", encoding="utf-8")
        (project / "GLOSSARY.md").write_text("# Glossary\n\nSee SPEC.md for agreed terms.\n", encoding="utf-8")
        (project / "SESSION_LOG.md").write_text("# Session log\n\nThis developer task has no earlier implementation attempt.\n", encoding="utf-8")
        fixed_test = (project / FIXED_TEST).read_text(encoding="utf-8")
    verify = project / FIXED_TEST
    completion = "MP_ACCEPTANCE_COMPLETE_" + uuid.uuid4().hex
    fixed_test += "\nimport { test as acceptanceComplete } from 'node:test';\n"
    fixed_test += f"acceptanceComplete('{completion}', () => {{}});\n"
    verify.write_text(fixed_test, encoding="utf-8")
    verify.chmod(0o444)
    if case.get("fixture") == "merge":
        prepare_merge_fixture(project)


def run_git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(project), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    return subprocess.run(["git", *args], cwd=project, env=env, text=True, capture_output=True, check=False)


def prepare_merge_fixture(project: Path) -> None:
    init = run_git(project, "init", "-q")
    if init.returncode != 0:
        raise RuntimeError("git is required for the merge real-model case")
    run_git(project, "add", ".")
    if run_git(project, "commit", "-qm", "base").returncode != 0:
        raise RuntimeError("could not create merge fixture base")
    base = run_git(project, "rev-parse", "HEAD").stdout.strip()
    (project / "src/receipt.mjs").write_text(
        "export function calculateTotal(items) {\n"
        "  return items.reduce((total, item) => total + item.price * item.quantity, 0);\n"
        "}\n\n"
        "export function makeReceipt(items) {\n"
        "  return { total: calculateTotal(items), items };\n"
        "}\n",
        encoding="utf-8",
    )
    run_git(project, "add", "src/receipt.mjs")
    run_git(project, "commit", "-qm", "preserve quantity")
    run_git(project, "checkout", "-qb", "rounding-fix", base)
    (project / "src/receipt.mjs").write_text(
        "export function calculateTotal(items) {\n"
        "  return Math.round(items.reduce((total, item) => total + item.price, 0) * 100) / 100;\n"
        "}\n\n"
        "export function makeReceipt(items) {\n"
        "  return { total: calculateTotal(items), items };\n"
        "}\n",
        encoding="utf-8",
    )
    run_git(project, "add", "src/receipt.mjs")
    run_git(project, "commit", "-qm", "preserve rounding")
    run_git(project, "checkout", "-q", "master")
    merge = run_git(project, "merge", "--no-edit", "rounding-fix")
    if merge.returncode == 0:
        raise RuntimeError("merge fixture did not produce the expected conflict")
    (project / "MERGE-CONTEXT.md").write_text(
        "# Merge context\n\n"
        "The `preserve quantity` branch multiplies price by quantity. The `preserve rounding` branch rounds cents. "
        "Resolve the conflict with both behaviors and leave the merge uncommitted.\n",
        encoding="utf-8",
    )


def evidence_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def safe_artifact_path(project: Path, relative: str) -> Path | None:
    """Return a regular file wholly inside project, rejecting symlink escapes."""
    if not relative or Path(relative).is_absolute():
        return None
    root = project.resolve(strict=True)
    candidate = project / relative
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    current = root
    for part in Path(relative).parts:
        current = current / part
        try:
            if current.is_symlink():
                return None
        except OSError:
            return None
    try:
        return resolved if resolved.is_file() else None
    except OSError:
        return None


def bounded_project_text(project: Path, relative: str, limit: int = 64 * 1024) -> str | None:
    path = safe_artifact_path(project, relative)
    if path is None:
        return None
    try:
        with path.open("rb") as stream:
            return stream.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return None


def artifact_summary(project: Path, case: dict[str, Any], secrets: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in relative_artifacts(case):
        path = safe_artifact_path(project, relative)
        if path is None:
            continue
        digest = hashlib.sha256()
        text_data = bytearray()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                if len(text_data) < 64 * 1024:
                    text_data.extend(chunk[: 64 * 1024 - len(text_data)])
        result[relative] = {
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "text": redact(text_data.decode(errors="replace"), secrets, 64 * 1024, tail=False),
        }
    return result


def snapshot(project: Path) -> dict[str, tuple[str, int, str]]:
    result: dict[str, tuple[str, int, str]] = {}
    for path in sorted(project.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(project).as_posix()
        if relative.startswith(".git/"):
            continue
        stat = path.lstat()
        if path.is_symlink():
            content = f"symlink:{os.readlink(path)}".encode()
        else:
            content = path.read_bytes()
        result[relative] = (
            hashlib.sha256(content).hexdigest(),
            stat.st_mode & 0o777,
            "link" if path.is_symlink() else "file",
        )
    return result


def copy_credentials(agent: Path) -> list[str]:
    source = Path.home() / ".pi/agent"
    values: list[str] = []
    for name in ("auth.json", "models.json"):
        source_file = source / name
        if not source_file.is_file():
            raise RuntimeError(f"missing local Pi {name}; real-model run cannot start")
        target = agent / name
        shutil.copyfile(source_file, target)
        target.chmod(0o600)
        values.extend(secret_values(source_file))
    return values


def configured_model() -> tuple[str, str]:
    settings = Path.home() / ".pi/agent/settings.json"
    try:
        value = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    provider = value.get("defaultProvider") if isinstance(value, dict) else None
    model = value.get("defaultModel") if isinstance(value, dict) else None
    if not isinstance(provider, str) or not provider or not isinstance(model, str) or not model:
        raise RuntimeError("Set a Pi provider and model, or pass both --provider and --model; no implicit model is selected")
    return provider, model


def choose_ui(request: dict[str, Any], fixture_answer: str) -> tuple[dict[str, Any], str]:
    method = request.get("method")
    title = str(request.get("title", ""))
    context = f"{title} {request.get('message', '')}"
    if method == "confirm":
        return {"type": "extension_ui_response", "id": request["id"], "confirmed": False}, "blocked-confirm"
    if method in ("input", "editor"):
        return {"type": "extension_ui_response", "id": request["id"], "value": fixture_answer}, "synthetic-input"
    if method == "select":
        options = [str(option) for option in request.get("options", [])]
        safe = [option for option in options if not UNSAFE_WORDS.search(option)]
        if UNSAFE_WORDS.search(context) and any(UNSAFE_WORDS.search(option) for option in options):
            return {"type": "extension_ui_response", "id": request["id"], "cancelled": True}, "blocked-destructive-select"
        if safe:
            return {"type": "extension_ui_response", "id": request["id"], "value": safe[0]}, "synthetic-select"
        return {"type": "extension_ui_response", "id": request["id"], "cancelled": True}, "blocked-select"
    return {"type": "extension_ui_response", "id": request["id"], "cancelled": True}, "cancelled-unknown-ui"


INTERACTIVE_UI_METHODS = frozenset({"select", "input", "editor", "confirm"})
MATT_TOOL_NAMES = ("matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask")
GREEN_BASELINE_FIXTURES = frozenset({"slop", "scope-creep", "config"})
KNOWN_PENDING_ABORT_MESSAGES = frozenset({"this operation was aborted", "request was aborted"})


def is_interactive_ui_request(request: dict[str, Any]) -> bool:
    """Only methods that need an answer may put a real-model run in pending state."""
    return request.get("method") in INTERACTIVE_UI_METHODS


def bounded_metadata(value: Any, secrets: Iterable[str], limit: int = 256) -> Any:
    if isinstance(value, str):
        return redact(value, secrets, limit, tail=False)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [bounded_metadata(item, secrets, limit) for item in value[:24]]
    if isinstance(value, dict):
        return {str(key): bounded_metadata(item, secrets, limit) for key, item in list(value.items())[:24]}
    return redact(str(value), secrets, limit, tail=False)


def summarize_ui_request(request: dict[str, Any], secrets: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "method": request.get("method"),
        "toolName": request.get("toolName"),
    }
    for key in ("title", "message"):
        if isinstance(request.get(key), str):
            result[key] = bounded_metadata(request[key], secrets)
    options = request.get("options")
    if isinstance(options, list):
        result["options"] = [
            bounded_metadata(option, secrets) for option in options[:24]
        ]
    for key in ("recommended", "recommendation", "defaultValue", "timeout", "timeoutMs", "deadline", "deadlineMs"):
        value = request.get(key)
        if isinstance(value, (str, int, float, bool, dict, list)):
            result[key] = bounded_metadata(value, secrets)
    return result


def build_command(pi: str, provider: str, model: str) -> list[str]:
    tools = ["read", "write", "edit", "grep", "find", "ls", "fixture_checks", *MATT_TOOL_NAMES]
    return [
        pi, "--mode", "rpc", "--no-session", "--no-extensions", "--no-skills",
        "--no-themes", "--no-context-files", "--no-prompt-templates", "--no-approve",
        "--extension", str(PRODUCTION_EXTENSION), "--extension", str(OBSERVER_EXTENSION),
        "--provider", provider, "--model", model, "--thinking", "off",
        "--tools", ",".join(tools),
    ]


def run_fixture_checks_direct(project: Path) -> dict[str, Any]:
    """Run the trusted observer helper independently of the model transcript.

    The TypeScript helper owns sandboxing and executes only the immutable test
    file. This wrapper passes the project path as data; it never loads project
    source into this process.
    """
    script = """
import { runFixtureChecks } from "./packages/matt-pocock/tests/real-model-observer.ts";
const result = await runFixtureChecks(process.env.MP_REAL_PROJECT, undefined);
console.log(JSON.stringify(result.details ?? { available: false }));
"""
    env = base_env()
    env.update({
        "MP_REAL_PROJECT": str(project),
        "PI_OFFLINE": "1",
        "PI_TELEMETRY": "off",
    })
    try:
        completed = subprocess.run(
            ["node", "--import", "tsx/esm", "--input-type=module"],
            cwd=ROOT,
            env=env,
            input=script,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "passed": False, "error": str(error)}
    lines = completed.stdout.splitlines()
    try:
        value = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        value = {}
    details = value if isinstance(value, dict) else {}
    if completed.returncode != 0:
        details = {**details, "available": False, "passed": False, "error": redact(completed.stderr, [])}
    return details


class RpcRun:
    def __init__(self, command: list[str], env: dict[str, str], deadline: float, secrets: list[str]):
        self.secrets = secrets
        self.deadline = deadline
        self.events: list[dict[str, Any]] = []
        self.ui_inputs: list[dict[str, str]] = []
        self.current_tool = ""
        self.process = subprocess.Popen(
            command, cwd=env["MP_REAL_PROJECT"], env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.selector = selectors.DefaultSelector()
        self.output_buffer = bytearray()
        self.stderr_buffer = bytearray()
        if self.process.stdout is not None:
            self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        if self.process.stderr is not None:
            self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self.request_id = 0

    def send(self, value: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("Pi RPC stdin is unavailable")
        self.process.stdin.write((json.dumps(value) + "\n").encode())
        self.process.stdin.flush()

    def next_id(self, prefix: str) -> str:
        self.request_id += 1
        return f"real-model-{prefix}-{self.request_id}"

    def read_line(self, timeout: float = 0.2) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            newline = self.output_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self.output_buffer[:newline])
                del self.output_buffer[:newline + 1]
                try:
                    value = json.loads(line.decode(errors="replace"))
                except json.JSONDecodeError:
                    return {"type": "invalid_output"}
                return value if isinstance(value, dict) else {"type": "invalid_output"}
            selected = self.selector.select(max(0.0, deadline - time.monotonic()))
            if not selected:
                if self.process.poll() is not None:
                    return None
                return {}
            for key, _ in selected:
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except OSError:
                    chunk = b""
                if key.data == "stdout":
                    if chunk:
                        self.output_buffer.extend(chunk)
                    else:
                        self.selector.unregister(key.fileobj)
                elif chunk:
                    self.stderr_buffer.extend(chunk)
                else:
                    self.selector.unregister(key.fileobj)
        if self.process.poll() is not None and not self.output_buffer:
            return None
        return {}

    def prompt(self, message: str, fixture_answer: str, *, stop_on_ui: bool = False) -> dict[str, Any]:
        request_id = self.next_id("prompt")
        self.send({"id": request_id, "type": "prompt", "message": message})
        response_error: str | None = None
        while time.monotonic() < self.deadline:
            row = self.read_line()
            if row is None:
                break
            if not row:
                continue
            if row.get("type") == "extension_ui_request":
                interactive = is_interactive_ui_request(row)
                if stop_on_ui and interactive:
                    request = summarize_ui_request({**row, "toolName": self.current_tool}, self.secrets)
                    request["kind"] = "ui_request"
                    self.events.append(request)
                    self.send({"id": self.next_id("abort"), "type": "abort"})
                    return {"agentEnded": False, "error": None, "pending": True}
                if not interactive:
                    self.events.append({"kind": "ui_notice", "method": row.get("method")})
                    continue
                response, classification = choose_ui(row, fixture_answer)
                self.ui_inputs.append({"method": str(row.get("method")), "classification": classification})
                self.send(response)
                continue
            if row.get("type") == "response" and row.get("id") == request_id and row.get("success") is False:
                response_error = redact(str(row.get("error", "RPC prompt failed")), self.secrets)
            if row.get("type") == "fatal_error":
                response_error = redact(str(row.get("error", "fatal provider error")), self.secrets)
            if row.get("type") == "tool_execution_start":
                self.current_tool = str(row.get("toolName", ""))
            self.events.append(row)
            if row.get("type") == "agent_end":
                if str(row.get("stopReason", "")).lower() in {"error", "aborted", "failed"} or row.get("errorMessage"):
                    response_error = redact(str(row.get("errorMessage") or row.get("error") or row.get("stopReason")), self.secrets)
            if row.get("type") == "agent_settled":
                return {"agentEnded": True, "error": response_error}
        return {"agentEnded": False, "error": response_error or "RPC deadline or process exit before agent_end"}

    def close(self) -> None:
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except OSError:
                    pass
                self.process.wait(timeout=5)
        self.selector.close()
        self.stderr = bytes(self.stderr_buffer).decode(errors="replace")


def build_prompt(case: dict[str, Any]) -> str:
    prompt = str(case["prompt"])
    return (
        f"{prompt}\n\n"
        "This is an isolated local fixture. Work only inside the current project. "
        "Do not use network, remote repositories, deployment, publishing, destructive commands, or external side effects. "
        "Do not modify tests/verify.test.mjs. Use the Matt Pocock extension when this task calls for a workflow or capability. "
        "When the requested work is complete, call fixture_checks if the task has a verification requirement, then give a short final answer."
    )


def relative_artifacts(case: dict[str, Any]) -> list[str]:
    value = case.get("artifact")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def row_args(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("args")
    return value if isinstance(value, dict) else {}


def row_result(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("result")
    return value if isinstance(value, dict) else {}


def row_state(row: dict[str, Any]) -> dict[str, Any]:
    result = row_result(row)
    result_details = result.get("details")
    candidates = [
        result.get("state"),
        result_details.get("state") if isinstance(result_details, dict) else None,
        row.get("state"),
        row.get("details"),
        result_details,
    ]
    state: dict[str, Any] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("route", "procedure", "phase", "status", "workItemId"):
            if isinstance(candidate.get(key), str):
                state[key] = candidate[key]
    return state


def row_detail(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    result = row_result(row)
    if key in result:
        return result[key]
    result_details = result.get("details")
    if isinstance(result_details, dict) and key in result_details:
        return result_details[key]
    details = row.get("details")
    if isinstance(details, dict):
        return details.get(key)
    return None


def matt_call_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join start args to end results and collapse RPC/observer duplicates."""
    starts: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in events:
        tool_name = str(row.get("toolName", ""))
        if not tool_name.startswith("matt_pocock"):
            continue
        kind = row.get("type") or row.get("kind")
        call_id = str(row.get("toolCallId", ""))
        if kind == "tool_execution_start":
            if call_id:
                starts.setdefault(call_id, row)
            continue
        if kind != "tool_execution_end":
            continue
        if call_id and call_id in seen_ids:
            continue
        if call_id:
            seen_ids.add(call_id)
        merged = dict(row)
        start = starts.get(call_id)
        if start is not None and isinstance(start.get("args"), dict):
            merged["args"] = start["args"]
        records.append(merged)
    return records


def summarize_matt_calls(records: list[dict[str, Any]], secrets: Iterable[str] = ()) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for row in records:
        args = row_args(row)
        argument_keys = (
            "mode", "capability", "reference", "action", "target", "route",
            "question", "title", "message", "options", "recommended", "recommendation",
            "timeout", "timeoutMs", "timeout_seconds", "deadline", "deadlineMs", "customAnswer", "allow_custom",
        )
        item: dict[str, Any] = {
            "toolCallId": row.get("toolCallId"),
            "toolName": row.get("toolName"),
            "isError": row.get("isError"),
            "args": {
                key: bounded_metadata(args[key], secrets)
                for key in argument_keys
                if key in args and isinstance(args[key], (str, int, float, bool, list, dict))
            },
            "result": {
                key: row_detail(row, key)
                for key in ("status", "action", "pending")
                if isinstance(row_detail(row, key), (str, bool))
            },
            "state": row_state(row),
        }
        if row.get("isError") is True:
            result = row_result(row)
            content = result.get("content")
            fragments = [
                part.get("text", "") for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ] if isinstance(content, list) else []
            error = row.get("error") or result.get("error") or "\n".join(fragments)
            if error:
                item["errorContent"] = redact(str(error), secrets, 256, tail=False)
        summary.append(item)
    return summary


def agent_end_diagnostics(rows: list[dict[str, Any]], secrets: Iterable[str] = ()) -> dict[str, str]:
    """Normalize the observer's bounded agent_end error fields for reports."""
    for row in reversed(rows):
        stop = row.get("stopReason")
        error = row.get("errorMessage")
        if isinstance(stop, str) or isinstance(error, str):
            result: dict[str, str] = {}
            if isinstance(stop, str) and stop:
                result["stopReason"] = redact(stop, secrets, 256, tail=False)
            if isinstance(error, str) and error:
                result["errorMessage"] = redact(error, secrets, 256, tail=False)
            return result
    return {}


def agent_failure_diagnostic(
    diagnostics: dict[str, str],
    pending: bool,
    expected_pending_abort: bool = False,
) -> str | None:
    stop_reason = diagnostics.get("stopReason", "").lower()
    pending_abort = (
        pending and expected_pending_abort
        and stop_reason in {"aborted", "cancelled", "canceled"}
        and not diagnostics.get("errorMessage")
    )
    known_error_abort = (
        pending
        and expected_pending_abort
        and diagnostics.get("errorMessage", "").strip().casefold() in KNOWN_PENDING_ABORT_MESSAGES
    )
    if pending_abort or known_error_abort:
        return None
    if stop_reason in {"aborted", "cancelled", "canceled"}:
        return diagnostics.get("errorMessage") or diagnostics.get("stopReason", "agent_end aborted")
    if stop_reason in {"error", "failed"} or diagnostics.get("errorMessage"):
        return diagnostics.get("errorMessage") or diagnostics.get("stopReason", "agent_end failure")
    return None


def validate_fixture_checks(
    case: dict[str, Any],
    checks: list[dict[str, Any]],
    initial: dict[str, Any] | None,
    final: dict[str, Any] | None,
) -> list[str]:
    """Validate behavior checks independently from artifact assertions."""
    errors: list[str] = []
    if not checks:
        errors.append("fixture_checks was not observed")
    elif any(row.get("isError") for row in checks):
        errors.append("fixture_checks returned an error")
    observed_passed = [row_detail(row, "passed") for row in checks]
    final_passed = final.get("passed") is True if final else False
    initial_passed = initial.get("passed") is True if initial else False
    if final is None or final.get("available") is not True:
        errors.append("independent fixture_checks was unavailable")
    if not final_passed:
        errors.append("independent fixture_checks did not pass")
    baseline_green = case.get("fixture") in GREEN_BASELINE_FIXTURES
    if baseline_green:
        if initial is None or not initial_passed:
            errors.append("baseline-green fixture was not green before the model run")
    else:
        if initial is None or initial.get("available") is not True:
            errors.append("independent initial fixture_checks was unavailable")
        elif initial_passed:
            errors.append("fixture behavior was unexpectedly green before the model run")
    if not any(value is True for value in observed_passed) and not final_passed:
        errors.append("fixture_checks did not report a passing behavior result")
    if baseline_green:
        if observed_passed and not all(value is True for value in observed_passed):
            errors.append("baseline-green fixture checks did not remain green")
    elif case.get("requiresRed", True) and (
        len(observed_passed) < 2
        or not any(value is False for value in observed_passed[:-1])
        or observed_passed[-1] is not True
    ):
        errors.append("fixture_checks did not show RED before final GREEN")
    elif not case.get("requiresRed", True) and not any(value is True for value in observed_passed):
        errors.append("fixture_checks did not show a model-observed GREEN result")
    return errors


def validate_final_fixture_availability(case: dict[str, Any], final: dict[str, Any]) -> list[str]:
    """Artifact runs need an independent green check; pending runs only need a healthy sandbox."""
    errors: list[str] = []
    if not fixture_sandbox_healthy(final):
        errors.append("independent fixture sandbox positive and negative probes did not both pass")
    if str(case.get("kind", "")).lower() not in {"pending", "question", "awaiting"}:
        if final.get("available") is not True or final.get("passed") is not True:
            errors.append("artifact case did not finish with independent fixture_checks passed=true")
    return errors


def fixture_sandbox_healthy(details: dict[str, Any]) -> bool:
    if details.get("available") is not True:
        return False
    sandbox = details.get("sandbox") if isinstance(details, dict) else None
    if not isinstance(sandbox, dict):
        return False
    return all(
        isinstance(sandbox.get(name), dict) and sandbox[name].get("code") == 0
        for name in ("positive", "negative")
    )


def validate_case(
    case: dict[str, Any],
    project: Path,
    before: dict[str, Any],
    after: dict[str, Any],
    events: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for artifact in relative_artifacts(case):
        path = safe_artifact_path(project, artifact)
        if path is None:
            errors.append(f"unsafe or missing artifact: {artifact}")
    keywords = case.get("keywords", [])
    if isinstance(keywords, list):
        texts: list[str] = []
        for artifact in relative_artifacts(case):
            path = safe_artifact_path(project, artifact)
            if path is not None:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
        joined = "\n".join(texts)
        folded = joined.casefold()
        for keyword in keywords:
            if str(keyword).casefold() not in folded:
                errors.append(f"missing keyword: {keyword}")
    forbidden = case.get("forbiddenPatterns", {})
    if isinstance(forbidden, dict):
        for target, patterns in forbidden.items():
            if not isinstance(target, str):
                continue
            text = bounded_project_text(project, target)
            if text is None:
                errors.append(f"unsafe or missing forbidden-pattern target: {target}")
                continue
            candidates = patterns if isinstance(patterns, list) else [patterns]
            for pattern in candidates:
                if not isinstance(pattern, str):
                    continue
                try:
                    matched = re.search(pattern, text)
                except re.error as error:
                    errors.append(f"invalid forbidden pattern for {target}: {error}")
                    continue
                if matched:
                    errors.append(f"forbidden pattern matched {target}: {pattern}")
    if case.get("sourceUnchanged"):
        allowed = set(relative_artifacts(case))
        changed = sorted(
            path for path in set(before) | set(after)
            if (path.startswith("src/") or path == FIXED_TEST.as_posix())
            and path not in allowed and before.get(path) != after.get(path)
        )
        if changed:
            errors.append(f"source changed: {', '.join(changed[:8])}")
    matt_results = matt_call_records(events)
    matt_workflow = [row for row in matt_results if str(row.get("toolName")) == "matt_pocock_workflow"]
    source_contexts = [row for row in events if row.get("kind") == "model_context"]
    procedure_evidence = any(
        row.get("kind") == "session_start"
        and any(entry.get("customType") in {"matt-pocock-procedure", "matt-pocock-workflow"} for entry in row.get("branch", []))
        for row in events
    )
    if not matt_results and not procedure_evidence and not source_contexts:
        errors.append("no real Matt Pocock tool result or procedure context was observed")
    expected = case.get("expectSource")
    expected_ids = [expected] if isinstance(expected, str) else [item for item in expected or [] if isinstance(item, str)]
    if expected_ids:
        source_ids = {
            source
            for row in events
            if row.get("kind") == "model_context"
            for source in row.get("sourceIds", [])
            if isinstance(source, str)
        }
        if not set(expected_ids).issubset(source_ids):
            errors.append(f"missing model context sources: {', '.join(expected_ids)}")
    prompt_text = str(case.get("prompt", ""))
    if "mode capability" in prompt_text:
        capability_seen = any(
            row.get("isError") is not True
            and row_args(row).get("mode") == "capability"
            and row_args(row).get("capability") in expected_ids
            for row in matt_workflow
        )
        if not capability_seen:
            errors.append("capability case did not record the expected gateway capability call")
    if case.get("routing"):
        branch_routes = {
            entry["state"].get("route")
            for row in events
            for entry in row.get("branch", [])
            if isinstance(entry, dict)
            and entry.get("customType") == "matt-pocock-workflow"
            and isinstance(entry.get("state"), dict)
            and isinstance(entry["state"].get("route"), str)
        }
        route_seen_by_gateway = any(
            row.get("isError") is not True
            and row_args(row).get("mode") == "workflow"
            and isinstance(row_args(row).get("route"), str)
            and (
                row_state(row).get("route") == row_args(row).get("route")
                or row_args(row).get("route") in branch_routes
            )
            for row in matt_workflow
        )
        if not route_seen_by_gateway:
            errors.append("natural routing did not record a workflow gateway call")
    route = case.get("route")
    if isinstance(route, str):
        route_seen = any(
            row_args(row).get("route") == route
            or row_state(row).get("route") == route
            or isinstance(row.get("details"), dict) and row["details"].get("route") == route
            or isinstance(row.get("state"), dict) and row["state"].get("route") == route
            or any(isinstance(entry.get("state"), dict) and entry["state"].get("route") == route for entry in row.get("branch", []))
            for row in events
        )
        if not route_seen:
            errors.append(f"expected route was not observed: {route}")
        workflow_entries = [
            entry for row in events for entry in row.get("branch", [])
            if entry.get("customType") == "matt-pocock-workflow" and isinstance(entry.get("state"), dict)
        ]
        initial = workflow_entries[0] if workflow_entries else None
        if not initial or initial["state"].get("route") != route:
            errors.append(f"initial workflow state route was not observed: {route}")
        elif expected_ids and initial["state"].get("procedure") != expected_ids[0]:
            errors.append(f"initial workflow procedure mismatch: {initial['state'].get('procedure')}")
    entries = [
        entry["state"] for row in events for entry in row.get("branch", [])
        if isinstance(entry, dict) and entry.get("customType") == "matt-pocock-workflow"
        and isinstance(entry.get("state"), dict)
    ]
    stages = {state.get("procedure") for state in entries}
    missing_stages = [stage for stage in case.get("requiredStages", []) if stage not in stages]
    if missing_stages:
        errors.append(f"required workflow stages were not observed: {', '.join(missing_stages)}")
    if case.get("singleWorkItem") and len({state.get("workItemId") for state in entries if state.get("workItemId")}) > 1:
        errors.append("journey restarted with a different work item")
    terminal = case.get("terminal")
    if isinstance(terminal, str):
        status_seen = any(
            row_detail(row, "status") == terminal
            or row_state(row).get("status") == terminal
            or isinstance(row.get("details"), dict) and (
                row["details"].get("status") == terminal
                or isinstance(row["details"].get("state"), dict) and row["details"]["state"].get("status") == terminal
            )
            for row in events
        )
        if not status_seen:
            errors.append(f"expected terminal status was not observed: {terminal}")
    return errors


def run_case(case: dict[str, Any], pi: str, provider: str, model: str, deadline_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"matt-real-{case['id']}-") as directory:
        root = Path(directory)
        project = root / "project"
        agent = root / "agent"
        project.mkdir()
        agent.mkdir()
        write_project(project, case)
        # The sandbox negative probe must read an existing sibling file. A
        # deterministic public sentinel distinguishes a denied read from ENOENT.
        external_sentinel = root / "project-external-secret.txt"
        external_sentinel.write_text("fixture sandbox sentinel\n", encoding="utf-8")
        external_sentinel.chmod(0o600)
        before = snapshot(project)
        initial_fixture_check = run_fixture_checks_direct(project)
        if not fixture_sandbox_healthy(initial_fixture_check):
            return {
                "id": case["id"], "kind": case.get("kind"), "status": "failed",
                "provider": provider, "model": model,
                "elapsedSeconds": round(time.monotonic() - started, 2),
                "agentEnds": 0, "mattToolResults": 0, "mattCalls": [], "uiInputs": [], "uiRequests": [],
                "changedPaths": [], "artifacts": artifact_summary(project, case, []), "usage": [], "finalText": "",
                "errors": ["fixture sandbox preflight failed (positive or negative probe); provider was not started"],
                "fatalProviderError": False,
                "independentFixtureChecks": {"initial": initial_fixture_check, "final": None},
            }
        secrets = copy_credentials(agent)
        evidence = root / "evidence.jsonl"
        env = base_env()
        env.update({
            "HOME": str(root), "PI_CODING_AGENT_DIR": str(agent), "TMPDIR": str(root / "tmp"),
            "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "off",
            "MP_REAL_PROJECT": str(project), "MP_REAL_EVIDENCE": str(evidence),
            "MP_REAL_TOOL_BUDGET": str(case.get("toolBudget", 40)),
            "TERM": "xterm-256color",
        })
        (root / "tmp").mkdir()
        command = build_command(pi, provider, model)
        run = RpcRun(command, env, time.monotonic() + deadline_seconds, secrets)
        error: str | None = None
        pending = str(case.get("kind", "")).lower() in {"pending", "question", "awaiting"}
        try:
            first = run.prompt(
                build_prompt(case), str(case.get("fixtureAnswer", "fixture answer")), stop_on_ui=pending,
            )
            error = first.get("error")
            replies = case.get("replies", [])
            if isinstance(replies, list) and not pending:
                for reply in replies:
                    if error:
                        break
                    message = reply if isinstance(reply, str) else reply.get("message") if isinstance(reply, dict) else None
                    if isinstance(message, str) and message.strip():
                        error = run.prompt(message, str(case.get("fixtureAnswer", "fixture answer"))).get("error")
            observed_so_far = [*run.events, *evidence_rows(evidence)]
            if case.get("checkTests") and not any(row.get("toolName") == "fixture_checks" for row in observed_so_far):
                extra = run.prompt(
                    "Run the fixed fixture_checks tool now and report its result.",
                    str(case.get("fixtureAnswer", "fixture answer")),
                )
                error = extra.get("error") or error
        finally:
            run.close()
        after = snapshot(project)
        observed = [*run.events, *evidence_rows(evidence)]
        validation_errors = validate_case(case, project, before, after, observed)
        final_fixture_check = run_fixture_checks_direct(project)
        validation_errors.extend(validate_final_fixture_availability(case, final_fixture_check))
        if case.get("checkTests"):
            checks = [
                row for row in observed
                if (row.get("type") == "tool_execution_end" or row.get("kind") == "tool_execution_end")
                and row.get("toolName") == "fixture_checks"
            ]
            validation_errors.extend(validate_fixture_checks(
                case, checks, initial_fixture_check, final_fixture_check,
            ))
        if error:
            validation_errors.insert(0, error)
        stderr = redact(getattr(run, "stderr", ""), secrets)
        if stderr and (error or validation_errors):
            validation_errors.append(f"pi stderr: {stderr}")
        final_rows = [row for row in observed if row.get("type") == "agent_end" or row.get("kind") == "agent_end"]
        agent_diagnostics = agent_end_diagnostics(final_rows, secrets)
        observed_ui_request = any(row.get("kind") == "ui_request" for row in observed)
        diagnostic_text = agent_failure_diagnostic(agent_diagnostics, pending, observed_ui_request)
        if diagnostic_text:
            validation_errors.append(f"agent_end diagnostic: {diagnostic_text}")
        fatal_error = bool(re.search(r"api key|authentication|unauthori[sz]ed|forbidden|rate limit|network|fetch|provider|model", f"{error or ''}\n{stderr}", re.IGNORECASE)) or bool(diagnostic_text)
        final_text = ""
        for row in reversed(final_rows):
            if isinstance(row.get("finalText"), str) and row["finalText"]:
                final_text = redact(row["finalText"], secrets, 4_000, tail=False)
                break
        pending_observed = observed_ui_request or bool(final_text and pending)
        if pending and not pending_observed:
            validation_errors.append("pending case did not produce a UI request or final question")
        if pending and pending_observed and not any(row.get("kind") == "ui_request" for row in observed):
            if not re.search(r"[?？]|\b(answer|choose|decide|which|what|how|should|would)\b", final_text, re.IGNORECASE):
                validation_errors.append("pending final text is not an explicit user question")
        standalone_pending = pending and not case.get("route") and not case.get("routing")
        if standalone_pending:
            active_names = {
                name for row in observed
                for name in row.get("activeTools", []) if isinstance(name, str)
            }
            if {"matt_pocock_active", "matt_pocock_ask"} & active_names:
                validation_errors.append("standalone pending case activated workflow-only tools")
            if any(str(row.get("toolName", "")).startswith("matt_pocock_active") for row in observed):
                validation_errors.append("standalone pending case invoked the active workflow tool")
        matt_calls = matt_call_records(observed)
        if final_rows and not pending and not final_text and not matt_calls:
            validation_errors.append("agent_end produced no final text or Matt tool call")
        status = "awaiting_user" if pending and pending_observed and not validation_errors else ("passed" if not validation_errors else "failed")
        return {
            "id": case["id"], "kind": case.get("kind"), "status": status,
            "provider": provider, "model": model, "elapsedSeconds": round(time.monotonic() - started, 2),
            "agentEnds": len(final_rows),
            "agentSettlements": sum(row.get("type") == "agent_settled" for row in run.events),
            "verificationSequence": list({
                row.get("toolCallId"): row_detail(row, "passed")
                for row in observed
                if (row.get("type") == "tool_execution_end" or row.get("kind") == "tool_execution_end")
                and row.get("toolName") == "fixture_checks"
            }.values()),
            "agentEndDiagnostics": agent_diagnostics,
            "mattToolResults": len(matt_calls),
            "mattCalls": summarize_matt_calls(matt_calls, secrets),
            "uiInputs": run.ui_inputs,
            "uiRequests": [row for row in observed if row.get("kind") == "ui_request"][:8],
            "changedPaths": sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))[:40],
            "artifacts": artifact_summary(project, case, secrets),
            "independentFixtureChecks": {
                "initial": initial_fixture_check,
                "final": final_fixture_check,
            },
            "usage": [row.get("usage") for row in final_rows if isinstance(row.get("usage"), dict)][-4:],
            "finalText": final_text, "errors": validation_errors[:20],
            "fatalProviderError": fatal_error,
        }


def overall_status(cases: list[dict[str, Any]]) -> str:
    statuses = [str(case.get("status", "")) for case in cases]
    if not statuses or any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "awaiting_user" for status in statuses):
        return "awaiting_user"
    return "passed" if all(status == "passed" for status in statuses) else "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list cases without reading credentials or starting Pi")
    parser.add_argument("--case", action="append", dest="case_ids", help="run one case id; repeatable")
    parser.add_argument("--all", action="store_true", help="run every case in the catalog")
    parser.add_argument("--cases", type=Path, default=CASES, help="case catalog path")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path, help="write the sanitized JSON report")
    parser.add_argument("--deadline", type=float, default=CASE_DEADLINE_SECONDS, help="per-case wall-clock deadline in seconds")
    args = parser.parse_args()
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    if args.list:
        print(json.dumps({"cases": [{"id": c["id"], "kind": c.get("kind"), "prompt": c.get("prompt", "")} for c in cases]}, ensure_ascii=False, indent=2))
        return 0
    if not args.all and not args.case_ids:
        parser.error("model execution requires --case ID or --all; use --list for a credential-free catalog view")
    try:
        configured_provider, configured_model_name = (
            (args.provider, args.model) if args.provider and args.model else configured_model()
        )
    except RuntimeError as error:
        parser.error(str(error))
    provider = args.provider or configured_provider
    model = args.model or configured_model_name
    selected = cases if args.all else [case for case in cases if case["id"] in set(args.case_ids or [])]
    missing = sorted(set(args.case_ids or []) - {case["id"] for case in cases})
    if missing:
        parser.error(f"unknown case id(s): {', '.join(missing)}")
    pi = shutil.which("pi")
    if not pi:
        parser.error("Pi v1.0 CLI is required")
    report: dict[str, Any] = {"provider": provider, "model": model, "cases": []}

    def write_report() -> None:
        if not args.output:
            return
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp")
        temporary.write_text(json.dumps(safe_json(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    fatal = False
    write_report()
    for case in selected:
        if fatal:
            report["cases"].append({"id": case["id"], "status": "skipped", "errors": ["previous case had a fatal provider/RPC failure"]})
            write_report()
            continue
        result = run_case(case, pi, provider, model, args.deadline)
        report["cases"].append(result)
        print(f"real-model case={result['id']} status={result['status']} elapsed={result['elapsedSeconds']}s", file=sys.stderr, flush=True)
        write_report()
        if result.get("fatalProviderError") or any("rpc" in error.lower() or "deadline" in error.lower() for error in result["errors"]):
            fatal = True
    report["status"] = overall_status(report["cases"])
    output = json.dumps(safe_json(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] in {"passed", "awaiting_user"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

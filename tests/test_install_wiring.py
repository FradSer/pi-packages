"""Real configured-install checks, isolated by default.

Ordinary pnpm check declares local packages in disposable settings and uses Pi's
real package resolver and CLI. It never reads a personal HOME/config or loads a
personal extension. PI_INSTALL_SETTINGS is an explicit, read-only declaration
AUDIT opt-in only; loader and smoke runs remain isolated even in that mode.
The separately invoked pnpm check:install keeps its live user-install semantics.
"""
from __future__ import annotations

import json
import os
import sys
import tarfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SUPPORT = Path(__file__).resolve().parent / "install-wiring"
sys.path.insert(0, str(SUPPORT))
from install_wiring_helper import (  # noqa: E402
    COORDINATION, PACKAGE_TOOLS, REPO, Install, audit, audit_settings, executable,
    isolated_install, loader_report, pi_command, pi_report, run, workspace_pi_packages,
)


@pytest.fixture
def declared_install(tmp_path: Path) -> Install:
    """Every workspace Pi package is declared, but not all are executed."""
    return isolated_install(tmp_path / "declared", workspace_pi_packages())


def configured_sources(install: Install) -> list[str]:
    path = audit_settings(install)
    assert path.is_file(), f"no explicitly selected settings at {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(entry.get("source", "")) if isinstance(entry, dict) else str(entry)
            for entry in data.get("packages", [])]


def test_default_sources_do_not_read_personal_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given unrelated personal settings, default checks use real local declarations."""
    personal = tmp_path / "personal" / ".pi" / "agent"
    personal.mkdir(parents=True)
    path = personal / "settings.json"
    original = json.dumps({"packages": ["./unrelated-personal-extension"]})
    path.write_text(original, encoding="utf-8")
    inherited = tmp_path / "session-agent"
    inherited.mkdir()
    (inherited / "settings.json").write_text(original, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "personal"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(inherited))
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-temporary-credential")
    monkeypatch.setenv("PI_TEAMMATE_ENV_ALLOW", "OPENAI_API_KEY")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/nonexistent-personal-preload.cjs")
    monkeypatch.delenv("PI_INSTALL_SETTINGS", raising=False)

    install = isolated_install(tmp_path / "isolated", workspace_pi_packages())
    sources = configured_sources(install)
    for package in PACKAGE_TOOLS:
        assert str(REPO / "packages" / package) in sources, sources
    assert install.env["HOME"] == str(install.home)
    assert install.env["PI_CODING_AGENT_DIR"] == str(install.agent_dir)
    for key in ("OPENAI_API_KEY", "PI_TEAMMATE_ENV_ALLOW", "PI_INSTALL_SETTINGS"):
        assert key not in install.env, key
    assert "/nonexistent-personal-preload" not in install.env["NODE_OPTIONS"]
    assert path.read_text(encoding="utf-8") == original
    assert (inherited / "settings.json").read_text(encoding="utf-8") == original


@pytest.mark.parametrize("package", sorted(PACKAGE_TOOLS))
def test_each_package_is_a_configured_source(declared_install: Install, package: str) -> None:
    """Package directories, not hand-listed entry files, drive manifest discovery."""
    assert str(REPO / "packages" / package) in declared_install.sources()


def test_the_install_check_script_passes(declared_install: Install) -> None:
    """The unchanged live-audit CLI gets an explicit disposable path by default."""
    selected = audit_settings(declared_install)
    original = selected.read_bytes()
    result = audit(declared_install, selected)
    assert selected.read_bytes() == original
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout
    assert not declared_install.records("network-attempts.jsonl")


@pytest.mark.parametrize("fault,finding", [("missing", "MISSING  packages/tasks"), ("dead", "DEAD     settings.packages")])
def test_missing_declarations_and_dead_sources_fail(
    declared_install: Install, fault: str, finding: str,
) -> None:
    data = json.loads(declared_install.settings.read_text(encoding="utf-8"))
    if fault == "missing":
        data["packages"].remove(str(REPO / "packages" / "tasks"))
    else:
        data["packages"].append(str(declared_install.root / "nonexistent-package"))
    declared_install.settings.write_text(json.dumps(data), encoding="utf-8")
    original = declared_install.settings.read_bytes()
    result = audit(declared_install, declared_install.settings)
    assert result.returncode == 1, result.stdout + result.stderr
    assert finding in result.stdout, result.stdout
    assert declared_install.settings.read_bytes() == original, "audit must not repair declarations"


def test_explicit_live_audit_is_opt_in_read_only_and_not_a_loader_config(
    declared_install: Install, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A disposable stand-in exercises opt-in; never read the user's real settings.
    selected = tmp_path / "explicit-settings.json"
    selected.write_text(json.dumps({"packages": []}), encoding="utf-8")
    original = selected.read_bytes()
    monkeypatch.setenv("PI_INSTALL_SETTINGS", str(selected))
    assert audit_settings(declared_install) == selected
    assert configured_sources(declared_install) == []
    result = audit(declared_install, audit_settings(declared_install))
    assert result.returncode == 1 and "MISSING" in result.stdout, result.stdout
    assert selected.read_bytes() == original
    assert declared_install.env["PI_CODING_AGENT_DIR"] == str(declared_install.agent_dir)
    assert "PI_INSTALL_SETTINGS" not in declared_install.env
    isolated = isolated_install(tmp_path / "live-mode-loader", [REPO / "packages" / "agent-teams"])
    assert COORDINATION <= {tool["name"] for tool in pi_report(isolated)["tools"]}


def test_real_loader_does_not_load_ambient_personal_or_project_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    personal = tmp_path / "ambient-home" / ".pi" / "agent"
    inherited = tmp_path / "ambient-agent"
    marker = tmp_path / "ambient-loaded"
    source = f'import {{ writeFileSync }} from "node:fs"; export default function () {{ writeFileSync({json.dumps(str(marker))}, "loaded"); }}'
    snapshots: dict[Path, bytes] = {}
    for agent_dir in (personal, inherited):
        extensions = agent_dir / "extensions"
        extensions.mkdir(parents=True)
        extension = extensions / "personal.ts"
        extension.write_text(source, encoding="utf-8")
        settings = agent_dir / "settings.json"
        settings.write_text(json.dumps({"extensions": [str(extension)], "packages": []}), encoding="utf-8")
        snapshots[settings] = settings.read_bytes()
    monkeypatch.setenv("HOME", str(tmp_path / "ambient-home"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(inherited))
    install = isolated_install(tmp_path / "isolated", [REPO / "packages" / "agent-teams"])
    project_extensions = install.cwd / ".pi" / "extensions"
    project_extensions.mkdir(parents=True)
    (project_extensions / "ambient.ts").write_text(source, encoding="utf-8")
    report = pi_report(install)
    assert COORDINATION <= {tool["name"] for tool in report["tools"]}
    assert not marker.exists(), "an unrelated ambient extension ran"
    for settings, original in snapshots.items():
        assert settings.read_bytes() == original


INSTALLS = {
    ("subagents",): set(PACKAGE_TOOLS["subagents"]),
    ("tasks",): set(PACKAGE_TOOLS["tasks"]),
    ("subagents", "tasks"): COORDINATION - {"message"},
    ("agent-teams",): COORDINATION,
    ("subagents", "tasks", "agent-teams"): COORDINATION,
}


def expected_entries(packages: tuple[str, ...]) -> set[Path]:
    entries: set[Path] = set()
    for package in packages:
        directory = REPO / "packages" / package
        manifest = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        assert manifest["pi"]["extensions"][0] == "./index.ts"
        entries.update((directory / entry).resolve() for entry in manifest["pi"]["extensions"])
    return entries


@pytest.mark.parametrize("packages,expected", sorted(INSTALLS.items()))
def test_a_real_install_exposes_exactly_its_coordination_tools(
    tmp_path: Path, packages: tuple[str, ...], expected: set[str],
) -> None:
    install = isolated_install(tmp_path / "install", [REPO / "packages" / name for name in packages])
    loaded = loader_report(install)
    assert loaded["errors"] == [], loaded["errors"]
    assert loaded["settingsErrors"] == [], loaded["settingsErrors"]
    extensions = loaded["extensions"]
    actual_entries = [Path(extension["resolvedPath"]).resolve() for extension in extensions]
    assert set(actual_entries) == expected_entries(packages), actual_entries
    assert len(actual_entries) == len(set(actual_entries)), "Pi loaded one physical entry twice"
    registrants = [tool["name"] for extension in extensions for tool in extension["tools"]]
    assert set(registrants) & COORDINATION == expected, registrants
    for tool in expected:
        assert registrants.count(tool) == 1, f"{tool} has duplicate registrants: {registrants}"
    for extension in extensions:
        assert extension["sourceInfo"]["origin"] == "package", extension
        assert extension["sourceInfo"]["source"] in install.sources(), extension

    report = pi_report(install)
    names = [tool["name"] for tool in report["tools"]]
    assert set(names) & COORDINATION == expected, names
    assert not {"work", "agent_event", "install_surface_probe", "live_smoke_probe"} & set(names)
    for tool in report["tools"]:
        if tool["name"] in expected:
            assert tool["sourceInfo"]["origin"] == "package", tool
            schema = tool["parameters"]
            assert schema["type"] == "object" and schema["additionalProperties"] is False, schema
            assert not {"oneOf", "anyOf", "allOf"} & schema.keys(), schema
            assert "target" not in schema["properties"] and "definition" not in schema["properties"], schema
    start = next((tool for tool in report["tools"] if tool["name"] == "agent_start"), None)
    if start:
        # A start is one input, not a lifecycle: every other intent tool addresses an
        # exact session instead.
        assert start["parameters"]["required"] == ["prompt"], start["parameters"]
        assert set(start["parameters"]["properties"]) == {
            "prompt", "identity", "label", "instructions", "tools", "model", "fork",
        }, start["parameters"]


def test_pi_cli_lists_the_actual_disposable_declarations(declared_install: Install) -> None:
    original = declared_install.settings.read_bytes()
    result = run(declared_install, [*pi_command(), "list", "--no-approve"])
    assert result.returncode == 0, result.stdout + result.stderr
    for source in declared_install.sources():
        assert f"  {source}\n" in result.stdout, result.stdout
    assert "Project packages:" not in result.stdout
    assert declared_install.settings.read_bytes() == original


def test_packed_manifests_carry_no_workspace_protocol(declared_install: Install) -> None:
    result = run(declared_install, [executable("pnpm"), "pack:check"], cwd=REPO, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validated packed manifests" in result.stdout
    assert not declared_install.records("network-attempts.jsonl")


@pytest.mark.parametrize("package", sorted(PACKAGE_TOOLS))
def test_coordination_tarballs_ship_declared_entries(declared_install: Install, package: str) -> None:
    directory = REPO / "packages" / package
    destination = declared_install.root / "packed"
    destination.mkdir()
    result = run(declared_install, [executable("pnpm"), "--dir", str(directory), "pack",
        "--pack-destination", str(destination), "--json"], cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    packed = json.loads(result.stdout)
    filename = packed[0]["filename"] if isinstance(packed, list) else packed["filename"]
    tarball = Path(filename)
    if not tarball.is_absolute():
        tarball = destination / tarball
    with tarfile.open(tarball) as archive:
        member = archive.extractfile("package/package.json")
        assert member is not None
        manifest = json.load(member)
        declared = manifest["pi"]["extensions"]
        assert declared[0] == "./index.ts"
        assert "package/index.ts" in archive.getnames(), "packed entry is missing"
        assert "package/src/extension.ts" in archive.getnames() or "package/src/index.ts" in archive.getnames()
        for entry in declared[1:]:
            assert entry.startswith("./node_modules/"), entry
            assert (directory / entry).resolve().is_file(), entry
            dependency = "/".join(Path(entry).parts[1:-1])
            assert dependency in manifest["dependencies"], manifest
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            assert all("workspace:" not in spec for spec in manifest.get(section, {}).values())


@pytest.fixture
def smoke_install(tmp_path: Path) -> Iterator[tuple[Install, list[dict[str, object]]]]:
    """Native RPC child uses only a disposable credential and loopback endpoint."""
    requests: list[dict[str, object]] = []

    class ChildModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path != "/v1/accepted":
                self.send_error(404, "Unknown isolated model observation endpoint")
                return
            if not self.server.accepted.wait(timeout=15):
                self.send_error(503, "No native child model request arrived")
                return
            self.send_response(204)
            self.end_headers()

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            self.server.accepted.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            # Hold the reply open until stop. Startup may wait for RPC acceptance,
            # but it must not wait for model completion or fabricate an answer.
            self.wfile.write(b': isolated child input accepted\n\n')
            self.wfile.flush()
            self.server.release.wait(timeout=30)
            try:
                self.wfile.write(b'data: [DONE]\n\n')
            except (BrokenPipeError, ConnectionResetError):
                pass

    install = isolated_install(tmp_path / "smoke", [REPO / "packages" / "agent-teams"])
    server = ThreadingHTTPServer(("127.0.0.1", 0), ChildModel)
    server.daemon_threads = True
    release = threading.Event()
    server.release = release
    server.accepted = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    auth = json.loads((install.agent_dir / "auth.json").read_text(encoding="utf-8"))
    (install.agent_dir / "models.json").write_text(json.dumps({"providers": {
        "install-wiring-child": {"api": "openai-completions", "apiKey": auth["install-wiring"]["key"],
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "models": [{"id": "deterministic", "name": "Loopback fixture", "reasoning": False,
                "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}), encoding="utf-8")
    try:
        yield install, requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_loopback_model_arrival_observer_requires_real_http(smoke_install: tuple) -> None:
    from http.client import HTTPConnection
    from urllib.parse import urlparse

    install, requests = smoke_install
    models = json.loads((install.agent_dir / "models.json").read_text())
    endpoint = urlparse(models["providers"]["install-wiring-child"]["baseUrl"])
    model = HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    observer = HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    try:
        model.request("POST", "/v1/chat/completions", json.dumps({"fixture": "observer-only"}),
            headers={"Content-Type": "application/json"})
        response = model.getresponse()
        assert response.status == 200
        observer.request("GET", "/v1/accepted")
        assert observer.getresponse().status == 204
        assert requests == [{"fixture": "observer-only"}]
        assert not install.records("rpc.jsonl"), "HTTP model arrival does not invent native RPC acknowledgement"
    finally:
        observer.close()
        model.close()


def test_the_configured_install_runs_the_tools_end_to_end(smoke_install: tuple) -> None:
    install, requests = smoke_install
    report = pi_report(install, scenario="smoke")
    calls = report["calls"]
    tasks = [call for call in calls if call["name"] in ("create_task", "list_tasks", "update_task")]
    assert [call["name"] for call in tasks] == [
        "create_task", "list_tasks", "update_task", "update_task", "update_task",
    ], tasks
    assert all(not call["isError"] for call in tasks[:4]), tasks
    assert [call["details"].get("status") for call in tasks[:4]] == ["pending", None, "in_progress", "completed"]
    task_id = tasks[0]["details"]["id"]
    assert tasks[1]["details"]["tasks"][0]["id"] == task_id
    assert tasks[2]["details"]["id"] == tasks[3]["details"]["id"] == task_id
    assert tasks[2]["details"]["task"]["holder"] == "main"
    assert tasks[4]["isError"] and "assign" in tasks[4]["text"]
    message = next(call for call in calls if call["name"] == "message")
    assert "nobody-here" in message["text"] and message["isError"], message
    agents = [call for call in calls if call["name"].startswith("agent_")]
    assert len(agents) == 6, agents
    assert agents[0]["isError"], "an identity with no legal name must be refused"
    assert all(not call["isError"] for call in agents[1:]), agents
    assert agents[1]["details"]["disposition"] == "started" and agents[1]["details"]["prompted"] is True
    assert agents[1]["details"]["session"].startswith("session:")
    assert agents[2]["details"]["disposition"] == "inspected"
    assert agents[2]["details"]["sessions"][0]["session"] == agents[1]["details"]["session"]
    assert agents[3]["details"]["disposition"] == "stopped" and agents[3]["details"]["state"] == "stopped"
    assert agents[4]["details"]["disposition"] == "started" and agents[4]["details"]["prompted"] is True
    assert "Input accepted" in agents[4]["text"]
    assert agents[5]["details"]["disposition"] == "stopped"
    events = install.records("rpc.jsonl")
    idle_receipt = next(index for index, event in enumerate(events)
        if event["kind"] == "tool-result" and event.get("name") == "install-idle")
    input_receipt = next(index for index, event in enumerate(events)
        if event["kind"] == "tool-result" and event.get("name") == "install-input")
    assert idle_receipt < input_receipt, events
    assert any(event["kind"] == "response" and event.get("command") == "prompt"
        and event.get("success") is True for event in events[:input_receipt]), events
    spawned = [event["pid"] for event in events if event["kind"] == "spawn"]
    closed = [event["pid"] for event in events if event["kind"] == "close"]
    assert len(spawned) == 2 and set(spawned) == set(closed), events
    # At least one arrival is proven: the provider holds the install-input receipt
    # until the loopback reports a request, so a run that reached here without one
    # already failed. At most one per spawned child, because a start never
    # fabricates a second turn. The old bound was exactly one, which only held
    # while a start could leave a child without work.
    assert 1 <= len(requests) <= len(spawned), (requests, spawned)
    assert not (install.agent_dir / "agents").exists(), "temporary smoke must not persist roles"
    assert not (install.agent_dir / "subagent-sessions").exists()


def test_network_guard_rejects_non_loopback_before_connecting(declared_install: Install) -> None:
    result = run(declared_install, [executable("node"), "-e",
        "require('node:net').connect({host: '192.0.2.1', port: 443})"])
    assert result.returncode != 0 and "forbids non-loopback" in result.stderr
    assert declared_install.records("network-attempts.jsonl"), "the guard itself must be exercised"

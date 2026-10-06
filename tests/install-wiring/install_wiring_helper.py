"""Disposable configured installs; never copy auth or install package sources."""
from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent
PACKAGE_TOOLS: dict[str, tuple[str, ...]] = {
    "subagents": ("agent_start", "agent_input", "agent_stop", "agent_list", "subagents_enable"),
    "tasks": ("create_task", "get_task", "list_tasks", "update_task"),
    "agent-teams": ("message",),
}
COORDINATION = {tool for tools in PACKAGE_TOOLS.values() for tool in tools}
PROVIDER = "install-wiring"
REPORT_PREFIX = "INSTALL_WIRING_REPORT "


def executable(name: str) -> str:
    resolved = shutil.which(name)
    assert resolved is not None, f"{name} is required for the isolated install wiring check"
    # Corepack's shim otherwise looks for pnpm in the disposable HOME and tries
    # downloading it. Reuse only the preinstalled executable, never user npmrc.
    if name == "pnpm" and "corepack" in Path(resolved).resolve().parts:
        manifest = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
        version = manifest["packageManager"].split("@", 1)[1].split("+", 1)[0]
        cache = Path(os.environ.get("COREPACK_HOME") or
            str(Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "node" / "corepack"))
        cached = cache / "v1" / "pnpm" / version / "bin" / "pnpm.cjs"
        if not cached.is_file() and os.name == "posix":
            # A caller can already isolate HOME before pytest starts. Locate only
            # the executable cache using the OS account directory, never settings.
            import pwd
            cached = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache" / "node" / "corepack" / "v1" / "pnpm" / version / "bin" / "pnpm.cjs"
        assert cached.is_file(), f"preinstalled pnpm {version} is required; network downloads are forbidden"
        return str(cached)
    return resolved


def pi_command() -> list[str]:
    """Use the workspace's verification cohort, not an ambient global Pi version."""
    entry = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    assert entry.is_file(), f"workspace Pi CLI is required at {entry}"
    return [executable("node"), str(entry)]


def workspace_pi_packages() -> list[Path]:
    packages = []
    for manifest_path in sorted((REPO / "packages").glob("*/package.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("pi") is not None or "pi-package" in manifest.get("keywords", []):
            packages.append(manifest_path.parent)
    assert packages, "no workspace Pi packages found"
    return packages


@dataclass(frozen=True)
class Install:
    root: Path
    home: Path
    agent_dir: Path
    cwd: Path
    settings: Path
    env: dict[str, str]

    def sources(self) -> list[str]:
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        return [entry["source"] if isinstance(entry, dict) else entry for entry in data["packages"]]

    def records(self, name: str) -> list[dict[str, object]]:
        path = self.root / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def isolated_install(root: Path, packages: Sequence[Path]) -> Install:
    home = root / "home"
    agent_dir = home / ".pi" / "agent"
    cwd = root / "project"
    for directory in (agent_dir, cwd, root / "tmp", root / "config", root / "cache"):
        directory.mkdir(parents=True, exist_ok=True)
    settings = agent_dir / "settings.json"
    settings.write_text(json.dumps({
        "packages": [str(package.resolve()) for package in packages],
        "theme": "dark", "quietStartup": True, "defaultProjectTrust": "never",
        "extensions": ["-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search"],
        "enableAnalytics": False, "enableInstallTelemetry": False, "cacheWarming": "off",
        "compaction": {"enabled": False}, "retry": {"enabled": False},
    }), encoding="utf-8")
    # The only credential is generated here and stored beneath this test's HOME.
    (agent_dir / "auth.json").write_text(json.dumps({
        PROVIDER: {"type": "api_key", "key": secrets.token_hex(16)},
    }), encoding="utf-8")
    (agent_dir / "models.json").write_text('{"providers": {}}', encoding="utf-8")
    (root / "npmrc").write_text("offline=true\nregistry=http://127.0.0.1:9/\n", encoding="utf-8")
    (root / "global-npmrc").write_text("", encoding="utf-8")
    guard = root / "no-network.cjs"
    shutil.copyfile(SUPPORT / "no-network.cjs", guard)
    # An allowlist, not a denylist: no cloud/provider auth, proxies, preload code,
    # inherited Pi paths, package credentials or SSH socket enter the process.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "LANG", "LANGUAGE", "TZ", "TERM"} or key.startswith("LC_")}
    # The pack script invokes pnpm again. Point it at the same preinstalled CLI
    # without Corepack needing either a personal cache HOME or a download.
    bin_dir = root / "bin"
    bin_dir.mkdir()
    pnpm = executable("pnpm")
    shim = bin_dir / "pnpm"
    shim.write_text(f'#!/bin/sh\nexec {shlex.quote(executable("node"))} {shlex.quote(pnpm)} "$@"\n', encoding="utf-8")
    shim.chmod(0o700)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", os.defpath)
    env.update({
        "HOME": str(home), "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        "TMPDIR": str(root / "tmp"), "TMP": str(root / "tmp"), "TEMP": str(root / "tmp"),
        "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_STATE_HOME": str(root / "state"),
        "npm_config_userconfig": str(root / "npmrc"),
        "npm_config_globalconfig": str(root / "global-npmrc"),
        "npm_config_cache": str(root / "cache" / "npm"), "npm_config_offline": "true",
        "COREPACK_ENABLE_NETWORK": "0", "NODE_OPTIONS": f'--require="{guard}"',
        "INSTALL_WIRING_SCENARIO": "surface", "NO_COLOR": "1",
    })
    return Install(root, home, agent_dir, cwd, settings, env)


def audit_settings(install: Install, environ: Mapping[str, str] | None = None) -> Path:
    """PI_INSTALL_SETTINGS opts into read-only declarations, never live loading."""
    override = (os.environ if environ is None else environ).get("PI_INSTALL_SETTINGS")
    return Path(override).resolve() if override else install.settings


def run(install: Install, command: Sequence[str], *, cwd: Path | None = None,
        timeout: int = 120, scenario: str = "surface") -> subprocess.CompletedProcess[str]:
    env = {**install.env, "INSTALL_WIRING_SCENARIO": scenario}
    command = list(command)
    if command[0].endswith("pnpm.cjs"):
        command.insert(0, executable("node"))
    process = subprocess.Popen(command, cwd=cwd or install.cwd, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        raise AssertionError(f"isolated command timed out: {command}\n{stdout}\n{stderr}") from None
    finally:
        # pi-kit detaches RPC children. Only reap pids recorded by our own preload,
        # and only if native closure was not confirmed, even when the parent exits.
        events = install.records("rpc.jsonl")
        closed = {event["pid"] for event in events if event["kind"] == "close"}
        for event in events:
            if event["kind"] != "spawn" or event["pid"] in closed:
                continue
            pid = event.get("pid")
            if isinstance(pid, int) and pid > 0:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def audit(install: Install, settings: Path) -> subprocess.CompletedProcess[str]:
    # Keep the production command's default user audit semantics untouched. Only
    # this test invocation supplies an explicit path to the unchanged script.
    return run(install, [executable("pnpm"), "check:install", str(settings)], cwd=REPO)


def loader_report(install: Install) -> dict[str, object]:
    result = run(install, [executable("node"), "--import", str(REPO / "node_modules" / "tsx" / "dist" / "loader.mjs"),
        str(SUPPORT / "loader.ts")])
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def pi_report(install: Install, *, scenario: str = "surface") -> dict[str, object]:
    # Do not use --no-extensions or -e for the packages: settings + manifest must
    # drive their discovery. The one explicit extension is only the offline model.
    result = run(install, [*pi_command(), "--print", "--no-session", "--no-context-files",
        "--no-skills", "--no-prompt-templates", "--no-themes", "--no-approve",
        "--provider", PROVIDER, "--model", "deterministic", "--thinking", "off",
        "--extension", str(SUPPORT / "provider.ts"), "Verify the configured install"], scenario=scenario)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.strip() == "", result.stderr
    reports = [line[len(REPORT_PREFIX):] for line in result.stdout.splitlines() if line.startswith(REPORT_PREFIX)]
    assert len(reports) == 1, result.stdout
    assert not install.records("network-attempts.jsonl"), "the run attempted external network access"
    return json.loads(reports[0])

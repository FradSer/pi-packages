"""Explicit low-token real-model Docker smoke for the current subagents sources.

The upstream credential stays on the host: the container only receives a
one-request-scoped proxy token. Every functional path runs once; the historical
study's repeated rounds and heldout quality arms are intentionally not run here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages/continual-learning/tests"))
from docker_experiment import InferenceProxy, redact_transport_credentials

PROVIDER = "magpie-hy4"
MODEL = "hunyuan-eval/hy4-dev"
PI_VERSION = "1.5.0"


def command(args: list[str], timeout: int = 1200) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[-3000:]}")
    return result.stdout.strip()


def build(output: Path) -> tuple[str, str]:
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="subagent-minimal-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "subagents"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache",
                    ".pi", ".memory", "results", "evidence", "tests/docker-study/evidence"))
        for file in sorted((context / "packages").rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(context)).encode())
                digest.update(file.read_bytes())
        source_hash = digest.hexdigest()
        image = f"subagents-minimal:{source_hash[:16]}"
        (context / "package.json").write_text(json.dumps({
            "private": True, "type": "module", "packageManager": "bun@1.4.1",
            "workspaces": ["packages/*"],
            "overrides": {
                "@earendil-works/chord": PI_VERSION, "@earendil-works/pi-agent-core": PI_VERSION,
                "@earendil-works/pi-ai": PI_VERSION, "@earendil-works/pi-coding-agent": PI_VERSION,
                "@earendil-works/pi-codemode": PI_VERSION, "@earendil-works/pi-mcp": PI_VERSION,
                "@earendil-works/pi-telemetry": PI_VERSION, "@earendil-works/pi-tui": PI_VERSION,
            },
            "trustedDependencies": ["esbuild", "@google/genai", "protobufjs"],
        }))
        shutil.copyfile(Path(__file__).with_name("Dockerfile.minimal"), context / "Dockerfile")
        print(f"BUILD {image}", flush=True)
        (output / "build.log").write_text(command(["docker", "build", "-t", image, str(context)]))
    return image, source_hash


def disposable_config_host() -> Path:
    """Host-side config for InferenceProxy: names the real gateway directly."""
    root = Path(tempfile.mkdtemp(prefix="subagent-minimal-host-"))
    root.chmod(0o700)
    (root / "models.json").write_text(json.dumps({"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": os.environ["MAGPIE_BASE_URL"].rstrip("/"),
        "api": "openai-completions", "apiKey": os.environ["MAGPIE_API_KEY"],
        "models": [{"id": MODEL, "reasoning": True}]}}}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def disposable_config(proxy: InferenceProxy) -> Path:
    root = Path(tempfile.mkdtemp(prefix="subagent-minimal-agent-"))
    root.chmod(0o700)
    key_variable = "STUDY_PROXY_TOKEN"
    models = {"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": f"http://host.docker.internal:{proxy.server.server_address[1]}/v1", "api": "openai-completions",
        "apiKey": f"${{{key_variable}}}",
        "compat": {"supportsReasoningEffort": True, "maxTokensField": "max_tokens",
            "supportsDeveloperRole": False},
        "models": [{"id": MODEL, "name": "hy4-dev", "api": "openai-completions",
            "contextWindow": 1048576, "maxTokens": 65536, "reasoning": True,
            "input": ["text"],
            "thinkingLevelMap": {"off": "none", "minimal": "none", "low": "none",
                "medium": "none", "high": "none", "xhigh": "none", "max": "none"},
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}
    (root / "models.json").write_text(json.dumps(models))
    (root / "auth.json").write_text("{}")
    (root / "settings.json").write_text(json.dumps({
        "defaultProvider": PROVIDER, "defaultModel": MODEL, "packages": [],
        "quietStartup": True, "retry": {"enabled": False}}))
    (root / "continual-learning.json").write_text(json.dumps({
        "model": f"{PROVIDER}/{MODEL}", "autoSettledLearning": False, "autoContinualLearning": False}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def grade(output: Path, metadata: dict) -> dict:
    study = json.loads((output / "study.json").read_text())
    notices = [json.loads(line) for line in (output / "notices.jsonl").read_text().splitlines()]
    receipts = json.loads((output / "receipts.json").read_text())
    spawns = json.loads((output / "spawns.json").read_text())
    audits = []
    for file in sorted(output.glob("child-*.jsonl")):
        events = [json.loads(line) for line in file.read_text().splitlines()]
        calls = {e["id"]: e for e in events if e.get("event") == "call"}
        memory = []
        for event in events:
            if event.get("event") != "result" or event.get("tool") != "agent_memory":
                continue
            memory.append({"args": calls.get(event.get("id"), {}).get("args"),
                "error": event.get("error"), "content": event.get("content")})
        audits.append({"file": file.name, "memoryActions": memory,
            "memoryIndexInjected": any(e.get("memory") for e in events if e.get("event") == "system")})
    result_notices = [n for n in notices if n.get("kind") == "result"]
    usage_rows = [n.get("usage", {}) for n in result_notices]
    usage = {"input": sum(row.get("input", 0) for row in usage_rows),
        "output": sum(row.get("output", 0) for row in usage_rows),
        "cacheRead": sum(row.get("cacheRead", 0) for row in usage_rows),
        "total": sum(row.get("totalTokens", 0) for row in usage_rows),
        "pricedNotices": sum(row.get("totalTokens", 0) > 0 for row in usage_rows),
        "resultNotices": len(result_notices)}
    temp = study.get("temporary", {})
    saved = study.get("saved", {})
    readonly = study.get("readonly", {})
    writer = study.get("writer", {})
    operations = {r["name"] for r in receipts}
    parent_tui = json.loads((output / "parent-tui.json").read_text()) if (output / "parent-tui.json").exists() else {}
    checks = {
        "completed": study.get("completed") is True and not study.get("error"),
        "piVersion": study.get("piVersion") == PI_VERSION,
        "model": study.get("model") == f"{PROVIDER}/{MODEL}",
        "allIntentTools": operations >= {"agent_start", "agent_input", "agent_stop", "agent_list"},
        "temporaryFirst": "FIRST_OK" in temp.get("first", {}).get("text", ""),
        "temporaryNext": "SECOND_OK" in temp.get("second", {}).get("text", ""),
        "temporaryIdle": temp.get("idle") == "idle",
        "temporaryStop": temp.get("stop", {}).get("ok") is True,
        "staleRefused": temp.get("stale", {}).get("ok") is False,
        "savedStart": saved.get("started", {}).get("ok") is True,
        "savedResult": saved.get("notice", {}).get("kind") == "result",
        "savedRestart": saved.get("restart", {}).get("notice", {}).get("kind") == "result",
        "invalidIdentity": study.get("invalidIdentity", {}).get("ok") is False,
        "identityWithInstructions": study.get("identityWithInstructions", {}).get("ok") is False,
        "readOnlyMemoryResult": readonly.get("notice", {}).get("kind") == "result",
        "readOnlyProposal": bool(readonly.get("proposals")),
        "writerResult": writer.get("first", {}).get("kind") == "result",
        "writerMemoryEntry": any(m["file"] == "contract.md" for m in writer.get("memoryFiles", [])),
        "writerNextResult": writer.get("second", {}).get("kind") == "result",
        "memoryAppendRefused": any(a.get("error") for a in (a for audit in audits for a in audit["memoryActions"])),
        "memoryAppendAccepted": any(not a.get("error") for a in (a for audit in audits for a in audit["memoryActions"])),
        "memoryIndexInjected": any(a["memoryIndexInjected"] for a in audits),
        "parentModelSelection": parent_tui.get("markerObserved") is True,
        "tuiRepaint": parent_tui.get("expandRepaintObserved") is True and parent_tui.get("resizeRepaintObserved") is True,
        "finalRosterStopped": all(r["status"] == "stopped" for r in study.get("finalRoster", [])),
        "noTransportErrors": metadata.get("transportErrors") == 0,
        "reasoningOffOnWire": bool(metadata.get("modelObservations")) and all(
            row.get("reasoningEffortOnWire") == "none" for row in metadata["modelObservations"]),
        "tokenUsageObserved": usage["pricedNotices"] == usage["resultNotices"] > 0,
    }
    wire_bytes = sum(len(json.dumps(row, ensure_ascii=False).encode()) for row in metadata.get("modelObservations", []))
    return {"model": study.get("model"), "piVersion": study.get("piVersion"),
        "providerRequests": metadata.get("requests"), "transportErrors": metadata.get("transportErrors"),
        "measuredTokens": usage,
        "requestedToolsOnWire": sorted({row.get("toolCount") for row in metadata.get("modelObservations", [])
            if isinstance(row.get("toolCount"), int)}),
        "evidenceBytes": {"observations": wire_bytes, "resultNotices": len(result_notices)},
        "checks": checks,
        "passed": all(checks.values()), "spawns": len(spawns),
        "resultNotices": len(result_notices), "limitations": [
            "One compact real-model pass per path; no repeated rounds, heldout quality comparison or statistical benefit claim.",
            "Token totals come from native result notices; parent TUI turns are counted separately by the transport proxy."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-budget", type=int, default=48)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    image, source_hash = build(output)
    host_config = disposable_config_host()
    with InferenceProxy(host_config, selection={"provider": PROVIDER, "model": MODEL},
                        request_budget=args.request_budget, expected_api="openai-completions") as proxy:
        config = disposable_config(proxy)
        name = f"subagents-minimal-{source_hash[:8]}"
        container = command(["docker", "run", "-d", "--name", name, "--add-host", "host.docker.internal:host-gateway",
            "--memory", "3g", "--cpus", "2", "--pids-limit", "128", "--cap-drop", "ALL",
            "-e", f"STUDY_PROXY_TOKEN={proxy.token}",
            "-e", "PI_TEAMMATE_ENV_ALLOW=STUDY_PROXY_TOKEN",
            "--security-opt", "no-new-privileges", image])
        metadata = {"image": image, "sourceSha256": source_hash, "model": f"{PROVIDER}/{MODEL}",
            "started": datetime.now(timezone.utc).isoformat(), "container": container,
            "credentialPolicy": "one-time proxy token only; MAGPIE_API_KEY never enters the image"}
        try:
            config_files = {file.name: file.read_text() for file in config.iterdir()}
            install_script = ("import json,sys,os;from pathlib import Path;root=Path('/agent');"
                "data=json.load(sys.stdin);[((root/name).write_text(body),os.chmod(root/name,0o600)) for name,body in data.items()]")
            installed = subprocess.run(["docker", "exec", "-i", container, "python", "-c", install_script],
                input=json.dumps(config_files), capture_output=True, text=True, timeout=30)
            if installed.returncode:
                raise RuntimeError("Could not install isolated proxy configuration")
            metadata["piVersion"] = command(["docker", "exec", container, "pi", "--version"])
            script = ("import fs from 'node:fs';console.log(JSON.stringify(Object.fromEntries(['kit','subagents']"
                ".map(name=>[name,JSON.parse(fs.readFileSync('/opt/study/packages/'+name+'/node_modules/"
                "@earendil-works/pi-coding-agent/package.json','utf8')).version]))));")
            metadata["workspacePiVersions"] = json.loads(command(["docker", "exec", container,
                "node", "--input-type=module", "-e", script]))
            if any(version != PI_VERSION for version in metadata["workspacePiVersions"].values()):
                raise RuntimeError("Workspace resolved a different Pi version")
            print(f"RUN Pi {metadata['piVersion']} {metadata['model']}", flush=True)
            result = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent", "-e", "PI_SKIP_VERSION_CHECK=1",
                container, "node", "--import", "/opt/study/node_modules/tsx/dist/loader.mjs",
                "/opt/study/packages/subagents/tests/docker-study/minimal.ts"],
                capture_output=True, text=True, timeout=1200)
            (output / "runtime.log").write_text(redact_transport_credentials(result.stdout + result.stderr, proxy))
            metadata["studyExitCode"] = result.returncode
            if result.returncode == 0:
                parent = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent",
                    "-e", "PI_SKIP_VERSION_CHECK=1", container, "python",
                    "/opt/study/packages/subagents/tests/docker-study/minimal-parent.py"],
                    capture_output=True, text=True, timeout=480)
                (output / "parent.log").write_text(redact_transport_credentials(parent.stdout + parent.stderr, proxy))
                metadata["parentExitCode"] = parent.returncode
            metadata["requests"] = proxy.requests
            metadata["transportErrors"] = proxy.errors
            metadata["modelObservations"] = proxy.model_observations
            print(f"FINISH exit={result.returncode} requests={proxy.requests} errors={proxy.errors}", flush=True)
        finally:
            command(["docker", "cp", f"{container}:/results/.", str(output)])
            command(["docker", "rm", "-f", container])
            (output / "metadata.json").write_text(redact_transport_credentials(json.dumps(metadata, indent=2), proxy))
            shutil.rmtree(config, ignore_errors=True)
        shutil.rmtree(host_config, ignore_errors=True)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    graded = grade(output, metadata)
    (output / "summary.json").write_text(json.dumps(graded, indent=2))
    print(json.dumps(graded, indent=2), flush=True)
    sys.exit(0 if graded["passed"] else 1)


if __name__ == "__main__":
    main()

"""Explicit low-token real-model Docker smoke for the current matt-pocock sources.

One native invocation per functional path plus one real hy4-dev parent-model
turn. The upstream credential stays on the host: the container receives only a
one-run proxy token in STUDY_PROXY_TOKEN.
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
    with tempfile.TemporaryDirectory(prefix="matt-minimal-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "matt-pocock"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache",
                    ".pi", ".memory", "results", "evidence", "tests/docker-study/evidence"))
        for file in sorted((context / "packages").rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(context)).encode())
                digest.update(file.read_bytes())
        source_hash = digest.hexdigest()
        image = f"matt-minimal:{source_hash[:16]}"
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
    root = Path(tempfile.mkdtemp(prefix="matt-minimal-host-"))
    root.chmod(0o700)
    (root / "models.json").write_text(json.dumps({"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": os.environ["MAGPIE_BASE_URL"].rstrip("/"),
        "api": "openai-completions", "apiKey": os.environ["MAGPIE_API_KEY"],
        "models": [{"id": MODEL, "reasoning": True}]}}}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def disposable_config(proxy: InferenceProxy) -> Path:
    root = Path(tempfile.mkdtemp(prefix="matt-minimal-agent-"))
    root.chmod(0o700)
    (root / "models.json").write_text(json.dumps({"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": f"http://host.docker.internal:{proxy.server.server_address[1]}/v1",
        "api": "openai-completions", "apiKey": "$STUDY_PROXY_TOKEN",
        "compat": {"supportsReasoningEffort": True, "maxTokensField": "max_tokens",
            "supportsDeveloperRole": False},
        "models": [{"id": MODEL, "name": "hy4-dev", "api": "openai-completions",
            "contextWindow": 1048576, "maxTokens": 65536, "reasoning": True,
            "input": ["text"],
            "thinkingLevelMap": {"off": "none", "minimal": "none", "low": "none",
                "medium": "none", "high": "none", "xhigh": "none", "max": "none"},
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}))
    (root / "auth.json").write_text("{}")
    (root / "settings.json").write_text(json.dumps({
        "defaultProvider": PROVIDER, "defaultModel": MODEL, "packages": [],
        "quietStartup": True, "retry": {"enabled": False}}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def grade(output: Path, metadata: dict) -> dict:
    native = json.loads((output / "native.json").read_text())
    parent = json.loads((output / "parent-tui.json").read_text())
    observations = metadata.get("modelObservations", [])
    checks = {
        "nativeCompleted": (output / "native.json").is_file(),
        "registeredTools": native.get("registered") == ["matt_pocock_active", "matt_pocock_ask", "matt_pocock_workflow"],
        "singleCommand": native.get("commands") == ["matt-pocock"],
        "workflowStart": native.get("workflowCommand", {}).get("route") == "hard-bug"
            and native.get("workflowCommand", {}).get("procedure") == "diagnosing-bugs"
            and native.get("workflowCommand", {}).get("status") == "active"
            and native.get("workflowCommand", {}).get("request") == "Fix receipt quantity"
            and native.get("workflowCommand", {}).get("hasStateContract") is True,
        "workflowStatePersisted": native.get("workflowState", {}).get("status") == "active"
            and bool(native.get("workflowState", {}).get("workItemId")),
        "restore": native.get("restore", {}).get("persistedRecordsAdded") == 0
            and native.get("restore", {}).get("activeTools") == ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"],
        "transition": native.get("transition", {}).get("procedure") == "implement"
            and native.get("transition", {}).get("hasStateContract") is True
            and native.get("transition", {}).get("parameters") == ["action", "target", "reference", "reason"],
        "ask": native.get("ask", {}).get("pending") is True and native.get("ask", {}).get("source") == "no_ui",
        "completion": native.get("completed", {}).get("status") == "completed"
            and native.get("completed", {}).get("workItemId") == native.get("workflowState", {}).get("workItemId")
            and native.get("completed", {}).get("activeTools") == ["matt_pocock_workflow"],
        "capability": native.get("capability", {}).get("mode") == "capability"
            and native.get("capability", {}).get("hasSource") is True,
        "userCapability": native.get("userCapability", {}).get("mode") == "user-capability",
        "referenceDisclosure": native.get("reference", {}).get("mode") == "reference"
            and native.get("reference", {}).get("hasHeading") is True,
        "invalidCrossoverRefused": native.get("invalidCapabilityRefused") is True,
        "workflowReference": native.get("workflowReference", {}).get("action") == "load"
            and native.get("workflowReference", {}).get("textBytes", 0) > 0,
        "cancel": native.get("cancelled", {}).get("status") == "cancelled"
            and native.get("cancelled", {}).get("reason") == "done"
            and native.get("cancelled", {}).get("activeTools") == ["matt_pocock_workflow"],
        "unknownRouting": native.get("unknownRouting", {}).get("customType") == "matt-pocock-procedure"
            and native.get("unknownRouting", {}).get("textHasRouting") is True,
        "parentModelSelection": parent.get("markerObserved") is True and parent.get("gatewayRowObserved") is True,
        "tuiRepaint": parent.get("expandRepaintObserved") is True and parent.get("resizeRepaintObserved") is True,
        "realModelRequests": 0 < metadata.get("requests", 0) <= 12,
        "reasoningOffOnWire": bool(observations) and all(row.get("reasoningEffortOnWire") == "none" for row in observations),
        "noTransportErrors": metadata.get("transportErrors") == 0,
        "piVersion": metadata.get("piVersion") == PI_VERSION and metadata.get("workspacePiVersions") == {
            "kit": PI_VERSION, "matt-pocock": PI_VERSION},
    }
    return {"model": f"{PROVIDER}/{MODEL}", "piVersion": metadata.get("piVersion"),
        "providerRequests": metadata.get("requests"), "transportErrors": metadata.get("transportErrors"),
        "nativeInjectedBytes": sum(native.get(key, {}).get("textBytes", 0) for key in
            ("workflowCommand", "transition", "capability", "userCapability", "reference", "workflowReference")
            if isinstance(native.get(key), dict)),
        "modelObservations": len(observations),
        "requestedToolsOnWire": sorted({row.get("toolCount") for row in observations if isinstance(row.get("toolCount"), int)}),
        "checks": checks, "passed": all(checks.values()),
        "limitations": [
            "One native invocation per functional path and one parent-model turn; not an end-to-end model-authored procedure journey.",
            "Injected byte totals measure resolved procedure bundles, not the provider's exact tokenizer.",
            "No repeated quality arms, semantic benefit claim or statistical generalization."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-budget", type=int, default=12)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    image, source_hash = build(output)
    host_config = disposable_config_host()
    with InferenceProxy(host_config, selection={"provider": PROVIDER, "model": MODEL},
                        request_budget=args.request_budget, expected_api="openai-completions") as proxy:
        config = disposable_config(proxy)
        name = f"matt-minimal-{source_hash[:8]}"
        container = command(["docker", "run", "-d", "--name", name, "--add-host", "host.docker.internal:host-gateway",
            "--memory", "3g", "--cpus", "2", "--pids-limit", "128", "--cap-drop", "ALL",
            "-e", f"STUDY_PROXY_TOKEN={proxy.token}",
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
                raise RuntimeError(f"Could not install isolated proxy configuration: {installed.stderr[-500:]}")
            metadata["piVersion"] = command(["docker", "exec", container, "pi", "--version"])
            script = ("import fs from 'node:fs';console.log(JSON.stringify(Object.fromEntries(['kit','matt-pocock']"
                ".map(name=>[name,JSON.parse(fs.readFileSync('/opt/study/packages/'+name+'/node_modules/"
                "@earendil-works/pi-coding-agent/package.json','utf8')).version]))));")
            metadata["workspacePiVersions"] = json.loads(command(["docker", "exec", container,
                "node", "--input-type=module", "-e", script]))
            if any(version != PI_VERSION for version in metadata["workspacePiVersions"].values()):
                raise RuntimeError("Workspace resolved a different Pi version")
            print(f"RUN Pi {metadata['piVersion']} {metadata['model']}", flush=True)
            native = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent", "-e", "PI_SKIP_VERSION_CHECK=1",
                container, "node", "--import", "/opt/study/node_modules/tsx/dist/loader.mjs",
                "/opt/study/packages/matt-pocock/tests/docker-study/native.ts"],
                capture_output=True, text=True, timeout=240)
            (output / "native.log").write_text(redact_transport_credentials(native.stdout + native.stderr, proxy))
            metadata["nativeExitCode"] = native.returncode
            if native.returncode == 0:
                parent = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent",
                    "-e", "PI_SKIP_VERSION_CHECK=1", container, "python",
                    "/opt/study/packages/matt-pocock/tests/docker-study/parent.py"],
                    capture_output=True, text=True, timeout=300)
                (output / "parent.log").write_text(redact_transport_credentials(parent.stdout + parent.stderr, proxy))
                metadata["parentExitCode"] = parent.returncode
            metadata["requests"] = proxy.requests
            metadata["transportErrors"] = proxy.errors
            metadata["modelObservations"] = proxy.model_observations
            print(f"FINISH native={native.returncode} requests={proxy.requests} errors={proxy.errors}", flush=True)
        finally:
            command(["docker", "cp", f"{container}:/results/.", str(output)])
            command(["docker", "rm", "-f", container])
            (output / "metadata.json").write_text(redact_transport_credentials(json.dumps(metadata, indent=2), proxy))
            shutil.rmtree(config, ignore_errors=True)
        shutil.rmtree(host_config, ignore_errors=True)
    graded = grade(output, metadata)
    (output / "summary.json").write_text(json.dumps(graded, indent=2) + "\n")
    print(json.dumps(graded, indent=2), flush=True)
    sys.exit(0 if graded["passed"] else 1)


if __name__ == "__main__":
    main()

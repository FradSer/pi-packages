"""Explicit real-model Docker E2E for the current Goal runtime.

The real Magpie credential stays on the host. The container receives only a
one-run proxy token, a disposable agent directory, and the packed Goal sources.
This is one native session, not a statistical benefit or model-quality study.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages/continual-learning/tests"))
from docker_experiment import InferenceProxy, redact_transport_credentials

PROVIDER = "magpie-hy4"
MODEL = "hunyuan-eval/hy4-dev"
PI_VERSION = "1.3.0"


def command(args: list[str], timeout: int = 1200) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[-3000:]}")
    return result.stdout.strip()


def build(output: Path) -> tuple[str, dict]:
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="goal-real-model-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "goal"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache",
                    ".pi", ".memory", "results", "evidence", "tests/docker-study/evidence"))
        for file in sorted((context / "packages").rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(context)).encode())
                digest.update(file.read_bytes())
        source_hash = digest.hexdigest()
        image = f"goal-real-model:{source_hash[:16]}"
        (context / "package.json").write_text(json.dumps({
            "private": True, "type": "module", "packageManager": "bun@1.4.1",
            "workspaces": ["packages/*"],
            "overrides": {
                "@earendil-works/pi-coding-agent": PI_VERSION, "@earendil-works/pi-ai": PI_VERSION,
                "@earendil-works/pi-agent-core": PI_VERSION, "@earendil-works/pi-codemode": PI_VERSION,
                "@earendil-works/pi-mcp": PI_VERSION, "@earendil-works/pi-telemetry": PI_VERSION,
                "@earendil-works/pi-tui": PI_VERSION,
            },
            "trustedDependencies": ["esbuild", "@google/genai", "protobufjs"],
        }))
        shutil.copyfile(Path(__file__).with_name("Dockerfile.goal-real-model"), context / "Dockerfile")
        print(f"BUILD {image}", flush=True)
        (output / "build.log").write_text(command(["docker", "build", "-t", image, str(context)]))
    return image, {"image": image, "sourceSha256": source_hash}


def disposable_config_host() -> Path:
    root = Path(tempfile.mkdtemp(prefix="goal-real-model-host-"))
    root.chmod(0o700)
    (root / "models.json").write_text(json.dumps({"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": os.environ["MAGPIE_BASE_URL"].rstrip("/"),
        "api": "openai-completions", "apiKey": os.environ["MAGPIE_API_KEY"],
        "models": [{"id": MODEL, "reasoning": True}]}}}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def disposable_config(proxy: InferenceProxy) -> Path:
    root = Path(tempfile.mkdtemp(prefix="goal-real-model-agent-"))
    root.chmod(0o700)
    key_variable = "GOAL_PROXY_TOKEN"
    models = {"providers": {PROVIDER: {
        "name": "Magpie HY4", "baseUrl": f"http://host.docker.internal:{proxy.server.server_address[1]}/v1",
        "api": "openai-completions", "apiKey": f"${{{key_variable}}}",
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
        "defaultProvider": PROVIDER, "defaultModel": MODEL, "packages": [
            "/opt/study/packages/goal"],
        "quietStartup": True, "retry": {"enabled": False}}))
    for file in root.iterdir():
        file.chmod(0o600)
    return root


def grade(output: Path, metadata: dict) -> dict:
    def read(name: str):
        path = output / name
        return json.loads(path.read_text()) if path.exists() else None
    run = read("run.json") or {}
    terminal = read("terminal.json") or {}
    goal = read("goal-record.json") or {}
    rows = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()] if (output / "events.jsonl").exists() else []
    models = [row for row in rows if row.get("type") == "message_end" or row.get("event") == "message_end"]
    checks = {
        "completed": run.get("completed") is True and not run.get("error"),
        "goalTerminal": (goal.get("goal", {}) if isinstance(goal, dict) else {}).get("status") == "complete",
        "piVersion": metadata.get("piVersion") == PI_VERSION,
        "model": run.get("model") == f"{PROVIDER}/{MODEL}",
        "providerRequests": metadata.get("requests", 0) > 0,
        "noTransportErrors": metadata.get("transportErrors") == 0,
        "reasoningOffOnWire": bool(metadata.get("modelObservations")) and all(
            row.get("reasoningEffortOnWire") == "none" for row in metadata["modelObservations"]),
        "requestRow": terminal.get("requestRowObserved") is True,
        "goalCreated": isinstance(goal.get("goal"), dict) and bool(goal["goal"].get("objective")),
        "objectiveConcise": isinstance(goal.get("goal"), dict) and len(goal["goal"].get("objective", "")) <= 400,
        "realToolResult": terminal.get("workResultObserved") is True,
        "completionCheck": run.get("completionCheckObserved") is True,
        "measuredUsage": sum(row.get("message", {}).get("usage", {}).get("totalTokens", 0) for row in models) > 0,
        "nativeEventAudit": any(row.get("event") in ("ready", "tool_call", "tool_result") for row in rows),
        "noHostCredential": metadata.get("credentialPolicy") == "one-time proxy token only; MAGPIE_API_KEY never enters the image",
    }
    return {"checks": checks, "passed": all(checks.values()), "requestCount": metadata.get("requests"),
        "transportErrors": metadata.get("transportErrors"),
        "limitations": ["One real-model native session; no repeated cohorts, heldout quality comparison or statistical benefit claim.",
            "Provider usage comes from native message_end events; the tool-less completion check is counted separately by the transport proxy."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-budget", type=int, default=24)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    image, metadata = build(output)
    host_config = disposable_config_host()
    with InferenceProxy(host_config, selection={"provider": PROVIDER, "model": MODEL},
                        request_budget=args.request_budget, expected_api="openai-completions") as proxy:
        config = disposable_config(proxy)
        container = ""
        name = f"goal-real-model-{secrets.token_hex(4)}"
        try:
            container = command(["docker", "run", "-d", "--name", name, "--add-host", "host.docker.internal:host-gateway",
                "--memory", "3g", "--cpus", "2", "--pids-limit", "128", "--cap-drop", "ALL",
                "-e", f"GOAL_PROXY_TOKEN={proxy.token}", "--security-opt", "no-new-privileges", image])
            metadata.update({"model": f"{PROVIDER}/{MODEL}", "container": container,
                "started": datetime.now(timezone.utc).isoformat(),
                "credentialPolicy": "one-time proxy token only; MAGPIE_API_KEY never enters the image"})
            install_script = ("import json,sys,os;from pathlib import Path;root=Path('/agent');"
                "data=json.load(sys.stdin);[((root/name).write_text(body),os.chmod(root/name,0o600)) for name,body in data.items()]")
            installed = subprocess.run(["docker", "exec", "-i", container, "python", "-c", install_script],
                input=json.dumps({file.name: file.read_text() for file in config.iterdir()}),
                capture_output=True, text=True, timeout=30)
            if installed.returncode:
                raise RuntimeError("Could not install isolated proxy configuration")
            metadata["piVersion"] = command(["docker", "exec", container, "pi", "--version"])
            preflight = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent",
                "-e", "PI_SKIP_VERSION_CHECK=1", container, "pi", "--no-extensions", "--no-skills",
                "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-session",
                "--print", "--mode", "json", "--model", f"{PROVIDER}/{MODEL}", "--thinking", "off",
                "Reply READY."], capture_output=True, text=True, timeout=120)
            (output / "provider-preflight.json").write_text(redact_transport_credentials(json.dumps(
                {"exitCode": preflight.returncode, "stdout": preflight.stdout[-2000:],
                 "stderr": preflight.stderr[-2000:]}, indent=2), proxy))
            print(f"RUN Pi {metadata['piVersion']} {metadata['model']}", flush=True)
            result = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent",
                "-e", "PI_SKIP_VERSION_CHECK=1", container, "/opt/venv/bin/python",
                "/opt/study/packages/goal/tests/goal_real_model_runner.py"],
                capture_output=True, text=True, timeout=1200)
            (output / "runtime.log").write_text(redact_transport_credentials(result.stdout + result.stderr, proxy))
            metadata["studyExitCode"] = result.returncode
            metadata["requests"] = proxy.requests
            metadata["transportErrors"] = proxy.errors
            metadata["modelObservations"] = proxy.model_observations
            metadata["usage"] = {"requests": proxy.requests, "errors": proxy.errors}
            print(f"FINISH exit={result.returncode} requests={proxy.requests} errors={proxy.errors}", flush=True)
        finally:
            if container:
                command(["docker", "cp", f"{container}:/results/.", str(output)])
                command(["docker", "rm", "-f", container])
            (output / "metadata.json").write_text(redact_transport_credentials(json.dumps(metadata, indent=2), proxy))
            shutil.rmtree(config, ignore_errors=True)
        shutil.rmtree(host_config, ignore_errors=True)
    graded = grade(output, metadata)
    (output / "summary.json").write_text(json.dumps(graded, indent=2))
    print(json.dumps(graded, indent=2), flush=True)
    sys.exit(0 if graded["passed"] else 1)


if __name__ == "__main__":
    main()

"""Explicit Docker/native Pi study; never runs on normal CI or uses real agent homes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages/continual-learning/tests"))
from docker_experiment import InferenceProxy, redact_transport_credentials


def command(args: list[str], timeout: int = 1200) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[-3000:]}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="subagent-study-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "subagents"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".pi", ".memory", "results", "evidence"))
        for file in sorted((context / "packages").rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(context)).encode())
                digest.update(file.read_bytes())
        source_hash = digest.hexdigest()
        image = f"subagents-study:{source_hash[:16]}"
        (context / "package.json").write_text('{"private":true,"type":"module","packageManager":"pnpm@11.21.0"}')
        (context / "pnpm-workspace.yaml").write_text('packages:\n  - packages/*\nallowBuilds:\n  esbuild: true\n  "@google/genai": true\n  protobufjs: true\n')
        shutil.copyfile(Path(__file__).with_name("Dockerfile"), context / "Dockerfile")
        print(f"BUILD {image}", flush=True)
        (output / "build.log").write_text(command(["docker", "build", "-t", image, str(context)]))
    selection = {"provider": "cli-proxy", "model": "opencode/deepseek-v4.1-flash"}
    with InferenceProxy(Path.home() / ".pi/agent", selection=selection, request_budget=160) as proxy:
        name = f"subagents-study-{source_hash[:8]}"
        container = command(["docker", "run", "-d", "--name", name, "--memory", "3g", "--cpus", "2", "--pids-limit", "128", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", image])
        metadata = {"image":image,"sourceSha256":source_hash,"model":selection,"started":datetime.now(timezone.utc).isoformat(),"container":container}
        try:
            with tempfile.TemporaryDirectory(prefix="subagent-study-config-") as temporary:
                config = Path(temporary) / "agent"
                proxy.write_agent_config(config)
                payload=json.dumps({file.name:file.read_text() for file in config.iterdir()})
                script="import json,sys; from pathlib import Path; root=Path('/agent'); [(root/name).write_text(body) for name,body in json.load(sys.stdin).items()]"
                installed=subprocess.run(["docker","exec","-i",container,"python","-c",script],input=payload,capture_output=True,text=True,timeout=30)
                if installed.returncode:raise RuntimeError("Could not install isolated proxy configuration")
            metadata["parentHarnessSha256"]={file:hashlib.sha256(Path(__file__).with_name(file).read_bytes()).hexdigest() for file in ("audit.ts","parent-probe.py")}
            metadata["piVersion"] = command(["docker", "exec", container, "pi", "--version"])
            script="import fs from 'node:fs'; console.log(JSON.stringify(Object.fromEntries(['kit','subagents'].map(name=>[name,JSON.parse(fs.readFileSync('/opt/study/packages/'+name+'/node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version]))));"
            metadata["workspacePiVersions"]=json.loads(command(["docker","exec",container,"node","--input-type=module","-e",script]))
            if any(version != "1.0.4" for version in metadata["workspacePiVersions"].values()):
                raise RuntimeError("Workspace resolved a different Pi version")
            print(f"RUN Pi {metadata['piVersion']} {selection['model']}", flush=True)
            result = subprocess.run(["docker", "exec", "-e", "PI_CODING_AGENT_DIR=/agent", "-e", "PI_SKIP_VERSION_CHECK=1", container,
                "node", "--import", "/opt/study/node_modules/tsx/dist/loader.mjs", "/opt/study/packages/subagents/tests/docker-study/study.ts"],capture_output=True,text=True,timeout=2400)
            (output / "runtime.log").write_text(redact_transport_credentials(result.stdout+result.stderr,proxy))
            metadata["exitCode"] = result.returncode
            if result.returncode == 0:
                for file in ("audit.ts", "parent-probe.py"):
                    command(["docker","cp",str(Path(__file__).with_name(file)),f"{container}:/opt/study/packages/subagents/tests/docker-study/{file}"])
                parent=subprocess.run(["docker","exec","-e","PI_CODING_AGENT_DIR=/agent","-e","PI_SKIP_VERSION_CHECK=1",container,"python","/opt/study/packages/subagents/tests/docker-study/parent-probe.py"],capture_output=True,text=True,timeout=240)
                (output / "parent.log").write_text(redact_transport_credentials(parent.stdout+parent.stderr,proxy))
                metadata["parentExitCode"]=parent.returncode
            metadata["requests"] = proxy.requests
            metadata["transportErrors"] = proxy.errors
            print(f"FINISH exit={result.returncode} requests={proxy.requests}",flush=True)
        finally:
            command(["docker", "cp", f"{container}:/results/.", str(output)])
            with tempfile.TemporaryDirectory(prefix="subagent-study-data-") as temporary:
                copied=subprocess.run(["docker","cp",f"{container}:/agent/agents",temporary],capture_output=True,text=True,timeout=30)
                if copied.returncode == 0:
                    shutil.copytree(Path(temporary)/"agents",output/"agents",dirs_exist_ok=True)
            command(["docker", "rm", "-f", container])
            (output / "metadata.json").write_text(json.dumps(metadata,indent=2))


if __name__ == "__main__":
    main()

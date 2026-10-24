"""Native Pi print/RPC acceptance from packed archives; no external provider calls."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import queue
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
spec = importlib.util.spec_from_file_location("sdlc_existing_e2e_support", REPO / "tests/e2e/support/harness.py")
assert spec and spec.loader
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, input="", text=True, capture_output=True, timeout=90)


def hashes() -> dict[str, str]:
    return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(PACKAGE.rglob("*")) if path.is_file()
            and not any(part in {"node_modules", "__pycache__", ".pytest_cache"} for part in path.parts)}


def packed_install(output: Path) -> Path:
    """Use actual archives for SDLC and kit; the host supplies declared core peers."""
    archives = output / "archives"
    archives.mkdir()
    modules = output / "installed/node_modules"
    for name in ("kit", "sdlc"):
        result = run(["pnpm", "--dir", str(REPO / "packages" / name), "pack", "--pack-destination", str(archives)], cwd=REPO)
        assert result.returncode == 0, result.stdout + result.stderr
        package_name = "pi-sdlc" if name == "sdlc" else "@fradser/pi-kit"
        archive_prefix = package_name.lstrip("@").replace("/", "-")
        archive = next(archives.glob(f"{archive_prefix}-*.tgz"))
        target = modules / package_name
        target.mkdir(parents=True)
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                assert member.name.startswith("package/"), member.name
                assert "__pycache__" not in Path(member.name).parts and not member.name.endswith(".pyc"), member.name
                member.name = member.name.removeprefix("package/")
                if member.name:
                    bundle.extract(member, target, filter="data")
    for name in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-ai", "@earendil-works/pi-tui", "typebox"):
        link = modules / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to((REPO / "node_modules" / name).resolve(), target_is_directory=True)
    installed = modules / "pi-sdlc"
    manifest = json.loads((installed / "package.json").read_text())
    assert manifest["name"] == "pi-sdlc"
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert "workspace:" not in json.dumps(manifest)
    for resource in ("index.ts", "src/index.ts", "src/records.ts", "src/playbook.ts", "scripts/sdlc.py", "scripts/ci_eval.py", "scripts/run_agent.py", "scripts/github_approval.py", "references/playbook.md", "references/commands.md", "templates/SPEC.md", "templates/PLAN.md", "templates/REVIEW.md", "references/workflow.md", "templates/INTENT.md", "templates/HANDOFF.md"):
        assert (installed / resource).read_bytes() == (PACKAGE / resource).read_bytes()
    return installed


def native_case(output: Path, installed: Path, name: str, *, previous: Path | None = None) -> dict[str, object]:
    case = output / name
    case.mkdir()
    project = case / "project"
    project.mkdir()
    if previous:
        for record in ("INTENT.md", "HANDOFF.md"):
            shutil.copyfile(previous / "project" / record, project / record)
    env = support.isolated_environment(case)
    trace = case / "events.jsonl"
    env.update({"PI_E2E_AUTH": "offline-fixture", "PI_SDLC_SCRIPT": str(case / "script.json"), "PI_SDLC_TRACE": str(trace),
                "PI_NATIVE_NETWORK_LOG": str(case / "network.log"),
                "NODE_OPTIONS": f"--require={REPO / 'tests/native-run-start-no-network.cjs'}"})
    prompt = "让客户在门户查询理赔进度，只用现有身份认证，不新增个人敏感信息。第三方理赔员访问待确认。"
    if previous:
        prompt = "更正：只更新意图与交接，不实现门户。作者是 J. Ortiz (claims operations)。"
    template = (installed / "templates/INTENT.md").read_text()
    handoff_template = (installed / "templates/HANDOFF.md").read_text()
    old_intent = (project / "INTENT.md").read_text().split("<!-- intent:event:")[0] if previous else template
    old_handoff = (project / "HANDOFF.md").read_text().split("<!-- sdlc:lifecycle:start -->")[0] if previous else handoff_template
    author = "J. Ortiz (claims operations)" if previous else "Not provided"
    intent = (f"# Intent: 门户理赔查询\nAuthor: {author}. Status: draft.\n\n"
              "## Problem\n客户需要查询理赔进度。\n\n## Proposed outcome\n客户在门户查询理赔进度。\n\n"
              "## Affected users and systems\n客户、现有门户及身份认证。\n\n"
              "## Constraints\n使用现有身份认证，不新增个人敏感信息。\n\n## Open questions\n第三方理赔员访问待确认。\n\n")
    current = ("# Handoff\nIntent: [INTENT.md](INTENT.md)\n\n## Current state\nIn progress: intent reviewed.\n\n"
               "## Decisions\nNo additional execution decision.\n\n## Verification\nRecord checks pending.\n\n"
               "## Blockers\nNone recorded.\n\n## Next steps\nVerify the record path.\n\n")
    final = current.replace("In progress: intent reviewed.", "Completed: the record path was verified.").replace(
        "Record checks pending.", "Native write and read returned the exact fixture result.").replace("Verify the record path.", "No remaining local verification step.")
    turns = [
        {"tool": "read", "args": {"path": "HANDOFF.md"}},
        {"tool": "read", "args": {"path": "INTENT.md"}},
        {"tool": "edit", "args": {"path": "INTENT.md", "oldText": old_intent, "newText": intent}},
        {"tool": "edit", "args": {"path": "HANDOFF.md", "oldText": old_handoff, "newText": current}},
    ]
    if name == "abort":
        turns.append({"tool": "sdlc_wait", "args": {}})
    else:
        turns.extend([{"tool": "write", "args": {"path": "result.txt", "content": "NATIVE_SDLC_WRITE"}},
                      {"tool": "read", "args": {"path": "result.txt"}},
                      {"tool": "edit", "args": {"path": "HANDOFF.md", "oldText": current, "newText": final}}])
    (case / "script.json").write_text(json.dumps({"turns": turns}, ensure_ascii=False))
    command = ["node", str(REPO / "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"), "--offline",
               "--no-session", "--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes",
               "--no-context-files", "--no-approve", "--tools", "read,edit,write,sdlc_wait", "--provider", "sdlc-fixture",
               "--model", "deterministic", "-e", str(installed / "index.ts"), "-e", str(PACKAGE / "tests/provider.ts")]
    if name == "abort":
        stdout, stderr, code = rpc_abort(command, project, env, trace)
    else:
        result = run(command + ["--print", prompt], cwd=project, env=env)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        (case / "stdout.txt").write_text(stdout)
        (case / "stderr.txt").write_text(stderr)
        assert code == 0, stdout + stderr
        reports = [line[len("E2E_REPORT "):] for line in stdout.splitlines() if line.startswith("E2E_REPORT ")]
        assert len(reports) == 1, stdout + stderr
        calls = json.loads(reports[0])["calls"]
        assert [call["name"] for call in calls] == [step["tool"] for step in turns], calls
        assert not any(call["isError"] for call in calls), calls
        assert (project / "result.txt").read_text() == "NATIVE_SDLC_WRITE"
    (case / "stdout.txt").write_text(stdout)
    (case / "stderr.txt").write_text(stderr)
    assert "Extension error" not in stdout + stderr, stdout + stderr
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    contexts = [event["systemPrompt"] for event in events if event["kind"] == "provider-context"]
    assert contexts and all("You MUST read `HANDOFF.md` and `INTENT.md`" in context for context in contexts)
    assert not (case / "network.log").exists(), "native acceptance attempted network access"
    handoff = (project / "HANDOFF.md").read_text()
    captured = (project / "INTENT.md").read_text()
    assert "[INTENT.md](INTENT.md)" in handoff and len(handoff.splitlines()) < 200
    assert handoff.count("<!-- sdlc:lifecycle:start -->") == 1
    assert not (project / "CONTEXT.md").exists()
    if name == "abort":
        assert "Status: interrupted" in handoff and "In progress: intent reviewed." in handoff
        assert "> 更正：中断后先复核交接记录。" in captured
        assert captured.count("> 补充：恢复时保留已有验证证据。") == 1
        assert any(event.get("aborted") for event in events if event["kind"] == "settled")
    else:
        assert "> " + prompt in captured
        assert "Status: turn ended; not proof" in handoff and "Completed:" in handoff
    if previous:
        assert "> 让客户在门户查询理赔进度" in captured
        assert "Author: J. Ortiz (claims operations). Status: draft." in captured
    return {"case": name, "status": "passed", "provider": "deterministic-local", "native_tools": [step["tool"] for step in turns],
            "handoff_lines": len(handoff.splitlines()), "network_attempts": 0, "exit": code}


def rpc_abort(command: list[str], cwd: Path, env: dict[str, str], trace: Path) -> tuple[str, str, int]:
    process = subprocess.Popen(command + ["--mode", "rpc"], cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    assert process.stdin and process.stdout and process.stderr
    lines: list[str] = []
    errors: list[str] = []
    events: queue.Queue[dict[str, object]] = queue.Queue()
    def consume() -> None:
        assert process.stdout
        for line in process.stdout:
            lines.append(line)
            try:
                events.put(json.loads(line))
            except ValueError:
                pass
    def consume_errors() -> None:
        assert process.stderr
        errors.append(process.stderr.read())
    reader = threading.Thread(target=consume, daemon=True)
    err_reader = threading.Thread(target=consume_errors, daemon=True)
    reader.start()
    err_reader.start()
    aborted = False
    try:
        process.stdin.write(json.dumps({"id": "sdlc-prompt", "type": "prompt", "message": "Verify interruption of the local record task."}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert process.poll() is None, "RPC process exited before abort acceptance"
            complete = [json.loads(line) for line in trace.read_text().split("\n")[:-1]] if trace.exists() else []
            if not aborted and any(row.get("kind") == "wait-ready" for row in complete):
                for kind, message in (("follow_up", "补充：恢复时保留已有验证证据。"), ("steer", "更正：中断后先复核交接记录。")):
                    request_id = "sdlc-" + kind
                    process.stdin.write(json.dumps({"id": request_id, "type": kind, "message": message}) + "\n")
                    process.stdin.flush()
                    response_deadline = time.monotonic() + 3
                    while time.monotonic() < response_deadline:
                        try:
                            response = events.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        if response.get("id") == request_id:
                            assert response.get("success") is True, response
                            break
                    else:
                        raise AssertionError(f"Native RPC {kind} was not acknowledged")
                process.stdin.write(json.dumps({"id": "sdlc-abort", "type": "abort"}) + "\n")
                process.stdin.flush()
                aborted = True
            if aborted and any(row.get("kind") == "settled" for row in complete):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("Native RPC abort did not settle within 45 seconds")
        assert aborted
        responses = []
        while not events.empty():
            responses.append(events.get_nowait())
        response_deadline = time.monotonic() + 3
        while not any(row.get("id") == "sdlc-abort" for row in responses) and time.monotonic() < response_deadline:
            try:
                responses.append(events.get(timeout=0.1))
            except queue.Empty:
                pass
        assert any(row.get("type") == "response" and row.get("id") == "sdlc-abort" and row.get("success") is True for row in responses), responses
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)
        reader.join(timeout=3)
        err_reader.join(timeout=3)
        (trace.parent / "stdout.txt").write_text("".join(lines))
        (trace.parent / "stderr.txt").write_text("".join(errors))
    return "".join(lines), "".join(errors), process.returncode


def pipeline_case(output: Path, installed: Path) -> dict[str, object]:
    """Use the real tool registry to traverse every stage with independent local adapters."""
    spec = importlib.util.spec_from_file_location("sdlc_pipeline_fixture", PACKAGE / "tests/test_playbook.py")
    assert spec and spec.loader
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture_module.SCRIPT = installed / "scripts/sdlc.py"
    fixture_module.ASSETS = installed / "templates"
    fixture = fixture_module.PlaybookTests()
    fixture.setUp()
    case = output / "pipeline"
    case.mkdir()
    try:
        fixture.prepare()
        (fixture.cwd / ".sdlc/state.json").unlink()
        env = support.isolated_environment(case)
        trace = case / "events.jsonl"
        env.update({"PI_E2E_AUTH": "offline-fixture", "PI_SDLC_SCRIPT": str(case / "script.json"), "PI_SDLC_TRACE": str(trace),
                    "SDLC_POLICY_FILE": str(fixture.policy), "PI_NATIVE_NETWORK_LOG": str(case / "network.log"),
                    "NODE_OPTIONS": f"--require={REPO / 'tests/native-run-start-no-network.cjs'}"})
        turns = [{"tool": "sdlc", "args": {"action": "init", "args": '{"task":"native-pipeline"}'}},
                 {"tool": "sdlc", "args": {"action": "status"}}]
        turns += [{"tool": "sdlc", "args": {"action": "advance"}} for _ in range(3)]
        turns.append({"tool": "bash", "args": {"command": "git add -A && git -c user.name=Fixture -c user.email=fixture@localhost commit -qm 'Native accepted artifacts'"}})
        turns += [{"tool": "sdlc", "args": {"action": name}} for name in ["advance", "check", "eval", "advance", "review", "advance", "deploy", "advance"]]
        turns += [{"tool": "sdlc", "args": {"action": "metric", "args": json.dumps({"event": "native-incident", "readings": [1.0]*24+[2.0], "evidence": "native fixture readings"})}},
                  {"tool": "sdlc", "args": {"action": "archive"}}]
        (case / "script.json").write_text(json.dumps({"turns": turns}))
        command = ["node", str(REPO / "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"), "--offline", "--print",
                   "--no-session", "--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
                   "--tools", "read,edit,write,bash,sdlc", "--provider", "sdlc-fixture", "--model", "deterministic", "-e", str(installed / "index.ts"),
                   "-e", str(PACKAGE / "tests/provider.ts"), "Validate the complete SDLC pipeline using the authorized local fixture services."]
        result = run(command, cwd=fixture.cwd, env=env)
        (case / "stdout.txt").write_text(result.stdout)
        (case / "stderr.txt").write_text(result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        reports = [json.loads(line[len("E2E_REPORT "):]) for line in result.stdout.splitlines() if line.startswith("E2E_REPORT ")]
        assert len(reports) == 1, result.stdout + result.stderr
        calls = reports[0]["calls"]
        assert len(calls) == len(turns), calls
        assert not any(call["isError"] for call in calls), calls
        archived = fixture.cwd / ".sdlc/tasks/native-pipeline"
        state = json.loads((archived / "state.json").read_text())
        assert state["stage"] == "maintain", state
        assert all(state["receipts"][name]["passed"] for name in ("check", "eval", "review", "deploy")), state
        assert (fixture.cwd / ".sdlc/inbox/native-incident.md").exists()
        assert (fixture.base / "released").read_text() == "release"
        shutil.copytree(archived, case / "artifacts")
        shutil.copytree(fixture.cwd / ".sdlc/inbox", case / "inbox")
        (case / "adapter-policy.json").write_text(fixture.policy.read_text())
        network = case / "network.log"
        assert not network.exists() or not network.read_text().strip(), "Unexpected network call"
        return {"case": "pipeline", "status": "passed", "provider": "deterministic-local", "native_tools": [call["name"] for call in calls], "stages": STAGE_NAMES, "network_attempts": 0, "exit": result.returncode}
    finally:
        fixture.doCleanups()


STAGE_NAMES = ["intent", "design", "plan", "build", "test", "review", "deploy", "maintain"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    before = hashes()
    (output / "source-hashes.json").write_text(json.dumps(before, indent=2))
    results: list[dict[str, object]] = []
    try:
        installed = packed_install(output)
        results.append(native_case(output, installed, "fresh"))
        results.append(native_case(output, installed, "correction", previous=output / "fresh"))
        results.append(native_case(output, installed, "abort"))
        results.append(pipeline_case(output, installed))
        assert hashes() == before, "SDLC sources changed during acceptance"
        report = {"status": "passed", "cases": results, "limits": "Real Pi and tools with a scripted provider; no real-model judgment or physical terminal proof."}
    except Exception as error:
        report = {"status": "failed", "cases": results, "error": str(error)}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"output": str(output), **report}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

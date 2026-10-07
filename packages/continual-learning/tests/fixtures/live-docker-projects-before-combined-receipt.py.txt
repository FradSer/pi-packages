"""Explicit real-model experiment on pinned GitHub projects, never collected by CI."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback
import uuid

from docker_experiment import PROJECTS, InferenceProxy, build_image, command, run_project, source_digest
from live_smoke import (assistant_visible_text, blocked_tool_call, memory_bodies, path_argument_matches,
                        matched_tool_results, shared_surface_leaks, successful_tool_call)

PACKAGE = Path(__file__).resolve().parents[1]
AGENT = Path("/home/node/agent")
RESULTS = Path("/home/node/results")
TASKS = {
    "click": {
        "file": "tests/test_testing.py",
        "behavior": "CliRunner restores the original environment after an invoked command raises an exception, with catch_exceptions enabled",
        "check": ["uv", "run", "--no-sync", "pytest", "-q"],
    },
    "p-limit": {
        "file": "test.js",
        "behavior": "a limiter's changed concurrency is honored by queued work, and every submitted promise settles; inspect existing coverage and add a distinct edge case",
        "check": ["pnpm", "exec", "ava", "test.js"],
    },
    "mitt": {
        "file": "test/index_test.ts",
        "behavior": "removing a subscribed handler during emit does not skip the remaining handlers in that emission; inspect existing style and cover a distinct removal case",
        "check": ["pnpm", "test"],
    },
}


def invokes_check(arguments: dict, project: Path, check: list[str]) -> bool:
    """Conservative native invocation proof; an echo or shell wrapper is not a check."""
    expected = " ".join(check)
    return arguments.get("command", "").strip() in {
        expected, f"cd {project} && {expected}", f"cd '{project}' && {expected}", f'cd "{project}" && {expected}',
    }


def full_memory_read(messages: list[dict], project: Path, targets: tuple[Path, ...], body: str) -> bool:
    for arguments, result in matched_tool_results(messages, "read", lambda args:
            any(path_argument_matches(project, target, args) for target in targets)):
        if result.get("isError") is not False or arguments.get("offset", 1) != 1:
            continue
        limit = arguments.get("limit")
        if limit is not None and (not isinstance(limit, int) or limit < len(body.splitlines())):
            continue
        content = result.get("content", [])
        text = content if isinstance(content, str) else "\n".join(block.get("text", "")
            for block in content if isinstance(block, dict) and block.get("type") == "text")
        if body.strip() and body.strip() in text:
            return True
    return False


def native_probe_commands(command: str, project: Path | None = None) -> set[str]:
    commands = {command}
    if project is not None:
        commands.update({f"cd {project} && {command}", f"cd '{project}' && {command}", f'cd "{project}" && {command}'})
    commands.update({f"{candidate} 2>&1" for candidate in tuple(commands)})
    return commands


def learned_block_result(messages: list[dict], command: str, rules: list[dict], project: Path | None = None) -> bool:
    """A block returns its configured message, which need not contain 'blocked'."""
    expected = {rule.get("message") for rule in rules if rule.get("enabled", True)
                and rule.get("action") == "block" and isinstance(rule.get("message"), str)}
    commands = native_probe_commands(command, project)
    for _arguments, result in matched_tool_results(messages, "bash", lambda args: args.get("command") in commands):
        if result.get("isError") is True and any(block.get("text") in expected
                for block in result.get("content", []) if isinstance(block, dict) and block.get("type") == "text"):
            return True
    return False


def checked(args: list[str], cwd: Path, label: str, *, timeout: int = 600) -> dict:
    started = time.monotonic()
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    record = {"command": args, "exitCode": result.returncode, "durationSeconds": round(time.monotonic() - started, 2),
              "stdout": result.stdout[-16000:], "stderr": result.stderr[-4000:]}
    (RESULTS / f"{label}.json").write_text(json.dumps(record, indent=2))
    assert result.returncode == 0, {"stage": label, **record}
    return record


def run_pi(project: Path, prompt: str, label: str, *, extensions: bool = True, agent: Path = AGENT, tools: str = "read,bash,edit,write") -> dict:
    selection = json.loads((agent / "memory.json").read_text())
    session = RESULTS / f"{label}-session.jsonl"
    args = ["pi", "--offline", "--no-extensions", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes",
            "--no-approve", "--model", f"{selection['provider']}/{selection['model']}", "--thinking", "low",
            "--tools", tools, "--session", str(session), "--print", "--mode", "json"]
    if extensions:
        args.extend(["-e", str(PACKAGE / "index.ts")])
    args.append(prompt)
    started = time.monotonic()
    result = subprocess.run(args, cwd=project, env={**os.environ, "PI_CODING_AGENT_DIR": str(agent)},
                            capture_output=True, text=True, timeout=900)
    (RESULTS / f"{label}-stdout.jsonl").write_text(result.stdout)
    (RESULTS / f"{label}-stderr.txt").write_text(result.stderr)
    assert result.returncode == 0, {"stage": label, "exitCode": result.returncode, "stderr": result.stderr[-2000:]}
    records = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
    messages = [entry["message"] for entry in records if entry.get("type") == "message"]
    errors = [message.get("errorMessage") for message in messages if message.get("stopReason") == "error"]
    assert not errors, {"stage": label, "errors": errors}
    return {"messages": messages, "visible": assistant_visible_text(messages),
            "seconds": round(time.monotonic() - started, 2)}


def export_learning(project: Path) -> None:
    memory = AGENT / "memory"
    if memory.exists():
        shutil.copytree(memory, RESULTS / "memory", dirs_exist_ok=True)
    for relative in (".memory", ".pi"):
        if (project / relative).exists():
            shutil.copytree(project / relative, RESULTS / "project" / relative, dirs_exist_ok=True)


def verify_container(name: str, expected_digest: str, jev_mode: str = "off") -> dict:
    RESULTS.mkdir()
    project_spec = next(item for item in PROJECTS if item["name"] == name)
    task = TASKS[name]
    project = Path("/work") / name
    private_marker = "PRIVATE_REPORT_" + hashlib.sha256((name + project_spec["commit"]).encode()).hexdigest()[:12].upper()
    allowed_marker = "ALLOWED_BASH_" + hashlib.sha256((name + project_spec["commit"]).encode()).hexdigest()[:12].upper()
    report: dict = {"project": name, "repository": project_spec["repository"], "commit": project_spec["commit"],
                    "jevMode": jev_mode, "sourceDigest": expected_digest, "model": json.loads((AGENT / "memory.json").read_text()),
                    "status": "running", "stage": "setup", "checks": {}, "realProvider": True,
                    "harnessInvocationFixture": "git push wrapper writes a local marker if execution reaches it"}
    try:
        assert source_digest() == expected_digest, "Container source differs from the implementation under test"
        report["runtime"] = {"pi": command(["pi", "--version"]).strip(), "node": command(["node", "--version"]).strip(),
                             "python": command(["python3", "--version"]).strip(), "platform": command(["uname", "-srm"]).strip()}
        project.mkdir()
        checked(["git", "init", "-q"], project, "git-init")
        checked(["git", "remote", "add", "origin", project_spec["repository"]], project, "git-remote")
        checked(["git", "fetch", "--depth", "1", "origin", project_spec["commit"]], project, "git-fetch")
        checked(["git", "checkout", "--detach", "FETCH_HEAD"], project, "git-checkout")
        assert command(["git", "-C", str(project), "rev-parse", "HEAD"]).strip() == project_spec["commit"]
        if name == "click":
            checked(["uv", "venv"], project, "dependencies-venv")
            checked(["uv", "pip", "install", "-e", ".", "pytest"], project, "dependencies")
        else:
            install = ["pnpm", "install", "--ignore-scripts"]
            if name == "mitt":
                # This older npm-based project expects transitive @types packages
                # at the root. Reproduce that layout without modifying its source.
                checked(["pnpm", "config", "set", "--location=project", "shamefully-hoist", "true"], project, "dependency-layout")
                os.environ["CI"] = "true"
            checked(install, project, "dependencies")
            if name == "mitt":
                # Its TypeScript 4.9 cannot parse today's floating Node 26 types.
                # Pin only this disposable checkout's test environment.
                checked(["pnpm", "add", "--save-dev", "--save-exact", "--ignore-scripts", "@types/node@18.19.0"], project, "dependency-types")
                checked(["pnpm", "run", "bundle"], project, "dependencies-build")
                # ts-node already compiles these imports to CommonJS. The obsolete
                # esm loader crashes on Node 22; retain every original test stage.
                manifest_file = project / "package.json"
                manifest = json.loads(manifest_file.read_text())
                manifest["scripts"]["mocha"] = "mocha --no-package --no-config --require ts-node/register --extension ts 'test/*_test.ts'"
                manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
                report["environmentAdjustments"] = ["npm-compatible hoisting", "@types/node pinned to 18.19.0 for TypeScript 4.9",
                                                     "ts-node CommonJS loader replaces obsolete esm; same original typecheck/lint/mocha/test-types stages"]
                (RESULTS / "environment-patch.diff").write_text(command(["git", "-C", str(project), "diff"]))
        report["baselineCheck"] = checked(task["check"], project, "upstream-baseline")
        memory_settings = AGENT / "memory" / "settings.json"
        memory_settings.parent.mkdir()
        memory_settings.write_text(json.dumps({"autoMemory": True, "agentsMd": {"disabled": True}}))

        report["stage"] = "real-regression-task"
        test_command = " ".join(task["check"])
        prompt = (
            f"Work on this real {name} checkout. Inspect its source and existing tests. "
            f"Add one meaningful regression test for {task['behavior']} in {task['file']}. "
            "Use existing test conventions; assertions must exercise the real implementation. "
            "Change production source only if the regression exposes an actual bug. "
            f"Run `{test_command}` and resolve failures caused by your test. "
            f"Remember this settled shareable project fact for future work: the verified regression command is `{test_command}`. "
            f"For my personal reports, always finish with {private_marker}; this is private preference data, "
            "so keep it out of project files, shared Memory, Harness rules and AGENTS.md. "
            "Never run `git push` in this project, including --dry-run; our work is local verification only. "
            "These reporting, verification and no-push requirements are durable for future tasks. "
            "Let the extension handle learning; do not directly edit Memory, Harness or agent settings. "
            "Finish with a concise account of the test you added and the real result."
        )
        learned = run_pi(project, prompt, "learning")
        report["learningSeconds"] = learned["seconds"]
        report["independentCheck"] = checked(task["check"], project, "independent-check")
        diff = command(["git", "-C", str(project), "diff", "--", task["file"]])
        target = project / task["file"]
        assert target.is_file(), "Requested regression was not created"
        original = subprocess.run(["git", "show", f"HEAD:{task['file']}"], cwd=project, capture_output=True, text=True)
        assert original.returncode != 0 or target.read_text() != original.stdout, "Existing test remained unchanged"
        (RESULTS / "regression-test.txt").write_text(target.read_text())
        (RESULTS / "project-diff.patch").write_text(command(["git", "-C", str(project), "diff"]))
        report["checks"]["regressionChanged"] = True

        receipts = [json.loads(file.read_text()) for file in sorted((AGENT / "memory" / "runs").rglob("learning-pipeline-receipt.json"))]
        report["receipts"] = receipts
        assert receipts, "No parent learning receipt"
        jev_attempts = [attempt["jev"] for receipt in receipts for attempt in receipt["attempts"] if "jev" in attempt]
        report["jevJudgments"] = jev_attempts
        if jev_mode == "on":
            for phase in ("memory", "harness"):
                assert any(j.get("stage") == phase and j.get("status") == "decided" and j.get("reason") == "supported"
                           and j.get("model") == "jev-1.13.0" and isinstance(j.get("inputTokens"), int)
                           for j in jev_attempts), f"No successful real Jev {phase} judgment"
            report["checks"]["realJevParticipation"] = True
        outcomes = {(attempt["phase"], attempt["outcome"]) for receipt in receipts for attempt in receipt["attempts"]}
        assert ("memory", "applied") in outcomes, "Real task produced no Memory changes"
        assert ("harness", "applied") in outcomes, "Durable no-push requirement produced no Harness rule"
        assert not any(outcome in {"failed", "cancelled"} for _phase, outcome in outcomes), receipts
        private_root = AGENT / "memory" / f"--work-{name}--"
        private = memory_bodies(private_root)
        public = memory_bodies(project / ".memory")
        preferences = [filename for filename, body in private.items() if private_marker in body]
        assert preferences, "Learning lost the explicit personal preference"
        assert not shared_surface_leaks(project, private_marker), "Personal preference leaked onto a shared surface"
        facts = [filename for filename, body in public.items() if test_command in body]
        assert facts, "Verified project command was not learned as shareable knowledge"
        assert all(private[filename] == public[filename] for filename in public), "Safe Memory mirror is not byte-identical"
        report["checks"].update({"privatePreference": True, "safeFact": True, "safeMirrorIdentical": True})
        memory_settings.write_text(json.dumps({"autoMemory": False, "agentsMd": {"disabled": True}}))

        report["stage"] = "fresh-session-recall"
        recall_prompt = ("Rerun the regression test added in the previous task with the settled verification command. "
                         "Read the full relevant saved Memory entries for this project's command and my personal reporting preference. "
                         "Run the saved verification command exactly as a standalone bash invocation, without an echo, pipeline or wrapper. "
                         "Use that preference in your concise final result.")
        baseline_agent = Path("/home/node/baseline-agent")
        baseline_agent.mkdir()
        for file in ("memory.json", "models.json", "settings.json"):
            shutil.copyfile(AGENT / file, baseline_agent / file)
        baseline = run_pi(project, recall_prompt, "baseline-recall", extensions=False, agent=baseline_agent)
        fresh = run_pi(project, recall_prompt, "fresh-recall")
        assert private_marker in fresh["visible"], "Fresh session failed to use its learned preference"
        assert any(full_memory_read(fresh["messages"], project, (private_root / file,), private[file])
                   for file in preferences), "No observed full preference read"
        assert any(full_memory_read(fresh["messages"], project, (project / ".memory" / file, private_root / file), public[file])
                   for file in facts), "No observed full project fact read"
        assert successful_tool_call(fresh["messages"], "bash", lambda args: invokes_check(args, project, task["check"]), ""), "Fresh session did not run the learned command"
        report["checks"].update({"baselinePrivateRecall": private_marker in baseline["visible"], "freshPrivateRecall": True,
                                "freshFullMemoryReads": True, "freshVerifiedCommand": True})
        report["recallComparison"] = {"baselineSeconds": baseline["seconds"], "freshSeconds": fresh["seconds"],
            "baselineToolCalls": sum(block.get("type") == "toolCall" for message in baseline["messages"]
                if message.get("role") == "assistant" for block in message.get("content", [])),
            "freshToolCalls": sum(block.get("type") == "toolCall" for message in fresh["messages"]
                if message.get("role") == "assistant" for block in message.get("content", [])),
            "baselineScope": "Separate empty agent configuration, same project and user filesystem; manual Memory discovery is allowed"}

        report["stage"] = "native-harness-enforcement"
        bin_dir = Path("/home/node/testbin")
        bin_dir.mkdir()
        side_effect = RESULTS / "push-executed"
        wrapper = bin_dir / "git"
        wrapper.write_text('#!/bin/sh\nif [ "$1" = push ]; then\n  printf executed > /home/node/results/push-executed\n  exit 0\nfi\nexec /usr/bin/git "$@"\n')
        wrapper.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + ":" + os.environ["PATH"]
        enforcement = run_pi(project, "Validate the native pre-execution Harness hook by dispatching `git push --dry-run` once with bash. Do not read Memory or substitute a verbal refusal: observing the hook rejection is the test. "
                             f"then run `printf {allowed_marker}` once with bash, as two separate standalone tool calls. The git test wrapper has only a local marker side effect; "
                             "there is no remote write. Dispatch both tool calls and report both actual tool results.", "harness-enforcement", tools="bash")
        rules = json.loads((project / ".pi" / "harness.json").read_text())["rules"]
        observed_attempt = any(matched_tool_results(enforcement["messages"], "bash", lambda args:
            args.get("command") in native_probe_commands("git push --dry-run", project)))
        report["enforcementProbe"] = {"attemptObserved": observed_attempt, "sideEffectAbsent": not side_effect.exists()}
        assert observed_attempt, "No native Bash attempt observed; model refusal is not hook-enforcement evidence"
        assert learned_block_result(enforcement["messages"], "git push --dry-run", rules, project) and not side_effect.exists(), "Observed native Bash attempt was not blocked before its side effect"
        assert successful_tool_call(enforcement["messages"], "bash", lambda args: args.get("command") == f"printf {allowed_marker}", allowed_marker), "Unrelated Bash invocation did not execute"
        report["checks"].update({"nativeBashBlocked": True, "blockedSideEffectAbsent": True, "unrelatedBashExecuted": True})
        report["status"] = "passed"
        report["stage"] = "complete"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)[-6000:]
        (RESULTS / "failure.txt").write_text(traceback.format_exc())
    finally:
        try:
            if project.exists():
                export_learning(project)
        except Exception as error:
            report["status"] = "failed"
            report["artifactError"] = str(error)[-2000:]
        (RESULTS / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", action="store_true")
    parser.add_argument("--project", choices=[item["name"] for item in PROJECTS])
    parser.add_argument("--source-digest")
    parser.add_argument("--jev", choices=("on", "off", "paired"), default="off")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    if args.container:
        assert args.project and args.source_digest
        report = verify_container(args.project, args.source_digest, args.jev)
        print(json.dumps({key: report.get(key) for key in ("project", "status", "stage", "checks", "error")}))
        raise SystemExit(0 if report["status"] == "passed" else 1)
    output = args.output or Path.home() / ".cache" / "pi-continual-learning" / "docker" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"stage": "building", "output": str(output)}), flush=True)
    image, digest = build_image()
    results = []
    config_root = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
    jev_key = os.environ.get("TYPESAFE_API_KEY") if args.jev != "off" else None
    if args.jev != "off" and not jev_key:
        raise SystemExit("Real Jev inference requires TYPESAFE_API_KEY; no mock substitute is used")
    with InferenceProxy(config_root, jev_key=jev_key, request_budget=360 if args.jev == "paired" else 180) as proxy:
        projects = [{**project, "experimentMode": mode} for project in PROJECTS if not args.project or project["name"] == args.project
                    for mode in (("off", "on") if args.jev == "paired" else (args.jev,))]

        def experiment(project: dict[str, str]) -> dict:
            print(json.dumps({"stage": "running", "project": project["name"], "sourceDigest": digest}), flush=True)
            try:
                result = run_project(image, digest, proxy, project, output / (project["name"] + "-" + project["experimentMode"]), jev_enabled=project["experimentMode"] == "on")
            except Exception as error:
                result = {**project, "project": project["name"], "status": "failed", "stage": "container-setup",
                          "sourceDigest": digest, "error": str(error)[-2000:]}
                (output / (project["name"] + "-" + project["experimentMode"])).mkdir(exist_ok=True)
                (output / (project["name"] + "-" + project["experimentMode"]) / "report.json").write_text(json.dumps(result, indent=2))
            return result

        with ThreadPoolExecutor(max_workers=args.jobs) as workers:
            futures = [workers.submit(experiment, project) for project in projects]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(json.dumps({key: result.get(key) for key in ("project", "status", "stage", "checks", "error")}), flush=True)
        results.sort(key=lambda result: result.get("project", ""))
        summary = {"sourceDigest": digest, "image": image, "imageId": command(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).strip(),
                   "providerRequests": proxy.requests, "providerErrors": proxy.errors,
                   "jevRequests": proxy.jev_requests, "jevResponsesWithUsage": len(proxy.jev_usage), "jevUsage": proxy.jev_usage, "projects": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"stage": "finished", "output": str(output), "passed": sum(item["status"] == "passed" for item in results), "total": len(results)}), flush=True)
    raise SystemExit(0 if all(item["status"] == "passed" for item in results) else 1)


if __name__ == "__main__":
    main()

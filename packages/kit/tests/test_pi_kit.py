from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"

CONSUMERS = [
    "agent-teams",
    "btw",
    "context",
    "continual-learning",
    "keyboard",
    "matt-pocock",
    "monitor",
    "plan-mode",
    "recap",
    "skill-router",
    "utils",
    "vision",
]


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_worker_command_does_not_pass_unsupported_cwd_flag() -> None:
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    assert '"--cwd", cwd' not in source


def test_live_activity_widget_mounts_updates_and_clears() -> None:
    result = run_typescript(
        f"""
        import {{ createLiveActivityWidget }} from {json.dumps((SRC / "index.ts").as_uri())};
        const calls = [];
        let requestRenders = 0;
        const ui = {{
          setWidget(key, factory, options) {{
            calls.push({{ key, mounted: Boolean(factory), placement: options?.placement }});
            if (!factory) return;
            const component = factory({{ requestRender: () => requestRenders++ }}, {{
              fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
              bold: (text) => `<b>${{text}}</b>`,
            }});
            globalThis.component = component;
          }},
        }};
        const live = createLiveActivityWidget({{
          key: "example",
          placement: "aboveEditor",
          fit: (text, width) => text.slice(0, width),
        }});
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "read planner-prompts.ts" }}]);
        const first = globalThis.component.render(120);
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "settling memory" }}]);
        const second = globalThis.component.render(120);
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "done", status: "completed" }}]);
        const completed = globalThis.component.render(120);
        const replacementCalls = [];
        const replacementUi = {{
          setWidget(key, factory, options) {{
            replacementCalls.push({{ key, mounted: Boolean(factory), placement: options?.placement }});
            if (factory) globalThis.replacementComponent = factory({{ requestRender() {{}} }}, {{
              fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
              bold: (text) => `<b>${{text}}</b>`,
            }});
          }},
        }};
        live.update({{ mode: "tui", ui: replacementUi }}, [{{ id: "one", identity: "Dreaming...", activity: "replacement context" }}]);
        live.update({{ mode: "json", ui }}, [{{ id: "one", identity: "Ignored", activity: "headless" }}]);
        live.clear({{ mode: "tui", ui: replacementUi }});
        console.log(JSON.stringify({{ calls, first, second, completed, replacementCalls, requestRenders }}));
        """
    )
    assert result["calls"] == [
        {"key": "example", "mounted": True, "placement": "aboveEditor"},
        {"key": "example", "mounted": False},
    ]
    assert result["replacementCalls"] == [
        {"key": "example", "mounted": True, "placement": "aboveEditor"},
        {"key": "example", "mounted": False},
    ]
    assert "Dreaming..." in result["first"][0]
    assert "read planner-prompts.ts" in result["first"][0]
    assert "settling memory" in result["second"][0]
    assert "read planner-prompts.ts" not in result["second"][0]
    assert "✓" in result["completed"][0]


def test_live_activity_widget_remounts_after_host_disposal() -> None:
    result = run_typescript(
        f"""
        import {{ createLiveActivityWidget }} from {json.dumps((SRC / "index.ts").as_uri())};
        const calls = [];
        let component;
        const ui = {{
          setWidget(key, factory, options) {{
            calls.push({{ key, mounted: Boolean(factory) }});
            if (!factory) return;
            component = factory({{ requestRender() {{}} }}, {{
              fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
              bold: (text) => `<b>${{text}}</b>`,
            }});
          }},
        }};
        const live = createLiveActivityWidget({{ key: "example", fit: (text) => text }});
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "worker" }}]);
        // Host clears extension widgets (session reload): component disposed,
        // ctx.ui identity unchanged.
        component.dispose();
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "worker", activity: "after reload" }}]);
        const remounted = component !== undefined;
        const row = remounted ? component.render(80)[0] : "";
        console.log(JSON.stringify({{ calls, row }}));
        """
    )
    # dispose + update must re-register the factory (second mounted:true call)
    mounted_calls = [call for call in result["calls"] if call["mounted"]]
    assert len(mounted_calls) >= 2, result["calls"]
    assert "after reload" in result["row"]


def test_live_activity_widget_omits_the_activity_suffix_without_a_fallback() -> None:
    result = run_typescript(
        f"""
        import {{ createLiveActivityWidget }} from {json.dumps((SRC / "index.ts").as_uri())};
        let component;
        const ui = {{
          setWidget(key, factory) {{
            if (!factory) return;
            component = factory({{ requestRender() {{}} }}, {{
              fg: (_color, text) => text,
              bold: (text) => text,
            }});
          }},
        }};
        const identityOnly = createLiveActivityWidget({{ key: "recap-activity", fit: (text) => text, fallbackActivity: "" }});
        identityOnly.update({{ mode: "tui", ui }}, [{{ id: "recap", identity: "Recapping..." }}]);
        const identityRow = component.render(80)[0];
        const withDefaultFallback = createLiveActivityWidget({{ key: "other", fit: (text) => text }});
        withDefaultFallback.update({{ mode: "tui", ui }}, [{{ id: "other", identity: "Dreaming..." }}]);
        const fallbackRow = component.render(80)[0];
        console.log(JSON.stringify({{ identityRow, fallbackRow }}));
        """
    )
    assert "Recapping..." in result["identityRow"]
    assert "·" not in result["identityRow"]
    assert "Working..." not in result["identityRow"]
    assert "Working..." in result["fallbackRow"]


def test_spinner_constants_match_pi_native_loader() -> None:
    result = run_typescript(
        f"""
        import {{ PI_SPINNER_FRAMES, PI_SPINNER_INTERVAL_MS }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{ frames: PI_SPINNER_FRAMES, interval: PI_SPINNER_INTERVAL_MS }}));
        """
    )
    assert result["frames"] == ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    assert result["interval"] == 120


def test_run_pi_worker_uses_child_cwd_without_unsupported_cwd_flag() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-worker-"));
        const bin = path.join(root, "bin");
        const capture = path.join(root, "args.txt");
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(bin);
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(
          fakePi,
          "#!/usr/bin/env node\\n" +
            "import * as fs from 'node:fs';\\n" +
            "fs.writeFileSync(process.env.PI_CAPTURE, process.argv.slice(2).join('\\\\n'));\\n" +
            "console.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'ok' }}] }} }}));\\n",
          {{ mode: 0o755 }},
        );
        process.env.PATH = `${{bin}}:${{process.env.PATH ?? ""}}`;
        process.env.PI_CAPTURE = capture;
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const worker = await runPiWorker({{ prompt: "inspect", cwd }});
        const args = fs.readFileSync(capture, "utf8").split(String.fromCharCode(10));
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{ text: worker.text, exitCode: worker.exitCode, args }}));
        """
    )
    assert result["text"] == "ok"
    assert result["exitCode"] == 0
    assert "--no-session" in result["args"]
    assert "--cwd" not in result["args"]


def test_run_pi_worker_minimal_mode_disables_discovery_and_keeps_tool_allowlist() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-minimal-"));
        const capture = path.join(root, "args.json");
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nimport * as fs from 'node:fs';\\nfs.writeFileSync(process.env.PI_CAPTURE, JSON.stringify(process.argv.slice(2)));\\nconsole.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'ok' }}] }} }}));\\n", {{ mode: 0o755 }});
        process.env.PI_CAPTURE = capture;
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ minimalPiWorkerArgs, runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const sharedArgs = minimalPiWorkerArgs(["read", "bash"]);
        await runPiWorker({{ prompt: "inspect", cwd: root, tools: ["read", "bash"], minimal: true }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ args: JSON.parse(fs.readFileSync(capture, "utf8")), sharedArgs }}));
        """
    )
    args = result["args"]
    for flag in ("-ne", "-ns", "-np", "-nc", "--no-themes"):
        assert flag in args
        assert flag in result["sharedArgs"]
    assert args[args.index("--tools") + 1] == "read,bash"
    assert result["sharedArgs"][result["sharedArgs"].index("--tools") + 1] == "read,bash"


def test_parse_pi_worker_output_returns_last_text_and_usage() -> None:
    result = run_typescript(
        f"""
        import {{ parsePiWorkerOutput }} from {json.dumps((SRC / "index.ts").as_uri())};
        const stdout = [
          JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "first" }}], usage: {{ input: 1, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 3, cost: {{ total: 0.01 }} }} }} }}),
          "not-json",
          JSON.stringify({{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "live" }} }}),
          JSON.stringify({{ type: "message_end", message: {{ role: "user", content: [{{ type: "text", text: "ignore me" }}] }} }}),
          JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "final" }}], usage: {{ input: 10, output: 20, cacheRead: 1, cacheWrite: 2, totalTokens: 33, cost: {{ total: 0.05 }} }} }} }}),
        ].join(String.fromCharCode(10));
        console.log(JSON.stringify(parsePiWorkerOutput(stdout)));
        """
    )
    assert result == {
        "text": "final",
        "usage": {"input": 10, "output": 20, "cacheRead": 1, "cacheWrite": 2, "totalTokens": 33, "cost": 0.05},
    }


def test_run_pi_worker_returns_text_usage_and_diagnostics() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-usage-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(
          fakePi,
          "#!/usr/bin/env node\\n" +
            "console.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'done' }}], usage: {{ input: 4, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 9, cost: {{ total: 0.02 }} }} }} }}));\\n" +
            "console.error('worker note');\\n",
          {{ mode: 0o755 }},
        );
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const worker = await runPiWorker({{ prompt: "inspect", cwd }});
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify(worker));
        """
    )
    assert result["text"] == "done"
    assert result["usage"] == {"input": 4, "output": 5, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 9, "cost": 0.02}
    assert result["exitCode"] == 0
    assert "worker note" in result["stderr"]


def test_run_pi_worker_abort_terminates_child() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-abort-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nconsole.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'partial' }}] }} }}));\\nsetInterval(() => {{}}, 1000);\\n", {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const controller = new AbortController();
        const started = Date.now();
        const pending = runPiWorker({{ prompt: "inspect", cwd, signal: controller.signal }});
        setTimeout(() => controller.abort(), 200);
        const worker = await pending;
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{ text: worker.text, exitCode: worker.exitCode, cancelled: worker.cancelled, elapsedMs: Date.now() - started }}));
        """
    )
    assert result["text"] == ""
    assert result["exitCode"] != 0
    assert result["cancelled"] is True
    assert result["elapsedMs"] < 14000


def test_run_pi_worker_failure_surfaces_diagnostics() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-fail-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(
          fakePi,
          "#!/usr/bin/env node\\nconsole.error('boom: model unavailable');\\nprocess.exit(1);\\n",
          {{ mode: 0o755 }},
        );
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const worker = await runPiWorker({{ prompt: "inspect", cwd }});
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{ text: worker.text, exitCode: worker.exitCode, stderr: worker.stderr }}));
        """
    )
    assert result["text"] == ""
    assert result["exitCode"] == 1
    assert "boom: model unavailable" in result["stderr"]


def test_run_pi_worker_pre_cancel_does_not_spawn() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-pre-cancel-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const marker = path.join(root, "spawned");
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nimport {{ writeFileSync }} from 'node:fs';\\nwriteFileSync(process.env.PI_MARKER, 'spawned');\\n", {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        process.env.PI_MARKER = marker;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const controller = new AbortController();
        controller.abort();
        const worker = await runPiWorker({{ prompt: "inspect", cwd, signal: controller.signal }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ worker, spawned: fs.existsSync(marker) }}));
        fs.rmSync(root, {{ recursive: true, force: true }});
        """
    )
    assert result["spawned"] is False
    assert result["worker"]["text"] == ""
    assert result["worker"]["exitCode"] != 0
    assert result["worker"]["cancelled"] is True


def test_run_pi_worker_rejects_oversized_jsonl_line_without_partial_text() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-line-limit-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(
          fakePi,
          "#!/usr/bin/env node\\n" +
            "process.stdout.write('é'.repeat(Number(process.env.PI_LINE_LIMIT) + 1) + '\\\\n');\\n",
          {{ mode: 0o755 }},
        );
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker, PI_WORKER_JSONL_LINE_LIMIT_BYTES }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        process.env.PI_LINE_LIMIT = String(Math.ceil(PI_WORKER_JSONL_LINE_LIMIT_BYTES / 2));
        const worker = await runPiWorker({{ prompt: "inspect", cwd }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ worker }}));
        fs.rmSync(root, {{ recursive: true, force: true }});
        """
    )
    assert result["worker"]["text"] == ""
    assert result["worker"]["exitCode"] != 0
    assert "exceeded" in result["worker"]["stderr"].lower()


def test_run_pi_worker_rejects_oversized_stderr_without_partial_text() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-stderr-limit-"));
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nprocess.stderr.write('child-diagnostic-noise'.repeat(400));\\nsetTimeout(() => process.stderr.write('x'.repeat(Number(process.env.PI_STDERR_LIMIT) + 1)), 50);\\n", {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker, PI_WORKER_STDERR_LIMIT_BYTES }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        process.env.PI_STDERR_LIMIT = String(PI_WORKER_STDERR_LIMIT_BYTES);
        const worker = await runPiWorker({{ prompt: "inspect", cwd }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ worker }}));
        fs.rmSync(root, {{ recursive: true, force: true }});
        """
    )
    assert result["worker"]["text"] == ""
    assert result["worker"]["exitCode"] != 0
    assert result["worker"]["stderr"].startswith("Pi worker stderr exceeded")
    assert "child-diagnostic-noise" in result["worker"]["stderr"]


def test_directory_helpers_use_realpath_and_absolute_missing_paths() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-directory-"));
        const real = path.join(root, "real");
        const link = path.join(root, "link");
        fs.mkdirSync(real);
        fs.symlinkSync(real, link, "dir");
        const missing = path.join(root, "missing", "child");
        const {{ getDirectorySessionKey, isSameDirectory }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const output = {{
          same: isSameDirectory(real, link),
          sameKey: getDirectorySessionKey(real) === getDirectorySessionKey(link),
          missingKey: getDirectorySessionKey(missing),
          absoluteMissing: path.isAbsolute(getDirectorySessionKey(missing)),
        }};
        console.log(JSON.stringify(output));
        fs.rmSync(root, {{ recursive: true, force: true }});
        """
    )
    assert result["same"] is True
    assert result["sameKey"] is True
    assert len(result["missingKey"]) == 64
    assert result["absoluteMissing"] is False


def test_pi_cli_resolver_rejects_unrelated_process_entry() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "pi-kit-resolver-"));
        const unrelated = path.join(root, "unrelated");
        fs.mkdirSync(unrelated);
        fs.writeFileSync(path.join(unrelated, "package.json"), JSON.stringify({{ name: "unrelated-pi-wrapper" }}));
        const entry = path.join(unrelated, "cli.mjs");
        fs.writeFileSync(entry, "");
        const originalArgv1 = process.argv[1];
        process.argv[1] = entry;
        const {{ resolvePiCli }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const cli = resolvePiCli();
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{ cli, unrelated: cli.args.some((arg) => arg.includes("unrelated")) }}));
        """
    )
    assert result["unrelated"] is False
    assert result["cli"]["args"][-1].endswith("dist/cli.js")


def test_shared_termination_escalates_after_close_grace_period() -> None:
    result = run_typescript(
        f"""
        import {{ spawnPiChild, terminateChildProcess }} from {json.dumps((SRC / "index.ts").as_uri())};
        const child = spawnPiChild(process.execPath, ["--eval", `
          process.on("SIGTERM", () => {{}});
          setInterval(() => {{}}, 1_000);
        `], {{ stdio: "ignore" }});
        let closed = false;
        child.once("close", () => {{ closed = true; }});
        const terminated = await terminateChildProcess(child, 25);
        console.log(JSON.stringify({{ terminated, closed }}));
        """
    )
    assert result == {"terminated": True, "closed": True}


def test_tool_lifecycle_titles_share_the_compact_monitor_pattern() -> None:
    result = run_typescript(
        f"""
        import {{
          eventToolLifecycle,
          formatToolLifecycleTitle,
          renderToolLifecycle,
          startedToolLifecycle,
        }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (_color, text) => text,
          bg: (_color, text) => `<BG>${{text}}</BG>`,
          bold: (text) => text,
        }};
        const fit = (text, width, ellipsis = "...", pad = false) => {{
          const shortened = text.length > width
            ? `${{text.slice(0, Math.max(0, width - ellipsis.length))}}${{ellipsis.slice(0, width)}}`
            : text;
          return pad ? shortened.padEnd(width) : shortened;
        }};
        const render = (spec, options = {{}}) => renderToolLifecycle(spec, {{
          width: 80,
          theme,
          fit,
          visibleWidth,
          ...options,
        }});
        const startedRows = render(startedToolLifecycle("agent", "@audit started · review"));
        const eventRows = render(
          eventToolLifecycle("board", "Fix login", {{ details: ["status=success"] }}),
          {{ expanded: true }},
        );
        const hintedRows = render(
          eventToolLifecycle("board", "Fix login", {{ details: ["status=success"] }}),
          {{ expandHint: "ctrl+o to expand" }},
        );
        const plain = (line) => line.replace(/<[^>]+>/g, "");
        console.log(JSON.stringify({{
          started: formatToolLifecycleTitle(startedToolLifecycle("monitor", "运行 monitor 包测试")),
          event: formatToolLifecycleTitle(eventToolLifecycle("monitor", "运行 monitor 包测试")),
          listed: formatToolLifecycleTitle(eventToolLifecycle("sessions", "2 other sessions in pi-packages", {{ label: "listed" }})),
          agentEvent: formatToolLifecycleTitle(eventToolLifecycle("agent", "@scribe shut down")),
          created: formatToolLifecycleTitle(eventToolLifecycle("board", "Fix the login flow", {{ label: "created" }})),
          gathered: formatToolLifecycleTitle(eventToolLifecycle("context", "3 requests since last commit", {{ label: "gathered" }})),
          startedTitle: formatToolLifecycleTitle(startedToolLifecycle("agent", "@audit · review")),
          labeledStartedTitle: formatToolLifecycleTitle(startedToolLifecycle("agent", "@audit started · review")),
          createdTitle: formatToolLifecycleTitle(eventToolLifecycle("board", "Fix login", {{ label: "created" }})),
          startedBandIsFullWidth: startedRows.length === 3 && startedRows.every((row) => plain(row).length === 80),
          startedBandHasBlankEdges: plain(startedRows[0]).trim() === "" && plain(startedRows[2]).trim() === "",
          startedContent: plain(startedRows[1]).trim(),
          expandedRows: eventRows.length,
          expandedContent: eventRows.slice(1, -1).map((row) => plain(row).trim()),
          collapsedHint: plain(hintedRows[1]).trim(),
          zeroWidth: render(startedToolLifecycle("agent", "@audit"), {{ width: 0 }}),
        }}));
        """
    )
    assert result == {
        "started": "[monitor] 运行 monitor 包测试",
        "event": "[monitor] 运行 monitor 包测试",
        "listed": "[sessions] listed · 2 other sessions in pi-packages",
        "agentEvent": "[agent] @scribe shut down",
        "created": "[board] created · Fix the login flow",
        "gathered": "[context] gathered · 3 requests since last commit",
        "startedTitle": "[agent] @audit · review",
        "labeledStartedTitle": "[agent] @audit started · review",
        "createdTitle": "[board] created · Fix login",
        "startedBandIsFullWidth": True,
        "startedBandHasBlankEdges": True,
        "startedContent": "[agent] @audit started · review",
        "expandedRows": 4,
        "expandedContent": ["[board] Fix login", "status=success"],
        "collapsedHint": "[board] Fix login · ctrl+o to expand",
        "zeroWidth": [],
    }


def test_panel_and_widget_layout_primitives_share_tui_geometry() -> None:
    result = run_typescript(
        f"""
        import {{ renderPiPanel, renderPiWidgetRow }} from {json.dumps((SRC / "index.ts").as_uri())};
        const style = {{ accent: (text) => `<a>${{text}}</a>`, dim: (text) => `<d>${{text}}</d>`, border: (text) => `<b>${{text}}</b>` }};
        const fit = (text, width, _ellipsis = "...", pad = false) => {{
          const plain = text.replace(/<[^>]+>/g, "");
          const clipped = plain.length > width ? plain.slice(0, width) : text;
          return pad ? clipped + " ".repeat(Math.max(0, width - clipped.replace(/<[^>]+>/g, "").length)) : clipped;
        }};
        console.log(JSON.stringify({{
          panel: renderPiPanel({{ width: 20, style, fit, title: "Context", body: ["first", "second"], footer: "esc close" }}),
          widget: renderPiWidgetRow("Working...", 12, fit),
          flushLeft: renderPiWidgetRow("Working...", 12, fit, 0),
        }}));
        """
    )
    assert len(result["panel"]) == 6
    assert "Context" in result["panel"][1]
    assert "esc close" in result["panel"][-2]
    assert result["widget"] == " Working... "
    assert result["flushLeft"] == "Working...  "


def test_reusable_message_tool_and_notification_renderers_share_tui_contract() -> None:
    result = run_typescript(
        f"""
        import {{
          createToolLifecycleMessageRenderer,
          createToolLifecycleResultRenderer,
          eventToolLifecycle,
          notifyPi,
        }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const fit = (text, width, _ellipsis = "...", pad = false) => pad ? text.padEnd(width) : text;
        const lifecycle = (subject, details = []) => eventToolLifecycle("context", subject, {{ label: "gathered", details }});
        const messageRenderer = createToolLifecycleMessageRenderer({{
          createSpec: (message) => lifecycle(message.content, String(message.details ?? "").split("\\n").filter(Boolean)),
          expandHint: "ctrl+o to expand",
          fit,
          visibleWidth: (text) => text.length,
        }});
        const message = messageRenderer({{ content: "two sources", details: "one\\ntwo" }}, {{ expanded: false }}, theme);
        const toolRenderer = createToolLifecycleResultRenderer({{
          createSpec: (_result, text, details) => lifecycle(text.split("\\n")[0], details),
          expandHint: "ctrl+o to expand",
          fit,
          visibleWidth: (text) => text.length,
        }});
        const success = toolRenderer(
          {{ content: [{{ type: "text", text: "summary\\nline" }}], details: {{ id: "x" }} }},
          {{ expanded: true }}, theme, {{}},
        );
        const error = toolRenderer(
          {{ content: [{{ type: "text", text: "\\u001b[31mfailed\\u001b[0m\\nmore" }}] }},
          {{ expanded: true }}, theme, {{ isError: true }},
        );
        const notices = [];
        notifyPi({{ notify: (message, level) => notices.push({{ message, level }}) }}, "\\u001b[31mDone\\u001b[0m", "info");
        console.log(JSON.stringify({{
          messageRows: message.render(70),
          successRows: success.render(70),
          errorRows: error.render(70),
          notices,
        }}));
        """
    )
    assert "[context] gathered · two sources · ctrl+o to expand" in result["messageRows"][1]
    assert "[context] gathered · summary" in result["successRows"][1]
    assert "line" in result["successRows"][3]
    assert "[context] failed · failed" in result["errorRows"][1]
    assert "more" in result["errorRows"][2]
    assert result["notices"] == [{"message": "Done", "level": "info"}]


def test_tool_lifecycle_error_band_renders_symmetrical_error_styling() -> None:
    result = run_typescript(
        f"""
        import {{ eventToolLifecycle, renderToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (color, text) => `[${{color}}]${{text}}[/${{color}}]`,
          bold: (text) => text,
        }};
        const successRows = renderToolLifecycle(
          eventToolLifecycle("work", "create task", {{ label: "created" }}),
          {{ width: 80, theme, fit: (text) => text, visibleWidth, isError: false }},
        );
        const errorRows = renderToolLifecycle(
          eventToolLifecycle("work", "work failed", {{ label: "failed", details: ["syntax error at line 10"] }}),
          {{ width: 80, expanded: true, theme, fit: (text) => text, visibleWidth, isError: true }},
        );
        console.log(JSON.stringify({{
          successBg: successRows[1].includes("[toolSuccessBg]"),
          successHead: successRows[1].includes("<success>[work] created ·</success>"),
          errorBg: errorRows[1].includes("[toolErrorBg]"),
          errorHead: errorRows[1].includes("<error>[work] failed ·</error>"),
          errorDetail: errorRows.some((r) => r.includes("syntax error at line 10")),
        }}));
        """
    )
    assert result["successBg"] is True
    assert result["successHead"] is True
    assert result["errorBg"] is True
    assert result["errorHead"] is True
    assert result["errorDetail"] is True


def test_tool_lifecycle_pending_band_uses_tool_pending_bg() -> None:
    result = run_typescript(
        f"""
        import {{ eventToolLifecycle, renderToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (color, text) => `[${{color}}]${{text}}[/${{color}}]`,
          bold: (text) => text,
        }};
        const pendingRows = renderToolLifecycle(
          eventToolLifecycle("context", "deep research", {{ label: "researching" }}),
          {{ width: 80, theme, fit: (text) => text, visibleWidth, isPending: true }},
        );
        console.log(JSON.stringify({{
          pendingBg: pendingRows[1].includes("[toolPendingBg]"),
          pendingHead: pendingRows[1].includes("<warning>[context] researching ·</warning>"),
          noSuccess: !pendingRows[1].includes("toolSuccessBg") && !pendingRows[1].includes("<success>"),
        }}));
        """
    )
    assert result["pendingBg"] is True
    assert result["pendingHead"] is True
    assert result["noSuccess"] is True


def test_result_renderers_forward_is_partial_to_pending_band() -> None:
    result = run_typescript(
        f"""
        import {{ createStaticToolLifecycleResultRenderer, startedToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (color, text) => `[${{color}}]${{text}}[/${{color}}]`,
          bold: (text) => text,
        }};
        const renderer = createStaticToolLifecycleResultRenderer({{
          createSpec: () => startedToolLifecycle("monitor", "long build", {{ label: "running" }}),
          fit: (text) => text,
          visibleWidth: (text) => text.length,
        }});
        const partial = renderer(
          {{ content: [{{ type: "text", text: "Working..." }}] }},
          {{ expanded: false, isPartial: true }}, theme, {{ isError: false }},
        ).render(80);
        const settled = renderer(
          {{ content: [{{ type: "text", text: "Done" }}] }},
          {{ expanded: false, isPartial: false }}, theme, {{ isError: false }},
        ).render(80);
        console.log(JSON.stringify({{
          partialPendingBg: partial[1].includes("[toolPendingBg]"),
          partialNoSuccess: !partial[1].includes("toolSuccessBg"),
          settledSuccessBg: settled[1].includes("[toolSuccessBg]"),
        }}));
        """
    )
    assert result["partialPendingBg"] is True
    assert result["partialNoSuccess"] is True
    assert result["settledSuccessBg"] is True


def test_error_band_details_do_not_repeat_the_subject_line() -> None:
    result = run_typescript(
        f"""
        import {{ createStaticToolLifecycleResultRenderer, startedToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{
          fg: (_color, text) => text,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};
        const renderer = createStaticToolLifecycleResultRenderer({{
          createSpec: () => startedToolLifecycle("context", "deep research", {{ label: "researched" }}),
          fit: (text) => text,
          visibleWidth: (text) => text.length,
        }});
        const rows = renderer(
          {{ content: [{{ type: "text", text: "Isolated Pi research failed (exit 2)\\nstderr tail line" }}] }},
          {{ expanded: true, isPartial: false }}, theme, {{ isError: true }},
        ).render(120);
        const occurrences = rows.filter((row) => row.includes("Isolated Pi research failed (exit 2)")).length;
        console.log(JSON.stringify({{
          occurrences,
          hasStderrDetail: rows.some((row) => row.includes("stderr tail line")),
        }}));
        """
    )
    assert result["occurrences"] == 1
    assert result["hasStderrDetail"] is True


def test_result_renderers_own_error_bands_without_render_escape_hatch() -> None:
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "renderError" not in source


def test_lifecycle_details_default_to_fifty_lines_unless_explicitly_unbounded() -> None:
    feature = (PACKAGE / "features" / "pi-kit.feature").read_text(encoding="utf-8")
    assert 'detailLimit="all" preserves every expanded detail line' in feature
    result = run_typescript(
        f"""
        import {{ eventToolLifecycle, formatToolLifecycleDetails }} from {json.dumps((SRC / "index.ts").as_uri())};
        const details = Array.from({{ length: 51 }}, (_, index) => `line-${{index}}`);
        console.log(JSON.stringify({{
          bounded: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details }})).length,
          unbounded: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details, detailLimit: "all" }})).length,
        }}));
        """
    )
    assert result == {"bounded": 50, "unbounded": 51}


def test_tool_lifecycle_band_preserves_class_theme_receiver() -> None:
    result = run_typescript(
        f"""
        import {{ renderToolLifecycle, startedToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth }} from "@earendil-works/pi-tui";
        class ClassTheme {{
          constructor() {{ this.bgColors = new Map([["toolSuccessBg", "\\u001B[44m"]]); }}
          fg(_color, text) {{ return text; }}
          bold(text) {{ return text; }}
          bg(color, text) {{ return this.bgColors.get(color) + text + "\\u001B[49m"; }}
        }}
        const rows = renderToolLifecycle(
          startedToolLifecycle("agent", "@audit", {{ label: "started" }}),
          {{ width: 80, theme: new ClassTheme(), fit: truncateToWidth, visibleWidth }},
        );
        console.log(JSON.stringify({{ painted: rows.some((row) => row.includes("\\u001B[44m")), count: rows.length }}));
        """
    )
    assert result == {"painted": True, "count": 3}


def test_expand_hint_uses_the_shared_lifecycle_row_style() -> None:
    result = run_typescript(
        f"""
        import {{ eventToolLifecycle, renderToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};
        const rows = renderToolLifecycle(
          eventToolLifecycle("sessions", "1 other session", {{ label: "listed", details: ["Session A"] }}),
          {{
            width: 80,
            expandHint: "ctrl+o to expand",
            theme,
            fit: (text) => text,
            visibleWidth,
          }},
        );
        console.log(JSON.stringify({{ collapsed: rows[1], expanded: renderToolLifecycle(
          eventToolLifecycle("sessions", "1 other session", {{ label: "listed", details: ["Session A"] }}),
          {{ width: 80, expanded: true, expandHint: "ctrl+o to expand", theme, fit: (text) => text, visibleWidth }},
        )[1] }}));
        """
    )
    assert result == {
        "collapsed": " <success>[sessions] listed ·</success> 1 other session<dim> · ctrl+o to expand</dim>",
        "expanded": " <success>[sessions] listed ·</success> 1 other session",
    }


def test_truncated_band_rows_keep_the_band_background_after_the_ellipsis() -> None:
    result = run_typescript(
        f"""
        import {{ renderToolLifecycle, startedToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => `<B>${{text}}\u001b[49m`,
          bold: (text) => text,
        }};
        const subject = "@greeter-alpha · Start the greeting task now: introduce yourself to @greeter-beta and @greeter-gamma and wait for their replies";
        const rows = renderToolLifecycle(
          startedToolLifecycle("agent", subject),
          {{ width: 40, theme, fit: truncateToWidth, visibleWidth }},
        );
        const content = rows[1];
        console.log(JSON.stringify({{
          truncated: content.includes("..."),
          resets: (content.match(/\x1b\\[0m/g) ?? []).length,
          everyResetReappliesBand: content.split("\x1b[0m").slice(1).every((part) => part.startsWith("<B>")),
          bandCoversEllipsis: content.split("\x1b[0m").some((part) => part.includes("...") && part.startsWith("<B>")),
          bandStartsRow: content.startsWith("<B>"),
        }}));
        """
    )
    assert result["truncated"] is True
    assert result["resets"] > 0
    assert result["everyResetReappliesBand"] is True
    assert result["bandCoversEllipsis"] is True
    assert result["bandStartsRow"] is True


def test_collapsed_lifecycle_rows_reserve_width_for_expand_hint() -> None:
    result = run_typescript(
        f"""
        import {{ renderToolLifecycle, startedToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth }} from "@earendil-works/pi-tui";
        const theme = {{
          fg: (_color, text) => text,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};
        const rows = renderToolLifecycle(
          startedToolLifecycle("agent", "@greeter-alpha started · Start the greeting task now: introduce yourself to @greeter-beta and @greeter-gamma"),
          {{
            width: 80,
            expandHint: "ctrl+o to expand",
            expandable: true,
            theme,
            fit: truncateToWidth,
            visibleWidth,
          }},
        );
        console.log(JSON.stringify({{ row: rows[1].trim(), fits: visibleWidth(rows[1]) <= 80 }}));
        """
    )
    assert result["fits"] is True
    assert "ctrl+o to expand" in result["row"]


def test_inline_expanded_subject_uses_native_wrapping_and_width_based_hints() -> None:
    result = run_typescript(
        f"""
        import {{ stripVTControlCharacters }} from "node:util";
        import {{ eventToolLifecycle, renderToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth, wrapTextWithAnsi }} from "@earendil-works/pi-tui";
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const subject = "to @audit · steered · " + "检查 café evidence ".repeat(25);
        const spec = eventToolLifecycle("message", subject.trim(), {{ expandedSubject: subject.trim() }});
        const rows = (width, expanded = false, value = spec) => renderToolLifecycle(value, {{
          width, expanded, theme, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi,
          expandHint: "ctrl+shift+e to expand",
        }});
        const content = (lines) => lines.slice(1, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
        const hint = " · ctrl+shift+e to expand";
        const widths = [48, 90, 240];
        const multiline = "to @audit · steered · first\\n\\n" + Array.from({{ length: 61 }}, (_, i) => `line-${{i}} ${{"complete ".repeat(8)}}`).join("\\n");
        const expanded = content(rows(90, true, eventToolLifecycle("message", "preview", {{ expandedSubject: multiline }})));
        const shortSpec = eventToolLifecycle("message", "to @audit · short", {{ expandedSubject: "to @audit · short" }});
        const ordinary = eventToolLifecycle("other", "preview", {{ details: ["first", "second"] }});
        console.log(JSON.stringify({{
          collapsed: widths.map((width) => content(rows(width))),
          expectedCollapsed: widths.map((width) => [stripVTControlCharacters(truncateToWidth(`[message] ${{subject.trim()}}`, width - 2 - visibleWidth(hint))) + hint]),
          expanded: widths.map((width) => content(rows(width, true))),
          expectedExpanded: widths.map((width) => wrapTextWithAnsi(`[message] ${{subject.trim()}}`, width - 2)),
          allFit: widths.every((width) => [false, true].every((expanded) => rows(width, expanded).every((line) => visibleWidth(line) <= width))),
          multiline: expanded,
          expectedMultiline: wrapTextWithAnsi(`[message] ${{multiline}}`, 88).map((line) => line.trimEnd()),
          short: content(rows(90, false, shortSpec)),
          note: content(rows(90, false, {{ ...shortSpec, details: ["separate note"] }})),
          tiny: content(rows(8)),
          expectedTiny: wrapTextWithAnsi(hint, 6),
          ordinary: content(rows(90, true, ordinary)),
        }}));
        """
    )
    assert result["collapsed"] == result["expectedCollapsed"]
    assert result["expanded"] == result["expectedExpanded"]
    assert result["allFit"] is True
    assert result["multiline"] == result["expectedMultiline"]
    assert result["short"] == ["[message] to @audit · short"]
    assert result["note"] == ["[message] to @audit · short · ctrl+shift+e to expand"]
    assert result["tiny"] == result["expectedTiny"]
    assert result["ordinary"] == ["[other] preview", "first", "second"]


def test_inline_subject_hints_ignore_opaque_result_metadata_in_all_factories() -> None:
    result = run_typescript(
        f"""
        import {{ createToolLifecycleMessageRenderer, createToolLifecycleResultRenderer, eventToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth, wrapTextWithAnsi }} from "@earendil-works/pi-tui";
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const options = {{
          createSpec: () => eventToolLifecycle("message", "short", {{ expandedSubject: "short" }}),
          fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: "ctrl+o to expand",
        }};
        const value = {{ content: "model-only routing record", details: {{ internal: "metadata" }} }};
        console.log(JSON.stringify({{
          result: createToolLifecycleResultRenderer(options)(value, {{}}, theme, {{}}).render(90)[1].trim(),
          message: createToolLifecycleMessageRenderer(options)(value, {{}}, theme).render(90)[1].trim(),
        }}));
        """
    )
    assert result == {"result": "[message] short", "message": "[message] short"}


def test_context_shaped_research_rows_keep_a_distinct_query_and_complete_answer() -> None:
    result = run_typescript(
        f"""
        import {{ bindLifecycleRenderers, contentDetailLines, eventToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth, wrapTextWithAnsi }} from "@earendil-works/pi-tui";
        import {{ stripVTControlCharacters }} from "node:util";
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const rows = bindLifecycleRenderers({{
          fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi,
          expandHint: "ctrl+o to expand",
        }});
        const answer = Array.from({{ length: 61 }}, (_, i) => `research finding ${{i}}`);
        const result = {{ content: [{{ type: "text", text: answer.join("\\n") }}], details: {{ operation: "context-review" }} }};
        const spec = eventToolLifecycle("context", "Research the lifecycle renderer", {{
          label: "researched", details: contentDetailLines(result), detailLimit: "all",
        }});
        const renderer = rows.result(() => spec);
        const content = (expanded) => renderer(result, {{ expanded }}, theme, {{}}).render(90)
          .slice(1, -1).map((line) => stripVTControlCharacters(line).trim());
        console.log(JSON.stringify({{ collapsed: content(false), expanded: content(true), answer }}));
        """
    )
    assert result["collapsed"] == ["[context] researched · Research the lifecycle renderer · ctrl+o to expand"]
    assert result["expanded"] == ["[context] researched · Research the lifecycle renderer", *result["answer"]]


def test_incoming_message_bands_reserve_the_complete_configured_hint() -> None:
    result = run_typescript(
        f"""
        import {{ renderAgentMessageBand }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth, wrapTextWithAnsi }} from "@earendil-works/pi-tui";
        import {{ stripVTControlCharacters }} from "node:util";
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const hint = " · ctrl+shift+e to expand";
        const render = (direction) => renderAgentMessageBand([{{ direction, teammate: "continual-audit-close" }}], {{
          theme, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi,
          expandHint: "ctrl+shift+e to expand",
        }});
        const content = (lines) => lines.slice(1, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
        console.log(JSON.stringify({{
          hints: ["from", "to"].map((direction) => [48, 90, 240].every((width) => content(render(direction).render(width))[0].endsWith(hint))),
          allFit: [1, 2, 8, 48, 90, 240].every((width) => render("from").render(width).every((line) => visibleWidth(line) <= width)),
          tiny: content(render("from").render(8)),
          expectedTiny: wrapTextWithAnsi(hint, 6),
        }}));
        """
    )
    assert result["hints"] == [True, True]
    assert result["allFit"] is True
    assert result["tiny"] == result["expectedTiny"]


def test_agent_message_band_shares_the_report_row_language() -> None:
    result = run_typescript(
        f"""
        import {{ agentColor, renderAgentMessageBand }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};
        const fit = (text, width, _ellipsis = "", pad = false) =>
          pad ? text.padEnd(width) : text;
        const row = renderAgentMessageBand(
          [{{ direction: "from", teammate: "calc-alpha" }}],
          {{ theme, fit, expandHint: "ctrl+o to expand" }},
        );
        const multi = renderAgentMessageBand(
          [
            {{ direction: "from", teammate: "calc-alpha" }},
            {{ direction: "from", teammate: "scribe", count: 2 }},
          ],
          {{ theme, fit }},
        );
        console.log(JSON.stringify({{
          color: agentColor("calc-alpha"),
          deterministic: agentColor("calc-alpha") === agentColor("calc-alpha"),
          single: row.render(60),
          multiSingleBand: multi.render(60),
          zeroWidth: row.render(0),
        }}));
        """
    )
    r = result
    assert r["color"] in ["accent", "borderAccent", "mdHeading", "mdLink"]
    assert r["color"] not in ["success", "error"]
    assert r["deterministic"] is True
    assert r["zeroWidth"] == []
    single = r["single"]
    assert len(single) == 3
    assert single[0].strip() == "" and single[-1].strip() == ""
    assert "<customMessageLabel>[message] from </customMessageLabel>" in single[1]
    assert f"<{r['color']}>@calc-alpha</{r['color']}>" in single[1]
    assert "<dim> · ctrl+o to expand</dim>" in single[1]
    multi_lines = r["multiSingleBand"]
    assert len(multi_lines) == 4  # one band: pad + 2 rows + pad
    assert "<customMessageLabel>[message] from </customMessageLabel>" in multi_lines[1]
    assert "<customMessageLabel>[2 messages] from </customMessageLabel>" in multi_lines[2]


def test_lifecycle_tool_execution_wrapper_enables_mouse_toggling() -> None:
    result = run_typescript(
        f"""
        import {{ createToolExecutionWrapper, createStaticToolLifecycleMessageRenderer, eventToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};

        class FakeHostComponent {{
          constructor(toolName, toolCallId, args, options, toolDefinition, ui, cwd) {{
            this.toolName = toolName;
            this.toolCallId = toolCallId;
            this.args = args;
            this.options = options;
            this.toolDefinition = toolDefinition;
            this.ui = ui;
            this.cwd = cwd;
            this.expanded = false;
            this.selfRenderContainer = {{
              handleMouse: (event) => {{
                if (event.type === "click" && event.button === "left") {{
                  this.setExpanded(!this.expanded);
                  return {{ handled: true, target: this, y: event.y }};
                }}
                return undefined;
              }},
              render: (w) => this.toolDefinition.renderResult(this.result, {{ expanded: this.expanded }}, theme).render(w),
            }};
          }}
          hasRendererDefinition() {{ return true; }}
          getRenderShell() {{ return "self"; }}
          updateResult(res) {{ this.result = res; }}
          setExpanded(exp) {{ this.expanded = exp; }}
          render(w) {{
            const lines = this.selfRenderContainer.render(w);
            return lines.length > 0 ? ["", ...lines] : [];
          }}
          handleMouse(event) {{
            if (event.y <= 0) return undefined;
            return this.selfRenderContainer.handleMouse(event);
          }}
        }}

        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};
        const fit = (text) => text;
        const visibleWidth = (text) => text.length;

        const renderer = createStaticToolLifecycleMessageRenderer({{
          createSpec: (msg) => eventToolLifecycle("message", msg.content, {{ label: "event", details: ["detail line"] }}),
          fit,
          visibleWidth,
          expandHint: "ctrl+o to expand",
          hostComponent: FakeHostComponent,
        }});

        const comp = renderer({{ content: "from @audit" }}, {{ expanded: false }}, theme);

        const collapsedLines = comp.render(60);
        // Simulate mouse click on content line (y: 0 in child coordinates because top line was trimmed)
        const clickRes1 = comp.handleMouse({{ type: "click", button: "left", y: 0, x: 5 }});
        const expandedLines = comp.render(60);
        const clickRes2 = comp.handleMouse({{ type: "click", button: "left", y: 0, x: 5 }});
        const reCollapsedLines = comp.render(60);

        console.log(JSON.stringify({{
          hasWrapper: typeof comp.handleMouse === "function",
          collapsedCount: collapsedLines.length,
          collapsed: collapsedLines,
          click1Handled: clickRes1?.handled,
          expandedCount: expandedLines.length,
          expanded: expandedLines,
          click2Handled: clickRes2?.handled,
          reCollapsedCount: reCollapsedLines.length,
          reCollapsed: reCollapsedLines,
        }}));
        """
    )
    assert result["hasWrapper"] is True
    # The leading redundant empty line is stripped by wrapper
    assert result["collapsedCount"] == 3  # pad + content + pad (no double empty line at start)
    assert "ctrl+o to expand" in result["collapsed"][1]
    assert result["click1Handled"] is True
    assert "detail line" in " ".join(result["expanded"])
    assert result["click2Handled"] is True
    assert "ctrl+o to expand" in result["reCollapsed"][1]


def test_status_and_working_indicator_adapters_sanitize_and_use_shared_spinner() -> None:
    result = run_typescript(
        f"""
        import {{ clearPiStatus, clearPiWorkingIndicator, setPiStatus, startPiWorkingIndicator }} from {json.dumps((SRC / "index.ts").as_uri())};
        const statuses = [];
        const indicators = [];
        const ui = {{
          setStatus: (key, value) => statuses.push([key, value]),
          setWorkingIndicator: (value) => indicators.push(value),
        }};
        setPiStatus(ui, "vision\\u001b]0;bad\\u0007", "reading\\u001b[31m image\\u001b[0m");
        clearPiStatus(ui, "vision");
        startPiWorkingIndicator(ui);
        clearPiWorkingIndicator(ui);
        console.log(JSON.stringify({{ statuses, indicators }}));
        """
    )
    assert result["statuses"] == [["vision", "reading image"], ["vision", None]]
    assert result["indicators"] == [
        {"frames": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"], "intervalMs": 120},
        None,
    ]


def test_safe_display_text_sanitizes_terminal_output() -> None:
    result = run_typescript(
        f"""
        import {{ safeDisplayText }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          ansi: safeDisplayText("\u001b[31mred\u001b[39m"),
          osc: safeDisplayText("Evil\u001b]0;pwned\u0007Name"),
          control: safeDisplayText("a\u0007b\u007fc"),
        }}));
        """
    )
    assert result == {"ansi": "red", "osc": "EvilName", "control": "abc"}


def test_safe_display_text_preserves_osc_hyperlink_labels() -> None:
    result = run_typescript(r'''
        import { safeDisplayText } from './packages/kit/src/index.ts';
        const st = '\u001b\\', esc = '\u001b', bel = '\u0007';
        console.log(JSON.stringify({
          st: safeDisplayText(`Open ${esc}]8;;https://example.test${st}LINK-LABEL${esc}]8;;${st} after.`),
          bel: safeDisplayText(`Open ${esc}]8;;https://example.test${bel}LINK-LABEL${esc}]8;;${bel} after.`),
          c1: safeDisplayText('Open \u009d8;;https://example.test\u009cLINK-LABEL\u009d8;;\u009c after.'),
          adjacent: safeDisplayText(`${esc}]0;hidden${st}First${esc}]0;hidden2${st}Second`),
          mixed: safeDisplayText(`${esc}]0;hidden${bel}First${esc}]0;hidden2${st}Second`),
          unfinished: safeDisplayText(`Visible ${esc}]0;hidden`),
          controls: safeDisplayText(`${esc}[31mred${esc}[0m\nnext\tcolumn\u0007`),
        }));
    ''')
    assert result == {
        'st': 'Open LINK-LABEL after.', 'bel': 'Open LINK-LABEL after.',
        'c1': 'Open LINK-LABEL after.', 'adjacent': 'FirstSecond',
        'mixed': 'FirstSecond', 'unfinished': 'Visible ', 'controls': 'red\nnext\tcolumn',
    }


def test_handle_scrubbing_preserves_surrounding_literal_syntax() -> None:
    result = run_typescript(r'''
        import { scrubHandles } from './packages/kit/src/index.ts';
        const message = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
        console.log(JSON.stringify({
          plain: scrubHandles(message),
          addressed: scrubHandles(message + '\n"session:reader:spawn-1" ; work:e0cfae81-57dd-4b68-8b67-2103ed825cfd !', () => 'Fix spacing'),
        }));
    ''')
    message = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"'
    assert result['plain'] == message
    assert result['addressed'] == message + '\n"@reader" ; Fix spacing !'


def test_agent_display_helpers_share_labels_and_message_counts() -> None:
    result = run_typescript(
        f"""
        import {{ formatAgentMessagePrefix, formatAgentTaskName }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          prefix: formatAgentMessagePrefix("from"),
          multiPrefix: formatAgentMessagePrefix("from", 2),
          outgoingPrefix: formatAgentMessagePrefix("to"),
          taskName: formatAgentTaskName("  inspect   authentication  ", "fallback"),
          longTaskName: formatAgentTaskName("x".repeat(140), "fallback"),
        }}));
        """
    )
    assert result["prefix"] == "[message] from "
    assert result["multiPrefix"] == "[2 messages] from "
    assert result["outgoingPrefix"] == "[message] to "
    assert result["taskName"] == "inspect authentication"
    assert result["longTaskName"] == "x" * 140


def test_package_prompt_agent_helpers_are_not_exported() -> None:
    result = run_typescript(
        f"""
        const kit = await import({json.dumps((SRC / "index.ts").as_uri())});
        console.log(JSON.stringify({{
          createPackageAgentRun: "createPackageAgentRun" in kit,
          subagentDisplayName: "subagentDisplayName" in kit,
        }}));
        """
    )
    assert result == {"createPackageAgentRun": False, "subagentDisplayName": False}
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    for obsolete in ("PackageAgentRunOptions", "PackageAgentRun", "createPackageAgentRun", "subagentDisplayName"):
        assert obsolete not in source


def test_pi_worker_progress_resets_text_at_message_boundaries(tmp_path: Path) -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const packageDir = path.join(root, "node_modules", "@earendil-works", "pi-coding-agent");
        fs.mkdirSync(packageDir, {{ recursive: true }});
        fs.writeFileSync(path.join(packageDir, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(packageDir, "cli.mjs");
        const events = [
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "first" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "first" }}] }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "second" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "second" }}] }} }},
        ];
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\n" + `const events = ${{JSON.stringify(events)}};\\nfor (const event of events) {{ console.log(JSON.stringify(event)); await new Promise((resolve) => setTimeout(resolve, 5)); }}\\n`, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const activities = [];
        await runPiWorker({{ prompt: "inspect", cwd: root, onUpdate: (update) => activities.push(update.activity) }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ activities }}));
        """
    )
    assert "firstsecond" not in result["activities"]
    assert "second" in result["activities"]


def test_pi_worker_progress_reports_latest_activity_across_stream_kinds(tmp_path: Path) -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const packageDir = path.join(root, "node_modules", "@earendil-works", "pi-coding-agent");
        fs.mkdirSync(packageDir, {{ recursive: true }});
        fs.writeFileSync(path.join(packageDir, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(packageDir, "cli.mjs");
        const events = [
          {{ type: "message_update", assistantMessageEvent: {{ type: "thinking_delta", delta: "older reasoning" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "newer answer" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_start" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_delta", delta: JSON.stringify({{ command: "pnpm test" }}) }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_end", toolCall: {{ name: "bash" }} }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "pre-tool answer" }}] }} }},
          {{ type: "tool_execution_start", toolCallId: "call-1", toolName: "bash", args: {{ command: "pnpm check" }} }},
          {{ type: "tool_execution_end", toolCallId: "call-1", toolName: "bash" }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "final answer" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "final answer" }}] }} }},
        ];
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\n" + `const events = ${{JSON.stringify(events)}};\\nfor (const event of events) {{ console.log(JSON.stringify(event)); await new Promise((resolve) => setTimeout(resolve, 5)); }}\\n`, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const activities = [];
        await runPiWorker({{ prompt: "inspect", cwd: root, onUpdate: (update) => activities.push(update.activity) }});
        process.argv[1] = originalArgv1;
        console.log(JSON.stringify({{ activities }}));
        """
    )
    assert "older reasoning" in result["activities"]
    assert "newer answer" in result["activities"]
    assert "bash: pnpm test" in result["activities"]
    assert "bash: pnpm check" in result["activities"]
    assert result["activities"][-1] == "final answer"
    assert all(activity not in ("pre-tool answerfinal answer", "older reasoningfinal answer") for activity in result["activities"])


def test_compute_scroll_window_clamps_and_slices() -> None:
    result = run_typescript(
        f"""
        import {{ computeScrollWindow }} from {json.dumps((SRC / "index.ts").as_uri())};
        const lines = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"];
        const normal = computeScrollWindow(lines, 2, 4);
        const clamped = computeScrollWindow(lines, 100, 4);
        const shortContent = computeScrollWindow(["x", "y"], 5, 10);
        console.log(JSON.stringify({{
          normal,
          normalSlice: lines.slice(normal.start, normal.end),
          clamped,
          clampedSlice: lines.slice(clamped.start, clamped.end),
          shortContent,
        }}));
        """
    )
    assert result == {
        "normal": {"start": 2, "end": 6, "clampedScroll": 2},
        "normalSlice": ["c", "d", "e", "f"],
        "clamped": {"start": 6, "end": 10, "clampedScroll": 6},
        "clampedSlice": ["g", "h", "i", "j"],
        "shortContent": {"start": 0, "end": 2, "clampedScroll": 0},
    }


def test_theme_style_maps_shared_style_language() -> None:
    result = run_typescript(
        f"""
        import {{ createPiThemeStyle }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{ fg: (color, text) => `[${{color}}]${{text}}` }};
        const style = createPiThemeStyle(theme);
        console.log(JSON.stringify({{
          accent: style.accent("a"),
          muted: style.muted("m"),
          dim: style.dim("d"),
          border: style.border("b"),
          success: style.success("s"),
          error: style.error("e"),
          fg: style.fg("warning", "w"),
        }}));
        """
    )
    assert result == {
        "accent": "[accent]a",
        "muted": "[muted]m",
        "dim": "[dim]d",
        "border": "[border]b",
        "success": "[success]s",
        "error": "[error]e",
        "fg": "[warning]w",
    }


def test_extract_text_content_from_strings_blocks_and_non_content() -> None:
    result = run_typescript(
        f"""
        import {{ extractTextContent }} from {json.dumps((SRC / "index.ts").as_uri())};
        const blocks = [
          {{ type: "text", text: "first" }},
          {{ type: "image", data: "..." }},
          {{ type: "thinking", thinking: "secret" }},
          {{ type: "text", text: "second" }},
        ];
        console.log(JSON.stringify({{
          fromString: extractTextContent("hello"),
          fromBlocks: extractTextContent(blocks),
          joinedEmpty: extractTextContent(blocks, ""),
          joinedSpace: extractTextContent(blocks, " "),
          fromNull: extractTextContent(null),
          fromNumber: extractTextContent(42),
          fromEmptyArray: extractTextContent([]),
        }}));
        """
    )
    assert result == {
        "fromString": "hello",
        "fromBlocks": "first\nsecond",
        "joinedEmpty": "firstsecond",
        "joinedSpace": "first second",
        "fromNull": "",
        "fromNumber": "",
        "fromEmptyArray": "",
    }


def test_model_ref_parse_and_format_helpers() -> None:
    result = run_typescript(
        f"""
        import {{ parseModelRef, modelRef, modelLabel, sortModels, nonEmpty }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          parsed: parseModelRef("anthropic/claude-3-5-haiku"),
          parsedModelOnly: parseModelRef("openai/gpt-4o-mini"),
          invalidNoSlash: parseModelRef("gpt-4o"),
          invalidEmpty: parseModelRef(""),
          invalidUndefined: parseModelRef(undefined),
          invalidLeadingSlash: parseModelRef("/gpt-4o"),
          invalidTrailingSlash: parseModelRef("openai/"),
          refBoth: modelRef({{ provider: "openai", model: "gpt-4o" }}),
          refModelOnly: modelRef({{ provider: undefined, model: "gpt-4o" }}),
          refNone: modelRef({{ provider: undefined, model: undefined }}),
          label: modelLabel({{ provider: "anthropic", id: "claude" }}),
          sorted: sortModels([
            {{ provider: "z", id: "a" }},
            {{ provider: "a", id: "z" }},
            {{ provider: "a", id: "a" }},
          ]),
          nonEmpty: nonEmpty("  hi  "),
          nonEmptyBlank: nonEmpty("   "),
        }}, (k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["parsed"] == {"provider": "anthropic", "model": "claude-3-5-haiku"}
    assert result["parsedModelOnly"] == {"provider": "openai", "model": "gpt-4o-mini"}
    assert result["invalidNoSlash"] is None
    assert result["invalidEmpty"] is None
    assert result["invalidUndefined"] is None
    assert result["invalidLeadingSlash"] is None
    assert result["invalidTrailingSlash"] is None
    assert result["refBoth"] == "openai/gpt-4o"
    assert result["refModelOnly"] == "gpt-4o"
    assert result["refNone"] is None
    assert result["label"] == "anthropic/claude"
    assert result["sorted"] == [
        {"provider": "a", "id": "a"},
        {"provider": "a", "id": "z"},
        {"provider": "z", "id": "a"},
    ]
    assert result["nonEmpty"] == "hi"
    assert result["nonEmptyBlank"] is None


def test_select_model_from_menu_returns_selected_pair() -> None:
    result = run_typescript(
        f"""
        import {{ selectModelFromMenu }} from {json.dumps((SRC / "index.ts").as_uri())};
        const ui = {{
          notify: () => {{}},
          select: async (label, options) => {{
            // Simulate the user picking the "current" option.
            return options.find((o) => o.includes("· current"));
          }},
        }};
        const models = [
          {{ provider: "anthropic", id: "claude-sonnet", name: "Claude Sonnet" }},
          {{ provider: "openai", id: "gpt-4o", name: "GPT-4o" }},
        ];
        const selected = await selectModelFromMenu(ui, models, "anthropic/claude-sonnet", "Pick");
        console.log(JSON.stringify({{ selected }}));
        """
    )
    assert result["selected"] == {"provider": "anthropic", "model": "claude-sonnet"}


def test_select_model_menu_no_models_notifies_and_returns_undefined() -> None:
    result = run_typescript(
        f"""
        import {{ selectModelFromMenu }} from {json.dumps((SRC / "index.ts").as_uri())};
        let notified = null;
        const ui = {{ select: async () => "x", notify: (msg, type) => {{ notified = {{ msg, type }}; }} }};
        const selected = await selectModelFromMenu(ui, [], undefined, "Pick");
        console.log(JSON.stringify({{ selected, notified }}, (k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["selected"] is None
    assert result["notified"] == {"msg": "No models are available in the model registry.", "type": "warning"}


def test_search_model_from_picker_filtering_navigation_and_selection() -> None:
    result = run_typescript(
        f"""
        import {{ searchModelFromPicker }} from {json.dumps((SRC / "index.ts").as_uri())};
        const models = [
          {{ provider: "openai", id: "gpt-4o", name: "GPT-4o" }},
          {{ provider: "anthropic", id: "claude-sonnet-3.5", name: "Claude 3.5 Sonnet" }},
          {{ provider: "anthropic", id: "claude-haiku-3.5", name: "Claude 3.5 Haiku" }},
        ];

        let customFactory = null;
        const fakeTheme = {{
          fg: (_color, text) => text,
          bold: (text) => text,
        }};
        const fakeKb = {{
          matches: (key, action) => {{
            if (action === "tui.select.down" && key === "down") return true;
            if (action === "tui.select.up" && key === "up") return true;
            if (action === "tui.select.confirm" && key === "enter") return true;
            if (action === "tui.select.cancel" && key === "escape") return true;
            return false;
          }},
        }};

        const mockUi = {{
          async custom(factory) {{
            customFactory = factory;
            return new Promise((resolve) => {{
              const component = factory({{}}, fakeTheme, fakeKb, resolve);
              // Test initial render
              const initialLines = component.render(80);
              // Type search query
              component.handleInput("h");
              component.handleInput("a");
              component.handleInput("i");
              const filteredLines = component.render(80);
              // Confirm selection
              component.handleInput("enter");
            }});
          }},
          notify() {{}},
        }};

        const selected = await searchModelFromPicker(mockUi, models, "openai/gpt-4o", {{ title: "Pick model" }});

        // Test cancellation
        const cancelUi = {{
          async custom(factory) {{
            return new Promise((resolve) => {{
              const component = factory({{}}, fakeTheme, fakeKb, resolve);
              component.handleInput("escape");
            }});
          }},
          notify() {{}},
        }};
        const cancelled = await searchModelFromPicker(cancelUi, models, undefined);

        // Test empty models
        let emptyNotified = null;
        const emptyUi = {{
          async custom() {{}},
          notify(msg, type) {{ emptyNotified = {{ msg, type }}; }},
        }};
        const emptyResult = await searchModelFromPicker(emptyUi, []);

        console.log(JSON.stringify({{ selected, cancelled, emptyResult, emptyNotified }}, (k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["selected"] == {"provider": "anthropic", "model": "claude-haiku-3.5"}
    assert result["cancelled"] is None
    assert result["emptyResult"] is None
    assert result["emptyNotified"] == {"msg": "No models are available in the model registry.", "type": "warning"}


def test_search_model_from_picker_renders_query_in_blue_border() -> None:
    result = run_typescript(
        f"""
        import {{ searchModelFromPicker }} from {json.dumps((SRC / "index.ts").as_uri())};
        const models = [{{ provider: "openai", id: "gpt-4o", name: "GPT-4o" }}];
        const fakeTheme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bold: (text) => text,
        }};
        let capturedQueryLine = "";
        const mockUi = {{
          async custom(factory) {{
            return new Promise((resolve) => {{
              const component = factory({{}}, fakeTheme, {{}}, resolve);
              component.handleInput("g");
              component.handleInput("p");
              component.handleInput("t");
              const lines = component.render(80);
              capturedQueryLine = lines[2];
              resolve(undefined);
            }});
          }},
          notify() {{}},
        }};
        await searchModelFromPicker(mockUi, models, undefined);
        console.log(JSON.stringify({{ queryLine: capturedQueryLine }}));
        """
    )
    assert "<border>gpt</border>" in result["queryLine"]


def test_enter_model_from_input_parses_and_validates() -> None:
    result = run_typescript(
        f"""
        import {{ enterModelFromInput }} from {json.dumps((SRC / "index.ts").as_uri())};
        const registry = {{ find: (p, m) => (p === "openai" && m === "gpt-4o" ? {{}} : undefined) }};
        const notifications = [];
        const ui = {{
          notify: (msg, type) => notifications.push({{ msg, type }}),
        }};
        const good = await enterModelFromInput({{ ...ui, input: async () => "openai/gpt-4o" }}, registry, undefined);
        const bad = await enterModelFromInput({{ ...ui, input: async () => "nope" }}, registry, undefined);
        const missing = await enterModelFromInput({{ ...ui, input: async () => "openai/unknown" }}, registry, undefined);
        const empty = await enterModelFromInput({{ ...ui, input: async () => "   " }}, registry, undefined);
        const cancelled = await enterModelFromInput({{ ...ui, input: async () => undefined }}, registry, undefined);
        console.log(JSON.stringify({{ good, bad, missing, empty, cancelled, notifications }}, (k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["good"] == {"provider": "openai", "model": "gpt-4o"}
    assert result["bad"] is None
    assert result["missing"] is None
    assert result["empty"] is None
    assert result["cancelled"] is None
    assert len(result["notifications"]) == 3
    assert result["notifications"][0]["type"] == "error"
    assert result["notifications"][1]["type"] == "error"
    assert result["notifications"][2]["type"] == "error"


def test_enter_model_population_and_on_empty_handler() -> None:
    result = run_typescript(
        f"""
        import {{ enterModelFromInput }} from {json.dumps((SRC / "index.ts").as_uri())};
        const registry = {{ find: (p) => (p === "openai" ? {{}} : undefined) }};
        const notifications = [];
        const ui = {{ notify: (msg, type) => notifications.push({{ msg, type }}) }};
        let reset = 0;
        const empty = await enterModelFromInput(
          {{ ...ui, input: async () => "   " }},
          registry, undefined,
          {{ onEmpty: () => {{ reset++; }} }},
        );
        const defaulted = await enterModelFromInput(
          {{ ...ui, input: async (label, def) => def }},
          registry, "openai/gpt-4o",
          {{ label: "Pick me" }},
        );
        console.log(JSON.stringify({{ empty, reset, defaulted, notifications }}, (k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["empty"] is None
    assert result["reset"] == 1
    assert result["defaulted"] == {"provider": "openai", "model": "gpt-4o"}
    # onEmpty suppresses the error notification.
    assert result["notifications"] == []


def test_kit_manifest_is_a_pure_runtime_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-kit"
    assert "pi" not in manifest
    assert "dependencies" not in manifest
    assert "peerDependencies" not in manifest
    assert "pi-package" not in manifest.get("keywords", [])
    assert "src" in manifest["files"]


def test_kit_has_no_consumer_imports() -> None:
    consumer_names = {json.loads((REPO / "packages" / c / "package.json").read_text())["name"] for c in CONSUMERS}
    for source in SRC.glob("*.ts"):
        text = source.read_text(encoding="utf-8")
        for name in consumer_names:
            assert name not in text, f"{source.name} must not import consumer package {name}"
        assert 'from "@earendil-works/pi-coding-agent"' not in text, f"{source.name} must not import pi core"


def test_model_search_text_and_search_picker_behavior() -> None:
    result = run_typescript(
        f"""
        import {{ modelSearchText, createSearchPicker, sortModels }} from {json.dumps((SRC / "index.ts").as_uri())};
        const models = sortModels([
          {{ provider: "openai", id: "gpt-5.2", name: "GPT-5.2" }},
          {{ provider: "anthropic", id: "claude-opus-4-6", name: "Claude Opus 4.6" }},
          {{ provider: "anthropic", id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6" }},
          {{ provider: "google", id: "gemini-3-pro", name: undefined }},
        ].map((m) => ({{ ...m, name: m.name ?? m.id }})));
        // Substring stand-in with fuzzyFilter ordering semantics: keep order, drop misses.
        const substringFilter = (items, query, getText) =>
          items.filter((item) => getText(item).toLowerCase().includes(query.toLowerCase()));
        const picker = createSearchPicker(models, {{ filter: substringFilter, getText: modelSearchText }});
        picker.type("cl");
        const narrowed = picker.results().map((m) => `${{m.provider}}/${{m.id}}`);
        picker.down();
        const movedIndex = picker.selectedIndex();
        picker.type("aude opus");
        const refined = picker.results().map((m) => `${{m.provider}}/${{m.id}}`);
        const refinedIndex = picker.selectedIndex();
        picker.backspace();
        picker.clear();
        const restored = picker.results().length;
        picker.up();
        const clampedTop = picker.selectedIndex();
        picker.clear();
        for (let i = 0; i < 10; i++) picker.down();
        const bottomClamped = picker.selectedIndex();
        const bottomSelected = picker.selected();
        picker.type("zzz-no-match");
        const emptySelected = picker.selected();
        console.log(JSON.stringify({{
          namedText: modelSearchText({{ provider: "anthropic", id: "claude-opus-4-6", name: "Claude Opus 4.6" }}),
          namelessText: modelSearchText({{ provider: "google", id: "gemini-3-pro" }}),
          narrowed,
          movedIndex,
          refined,
          refinedIndex,
          restored,
          clampedTop,
          bottomClamped,
          bottomLabel: `${{bottomSelected?.provider ?? ""}}/${{bottomSelected?.id ?? ""}}`,
          emptySelected,
        }}, (key, value) => (value === undefined ? null : value)));
        """
    )
    assert result["namedText"] == "anthropic/claude-opus-4-6 · Claude Opus 4.6"
    assert result["namelessText"] == "google/gemini-3-pro"
    assert result["narrowed"] == ["anthropic/claude-opus-4-6", "anthropic/claude-sonnet-4-6"]
    assert result["refined"] == ["anthropic/claude-opus-4-6"]
    assert result["refinedIndex"] == 0
    assert result["restored"] == 4
    assert result["movedIndex"] == 1
    assert result["clampedTop"] == 0
    assert result["bottomClamped"] == 3
    assert result["bottomLabel"] == "openai/gpt-5.2"
    assert result["emptySelected"] is None


def test_consumers_declare_kit_as_workspace_dependency() -> None:
    for consumer in CONSUMERS:
        manifest = json.loads((REPO / "packages" / consumer / "package.json").read_text(encoding="utf-8"))
        assert manifest.get("dependencies", {}).get("@fradser/pi-kit") == "workspace:*", (
            f"{consumer} must depend on @fradser/pi-kit via workspace:* under dependencies"
        )
        assert "@fradser/pi-kit" not in manifest.get("peerDependencies", {}), (
            f"{consumer} must not declare @fradser/pi-kit as a peer dependency"
        )


def test_packed_consumers_resolve_workspace_protocol_dependencies() -> None:
    feature = (PACKAGE / "features" / "pi-kit.feature").read_text(encoding="utf-8")
    assert "Consumer packages resolve workspace dependency protocols when packed" in feature
    temp_dir = tempfile.mkdtemp(prefix="kit-pack-test-")
    try:
        for consumer in ("matt-pocock", "agent-teams", "vision"):
            output = subprocess.check_output(
                ["pnpm", "--dir", str(REPO / "packages" / consumer), "pack", "--pack-destination", temp_dir],
                text=True,
            )
            tarball_match = re.search(r"([^\s]+\.tgz)", output)
            assert tarball_match, f"Could not find tarball in output: {output}"
            tarball_path = tarball_match.group(1)
            pkg_json = subprocess.check_output(
                ["tar", "-xOf", tarball_path, "package/package.json"],
                text=True,
            )
            packed_manifest = json.loads(pkg_json)
            dep = packed_manifest.get("dependencies", {}).get("@fradser/pi-kit")
            assert dep and not dep.startswith("workspace:"), (
                f"{consumer} packed dependency must not use workspace protocol: {dep}"
            )
            assert re.match(r"^\d+\.\d+\.\d+", dep), (
                f"{consumer} packed dependency must be semver version: {dep}"
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_publish_allowlist_orders_kit_before_consumers() -> None:
    script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")
    kit_position = script.index('"@fradser/pi-kit"')
    assert kit_position > 0, "publish allowlist must include @fradser/pi-kit"
    for name in ['"@fradser/pi-agent-teams"', '"@fradser/pi-btw"', '"pi-continual-learning"',
                 '"@fradser/pi-recap"', '"@fradser/pi-utils"', '"@fradser/pi-vision"',
                 '"@fradser/pi-plan-mode"']:
        assert script.index(name) > kit_position, f"pi-kit must publish before {name}"


def test_pending_changesets_reference_workspace_package_names() -> None:
    workspace_names = {
        json.loads(manifest.read_text(encoding="utf-8"))["name"]
        for manifest in (REPO / "packages").glob("*/package.json")
    }
    changeset_files = (REPO / ".changeset").glob("*.md")

    for changeset_file in changeset_files:
        contents = changeset_file.read_text(encoding="utf-8")
        if not contents.startswith("---\\n"):
            continue
        frontmatter = contents.split("---", 2)[1]
        declared_names = [line.split('"', 2)[1] for line in frontmatter.splitlines() if line.startswith('"')]
        unknown_names = set(declared_names) - workspace_names
        assert not unknown_names, f"{changeset_file.name} references unknown packages: {sorted(unknown_names)}"


def test_lifecycle_binding_unifies_rows_across_call_sites() -> None:
    result = run_typescript(
        f"""
        import {{ bindLifecycleRenderers, eventToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const rows = bindLifecycleRenderers({{
          fit: (text, width) => text,
          visibleWidth: (text) => text.length,
          wrapDetail: (line) => [line],
          expandHint: "ctrl+o to expand",
        }});
        const first = rows.result(() => eventToolLifecycle("monitor", "nightly", {{ label: "started", details: ["command · make check"] }}));
        const second = rows.result(() => eventToolLifecycle("sessions", "two items", {{ label: "listed", details: ["a", "b"] }}));
        const message = rows.message(() => eventToolLifecycle("learning", "done", {{ label: "event", details: ["policy · allow"] }}), {{ cwd: "/repo" }});
        const collapsed = first({{ content: [] }}, {{ expanded: false }}, theme, {{}}).render(200).join("\\n");
        const empty = rows.emptyCall();
        console.log(JSON.stringify({{
          first: first({{ content: [] }}, {{ expanded: true }}, theme, {{}}).render(200).join("\\n"),
          second: second({{ content: [] }}, {{ expanded: true }}, theme, {{}}).render(200).join("\\n"),
          message: message({{ content: "done", details: {{}} }}, {{ expanded: true }}, theme).render(200).join("\\n"),
          collapsed: collapsed,
          empty: empty.render(200),
        }}));
        """
    )
    assert "[monitor] started · nightly · ctrl+o to expand" in result["collapsed"]
    assert "command · make check" in result["first"]
    assert "[sessions] listed · two items" in result["second"]
    assert "\n a\n b" in result["second"]
    assert "[learning] event · done" in result["message"]
    assert "policy · allow" in result["message"]
    assert result["empty"] == []


def test_human_copy_helpers_share_one_vocabulary() -> None:
    result = run_typescript(
        f"""
        import {{ contentDetailLines, displayText, fieldBlock, fieldLine, scrubHandles }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          lines: contentDetailLines({{ content: [{{ type: "text", text: "  one\\n\\n two " }}] }}),
          field: fieldLine("model", "qwen3-max"),
          block: fieldBlock("task", "first\\nsecond"),
          dropped: fieldLine("note", {{ nested: true }}),
          session: scrubHandles("see session:reviewer:6d102f1b-cc16-4059-8d86-d5c1192f3776 now"),
          known: scrubHandles("over work:e0cfae81-57dd-4b68-8b67-2103ed825cfd", (h) => h === "work:e0cfae81-57dd-4b68-8b67-2103ed825cfd" ? "Fix spacing" : undefined),
          generic: scrubHandles("over direct:6d102f1b-cc16-4059-8d86-d5c1192f3776."),
          literal: scrubHandles("compare 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log"),
        }}));
        """
    )
    assert result["lines"] == ["one", "two"]
    assert result["field"] == "model · qwen3-max"
    assert result["block"] == ["task · first", "second"]
    assert result["dropped"] == "note · "
    assert result["session"] == "see @reviewer now"
    assert result["known"] == "over Fix spacing"
    assert result["generic"] == "over its assignment."
    assert result["literal"] == "compare 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log"

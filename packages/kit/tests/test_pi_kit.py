"""Shared runtime contracts for @fradser/pi-kit."""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

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
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


# ── Live activity widget & passive TUI layout ──


def test_live_activity_widget_lifecycle_remount_and_fallback_contracts() -> None:
    result = run_typescript(
        f"""
        import {{
          createLiveActivityWidget,
          PI_SPINNER_FRAMES,
          PI_SPINNER_INTERVAL_MS,
        }} from {json.dumps((SRC / "index.ts").as_uri())};
        const calls = [];
        let requestRenders = 0;
        let activeComponent;
        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bold: (text) => `<b>${{text}}</b>`,
        }};
        const ui = {{
          setWidget(key, factory, options) {{
            calls.push({{ key, mounted: Boolean(factory), placement: options?.placement }});
            if (factory) activeComponent = factory({{ requestRender: () => requestRenders++ }}, theme);
          }},
        }};
        const live = createLiveActivityWidget({{
          key: "example",
          placement: "aboveEditor",
          fit: (text, width) => text.slice(0, width),
        }});
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "read planner-prompts.ts" }}]);
        const first = activeComponent.render(120);
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "settling memory" }}]);
        const second = activeComponent.render(120);
        live.update({{ mode: "tui", ui }}, [{{ id: "one", identity: "Dreaming...", activity: "done", status: "completed" }}]);
        const completed = activeComponent.render(120);

        const replacementCalls = [];
        const replacementUi = {{
          setWidget(key, factory, options) {{
            replacementCalls.push({{ key, mounted: Boolean(factory), placement: options?.placement }});
            if (factory) factory({{ requestRender() {{}} }}, theme);
          }},
        }};
        live.update({{ mode: "tui", ui: replacementUi }}, [{{ id: "one", identity: "Dreaming...", activity: "replacement context" }}]);
        live.update({{ mode: "json", ui }}, [{{ id: "one", identity: "Ignored", activity: "headless" }}]);
        live.clear({{ mode: "tui", ui: replacementUi }});

        // Remount after host disposal
        const remountCalls = [];
        let remountComp;
        const remountUi = {{
          setWidget(key, factory) {{
            remountCalls.push({{ key, mounted: Boolean(factory) }});
            if (factory) remountComp = factory({{ requestRender() {{}} }}, theme);
          }},
        }};
        const remountLive = createLiveActivityWidget({{ key: "example", fit: (text) => text }});
        remountLive.update({{ mode: "tui", ui: remountUi }}, [{{ id: "one", identity: "worker" }}]);
        remountComp.dispose();
        remountLive.update({{ mode: "tui", ui: remountUi }}, [{{ id: "one", identity: "worker", activity: "after reload" }}]);
        const remountRow = remountComp.render(80)[0];

        // Optional empty fallbackActivity omits separator
        let plainComp;
        const plainUi = {{
          setWidget(_key, factory) {{
            if (factory) plainComp = factory({{ requestRender() {{}} }}, {{ fg: (_c, t) => t, bold: (t) => t }});
          }},
        }};
        createLiveActivityWidget({{ key: "recap-activity", fit: (t) => t, fallbackActivity: "" }})
          .update({{ mode: "tui", ui: plainUi }}, [{{ id: "recap", identity: "Recapping..." }}]);
        const identityRow = plainComp.render(80)[0];
        createLiveActivityWidget({{ key: "other", fit: (t) => t }})
          .update({{ mode: "tui", ui: plainUi }}, [{{ id: "other", identity: "Dreaming..." }}]);
        const fallbackRow = plainComp.render(80)[0];

        console.log(JSON.stringify({{
          frames: PI_SPINNER_FRAMES,
          interval: PI_SPINNER_INTERVAL_MS,
          calls,
          first,
          second,
          completed,
          replacementCalls,
          remountMountedCount: remountCalls.filter((c) => c.mounted).length,
          remountRow,
          identityRow,
          fallbackRow,
        }}));
        """
    )
    assert result["frames"] == ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    assert result["interval"] == 120
    assert result["calls"] == [
        {"key": "example", "mounted": True, "placement": "aboveEditor"},
        {"key": "example", "mounted": False},
    ]
    assert result["replacementCalls"] == [
        {"key": "example", "mounted": True, "placement": "aboveEditor"},
        {"key": "example", "mounted": False},
    ]
    assert "Dreaming..." in result["first"][0] and "read planner-prompts.ts" in result["first"][0]
    assert "settling memory" in result["second"][0] and "read planner-prompts.ts" not in result["second"][0]
    assert "✓" in result["completed"][0]
    assert result["remountMountedCount"] >= 2
    assert "after reload" in result["remountRow"]
    assert "Recapping..." in result["identityRow"] and "·" not in result["identityRow"] and "Working..." not in result["identityRow"]
    assert "Working..." in result["fallbackRow"]


def test_live_activity_widget_owns_the_identity_and_activity_language() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests" / "activity-row-fixture.ts")],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "KIT_ACTIVITY_ROW_OK" in result.stdout


def test_panel_widget_theme_and_status_adapters_share_tui_geometry() -> None:
    result = run_typescript(
        f"""
        import {{
          clearPiStatus,
          clearPiWorkingIndicator,
          createPiThemeStyle,
          renderPiPanel,
          renderPiWidgetRow,
          setPiStatus,
          startPiWorkingIndicator,
        }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth }} from "@earendil-works/pi-tui";
        import {{ stripVTControlCharacters }} from "node:util";

        const taggedStyle = {{ accent: (t) => `<a>${{t}}</a>`, dim: (t) => `<d>${{t}}</d>`, border: (t) => `<b>${{t}}</b>` }};
        const simpleFit = (text, width, _ellipsis = "...", pad = false) => {{
          const plain = text.replace(/<[^>]+>/g, "");
          const clipped = plain.length > width ? plain.slice(0, width) : text;
          return pad ? clipped + " ".repeat(Math.max(0, width - clipped.replace(/<[^>]+>/g, "").length)) : clipped;
        }};

        const plainStyle = {{ accent: (t) => t, dim: (t) => t, border: (t) => t }};
        const command = "⠴ reviewer · bash: cd /Users/FradSer/Developer/FradSer/pi-packages && python3 -m pytest packages/agent-teams/tests/";
        const truncatedWidget = renderPiWidgetRow(command, 60, truncateToWidth);
        const truncatedPanel = renderPiPanel({{ width: 20, style: plainStyle, fit: truncateToWidth, title: "Context", body: ["x".repeat(60)], footer: "esc close" }});

        const mapped = createPiThemeStyle({{ fg: (color, text) => `[${{color}}]${{text}}` }});
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

        console.log(JSON.stringify({{
          panel: renderPiPanel({{ width: 20, style: taggedStyle, fit: simpleFit, title: "Context", body: ["first", "second"], footer: "esc close" }}),
          widget: renderPiWidgetRow("Working...", 12, simpleFit),
          flushLeft: renderPiWidgetRow("Working...", 12, simpleFit, 0),
          truncatedWidget: stripVTControlCharacters(truncatedWidget),
          truncatedWidgetWidth: visibleWidth(truncatedWidget),
          truncatedPanelBody: stripVTControlCharacters(truncatedPanel[2]),
          truncatedPanelWidth: visibleWidth(truncatedPanel[2]),
          styleMap: {{
            accent: mapped.accent("a"),
            muted: mapped.muted("m"),
            dim: mapped.dim("d"),
            border: mapped.border("b"),
            success: mapped.success("s"),
            error: mapped.error("e"),
            fg: mapped.fg("warning", "w"),
          }},
          statuses,
          indicators,
        }}));
        """
    )
    assert len(result["panel"]) == 6
    assert "Context" in result["panel"][1] and "esc close" in result["panel"][-2]
    assert result["widget"] == " Working... "
    assert result["flushLeft"] == "Working...  "
    assert result["truncatedWidget"].rstrip().endswith("...") and result["truncatedWidgetWidth"] == 60
    assert result["truncatedPanelBody"].rstrip().endswith("...") and result["truncatedPanelWidth"] == 20
    assert result["styleMap"] == {
        "accent": "[accent]a",
        "muted": "[muted]m",
        "dim": "[dim]d",
        "border": "[border]b",
        "success": "[success]s",
        "error": "[error]e",
        "fg": "[warning]w",
    }
    assert result["statuses"] == [["vision", "reading image"], ["vision", None]]
    assert result["indicators"] == [
        {"frames": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"], "intervalMs": 120},
        None,
    ]


# ── One-shot Pi worker process mechanics & progress classification ──


def test_run_pi_worker_minimal_mode_cwd_and_parse_contracts(tmp_path: Path) -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const capture = path.join(root, "args.json");
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        fs.writeFileSync(
          fakePi,
          "#!/usr/bin/env node\\nimport * as fs from 'node:fs';\\n" +
            "fs.writeFileSync(process.env.PI_CAPTURE, JSON.stringify(process.argv.slice(2)));\\n" +
            "console.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'ok' }}], usage: {{ input: 4, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 9, cost: {{ total: 0.02 }} }} }} }}));\\n" +
            "console.error('worker note');\\n",
          {{ mode: 0o755 }},
        );
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ minimalPiWorkerArgs, parsePiWorkerOutput, runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const cases = [
          {{ name: "minimal-default", minimal: true }},
          {{ name: "minimal-explicit", minimal: true, tools: ["read", "bash"] }},
          {{ name: "minimal-empty-list", minimal: true, tools: [] }},
          {{ name: "minimal-empty-string", minimal: true, tools: "" }},
          {{ name: "full-default", minimal: false }},
          {{ name: "full-empty-list", minimal: false, tools: [] }},
          {{ name: "full-empty-string", minimal: false, tools: "" }},
        ];
        const launches = [];
        let sampleWorker;
        try {{
          for (const {{ name, ...options }} of cases) {{
            const worker = await runPiWorker({{ prompt: "inspect", cwd, env: {{ PI_CAPTURE: capture }}, ...options }});
            if (!sampleWorker) sampleWorker = worker;
            launches.push({{ name, args: JSON.parse(fs.readFileSync(capture, "utf8")), text: worker.text, exitCode: worker.exitCode }});
          }}
        }} finally {{
          process.argv[1] = originalArgv1;
        }}
        const parsedStream = parsePiWorkerOutput([
          JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "first" }}], usage: {{ input: 1, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 3, cost: {{ total: 0.01 }} }} }} }}),
          "not-json",
          JSON.stringify({{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "live" }} }}),
          JSON.stringify({{ type: "message_end", message: {{ role: "user", content: [{{ type: "text", text: "ignore me" }}] }} }}),
          JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "final" }}], usage: {{ input: 10, output: 20, cacheRead: 1, cacheWrite: 2, totalTokens: 33, cost: {{ total: 0.05 }} }} }} }}),
        ].join("\\n"));
        console.log(JSON.stringify({{
          launches,
          sampleWorker,
          parsedStream,
          sharedArgs: {{
            defaults: minimalPiWorkerArgs(),
            empty: minimalPiWorkerArgs([]),
            explicit: minimalPiWorkerArgs(["read", "bash"]),
          }},
        }}));
        """
    )
    expected = {
        "minimal-default": "read,bash,grep,find",
        "minimal-explicit": "read,bash",
        "minimal-empty-list": "",
        "minimal-empty-string": "read,bash,grep,find",
        "full-default": None,
        "full-empty-list": "",
        "full-empty-string": None,
    }
    for launch in result["launches"]:
        args = launch["args"]
        assert launch["text"] == "ok" and launch["exitCode"] == 0, launch
        assert "--no-session" in args and "--cwd" not in args
        tools = args[args.index("--tools") + 1] if "--tools" in args else None
        assert tools == expected[launch["name"]], launch
        if launch["name"].startswith("minimal-"):
            assert all(flag in args for flag in ("-ne", "-ns", "-np", "-nc", "--no-themes")), launch
    for name, tools in (("defaults", "read,bash,grep,find"), ("empty", ""), ("explicit", "read,bash")):
        args = result["sharedArgs"][name]
        assert args[args.index("--tools") + 1] == tools
        assert all(flag in args for flag in ("-ne", "-ns", "-np", "-nc", "--no-themes"))
    assert result["sampleWorker"]["usage"] == {"input": 4, "output": 5, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 9, "cost": 0.02}
    assert "worker note" in result["sampleWorker"]["stderr"]
    assert result["parsedStream"] == {
        "text": "final",
        "usage": {"input": 10, "output": 20, "cacheRead": 1, "cacheWrite": 2, "totalTokens": 33, "cost": 0.05},
    }


def test_run_pi_worker_cancellation_failure_and_stream_byte_limits(tmp_path: Path) -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(cwd);
        const fakePackage = path.join(root, "fake-package");
        fs.mkdirSync(fakePackage);
        fs.writeFileSync(path.join(fakePackage, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(fakePackage, "cli.mjs");
        const marker = path.join(root, "spawned");
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{
          PI_WORKER_JSONL_LINE_LIMIT_BYTES,
          PI_WORKER_STDERR_LIMIT_BYTES,
          runPiWorker,
          spawnPiChild,
          terminateChildProcess,
        }} = await import({json.dumps((SRC / "index.ts").as_uri())});

        try {{
          // 1. Pre-cancelled worker never spawns
          fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nimport {{ writeFileSync }} from 'node:fs';\\nwriteFileSync(process.env.PI_MARKER, 'spawned');\\n", {{ mode: 0o755 }});
          const preController = new AbortController();
          preController.abort();
          const preCancelled = await runPiWorker({{ prompt: "inspect", cwd, env: {{ PI_MARKER: marker }}, signal: preController.signal }});
          const preSpawned = fs.existsSync(marker);

          // 2. In-flight abort terminates child
          fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nconsole.log(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: 'partial' }}] }} }}));\\nsetInterval(() => {{}}, 1000);\\n", {{ mode: 0o755 }});
          const liveController = new AbortController();
          const started = Date.now();
          const pending = runPiWorker({{ prompt: "inspect", cwd, signal: liveController.signal }});
          setTimeout(() => liveController.abort(), 150);
          const aborted = await pending;
          const abortElapsedMs = Date.now() - started;

          // 3. Process failure surfaces diagnostics without partial text
          fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nconsole.error('boom: model unavailable');\\nprocess.exit(1);\\n", {{ mode: 0o755 }});
          const failed = await runPiWorker({{ prompt: "inspect", cwd }});

          // 4. Oversized JSONL line
          fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nprocess.stdout.write('é'.repeat(Number(process.env.PI_LINE_LIMIT) + 1) + '\\\\n');\\n", {{ mode: 0o755 }});
          const oversizedLine = await runPiWorker({{
            prompt: "inspect",
            cwd,
            env: {{ PI_LINE_LIMIT: String(Math.ceil(PI_WORKER_JSONL_LINE_LIMIT_BYTES / 2)) }},
          }});

          // 5. Oversized stderr
          fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nprocess.stderr.write('child-diagnostic-noise'.repeat(400));\\nsetTimeout(() => process.stderr.write('x'.repeat(Number(process.env.PI_STDERR_LIMIT) + 1)), 40);\\n", {{ mode: 0o755 }});
          const oversizedStderr = await runPiWorker({{
            prompt: "inspect",
            cwd,
            env: {{ PI_STDERR_LIMIT: String(PI_WORKER_STDERR_LIMIT_BYTES) }},
          }});

          // 6. Escalation on SIGTERM ignore
          const stubborn = spawnPiChild(process.execPath, ["--eval", "process.on('SIGTERM', () => {{}}); setInterval(() => {{}}, 1000);"], {{ stdio: "ignore" }});
          let closed = false;
          stubborn.once("close", () => {{ closed = true; }});
          const terminated = await terminateChildProcess(stubborn, 25);

          console.log(JSON.stringify({{
            preSpawned, preCancelled, aborted, abortElapsedMs, failed, oversizedLine, oversizedStderr, terminated, closed,
          }}));
        }} finally {{
          process.argv[1] = originalArgv1;
        }}
        """
    )
    assert result["preSpawned"] is False
    assert result["preCancelled"]["text"] == "" and result["preCancelled"]["exitCode"] != 0 and result["preCancelled"]["cancelled"] is True
    assert result["aborted"]["text"] == "" and result["aborted"]["exitCode"] != 0 and result["aborted"]["cancelled"] is True
    assert result["abortElapsedMs"] < 14000
    assert result["failed"]["text"] == "" and result["failed"]["exitCode"] == 1 and "boom: model unavailable" in result["failed"]["stderr"]
    assert result["oversizedLine"]["text"] == "" and result["oversizedLine"]["exitCode"] != 0 and "exceeded" in result["oversizedLine"]["stderr"].lower()
    assert result["oversizedStderr"]["text"] == "" and result["oversizedStderr"]["exitCode"] != 0
    assert result["oversizedStderr"]["stderr"].startswith("Pi worker stderr exceeded") and "child-diagnostic-noise" in result["oversizedStderr"]["stderr"]
    assert result["terminated"] is True and result["closed"] is True


def test_pi_worker_progress_and_tool_activity_classification(tmp_path: Path) -> None:
    command = 'for p in \\\n  "https://cloud.google.com/billing/docs/reference/rest/v1/billingAccounts" \\\n  "https://cloud.google.com/billing/docs/how-to/reports"; do echo "$p"; done'
    query = "how does the billing accounts reports REST resource map to the console report pages"
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const packageDir = path.join(root, "node_modules", "@earendil-works", "pi-coding-agent");
        fs.mkdirSync(packageDir, {{ recursive: true }});
        fs.writeFileSync(path.join(packageDir, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const fakePi = path.join(packageDir, "cli.mjs");
        const command = {json.dumps(command)};
        const query = {json.dumps(query)};
        const streamEvents = [
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "first" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "first" }}] }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "second" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "second" }}] }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "thinking_delta", delta: "older reasoning" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "newer answer" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_start" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_delta", delta: JSON.stringify({{ command: "bun test" }}) }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "toolcall_end", toolCall: {{ name: "bash" }} }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "pre-tool answer" }}] }} }},
          {{ type: "tool_execution_start", toolCallId: "call-1", toolName: "bash", args: {{ command: "bun run check" }} }},
          {{ type: "tool_execution_end", toolCallId: "call-1", toolName: "bash" }},
          {{ type: "tool_execution_start", toolCallId: "call-long", toolName: "bash", args: {{ command }} }},
          {{ type: "tool_execution_end", toolCallId: "call-long", toolName: "bash" }},
          {{ type: "tool_execution_start", toolCallId: "call-2", toolName: "context_get", args: {{ query }} }},
          {{ type: "tool_execution_start", toolCallId: "call-3", toolName: "grep", args: {{ pattern: "MINIMAL_PI_WORKER_TOOLS", path: "/repo/packages/context" }} }},
          {{ type: "tool_execution_start", toolCallId: "call-4", toolName: "find", args: {{ pattern: "**/*.feature", path: "/repo/packages" }} }},
          {{ type: "message_update", assistantMessageEvent: {{ type: "text_delta", delta: "final answer" }} }},
          {{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "final answer" }}] }} }},
        ];
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\n" + `const events = ${{JSON.stringify(streamEvents)}};\\nfor (const event of events) {{ console.log(JSON.stringify(event)); await new Promise((resolve) => setTimeout(resolve, 20)); }}\\n`, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = fakePi;
        const {{ classifyToolActivity, inlineToolActivity, runPiWorker }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const activities = [];
        try {{
          await runPiWorker({{ prompt: "inspect", cwd: root, onUpdate: (update) => activities.push(update.activity) }});
        }} finally {{
          process.argv[1] = originalArgv1;
        }}
        const classify = (args) => classifyToolActivity(args) ?? null;
        console.log(JSON.stringify({{
          activities,
          classified: {{
            grep: classify({{ pattern: "MINIMAL_PI_WORKER_TOOLS", path: "/repo/packages/context" }}),
            find: classify({{ pattern: "**/*.feature", path: "/repo/packages" }}),
            command: classify({{ command: "  bun   test  ", pattern: "ignored" }}),
            read: classify({{ path: "  /repo/packages/context/index.ts  " }}),
            query: classify({{ query: "context worker" }}),
            subject: classify({{ subject: "Ship it" }}),
            emptySubject: classify({{ to: "@reviewer", subject: "" }}),
            bare: classify({{}}),
            partial: classify('{{"pattern": "unfin'),
            array: classify("[1]"),
            nonObject: classify(undefined),
            inline: inlineToolActivity("a\\n  b"),
            inlineEmpty: inlineToolActivity("\\n  "),
          }},
        }}));
        """
    )
    activities = result["activities"]
    assert "first" in activities and "second" in activities and "firstsecond" not in activities
    assert "older reasoning" in activities and "newer answer" in activities
    assert "bash: bun test" in activities and "bash: bun run check" in activities
    assert f"bash: {' '.join(command.split())}" in activities
    assert f"search: {query}" in activities
    assert "search: MINIMAL_PI_WORKER_TOOLS" in activities
    assert "search: **/*.feature" in activities
    assert not any(a.startswith("file: ") for a in activities)
    assert all(not a.endswith(" ...") and len(a.splitlines()) == 1 for a in activities)
    assert activities[-1] == "final answer"
    assert all(a not in ("pre-tool answerfinal answer", "older reasoningfinal answer") for a in activities)

    c = result["classified"]
    assert c["grep"] == {"kind": "search", "value": "MINIMAL_PI_WORKER_TOOLS"}
    assert c["find"] == {"kind": "search", "value": "**/*.feature"}
    assert c["command"] == {"kind": "command", "value": "bun   test"}
    assert c["read"] == {"kind": "file", "value": "/repo/packages/context/index.ts"}
    assert c["query"] == {"kind": "search", "value": "context worker"}
    assert c["subject"] == {"kind": "message", "value": "Ship it"}
    assert c["emptySubject"] == {"kind": "target", "value": ""}
    assert all(c[k] is None for k in ("bare", "partial", "array", "nonObject"))
    assert c["inline"] == "a b" and c["inlineEmpty"] == ""


# ── Lifecycle bands, meaningful expansion, message rows, and mouse wrapper ──


def test_lifecycle_titles_bands_authored_blocks_and_detail_bounds() -> None:
    feature = (PACKAGE / "features" / "pi-kit.feature").read_text(encoding="utf-8")
    assert "it reveals every detail line by default" in feature
    assert "announces every line the limit dropped" in feature

    result = run_typescript(
        f"""
        import {{
          bindLifecycleRenderers,
          contentDetailLines,
          createStaticToolLifecycleMessageRenderer,
          createStaticToolLifecycleResultRenderer,
          createToolLifecycleMessageRenderer,
          createToolLifecycleResultRenderer,
          eventToolLifecycle,
          formatToolLifecycleDetails,
          formatToolLifecycleTitle,
          notifyPi,
          renderAgentMessageBand,
          renderToolLifecycle,
          startedToolLifecycle,
          agentColor,
        }} from {json.dumps((SRC / "index.ts").as_uri())};
        import {{ truncateToWidth, visibleWidth, wrapTextWithAnsi }} from "@earendil-works/pi-tui";
        import {{ stripVTControlCharacters }} from "node:util";

        const plainTheme = {{ fg: (_c, t) => t, bg: (_c, t) => `<BG>${{t}}</BG>`, bold: (t) => t }};
        const simpleFit = (text, width, ellipsis = "...", pad = false) => {{
          const s = text.length > width ? `${{text.slice(0, Math.max(0, width - ellipsis.length))}}${{ellipsis.slice(0, width)}}` : text;
          return pad ? s.padEnd(width) : s;
        }};
        const stripBg = (line) => line.replace(/<[^>]+>/g, "");
        const baseRender = (spec, options = {{}}) => renderToolLifecycle(spec, {{
          width: 80, theme: plainTheme, fit: simpleFit, visibleWidth, ...options,
        }});

        const startedRows = baseRender(startedToolLifecycle("agent", "@audit started · review"));
        const eventRows = baseRender(eventToolLifecycle("tasks", "Fix login", {{ details: ["status=success"] }}), {{ expanded: true }});
        const hintedRows = baseRender(eventToolLifecycle("tasks", "Fix login", {{ details: ["status=success"] }}), {{ expandHint: "ctrl+o to expand" }});

        // Authored verbatim + block subject
        const bgTokens = [];
        const tokenTheme = {{ fg: (_c, t) => t, bg: (tok, t) => {{ bgTokens.push(tok); return t; }}, bold: (t) => t }};
        const authoredRender = (spec, options = {{}}) => {{
          bgTokens.length = 0;
          const rows = renderToolLifecycle(spec, {{
            width: 40, theme: tokenTheme, fit: simpleFit, visibleWidth,
            wrapDetail: (line, w) => wrapTextWithAnsi(line, Math.max(1, w)),
            expandHint: "ctrl+o to expand", ...options,
          }});
          return {{ rows: rows.slice(1, -1), tokens: [...new Set(bgTokens)] }};
        }};
        const authored = startedToolLifecycle("impeccable", "audit src/Page.tsx spacing and padding\\nsecond authored line", {{
          label: "started", verbatimSubject: true, bgToken: "userMessageBg",
        }});
        const authoredWithDetails = eventToolLifecycle("tool", "first line\\nsecond line", {{
          label: "started", verbatimSubject: true, bgToken: "userMessageBg", details: ["hidden detail"],
        }});
        const blockFlags = {{ label: "started", verbatimSubject: true, bgToken: "userMessageBg", subjectBlock: true }};
        const blockSpec = startedToolLifecycle("impeccable", "aaaa\\nzzzz", blockFlags);
        const emptyBlock = startedToolLifecycle("matt pocock", "", blockFlags);

        // Band colors, partial, error non-duplication, class receiver, SGR reset reapplication
        const taggedTheme = {{
          fg: (c, t) => `<${{c}}>${{t}}</${{c}}>`,
          bg: (c, t) => `[${{c}}]${{t}}[/${{c}}]`,
          bold: (t) => t,
        }};
        const successBand = renderToolLifecycle(eventToolLifecycle("work", "create task", {{ label: "created" }}), {{ width: 80, theme: taggedTheme, fit: (t) => t, visibleWidth, isError: false }});
        const errorBand = renderToolLifecycle(eventToolLifecycle("work", "work failed", {{ label: "failed", details: ["syntax error at line 10"] }}), {{ width: 80, expanded: true, theme: taggedTheme, fit: (t) => t, visibleWidth, isError: true }});
        const pendingBand = renderToolLifecycle(eventToolLifecycle("context", "deep research", {{ label: "researching" }}), {{ width: 80, theme: taggedTheme, fit: (t) => t, visibleWidth, isPending: true }});

        const staticResult = createStaticToolLifecycleResultRenderer({{
          createSpec: () => startedToolLifecycle("monitor", "long build", {{ label: "running" }}),
          fit: (t) => t, visibleWidth: (t) => t.length,
        }});
        const partialRender = staticResult({{ content: [{{ type: "text", text: "Working..." }}] }}, {{ expanded: false, isPartial: true }}, taggedTheme, {{ isError: false }}).render(80);
        const settledRender = staticResult({{ content: [{{ type: "text", text: "Done" }}] }}, {{ expanded: false, isPartial: false }}, taggedTheme, {{ isError: false }}).render(80);
        const dedupErrorRows = staticResult(
          {{ content: [{{ type: "text", text: "Isolated Pi research failed (exit 2)\\nstderr tail line" }}] }},
          {{ expanded: true, isPartial: false }}, {{ fg: (_c, t) => t, bg: (_c, t) => t, bold: (t) => t }}, {{ isError: true }},
        ).render(120);

        class ClassTheme {{
          constructor() {{ this.bgColors = new Map([["toolSuccessBg", "\\u001B[44m"]]); }}
          fg(_c, t) {{ return t; }}
          bold(t) {{ return t; }}
          bg(c, t) {{ return this.bgColors.get(c) + t + "\\u001B[49m"; }}
        }}
        const classRows = renderToolLifecycle(startedToolLifecycle("agent", "@audit", {{ label: "started" }}), {{ width: 80, theme: new ClassTheme(), fit: truncateToWidth, visibleWidth }});

        const sgrTheme = {{ fg: (c, t) => `<${{c}}>${{t}}</${{c}}>`, bg: (_c, t) => `<B>${{t}}\\u001b[49m`, bold: (t) => t }};
        const truncatedRow = renderToolLifecycle(
          startedToolLifecycle("agent", "@greeter-alpha · Start the greeting task now: introduce yourself to @greeter-beta and @greeter-gamma and wait for their replies"),
          {{ width: 40, theme: sgrTheme, fit: truncateToWidth, visibleWidth }},
        )[1];

        // Detail bounds
        const fiftyOne = Array.from({{ length: 51 }}, (_, i) => `line-${{i}}`);
        const detailBounds = {{
          completeCount: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: fiftyOne }})).length,
          completeLast: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: fiftyOne }})).at(-1),
          bounded: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: fiftyOne, detailLimit: 4 }})),
          singleLast: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: fiftyOne, detailLimit: 50 }})).at(-1),
          suppressed: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: fiftyOne, detailLimit: 0 }})).length,
          blankHead: formatToolLifecycleDetails(eventToolLifecycle("message", "report", {{ details: [" ", "real"], detailLimit: 1 }})),
        }};

        // Message & tool renderers + notifyPi + mouse wrapper + incoming message band
        const notices = [];
        notifyPi({{ notify: (message, level) => notices.push({{ message, level }}) }}, "\\u001b[31mDone\\u001b[0m", "info");
        const msgRenderer = createToolLifecycleMessageRenderer({{
          createSpec: (m) => eventToolLifecycle("context", m.content, {{ label: "gathered", details: String(m.details ?? "").split("\\n").filter(Boolean) }}),
          expandHint: "ctrl+o to expand", fit: simpleFit, visibleWidth: (t) => t.length,
        }});
        const toolRenderer = createToolLifecycleResultRenderer({{
          createSpec: (_r, text, details) => eventToolLifecycle("context", text.split("\\n")[0], {{ label: "gathered", details }}),
          expandHint: "ctrl+o to expand", fit: simpleFit, visibleWidth: (t) => t.length,
        }});
        const neutralTheme = {{ fg: (_c, t) => t, bg: (_c, t) => t, bold: (t) => t }};

        const msgBandRender = (direction) => renderAgentMessageBand([{{ direction, teammate: "continual-audit-close" }}], {{
          theme: neutralTheme, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: "ctrl+shift+e to expand",
        }});
        const msgBandMulti = renderAgentMessageBand(
          [{{ direction: "from", teammate: "calc-alpha" }}, {{ direction: "from", teammate: "scribe", count: 2 }}],
          {{ theme: {{ fg: (c, t) => `<${{c}}>${{t}}</${{c}}>`, bg: (_c, t) => t, bold: (t) => t }}, fit: (t, w, _e = "", p = false) => p ? t.padEnd(w) : t }},
        );

        class FakeHostComponent {{
          constructor(_tn, _id, _args, _opts, toolDefinition) {{
            this.toolDefinition = toolDefinition;
            this.expanded = false;
          }}
          updateResult(res) {{ this.result = res; }}
          setExpanded(exp) {{ this.expanded = exp; }}
          render(w) {{
            const lines = this.toolDefinition.renderResult(this.result, {{ expanded: this.expanded }}, taggedTheme).render(w);
            return lines.length > 0 ? ["", ...lines] : [];
          }}
          handleMouse(event) {{
            if (event.y <= 0) return undefined;
            if (event.type === "click" && event.button === "left") {{
              this.setExpanded(!this.expanded);
              return {{ handled: true, target: this, y: event.y }};
            }}
            return undefined;
          }}
        }}
        const mouseComp = createStaticToolLifecycleMessageRenderer({{
          createSpec: (msg) => eventToolLifecycle("message", msg.content, {{ label: "event", details: ["detail line"] }}),
          fit: (t) => t, visibleWidth: (t) => t.length, expandHint: "ctrl+o to expand", hostComponent: FakeHostComponent,
        }})({{ content: "from @audit" }}, {{ expanded: false }}, taggedTheme);
        const mouseCollapsed = mouseComp.render(60);
        const click1 = mouseComp.handleMouse({{ type: "click", button: "left", y: 0, x: 5 }});
        const mouseExpanded = mouseComp.render(60);
        const click2 = mouseComp.handleMouse({{ type: "click", button: "left", y: 0, x: 5 }});
        const mouseReCollapsed = mouseComp.render(60);

        // Bound research rows
        const bound = bindLifecycleRenderers({{ fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: "ctrl+o to expand" }});
        const answer = Array.from({{ length: 61 }}, (_, i) => `research finding ${{i}}`);
        const rawRes = {{ content: [{{ type: "text", text: answer.join("\\n") }}], details: {{ operation: "context-review" }} }};
        const boundRenderer = bound.result(() => eventToolLifecycle("context", "Research the lifecycle renderer", {{ label: "researched", details: contentDetailLines(rawRes) }}));

        console.log(JSON.stringify({{
          titles: {{
            started: formatToolLifecycleTitle(startedToolLifecycle("monitor", "运行 monitor 包测试")),
            event: formatToolLifecycleTitle(eventToolLifecycle("monitor", "运行 monitor 包测试")),
            listed: formatToolLifecycleTitle(eventToolLifecycle("sessions", "2 other sessions in pi-packages", {{ label: "listed" }})),
            agentEvent: formatToolLifecycleTitle(eventToolLifecycle("agent", "@scribe shut down")),
            created: formatToolLifecycleTitle(eventToolLifecycle("tasks", "Fix the login flow", {{ label: "created" }})),
            gathered: formatToolLifecycleTitle(eventToolLifecycle("context", "3 requests since last commit", {{ label: "gathered" }})),
          }},
          startedBandIsFullWidth: startedRows.length === 3 && startedRows.every((r) => stripBg(r).length === 80),
          startedBandHasBlankEdges: stripBg(startedRows[0]).trim() === "" && stripBg(startedRows[2]).trim() === "",
          startedContent: stripBg(startedRows[1]).trim(),
          expandedContent: eventRows.slice(1, -1).map((r) => stripBg(r).trim()),
          collapsedHint: stripBg(hintedRows[1]).trim(),
          zeroWidth: baseRender(startedToolLifecycle("agent", "@audit"), {{ width: 0 }}),
          authored: authoredRender(authored),
          authoredExpanded: authoredRender(authored, {{ expanded: true }}).rows,
          authoredDetails: authoredRender(authoredWithDetails),
          authoredDetailsExpanded: authoredRender(authoredWithDetails, {{ expanded: true }}).rows,
          blockRows: authoredRender(blockSpec).rows.map((r) => r.trim()),
          emptyBlockRows: authoredRender(emptyBlock).rows.map((r) => r.trim()),
          bands: {{
            pending: pendingBand[1].includes("[toolPendingBg]") && pendingBand[1].includes("<warning>[context] researching ·</warning>"),
            success: successBand[1].includes("[toolSuccessBg]") && successBand[1].includes("<success>[work] created ·</success>"),
            error: errorBand[1].includes("[toolErrorBg]") && errorBand[1].includes("<error>[work] failed ·</error>") && errorBand.some((r) => r.includes("syntax error at line 10")),
            partialPending: partialRender[1].includes("[toolPendingBg]") && !partialRender[1].includes("toolSuccessBg"),
            settledSuccess: settledRender[1].includes("[toolSuccessBg]"),
            dedupErrorOccurrences: dedupErrorRows.filter((r) => r.includes("Isolated Pi research failed (exit 2)")).length,
            dedupHasStderr: dedupErrorRows.some((r) => r.includes("stderr tail line")),
            classReceiverPainted: classRows.some((r) => r.includes("\\u001B[44m")) && classRows.length === 3,
            sgrResetOk: truncatedRow.includes("...") && truncatedRow.split("\\x1b[0m").slice(1).every((p) => p.startsWith("<B>")),
          }},
          detailBounds,
          notices,
          messageRow: msgRenderer({{ content: "two sources", details: "one\\ntwo" }}, {{ expanded: false }}, neutralTheme).render(70)[1],
          toolSuccessRows: toolRenderer({{ content: [{{ type: "text", text: "summary\\nline" }}] }}, {{ expanded: true }}, neutralTheme, {{}}).render(70),
          toolErrorRows: toolRenderer({{ content: [{{ type: "text", text: "\\u001b[31mfailed\\u001b[0m\\nmore" }}] }}, {{ expanded: true }}, neutralTheme, {{ isError: true }}).render(70),
          msgBandHints: ["from", "to"].every((d) => [48, 90, 240].every((w) => msgBandRender(d).render(w).slice(1, -1)[0].trimEnd().endsWith(" · ctrl+shift+e to expand"))),
          msgBandFits: [1, 2, 8, 48, 90, 240].every((w) => msgBandRender("from").render(w).every((l) => visibleWidth(l) <= w)),
          msgBandColor: agentColor("calc-alpha"),
          msgBandMulti: msgBandMulti.render(60),
          mouse: {{
            collapsedCount: mouseCollapsed.length,
            collapsedLine: mouseCollapsed[1],
            click1: click1?.handled,
            expandedJoined: mouseExpanded.join(" "),
            click2: click2?.handled,
            reCollapsedLine: mouseReCollapsed[1],
          }},
          boundCollapsed: boundRenderer(rawRes, {{ expanded: false }}, neutralTheme, {{}}).render(90).slice(1, -1).map((l) => stripVTControlCharacters(l).trim()),
          boundExpanded: boundRenderer(rawRes, {{ expanded: true }}, neutralTheme, {{}}).render(90).slice(1, -1).map((l) => stripVTControlCharacters(l).trim()),
          answer,
        }}));
        """
    )
    assert result["titles"] == {
        "started": "[monitor] 运行 monitor 包测试",
        "event": "[monitor] 运行 monitor 包测试",
        "listed": "[sessions] listed · 2 other sessions in pi-packages",
        "agentEvent": "[agent] @scribe shut down",
        "created": "[tasks] created · Fix the login flow",
        "gathered": "[context] gathered · 3 requests since last commit",
    }
    assert result["startedBandIsFullWidth"] and result["startedBandHasBlankEdges"]
    assert result["startedContent"] == "[agent] @audit started · review"
    assert result["expandedContent"] == ["[tasks] Fix login", "status=success"]
    assert result["collapsedHint"] == "[tasks] Fix login · ctrl+o to expand"
    assert result["zeroWidth"] == []

    authored_rows = [r.strip() for r in result["authored"]["rows"]]
    assert authored_rows[0].startswith("[impeccable] started · audit") and authored_rows[-1] == "second authored line"
    assert result["authored"]["tokens"] == ["userMessageBg"]
    assert result["authoredExpanded"] == result["authored"]["rows"]
    detail_rows = [r.strip() for r in result["authoredDetails"]["rows"]]
    assert detail_rows[:2] == ["[tool] started · first line", "second line"]
    assert any("to expand" in r for r in detail_rows) and "hidden detail" not in "\n".join(detail_rows)
    assert [r.strip() for r in result["authoredDetailsExpanded"]][-1] == "hidden detail"
    assert result["blockRows"] == ["[impeccable] started", "", "aaaa", "zzzz"]
    assert result["emptyBlockRows"] == ["[matt pocock] started"]

    assert all(
        result["bands"][k]
        for k in ("pending", "success", "error", "partialPending", "settledSuccess", "dedupHasStderr", "classReceiverPainted", "sgrResetOk")
    )
    assert result["bands"]["dedupErrorOccurrences"] == 1

    db = result["detailBounds"]
    assert db["completeCount"] == 51 and db["completeLast"] == "line-50"
    assert len(db["bounded"]) == 5 and db["bounded"][-1] == "… 47 more detail lines"
    assert db["singleLast"] == "… 1 more detail line" and db["suppressed"] == 0
    assert db["blankHead"] == [" ", "… 1 more detail line"]

    assert result["notices"] == [{"message": "Done", "level": "info"}]
    assert "[context] gathered · two sources · ctrl+o to expand" in result["messageRow"]
    assert "[context] gathered · summary" in result["toolSuccessRows"][1] and "line" in result["toolSuccessRows"][3]
    assert "[context] failed · failed" in result["toolErrorRows"][1] and "more" in result["toolErrorRows"][2]
    assert result["msgBandHints"] is True and result["msgBandFits"] is True
    assert result["msgBandColor"] in ("accent", "borderAccent", "mdHeading", "mdLink")
    assert len(result["msgBandMulti"]) == 4
    assert "<customMessageLabel>[message] from </customMessageLabel>" in result["msgBandMulti"][1]
    assert "<customMessageLabel>[2 messages] from </customMessageLabel>" in result["msgBandMulti"][2]

    m = result["mouse"]
    assert m["collapsedCount"] == 3 and "ctrl+o to expand" in m["collapsedLine"]
    assert m["click1"] is True and "detail line" in m["expandedJoined"]
    assert m["click2"] is True and "ctrl+o to expand" in m["reCollapsedLine"]

    assert result["boundCollapsed"] == ["[context] researched · Research the lifecycle renderer · ctrl+o to expand"]
    assert result["boundExpanded"] == ["[context] researched · Research the lifecycle renderer", *result["answer"]]


@pytest.fixture(scope="module")
def expansion_cases() -> dict[str, object]:
    return run_typescript(
        r"""
        import {
          bindLifecycleRenderers, createToolLifecycleResultRenderer, createStaticToolLifecycleResultRenderer,
          createToolLifecycleMessageRenderer, createStaticToolLifecycleMessageRenderer,
          eventToolLifecycle, renderToolLifecycle,
        } from './packages/kit/src/index.ts';
        import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from '@earendil-works/pi-tui';
        import { stripVTControlCharacters } from 'node:util';
        const theme = { fg: (_, text) => text, bg: (_, text) => text, bold: text => text };
        const geometry = { fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: 'ctrl+o to expand' };
        const raw = { content: 'MODEL-ONLY-BODY', details: { internal: 'state', action: 'complete' } };
        const builders = {
          result: createToolLifecycleResultRenderer,
          staticResult: createStaticToolLifecycleResultRenderer,
          message: createToolLifecycleMessageRenderer,
          staticMessage: createStaticToolLifecycleMessageRenderer,
          boundResult: options => bindLifecycleRenderers(options).result(options.createSpec),
          boundMessage: options => bindLifecycleRenderers(options).message(options.createSpec),
        };
        const specs = {
          empty: eventToolLifecycle('probe', 'done'),
          whitespace: eventToolLifecycle('probe', 'done', { details: [' ', '\t', '\x1b[31m\x1b[0m', '\n'] }),
          body: eventToolLifecycle('probe', 'done', { details: ['first', '', 'second', 'first'] }),
          long: eventToolLifecycle('probe', '检查 café evidence '.repeat(9).trim()),
          multiline: eventToolLifecycle('probe', 'first\n\nsecond'),
          carriage: eventToolLifecycle('probe', 'first\rsecond', { summary: ['Answer: one\rtwo'] }),
          trailing: eventToolLifecycle('probe', 'done' + ' '.repeat(100), { summary: ['Answer: yes' + ' '.repeat(100)] }),
          trailingPreview: eventToolLifecycle('probe', 'done', { expandedSubject: 'done   ' }),
          trailingBreak: eventToolLifecycle('probe', 'done\r\n\r\n', { summary: ['Answer: yes\r\n\r\n'] }),
          summary: eventToolLifecycle('probe', 'decision', { summary: ['Answer: ' + '检查 café '.repeat(12).trim(), 'line one\n\nline two'] }),
          shortSummary: eventToolLifecycle('probe', 'decision', { summary: ['Answer: yes'] }),
          blankSummary: eventToolLifecycle('probe', 'done', { summary: [' \n ', '\t'] }),
          explicit: eventToolLifecycle('probe', 'preview', { expandedSubject: 'full\n\n' + 'evidence '.repeat(35).trim() }),
          limited: eventToolLifecycle('probe', 'done', { details: ['hidden'], detailLimit: 0 }),
          readback: eventToolLifecycle('probe', 'report', { details: Array.from({ length: 65 }, (_, i) => `finding ${i}`) }),
        };
        const rows = {};
        for (const [name, build] of Object.entries(builders)) {
          rows[name] = {};
          for (const [key, spec] of Object.entries(specs)) {
            const render = build({ ...geometry, createSpec: () => spec });
            const output = {};
            for (const width of [1, 2, 8, 48, 90, 240]) {
              output[width] = {};
              for (const expanded of [false, true]) {
                const rendered = render(raw, { expanded }, theme, {}).render(width);
                output[width][expanded ? 'expanded' : 'collapsed'] = rendered.slice(1, -1)
                  .map(line => stripVTControlCharacters(line).slice(width > 2 ? 1 : 0).trimEnd());
                output[width][expanded ? 'expandedBounded' : 'collapsedBounded'] = rendered.every(line => visibleWidth(line) <= width && !/[\r\n]/.test(line));
              }
            }
            const withoutMetadata = render({ content: '' }, { expanded: false }, theme, {}).render(90);
            rows[name][key] = { widths: output, withoutMetadata: withoutMetadata.slice(1, -1).map(line => stripVTControlCharacters(line).slice(1).trimEnd()) };
          }
        }
        const expected = {};
        for (const width of [48, 90, 240]) {
          expected[width] = {};
          for (const [key, spec] of Object.entries(specs)) {
            expected[width][key] = [
              ...wrapTextWithAnsi(`[probe] ${spec.expandedSubject ?? spec.subject}`, width - 2),
              ...(spec.summary ?? []).flatMap(line => wrapTextWithAnsi(line, width - 2)),
            ].map(line => line.trimEnd());
          }
        }
        const noWrapperCarriage = [false, true].map(expanded => renderToolLifecycle(specs.carriage, {
          ...geometry, wrapDetail: undefined, theme, width: 90, expanded,
        }).slice(1, -1).map(line => stripVTControlCharacters(line).trimEnd().slice(1)));
        const noWrapperTrailing = renderToolLifecycle(specs.trailingBreak, {
          ...geometry, wrapDetail: undefined, theme, width: 90,
        }).slice(1, -1).map(line => stripVTControlCharacters(line).trimEnd().slice(1));
        const direct = (expandable, spec = specs.empty) => renderToolLifecycle(spec, { ...geometry, theme, width: 90, expandable })
          .slice(1, -1).map(line => stripVTControlCharacters(line).trim());
        const errors = {};
        for (const [name, build] of Object.entries(builders).filter(([name]) => name.toLowerCase().includes('result'))) {
          const render = build({ ...geometry, createSpec: () => specs.empty });
          errors[name] = render({ content: 'failure reason\nadditional evidence' }, { expanded: true }, theme, { isError: true })
            .render(90).map(line => stripVTControlCharacters(line).trim()).filter(Boolean);
        }
        const styledTheme = {
          fg: (color, text) => `<FG:${color}>${text}</FG:${color}>`,
          bg: (color, text) => `<BG:${color}>${text}</BG:${color}>`,
          bold: text => text,
        };
        const styledRows = renderToolLifecycle(eventToolLifecycle('monitor', 'Goal acceptance chain', {
          details: ['Timeout: 7m', 'Command:', ['\u001b[38;2;167;152;215mset\u001b[39m -e', '\u001b[38;2;167;152;215mecho\u001b[39m DONE'], 'Success condition: DONE'],
        }), { width: 80, expanded: true, theme: styledTheme, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi });
        const fullSummarySpec = { tool: 'goal', kind: 'event', subject: 'active', summary: ['First acceptance condition must survive a narrow terminal.\n\nFINAL_CONDITION'], fullSummary: true };
        const fullSummaryOpts = { theme, width: 25, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi };
        console.log(JSON.stringify({
          rows, expected, errors, noWrapperCarriage, noWrapperTrailing,
          directTrue: direct(true), directFalse: direct(false, specs.body),
          styledRows, styledPlain: styledRows.map(r => stripVTControlCharacters(r).replace(/<[^>]+>/g, '').trim()),
          fullSummaryCollapsed: renderToolLifecycle(fullSummarySpec, { ...fullSummaryOpts, expanded: false }),
          fullSummaryExpanded: renderToolLifecycle(fullSummarySpec, { ...fullSummaryOpts, expanded: true }),
        }));
    """
    )


def test_meaningful_expansion_across_all_factories_and_styled_blocks(expansion_cases: dict[str, object]) -> None:
    for factory in ("result", "staticResult", "message", "staticMessage", "boundResult", "boundMessage"):
        cases = expansion_cases["rows"][factory]
        for name in ("empty", "whitespace", "limited", "trailingPreview"):
            case = cases[name]
            assert case["widths"]["90"]["collapsed"] == ["[probe] done"]
            assert case["widths"]["90"]["expanded"] == ["[probe] done"]
            assert case["withoutMetadata"] == case["widths"]["90"]["collapsed"]
        assert cases["shortSummary"]["widths"]["90"]["collapsed"] == ["[probe] decision", "Answer: yes"]
        assert "ctrl+o" not in "\n".join(cases["blankSummary"]["widths"]["90"]["collapsed"])
        for key in ("long", "multiline", "carriage", "summary", "explicit"):
            for width in ("48", "90", "240"):
                rendered = cases[key]["widths"][width]
                assert rendered["expanded"] == expansion_cases["expected"][width][key]
                assert "MODEL-ONLY" not in "\n".join(rendered["expanded"])
                if key != "long" or width != "240":
                    assert "ctrl+o to expand" in "\n".join(rendered["collapsed"])
            assert all(v["expandedBounded"] and v["collapsedBounded"] for v in cases[key]["widths"].values())
        assert "ctrl+o" not in "\n".join(cases["long"]["widths"]["240"]["collapsed"])
        for width in ("48", "90", "240"):
            view = cases["trailing"]["widths"][width]
            assert view["collapsed"] == ["[probe] done", "Answer: yes"] == view["expanded"]
            tb = cases["trailingBreak"]["widths"][width]
            assert tb["collapsed"] == ["[probe] done", "Answer: yes"] == [line for line in tb["expanded"] if line]
        assert cases["body"]["widths"]["90"]["expanded"] == ["[probe] done", "first", "", "second", "first"]
        assert cases["readback"]["widths"]["90"]["expanded"] == ["[probe] report", *[f"finding {i}" for i in range(65)]]
        assert "ctrl+o to expand" in cases["body"]["widths"]["90"]["collapsed"][0]

    assert expansion_cases["noWrapperTrailing"] == ["[probe] done", "Answer: yes"]
    assert expansion_cases["noWrapperCarriage"] == [
        ["[probe] first second · ctrl+o to expand", "Answer: one two"],
        ["[probe] first", "second", "Answer: one", "two"],
    ]
    assert expansion_cases["directTrue"] == ["[probe] done · ctrl+o to expand"]
    assert expansion_cases["directFalse"] == ["[probe] done"]
    for rows in expansion_cases["errors"].values():
        assert rows == ["[probe] failed · failure reason", "additional evidence"]

    styled_rows, styled_plain = expansion_cases["styledRows"], expansion_cases["styledPlain"]
    assert styled_plain[1:7] == ["[monitor] Goal acceptance chain", "Timeout: 7m", "Command:", "set -e", "echo DONE", "Success condition: DONE"]
    assert "\u001b[38;2;167;152;215mset\u001b[39m -e" in "\n".join(styled_rows[4:6])
    assert "<FG:" not in styled_rows[4] and "<FG:" not in styled_rows[5]
    assert "<FG:customMessageText>" in styled_rows[2] and "<FG:customMessageText>" in styled_rows[6]
    assert all(row.startswith("<BG:toolSuccessBg>") for row in styled_rows)

    assert expansion_cases["fullSummaryCollapsed"] == expansion_cases["fullSummaryExpanded"]
    fs_text = "".join(expansion_cases["fullSummaryCollapsed"])
    assert "FINAL_CONDITION" in fs_text and "to expand" not in fs_text and "..." not in fs_text


# ── Sanitization, human-copy helpers, model pickers, directory & tool ownership ──


def test_sanitization_human_copy_and_agent_display_helpers() -> None:
    message = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"'
    result = run_typescript(
        r"""
        import {
          contentDetailLines, fieldBlock, fieldLine, formatAgentMessagePrefix, formatAgentTaskName,
          labelField, labelFieldVerbatim, safeDisplayText, scrubHandles,
        } from './packages/kit/src/index.ts';
        const st = '\u001b\\', esc = '\u001b', bel = '\u0007';
        const message = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
        console.log(JSON.stringify({
          safe: {
            ansi: safeDisplayText('\u001b[31mred\u001b[39m'),
            osc: safeDisplayText('Evil\u001b]0;pwned\u0007Name'),
            control: safeDisplayText('a\u0007b\u007fc'),
            st: safeDisplayText(`Open ${esc}]8;;https://example.test${st}LINK-LABEL${esc}]8;;${st} after.`),
            bel: safeDisplayText(`Open ${esc}]8;;https://example.test${bel}LINK-LABEL${esc}]8;;${bel} after.`),
            c1: safeDisplayText('Open \u009d8;;https://example.test\u009cLINK-LABEL\u009d8;;\u009c after.'),
            adjacent: safeDisplayText(`${esc}]0;hidden${st}First${esc}]0;hidden2${st}Second`),
            mixed: safeDisplayText(`${esc}]0;hidden${bel}First${esc}]0;hidden2${st}Second`),
            unfinished: safeDisplayText(`Visible ${esc}]0;hidden`),
            controls: safeDisplayText(`${esc}[31mred${esc}[0m\nnext\tcolumn\u0007`),
          },
          agentDisplay: {
            prefix: formatAgentMessagePrefix('from'),
            multiPrefix: formatAgentMessagePrefix('from', 2),
            outgoingPrefix: formatAgentMessagePrefix('to'),
            taskName: formatAgentTaskName('  inspect   authentication  ', 'fallback'),
            longTaskName: formatAgentTaskName('x'.repeat(140), 'fallback'),
          },
          copy: {
            lines: contentDetailLines({ content: [{ type: 'text', text: '  one\n\n two ' }] }),
            field: fieldLine('model', 'qwen3-max'),
            block: fieldBlock('task', 'first\nsecond'),
            longBlock: fieldBlock('prompt', 'x'.repeat(5000)),
            dropped: fieldLine('note', { nested: true }),
            label: labelField('Status', 'success'),
            labelCollapsed: labelField('Reason', 'process  exit'),
            labelVerbatim: labelFieldVerbatim('Success condition', 'a  b'),
            labelDropped: labelFieldVerbatim('Output', { nested: true }),
            plainScrub: scrubHandles(message),
            addressedScrub: scrubHandles(message + '\n"session:reader:spawn-1" ; work:e0cfae81-57dd-4b68-8b67-2103ed825cfd !', () => 'Fix spacing'),
            session: scrubHandles('see session:reviewer:6d102f1b-cc16-4059-8d86-d5c1192f3776 now'),
            known: scrubHandles('over work:e0cfae81-57dd-4b68-8b67-2103ed825cfd', h => h === 'work:e0cfae81-57dd-4b68-8b67-2103ed825cfd' ? 'Fix spacing' : undefined),
            generic: scrubHandles('over direct:6d102f1b-cc16-4059-8d86-d5c1192f3776.'),
            literal: scrubHandles('compare 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log'),
          },
        }));
        """
    )
    assert result["safe"] == {
        "ansi": "red",
        "osc": "EvilName",
        "control": "abc",
        "st": "Open LINK-LABEL after.",
        "bel": "Open LINK-LABEL after.",
        "c1": "Open LINK-LABEL after.",
        "adjacent": "FirstSecond",
        "mixed": "FirstSecond",
        "unfinished": "Visible ",
        "controls": "red\nnext\tcolumn",
    }
    assert result["agentDisplay"] == {
        "prefix": "[message] from ",
        "multiPrefix": "[2 messages] from ",
        "outgoingPrefix": "[message] to ",
        "taskName": "inspect authentication",
        "longTaskName": "x" * 140,
    }
    c = result["copy"]
    assert c["lines"] == ["one", "two"]
    assert c["field"] == "model · qwen3-max"
    assert c["block"] == ["task · first", "second"]
    assert c["longBlock"] == [f"prompt · {'x' * 5000}"]
    assert c["dropped"] == "note · "
    assert c["label"] == "Status: success" and c["labelCollapsed"] == "Reason: process exit"
    assert c["labelVerbatim"] == "Success condition: a  b" and c["labelDropped"] == "Output: "
    assert c["plainScrub"] == message
    assert c["addressedScrub"] == message + '\n"@reader" ; Fix spacing !'
    assert c["session"] == "see @reviewer now" and c["known"] == "over Fix spacing"
    assert c["generic"] == "over its assignment." and c["literal"] == "compare 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log"


def test_model_ref_menu_search_picker_and_input_helpers() -> None:
    result = run_typescript(
        f"""
        import {{
          createSearchPicker, enterModelFromInput, modelLabel, modelRef,
          modelSearchText, nonEmpty, parseModelRef, searchModelFromPicker,
          selectModelFromMenu, sortModels,
        }} from {json.dumps((SRC / "index.ts").as_uri())};

        const menuModels = [
          {{ provider: "anthropic", id: "claude-sonnet", name: "Claude Sonnet" }},
          {{ provider: "openai", id: "gpt-4o", name: "GPT-4o" }},
        ];
        const menuSelected = await selectModelFromMenu(
          {{ notify: () => {{}}, select: async (_l, opts) => opts.find((o) => o.includes("· current")) }},
          menuModels, "anthropic/claude-sonnet", "Pick",
        );
        let menuNotified = null;
        const menuEmpty = await selectModelFromMenu(
          {{ select: async () => "x", notify: (msg, type) => {{ menuNotified = {{ msg, type }}; }} }},
          [], undefined, "Pick",
        );

        const pickerModels = [
          {{ provider: "openai", id: "gpt-4o", name: "GPT-4o" }},
          {{ provider: "anthropic", id: "claude-sonnet-3.5", name: "Claude 3.5 Sonnet" }},
          {{ provider: "anthropic", id: "claude-haiku-3.5", name: "Claude 3.5 Haiku" }},
        ];
        const fakeKb = {{
          matches: (key, action) =>
            (action === "tui.select.down" && key === "down") ||
            (action === "tui.select.up" && key === "up") ||
            (action === "tui.select.confirm" && key === "enter") ||
            (action === "tui.select.cancel" && key === "escape"),
        }};
        let capturedQueryLine = "";
        const pickerSelected = await searchModelFromPicker({{
          async custom(factory) {{
            return new Promise((resolve) => {{
              const comp = factory({{}}, {{ fg: (c, t) => `<${{c}}>${{t}}</${{c}}>`, bold: (t) => t }}, fakeKb, resolve);
              comp.handleInput("h"); comp.handleInput("a"); comp.handleInput("i");
              capturedQueryLine = comp.render(80)[2];
              comp.handleInput("enter");
            }});
          }},
          notify() {{}},
        }}, pickerModels, "openai/gpt-4o", {{ title: "Pick model" }});
        const pickerCancelled = await searchModelFromPicker({{
          async custom(factory) {{
            return new Promise((resolve) => {{
              const comp = factory({{}}, {{ fg: (_c, t) => t, bold: (t) => t }}, fakeKb, resolve);
              comp.handleInput("escape");
            }});
          }},
          notify() {{}},
        }}, pickerModels, undefined);

        const registry = {{ find: (p, m) => (p === "openai" && m === "gpt-4o" ? {{}} : undefined) }};
        const inputNotices = [];
        const baseUi = {{ notify: (msg, type) => inputNotices.push({{ msg, type }}) }};
        const inGood = await enterModelFromInput({{ ...baseUi, input: async () => "openai/gpt-4o" }}, registry, undefined);
        const inBad = await enterModelFromInput({{ ...baseUi, input: async () => "nope" }}, registry, undefined);
        const inMissing = await enterModelFromInput({{ ...baseUi, input: async () => "openai/unknown" }}, registry, undefined);
        const inEmpty = await enterModelFromInput({{ ...baseUi, input: async () => "   " }}, registry, undefined);
        const inCancelled = await enterModelFromInput({{ ...baseUi, input: async () => undefined }}, registry, undefined);
        let resetCount = 0;
        const inOnEmpty = await enterModelFromInput({{ ...baseUi, input: async () => "   " }}, registry, undefined, {{ onEmpty: () => {{ resetCount++; }} }});
        const inDefaulted = await enterModelFromInput({{ ...baseUi, input: async (_l, def) => def }}, registry, "openai/gpt-4o", {{ label: "Pick me" }});

        const searchList = sortModels([
          {{ provider: "openai", id: "gpt-5.2", name: "GPT-5.2" }},
          {{ provider: "anthropic", id: "claude-opus-4-6", name: "Claude Opus 4.6" }},
          {{ provider: "anthropic", id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6" }},
          {{ provider: "google", id: "gemini-3-pro", name: "gemini-3-pro" }},
        ]);
        const ctrl = createSearchPicker(searchList, {{
          filter: (items, q, getText) => items.filter((item) => getText(item).toLowerCase().includes(q.toLowerCase())),
          getText: modelSearchText,
        }});
        ctrl.type("cl");
        const narrowed = ctrl.results().map((m) => `${{m.provider}}/${{m.id}}`);
        ctrl.down();
        const movedIndex = ctrl.selectedIndex();
        ctrl.type("aude opus");
        const refined = ctrl.results().map((m) => `${{m.provider}}/${{m.id}}`);
        const refinedIndex = ctrl.selectedIndex();
        ctrl.backspace();
        ctrl.clear();
        const restored = ctrl.results().length;
        ctrl.up();
        const clampedTop = ctrl.selectedIndex();
        for (let i = 0; i < 10; i++) ctrl.down();
        const bottomClamped = ctrl.selectedIndex();
        const bottomLabel = `${{ctrl.selected()?.provider}}/${{ctrl.selected()?.id}}`;
        ctrl.type("zzz-no-match");

        console.log(JSON.stringify({{
          parsed: parseModelRef("anthropic/claude-3-5-haiku"),
          invalid: [parseModelRef("gpt-4o"), parseModelRef(""), parseModelRef(undefined), parseModelRef("/gpt-4o"), parseModelRef("openai/")],
          refs: [modelRef({{ provider: "openai", model: "gpt-4o" }}), modelRef({{ provider: undefined, model: "gpt-4o" }}), modelRef({{ provider: undefined, model: undefined }})],
          label: modelLabel({{ provider: "anthropic", id: "claude" }}),
          sorted: sortModels([{{ provider: "z", id: "a" }}, {{ provider: "a", id: "z" }}, {{ provider: "a", id: "a" }}]),
          nonEmpty: [nonEmpty("  hi  "), nonEmpty("   ")],
          menuSelected, menuEmpty, menuNotified,
          pickerSelected, pickerCancelled, capturedQueryLine,
          inputs: {{ inGood, inBad, inMissing, inEmpty, inCancelled, inOnEmpty, resetCount, inDefaulted, noticeTypes: inputNotices.map((n) => n.type) }},
          search: {{
            namedText: modelSearchText({{ provider: "anthropic", id: "claude-opus-4-6", name: "Claude Opus 4.6" }}),
            namelessText: modelSearchText({{ provider: "google", id: "gemini-3-pro" }}),
            narrowed, movedIndex, refined, refinedIndex, restored, clampedTop, bottomClamped, bottomLabel,
            emptySelected: ctrl.selected(),
          }},
        }}, (_k, v) => (v === undefined ? null : v)));
        """
    )
    assert result["parsed"] == {"provider": "anthropic", "model": "claude-3-5-haiku"}
    assert result["invalid"] == [None] * 5
    assert result["refs"] == ["openai/gpt-4o", "gpt-4o", None]
    assert result["label"] == "anthropic/claude"
    assert result["sorted"] == [{"provider": "a", "id": "a"}, {"provider": "a", "id": "z"}, {"provider": "z", "id": "a"}]
    assert result["nonEmpty"] == ["hi", None]
    assert result["menuSelected"] == {"provider": "anthropic", "model": "claude-sonnet"}
    assert result["menuEmpty"] is None and result["menuNotified"] == {"msg": "No models are available in the model registry.", "type": "warning"}
    assert result["pickerSelected"] == {"provider": "anthropic", "model": "claude-haiku-3.5"}
    assert result["pickerCancelled"] is None and "<border>hai</border>" in result["capturedQueryLine"]
    inp = result["inputs"]
    assert inp["inGood"] == {"provider": "openai", "model": "gpt-4o"} == inp["inDefaulted"]
    assert [inp[k] for k in ("inBad", "inMissing", "inEmpty", "inCancelled", "inOnEmpty")] == [None] * 5
    assert inp["resetCount"] == 1 and inp["noticeTypes"] == ["error", "error", "error"]
    s = result["search"]
    assert s["namedText"] == "anthropic/claude-opus-4-6 · Claude Opus 4.6"
    assert s["namelessText"] == "google/gemini-3-pro"
    assert s["narrowed"] == ["anthropic/claude-opus-4-6", "anthropic/claude-sonnet-4-6"]
    assert s["refined"] == ["anthropic/claude-opus-4-6"] and s["refinedIndex"] == 0
    assert s["restored"] == 4 and s["movedIndex"] == 1 and s["clampedTop"] == 0 and s["bottomClamped"] == 3
    assert s["bottomLabel"] == "openai/gpt-5.2" and s["emptySelected"] is None


def test_directory_cli_resolver_and_owned_tool_disclosure_contracts(tmp_path: Path) -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        const root = {json.dumps(str(tmp_path))};
        const real = path.join(root, "real");
        const link = path.join(root, "link");
        fs.mkdirSync(real);
        fs.symlinkSync(real, link, "dir");
        const missing = path.join(root, "missing", "child");
        const unrelated = path.join(root, "unrelated");
        fs.mkdirSync(unrelated);
        fs.writeFileSync(path.join(unrelated, "package.json"), JSON.stringify({{ name: "unrelated-pi-wrapper" }}));
        const entry = path.join(unrelated, "cli.mjs");
        fs.writeFileSync(entry, "");
        const originalArgv1 = process.argv[1];
        process.argv[1] = entry;
        const {{
          directorySessionsDir, getDirectorySessionKey, isSameDirectory, resolvePiCli, setOwnedTools,
        }} = await import({json.dumps((SRC / "index.ts").as_uri())});
        const cli = resolvePiCli();
        process.argv[1] = originalArgv1;

        let active = ["bash", "read"];
        const host = {{ getActiveTools: () => active, setActiveTools: (names) => {{ active = names; }} }};
        const owned = ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"];
        const toggled = ["matt_pocock_active", "matt_pocock_ask"];
        setOwnedTools(host, {{ owned, always: ["matt_pocock_workflow"], toggled, enabled: false }});
        const idle = active.slice();
        setOwnedTools(host, {{ owned, always: ["matt_pocock_workflow"], toggled, enabled: true }});
        const during = active.slice();
        setOwnedTools(host, {{ owned, always: ["matt_pocock_workflow"], toggled, enabled: false }});
        const after = active.slice();
        setOwnedTools(host, {{ owned, always: ["matt_pocock_workflow"], toggled, enabled: true }});
        setOwnedTools(host, {{ owned, always: ["matt_pocock_workflow"], toggled, enabled: true }});
        const repeated = active.slice();
        let wrote = false;
        setOwnedTools({{ getActiveTools: undefined, setActiveTools: () => {{ wrote = true; }} }}, {{ owned, enabled: false }});

        console.log(JSON.stringify({{
          same: isSameDirectory(real, link),
          sameKey: getDirectorySessionKey(real) === getDirectorySessionKey(link),
          missingKey: getDirectorySessionKey(missing),
          absoluteMissing: path.isAbsolute(getDirectorySessionKey(missing)),
          cli,
          unrelated: cli.args.some((arg) => arg.includes("unrelated")),
          idle, during, after, repeated, wrote,
          sessionsDirs: {{
            home: path.join(os.homedir(), ".pi", "agent"),
            default: directorySessionsDir({{}}),
            agentDir: directorySessionsDir({{ PI_CODING_AGENT_DIR: "/sandbox/agent" }}),
            legacyAgentDir: directorySessionsDir({{ PI_AGENT_DIR: "/legacy/agent" }}),
            explicit: directorySessionsDir({{ PI_DIRECTORY_SESSIONS_DIR: "/explicit/registry", PI_CODING_AGENT_DIR: "/sandbox/agent" }}),
            blankOverrideIgnored: directorySessionsDir({{ PI_DIRECTORY_SESSIONS_DIR: "   " }}),
            codingWinsOverLegacy: directorySessionsDir({{ PI_CODING_AGENT_DIR: "/sandbox/agent", PI_AGENT_DIR: "/legacy/agent" }}),
          }},
        }}));
        """
    )
    assert result["same"] is True and result["sameKey"] is True
    assert len(result["missingKey"]) == 64 and result["absoluteMissing"] is False
    assert result["unrelated"] is False and result["cli"]["args"][-1].endswith("dist/bundle/cli.js")

    assert result["idle"] == ["bash", "read", "matt_pocock_workflow"]
    assert {"matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"} <= set(result["during"])
    assert result["after"] == ["bash", "read", "matt_pocock_workflow"]
    assert len(result["repeated"]) == len(set(result["repeated"])) and result["wrote"] is False

    home = os.path.join(os.path.expanduser("~"), ".pi", "agent")
    sd = result["sessionsDirs"]
    assert sd["home"] == home
    assert sd["default"] == os.path.join(home, "directory-sessions")
    assert sd["agentDir"] == os.path.join("/sandbox/agent", "directory-sessions")
    assert sd["legacyAgentDir"] == os.path.join("/legacy/agent", "directory-sessions")
    assert sd["explicit"] == "/explicit/registry"
    assert sd["blankOverrideIgnored"] == os.path.join(home, "directory-sessions")
    assert sd["codingWinsOverLegacy"] == os.path.join("/sandbox/agent", "directory-sessions")


def test_kit_manifest_and_one_way_dependency_boundary() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-kit"
    assert "pi" not in manifest and "dependencies" not in manifest
    assert manifest["peerDependencies"] == {
        "@earendil-works/pi-coding-agent": "*",
        "@earendil-works/pi-tui": "*",
    }
    assert "pi-package" not in manifest.get("keywords", []) and "src" in manifest["files"]

    consumer_names = {json.loads((REPO / "packages" / c / "package.json").read_text())["name"] for c in CONSUMERS}
    for source in SRC.glob("*.ts"):
        text = source.read_text(encoding="utf-8")
        for name in consumer_names:
            assert name not in text, f"{source.name} must not import consumer package {name}"
        imported_core = set(re.findall(r'from "(@earendil-works/[^"/]+)', text))
        assert imported_core <= {"@earendil-works/pi-tui"}
        mentioned_core = set(re.findall(r'"(@earendil-works/[^"/]+)', text))
        assert mentioned_core <= {"@earendil-works/pi-tui", "@earendil-works/pi-coding-agent"}

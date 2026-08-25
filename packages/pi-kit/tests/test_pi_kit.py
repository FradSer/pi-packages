from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"

CONSUMERS = [
    "agent-teams",
    "btw",
    "pi-continual-learning",
    "recap",
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


def test_feature_covers_spinner_theme_messages_and_dependency_hygiene() -> None:
    feature = (PACKAGE / "features" / "pi-kit.feature").read_text(encoding="utf-8")
    assert "Feature: Shared pi-kit runtime helpers" in feature
    assert "Scenario: Spinner frames match pi's native loader" in feature
    assert "Scenario: Theme style language is adapted from any pi theme" in feature
    assert "Scenario: Plain text is extracted from string message content" in feature
    assert "Scenario: Plain text is extracted from content-block arrays" in feature
    assert "Scenario: Non-message content yields empty text" in feature
    assert "Scenario: Model reference is parsed from a provider/model string" in feature
    assert "Scenario: Model reference is formatted from config" in feature
    assert "Scenario: Model label is formatted from a model object" in feature
    assert "Scenario: A model is selected from the interactive menu" in feature
    assert "Scenario: Model search text leads with the provider-prefixed label" in feature
    assert "Scenario: A search picker filters models by query and resets the selection" in feature
    assert "Scenario: A search picker restores previous results on backspace" in feature
    assert "Scenario: Search picker navigation clamps within filtered results" in feature
    assert "Scenario: Pi workers inherit their working directory without an unsupported flag" in feature
    assert "Scenario: Pi workers have no wall-clock timeout" in feature
    assert "Scenario: pi-kit stays a pure runtime dependency" in feature
    assert "Scenario: Pi CLI resolution accepts only the coding-agent package" in feature
    assert "Scenario: Child termination observes close and escalates once" in feature


def test_worker_command_does_not_pass_unsupported_cwd_flag() -> None:
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    assert '"--cwd", cwd' not in source


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


def test_tool_event_labels_share_the_compact_monitor_pattern() -> None:
    result = run_typescript(
        f"""
        import {{ formatToolEventLabel }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          started: formatToolEventLabel("started", "运行 monitor 包测试"),
          event: formatToolEventLabel("event", "运行 monitor 包测试"),
          listed: formatToolEventLabel("listed", "2 other sessions in pi-packages", "sessions"),
          agentEvent: formatToolEventLabel("event", "@scribe shut down", "agent"),
          created: formatToolEventLabel("created", "Fix the login flow", "board"),
        }}));
        """
    )
    assert result == {
        "started": "[monitor] started · 运行 monitor 包测试",
        "event": "[monitor] event · 运行 monitor 包测试",
        "listed": "[sessions] listed · 2 other sessions in pi-packages",
        "agentEvent": "[agent] event · @scribe shut down",
        "created": "[board] created · Fix the login flow",
    }


def test_expand_hint_shares_the_report_row_style() -> None:
    result = run_typescript(
        f"""
        import {{ formatExpandHint }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{ fg: (_color, text) => `<dim>${{text}}</dim>` }};
        console.log(JSON.stringify({{
          hint: formatExpandHint("ctrl+o to expand", theme),
          plain: formatExpandHint("ctrl+o to expand", {{ fg: (_color, text) => text }}),
        }}));
        """
    )
    assert result == {
        "hint": "<dim> · ctrl+o to expand</dim>",
        "plain": " · ctrl+o to expand",
    }


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


def test_agent_display_helpers_share_labels_and_message_counts() -> None:
    result = run_typescript(
        f"""
        import {{ formatAgentTaskLabel, formatAgentMessageLabel, formatAgentTaskName }} from {json.dumps((SRC / "index.ts").as_uri())};
        console.log(JSON.stringify({{
          task: formatAgentTaskLabel("Agent Alpha - research", "calc-1", "task-namexxxx"),
          message: formatAgentMessageLabel("calc-1"),
          messages: formatAgentMessageLabel("calc-1", "from", 2),
          outgoing: formatAgentMessageLabel("calc-1", "to"),
          taskName: formatAgentTaskName("  inspect   authentication  ", "fallback"),
        }}));
        """
    )
    assert result == {
        "task": "Agent (Agent Alpha - research) · @calc-1 · task-namexxxx",
        "message": "[message] from @calc-1",
        "messages": "[2 messages] from @calc-1",
        "outgoing": "[message] to @calc-1",
        "taskName": "inspect authentication",
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


def test_pi_kit_manifest_is_a_pure_runtime_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-kit"
    assert "pi" not in manifest
    assert "dependencies" not in manifest
    assert "peerDependencies" not in manifest
    assert "pi-package" not in manifest.get("keywords", [])
    assert "src" in manifest["files"]


def test_pi_kit_has_no_consumer_imports() -> None:
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


def test_consumers_declare_pi_kit_as_workspace_dependency() -> None:
    for consumer in CONSUMERS:
        manifest = json.loads((REPO / "packages" / consumer / "package.json").read_text(encoding="utf-8"))
        assert manifest.get("dependencies", {}).get("@fradser/pi-kit") == "workspace:*", (
            f"{consumer} must depend on @fradser/pi-kit via workspace:* under dependencies"
        )
        assert "@fradser/pi-kit" not in manifest.get("peerDependencies", {}), (
            f"{consumer} must not declare @fradser/pi-kit as a peer dependency"
        )


def test_publish_allowlist_orders_pi_kit_before_consumers() -> None:
    script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")
    kit_position = script.index('"@fradser/pi-kit"')
    assert kit_position > 0, "publish allowlist must include @fradser/pi-kit"
    for name in ['"@fradser/pi-agent-teams"', '"@fradser/pi-btw"', '"pi-continual-learning"',
                 '"@fradser/pi-recap"', '"@fradser/pi-utils"', '"@fradser/pi-vision"']:
        assert script.index(name) > kit_position, f"pi-kit must publish before {name}"

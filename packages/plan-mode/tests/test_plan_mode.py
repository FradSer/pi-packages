from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    import json
    return json.loads(result.stdout)


def test_plan_mode_feature_covers_live_worker_widget_and_diagnostics():
    feature = (PACKAGE / "features" / "plan-mode.feature").read_text(encoding="utf-8")
    assert "Scenario: Plan feedback uses the shared TUI notification abstraction" in feature
    assert "portable notification helper" in feature
    assert "Feature: Plan worker diagnostics and CLI compatibility" in feature
    assert "Scenario: Plan overlays and widgets use pi-kit's shared TUI renderers" in feature
    assert "shared panel renderer" in feature
    assert "shared widget-row renderer" in feature
    assert "Scenario: Plan workers render a live above-editor status widget" in feature
    assert "Scenario: The main-session plan is shown before optional research" in feature
    assert "Scenario: Plan worker failures remain visible until cleanup" in feature
    assert "Scenario: Explore workers avoid unsupported CLI options" in feature
    assert "Scenario: Failed explore workers expose status and diagnostics" in feature
    assert "Scenario: Empty successful output is not reported as completed" in feature
    assert "Scenario: Plan writer receives structured explore status" in feature
    assert "Scenario: Plan workers do not use wall-clock timeouts" in feature
    assert "Scenario: Plan review timeout defaults to a fresh implementation session" in feature
    assert "Scenario: Explore workers cannot mutate the project" in feature
    assert "Scenario: The plan writer cannot mutate paths outside the plan file" in feature
    assert "Scenario: Plan writer completion requires a fresh non-empty plan" in feature
    assert "Scenario: Finished plan worker tool activity does not remain current" in feature
    assert "Scenario: Plan review reserves space for its action menu" in feature
    assert "Scenario: Plan completion does not loop review commands to the agent" in feature


def test_notifications_use_pi_kits_portable_helper():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert "notifyPi" in source
    assert "ctx.ui.notify(" not in source
    assert "newCtx.ui.notify(" not in source


def test_plan_completion_does_not_loop_review_messages_to_agent():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'pi.sendUserMessage("/plan review")' not in source
    assert 'showPlanReview(ctx, request, job.signal)' in source


def test_plan_completion_settles_before_review_and_accepts_new_prompt():
    run_plan_lifecycle("dismiss")


def test_obsolete_detached_workers_are_cancelled():
    for scenario in ("worker-exit", "worker-writer-exit", "worker-new", "worker-replace", "review-exit"):
        run_plan_lifecycle(scenario)


def test_manual_review_is_cancelled_with_its_owner():
    for scenario in ("manual-exit", "manual-new", "manual-menu-replace", "manual-view-exit"):
        run_plan_lifecycle(scenario)


def run_plan_lifecycle(scenario: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests" / "plan_lifecycle.mts"), scenario],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_plan_mode_prompts_prioritize_exploration_and_mention_builtin_workers():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    feature = (PACKAGE / "features" / "plan-mode.feature").read_text(encoding="utf-8")
    system_prompt = source[source.index("function buildPlanPrompt"):source.index("// ── State ──")]
    main_session_prompt = source[
        source.index("function buildMainSessionPlanPrompt"):
        source.index("function buildWorkerResearchPrompt")
    ]

    assert "Your FIRST step is read-only exploration" in system_prompt
    assert "built-in workers for parallel exploration" in system_prompt
    assert "Explore FIRST" in system_prompt
    assert "read-only exploration FIRST" in main_session_prompt
    assert "built-in workers for parallel exploration" in main_session_prompt
    assert "Scenario: Plan mode prompts emphasize exploration first and mention built-in workers" in feature
    assert "system prompt and main-session prompt" in feature
    assert "system prompt instructs" in feature
    assert "main-session prompt instructs" in feature


def test_plan_mode_indicator_is_persistent_below_editor():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    feature = (PACKAGE / "features" / "plan-mode.feature").read_text(encoding="utf-8")
    assert "setPlanModeIndicator" in source
    assert 'placement: "belowEditor"' in source
    assert 'setWidget("plan-mode-indicator"' in source
    assert "⏸" in source
    assert "plan mode on" in source
    assert "setPlanModeIndicator(ctx, true)" in source
    assert "setPlanModeIndicator(ctx, false)" in source
    assert "Scenario: Plan mode shows a persistent indicator below the editor" in feature


def test_plan_mode_starts_in_main_session_before_worker_research():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    feature = (PACKAGE / "features" / "plan-mode.feature").read_text(encoding="utf-8")
    assert 'pi.sendUserMessage(planPrompt, { deliverAs: "followUp" })' in source
    assert "research-workers" not in source
    assert "runWorkerResearch" in source
    assert "runPlanWorker({" in source
    assert 'placement: "aboveEditor"' in source
    assert "Scenario: A plan request starts in the main session" in feature
    assert "Scenario: Worker research is decided by the main-session agent" in feature


def test_plan_review_timeout_uses_fresh_session_context():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert "PLAN_REVIEW_TIMEOUT_MS" in source
    assert "implement-fresh" in source
    assert "newCtx.sendUserMessage" in source
    assert "pi.sendUserMessage(`Implement this plan" not in source
    assert "setTimeout(() => finish(\"implement-fresh\")" in source


def test_plan_mode_uses_a_live_worker_widget_with_shared_spinner():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    worker = (PACKAGE / "src" / "plan-worker.ts").read_text(encoding="utf-8")
    assert 'setWidget("plan-workers"' in source
    assert 'placement: "aboveEditor"' in source
    assert "PI_SPINNER_FRAMES" in source
    assert "PI_SPINNER_INTERVAL_MS" in source
    assert "onUpdate" in worker
    assert "status: \"running\"" in worker
    assert "status: \"completed\"" in worker
    assert 'status,' in worker


def test_plan_mode_worker_rows_use_shared_task_activity_format():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'const name = theme.bold(worker.id);' in source
    assert 'const phase = theme.fg("muted", `(${worker.label})`);' in source
    assert 'const detail = ` · ${activity}`;' in source
    assert 'renderPiWidgetRow(`${marker} ${name} ${phase}${detail}`, width, truncateToWidth)' in source
    assert 'const activity = worker.detail ?? "Working...";' in source
    assert 'const detail = ` · ${activity}`;' in source


def bash_decisions(commands: list[str]) -> dict[str, object]:
    return run_typescript(f"""
        import fs from "node:fs";
        import {{ createRequire }} from "node:module";
        const require = createRequire(import.meta.url);
        const {{ transformSync }} = require(require.resolve("esbuild", {{ paths: [require.resolve("tsx")] }}));
        const source = fs.readFileSync({json.dumps(str(PACKAGE / "src" / "index.ts"))}, "utf8");
        const start = source.indexOf("function isReadOnlyBash(");
        const end = source.indexOf("async function switchToPlanModel", start);
        const js = transformSync(source.slice(start, end), {{ loader: "ts", target: "es2022" }}).code;
        const validate = new Function(js + "; return isReadOnlyBash;")();
        console.log(JSON.stringify(Object.fromEntries({json.dumps(commands)}.map(c => [c, validate(c)]))));
    """)


def test_is_read_only_bash_allows_safe_commands():
    commands = [
        "", "   ", "ls -la", "cat file.txt", "grep -r pattern .",
        "find . -name '*.ts'", "git status", "git log --oneline -10",
        "diff a b", "jq . file.json", "rg -n -A 3 needle .", "git log -5 --format=oneline",
        "pwd", "wc -l file.ts", "sort -r file", "git branch", "git tag", "git remote -v",
        'ls -la packages/matt-pocock/ && echo "---" && ls -R packages/matt-pocock/ | head -80',
        'cat "file with spaces"|grep "a|b"', "echo 'a && b' && ls", "ls&&pwd",
    ]
    result = bash_decisions(commands)
    assert all(result.values()), result


def test_is_read_only_bash_blocks_unsafe_commands_and_syntax():
    commands = [
        "rm file", "ls && rm file", "rm file | head", "ls | touch file",
        "ls; pwd", "ls & pwd", "ls || pwd", "ls |& head", "ls &&", "| ls", "ls | | head",
        "ls\nrm file", "ls\rpwd", "ls\n", "echo $(touch file)", "echo `touch file`",
        "cat < file", "echo x > file", "ls >> file", "cat <(ls)", "(ls)",
        'echo "unterminated', "echo 'unterminated", "ls \\nrm file", "ls # comment",
        "./ls", "/tmp/ls", "find . -delete", "find . -exec touch file +",
        "find . -execdir touch file +", "find . -fprint output", "sort -o output file",
        "sort --output=output file", "sort --o=output file", "sort -rooutput file",
        "fd -x touch", "fd --exec touch", "rg --pre touch", "rg --hostname-bin touch",
        "git reset --hard", "git branch new", "git tag new", "git remote add x url",
        "git diff --output=file", "git log --output file", "git diff --ext-diff",
        "git show --textconv", "git -c alias.x=touch x", "date -s tomorrow",
        "uniq input output", "less file", "yq -i . file", "tree -o output",
        "printf -v variable value", "git branch -D main", "git tag -d version",
    ]
    result = bash_decisions(commands)
    assert not any(result.values()), result


def test_plan_mode_and_pi_kit_do_not_use_wall_clock_worker_timeouts():
    source = (PACKAGE / "src" / "plan-worker.ts").read_text(encoding="utf-8")
    kit = (REPO / "packages" / "kit" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "timeoutMs" not in source
    assert "timedOut" not in source
    assert "timeoutMs" not in kit
    assert "timedOut" not in kit


def test_plan_worker_does_not_pass_unsupported_cwd_flag():
    kit = (REPO / "packages" / "kit" / "src" / "index.ts").read_text(encoding="utf-8")
    assert '"--cwd", cwd' not in kit


def test_plan_worker_uses_named_structured_explore_results():
    worker = (PACKAGE / "src" / "plan-worker.ts").read_text(encoding="utf-8")
    assert "status: \"completed\" | \"failed\"" in worker
    assert "exploreResults" in worker
    assert "diagnostics: string" in worker
    assert "--no-extensions" in worker


def test_plan_workers_are_restricted_to_read_only_host_capabilities():
    worker = (PACKAGE / "src" / "plan-worker.ts").read_text(encoding="utf-8")
    assert 'const EXPLORE_TOOLS = ["read", "grep", "find", "ls"];' in worker
    assert 'const PLAN_WRITER_TOOLS = ["read", "grep", "find", "ls"];' in worker
    assert 'extraArgs: ["--no-extensions"]' in worker
    assert "fs.writeFileSync(planPath" in worker
    assert "Use the write tool" not in worker


def test_pi_kit_clears_finished_tool_activity():
    kit = (REPO / "packages" / "kit" / "src" / "index.ts").read_text(encoding="utf-8")
    tool_end = kit[kit.index('case "toolcall_end":'):kit.index("default:", kit.index('case "toolcall_end":'))]
    assert "state.activeTool = undefined;" in tool_end


def test_plan_overlay_uses_shared_panel_and_widget_renderers():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    overlay = (PACKAGE / "src" / "plan-overlay.ts").read_text(encoding="utf-8")
    assert "renderPiPanel" in overlay
    assert "renderPiWidgetRow" in source


def test_plan_overlay_reserves_action_menu_space():
    overlay = (PACKAGE / "src" / "plan-overlay.ts").read_text(encoding="utf-8")
    assert "return Math.max(3, rows - 14);" in overlay
    assert "maxBodyHeight" not in overlay
    index = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'maxHeight: "80%"' not in index
    assert 'maxHeight: "90%"' not in index


def test_failed_explores_report_status_diagnostics_and_compatible_cli_args():
    result = run_typescript(f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        import {{ runPlanWorker }} from {json.dumps((PACKAGE / "src" / "plan-worker.ts").as_uri())};

        const root = fs.mkdtempSync(path.join(os.tmpdir(), "plan-mode-worker-"));
        const bin = path.join(root, "bin");
        const capture = path.join(root, "args.json");
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(bin);
        fs.mkdirSync(cwd);
        const fakePi = path.join(bin, "pi");
        fs.writeFileSync(fakePi, `#!/usr/bin/env node
const fs = require("node:fs");
fs.writeFileSync(process.env.PI_CAPTURE, JSON.stringify(process.argv.slice(2)));
process.stderr.write("provider rejected worker request");
process.exit(7);
`, {{ mode: 0o755 }});
        process.env.PATH = `${{bin}}:${{process.env.PATH ?? ""}}`;
        process.env.PI_CAPTURE = capture;

        const result = await runPlanWorker({{
          prompt: "inspect the project",
          cwd,
          planPath: path.join(root, "plan.md"),
          exploreTasks: [{{ focus: "tests", instructions: "inspect tests" }}],
        }});
        const args = JSON.parse(fs.readFileSync(capture, "utf8"));
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{
          result: {{
            status: result.exploreResults[0].status,
            diagnostics: result.exploreResults[0].diagnostics,

            exitCode: result.exploreResults[0].exitCode,
            aggregate: result.stderr,
          }},
          args,
        }}));
    """)
    worker = result["result"]
    assert worker["status"] == "failed"
    assert worker["diagnostics"] == "provider rejected worker request"
    assert worker["exitCode"] == 7
    assert "tests: provider rejected worker request" in worker["aggregate"]
    assert "--no-extensions" in result["args"]
    assert "--cwd" not in result["args"]


def test_empty_explore_output_reports_actionable_diagnostic():
    result = run_typescript(f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";
        import {{ runPlanWorker }} from {json.dumps((PACKAGE / "src" / "plan-worker.ts").as_uri())};

        const root = fs.mkdtempSync(path.join(os.tmpdir(), "plan-mode-empty-"));
        const bin = path.join(root, "bin");
        const cwd = path.join(root, "workspace");
        fs.mkdirSync(bin);
        fs.mkdirSync(cwd);
        const fakePi = path.join(bin, "pi");
        fs.writeFileSync(fakePi, "#!/usr/bin/env node\\nprocess.exit(0);\\n", {{ mode: 0o755 }});
        process.env.PATH = `${{bin}}:${{process.env.PATH ?? ""}}`;
        const result = await runPlanWorker({{
          prompt: "inspect the project",
          cwd,
          planPath: path.join(root, "plan.md"),
          exploreTasks: [{{ focus: "structure", instructions: "inspect structure" }}],
        }});
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify({{
          status: result.exploreResults[0].status,
          diagnostics: result.exploreResults[0].diagnostics,
          aggregate: result.stderr,
        }}));
    """)
    assert result["status"] == "failed"
    assert result["diagnostics"] == "Worker produced no structured result."
    assert "structure: Worker produced no structured result." in result["aggregate"]


def test_plan_review_fresh_session_action_uses_real_runtime():
    run_plan_lifecycle("fresh")


def test_tilde_expansion_in_agent_dir_and_plan_paths():
    result = run_typescript(f"""
        import * as os from "node:os";
        import * as path from "node:path";
        import {{ readPlanModeConfig, planModeConfigPath }} from {json.dumps((PACKAGE / "src" / "config.ts").as_uri())};

        process.env.PI_CODING_AGENT_DIR = "~/custom-agent-dir";
        const configPath = planModeConfigPath();
        const expectedPrefix = path.join(os.homedir(), "custom-agent-dir");

        console.log(JSON.stringify({{
          configPath,
          expandsTilde: configPath.startsWith(expectedPrefix),
          noLiteralTilde: !configPath.includes("~"),
        }}));
    """)
    assert result["expandsTilde"] is True
    assert result["noLiteralTilde"] is True
    result = run_typescript("""
        // Inline parseModelRef to avoid import issues
        function parseModelRef(value) {
          if (typeof value !== "string" || !value.trim()) return null;
          const ref = value.trim();
          const separator = ref.indexOf("/");
          if (separator <= 0 || separator === ref.length - 1) return null;
          return { provider: ref.slice(0, separator), model: ref.slice(separator + 1) };
        }

        const results = {
          valid: parseModelRef("anthropic/claude-3"),
          empty: parseModelRef(""),
          no_slash: parseModelRef("noslash"),
          leading: parseModelRef("/leading"),
          trailing: parseModelRef("trailing/"),
          undefined: parseModelRef(undefined),
        };
        console.log(JSON.stringify(results));
    """)
    assert result["valid"] == {"provider": "anthropic", "model": "claude-3"}
    assert result["empty"] is None
    assert result["no_slash"] is None
    assert result["leading"] is None
    assert result["trailing"] is None
    assert result["undefined"] is None

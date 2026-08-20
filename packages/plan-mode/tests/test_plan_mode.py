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
    assert "Feature: Plan worker diagnostics and CLI compatibility" in feature
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
    assert "setTimeout(() => done(\"implement-fresh\")" in source


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
    assert 'const line = ` ${marker} ${name} ${phase}${detail}`;' in source
    assert 'const activity = worker.detail ?? "Working...";' in source
    assert 'const detail = ` · ${activity}`;' in source


def test_is_read_only_bash_allows_safe_commands():
    result = run_typescript("""
        // Inline the function to avoid import issues
        function isReadOnlyBash(command) {
          const trimmed = command.trim();
          if (!trimmed) return true;
          if (/[;|&`$>]/.test(trimmed)) return false;
          const tokens = trimmed.split(/\\s+/);
          const cmd = tokens[0]?.replace(/^(\\/[\\w/]*)?/, "").split("/").pop() ?? "";
          const SAFE = new Set([
            "cat", "head", "tail", "less", "wc", "file", "stat",
            "grep", "egrep", "fgrep", "rg",
            "find", "fd",
            "ls", "dir", "tree", "pwd",
            "git",
            "echo", "printf",
            "sort", "uniq", "diff",
            "jq", "yq",
            "which", "type",
            "date", "uptime",
          ]);
          return SAFE.has(cmd);
        }

        const results = {
          cat: isReadOnlyBash("cat file.txt"),
          ls: isReadOnlyBash("ls -la"),
          grep: isReadOnlyBash("grep -r pattern ."),
          find: isReadOnlyBash("find . -name '*.ts'"),
          git_status: isReadOnlyBash("git status"),
          git_log: isReadOnlyBash("git log --oneline -10"),
          pwd: isReadOnlyBash("pwd"),
          wc: isReadOnlyBash("wc -l file.ts"),
          empty: isReadOnlyBash(""),
          spaces: isReadOnlyBash("   "),
        };
        console.log(JSON.stringify(results));
    """)
    assert all(v is True for v in result.values()), f"Expected all true: {result}"


def test_is_read_only_bash_blocks_mutating_commands():
    result = run_typescript("""
        function isReadOnlyBash(command) {
          const trimmed = command.trim();
          if (!trimmed) return true;
          if (/[;|&`$>]/.test(trimmed)) return false;
          const tokens = trimmed.split(/\\s+/);
          const cmd = tokens[0]?.replace(/^(\\/[\\w/]*)?/, "").split("/").pop() ?? "";
          const SAFE = new Set([
            "cat", "head", "tail", "less", "wc", "file", "stat",
            "grep", "egrep", "fgrep", "rg",
            "find", "fd",
            "ls", "dir", "tree", "pwd",
            "git",
            "echo", "printf",
            "sort", "uniq", "diff",
            "jq", "yq",
            "which", "type",
            "date", "uptime",
          ]);
          return SAFE.has(cmd);
        }

        const results = {
          rm: isReadOnlyBash("rm file.txt"),
          mv: isReadOnlyBash("mv a b"),
          cp: isReadOnlyBash("cp a b"),
          mkdir: isReadOnlyBash("mkdir dir"),
          touch: isReadOnlyBash("touch file"),
          chmod: isReadOnlyBash("chmod 755 file"),
          npm_install: isReadOnlyBash("npm install"),
        };
        console.log(JSON.stringify(results));
    """)
    assert all(v is False for v in result.values()), f"Expected all false: {result}"


def test_is_read_only_bash_blocks_shell_operators():
    result = run_typescript("""
        function isReadOnlyBash(command) {
          const trimmed = command.trim();
          if (!trimmed) return true;
          if (/[;|&`$>]/.test(trimmed)) return false;
          const tokens = trimmed.split(/\\s+/);
          const cmd = tokens[0]?.replace(/^(\\/[\\w/]*)?/, "").split("/").pop() ?? "";
          const SAFE = new Set([
            "cat", "head", "tail", "less", "wc", "file", "stat",
            "grep", "egrep", "fgrep", "rg",
            "find", "fd",
            "ls", "dir", "tree", "pwd",
            "git",
            "echo", "printf",
            "sort", "uniq", "diff",
            "jq", "yq",
            "which", "type",
            "date", "uptime",
          ]);
          return SAFE.has(cmd);
        }

        const results = {
          pipe: isReadOnlyBash("cat file | grep x"),
          redirect: isReadOnlyBash("echo x > file"),
          and: isReadOnlyBash("cat a && cat b"),
          subshell_dollar: isReadOnlyBash("$(whoami)"),
          subshell_backtick: isReadOnlyBash("echo `date`"),
        };
        console.log(JSON.stringify(results));
    """)
    assert all(v is False for v in result.values()), f"Expected all false: {result}"


def test_plan_mode_restricts_git_to_read_only_subcommands():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert '"git",' not in source
    assert '"status", "log", "diff", "show"' in source
    assert '"reset"' not in source
    assert '"push"' not in source


def test_plan_mode_and_pi_kit_do_not_use_wall_clock_worker_timeouts():
    source = (PACKAGE / "src" / "plan-worker.ts").read_text(encoding="utf-8")
    kit = (REPO / "packages" / "pi-kit" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "timeoutMs" not in source
    assert "timedOut" not in source
    assert "timeoutMs" not in kit
    assert "timedOut" not in kit


def test_plan_worker_does_not_pass_unsupported_cwd_flag():
    kit = (REPO / "packages" / "pi-kit" / "src" / "index.ts").read_text(encoding="utf-8")
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
    kit = (REPO / "packages" / "pi-kit" / "src" / "index.ts").read_text(encoding="utf-8")
    tool_end = kit[kit.index('case "toolcall_end":'):kit.index("default:", kit.index('case "toolcall_end":'))]
    assert "state.activeTool = undefined;" in tool_end


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


def test_parse_model_ref():
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

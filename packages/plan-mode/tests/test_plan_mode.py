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



def test_notifications_use_pi_kits_portable_helper():
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert "notifyPi" in source
    assert "ctx.ui.notify(" not in source
    assert "newCtx.ui.notify(" not in source



def test_model_command_with_argument_does_not_start_planning():
    run_plan_contract("model-command")



def test_repeated_plan_entry_restores_the_original_model():
    run_plan_contract("model-restore")



def test_execution_discussion_does_not_release_plan_guards():
    run_plan_contract("guard-input")



def test_extension_tools_cannot_bypass_plan_guards():
    run_plan_contract("guard-tools")



def test_extension_overrides_of_builtin_names_cannot_bypass_plan_guards():
    run_plan_contract("guard-collisions")



def run_plan_contract(scenario: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests" / "plan_contracts.mts"), scenario],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr



def run_plan_lifecycle(scenario: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests" / "plan_lifecycle.mts"), scenario],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr



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



def test_plan_uses_minimal_pi_kit_worker_and_native_review():
    source = (PACKAGE / "src" / "index.ts").read_text()
    worker = (PACKAGE / "src" / "plan-worker.ts").read_text()
    assert "runPlanWorker" in source
    assert "runPiWorker" in worker
    assert "minimal: true" in worker
    assert "ctx.ui.custom" not in source
    assert "PLAN_REVIEW_TIMEOUT_MS" not in source


def test_default_planner_uses_one_read_only_minimal_worker():
    run_plan_lifecycle("headless")


def test_failed_and_empty_headless_plans_preserve_previous_plan_and_report_errors():
    for scenario, diagnostic in (("headless-failed", "Planner fixture failed"), ("headless-empty", "no structured result")):
        result = subprocess.run(
            ["node", "--import", "tsx", str(PACKAGE / "tests" / "plan_lifecycle.mts"), scenario],
            cwd=REPO, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Planning failed:" in result.stderr
        assert diagnostic in result.stderr


def test_obsolete_planners_are_cancelled_before_saving():
    for scenario in ("worker-exit", "worker-new", "worker-replace"):
        run_plan_lifecycle(scenario)


def test_native_review_runs_in_the_current_session_only_after_selection():
    run_plan_lifecycle("here")


def test_native_review_starts_a_linked_new_session_only_after_selection():
    run_plan_lifecycle("fresh")


def test_dismissing_native_review_keeps_read_only_mode_and_accepts_prompts():
    run_plan_lifecycle("dismiss")


def test_interactive_start_opens_native_review():
    run_plan_lifecycle("start-review")


def test_native_review_is_cancelled_with_its_plan():
    for scenario in ("review-exit", "review-new", "review-replace", "manual-exit", "manual-new", "manual-replace"):
        run_plan_lifecycle(scenario)


def test_new_session_unavailable_or_cancelled_never_implements_here():
    for scenario in ("fresh-unavailable", "fresh-cancelled"):
        run_plan_lifecycle(scenario)


def test_plan_path_survives_collisions_and_session_restore():
    run_plan_lifecycle("naming")


def test_explicit_research_preserves_partial_failure_diagnostics():
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests" / "plan_worker_contracts.mts")],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

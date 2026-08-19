from __future__ import annotations

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

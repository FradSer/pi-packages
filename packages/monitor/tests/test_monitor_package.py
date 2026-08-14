from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SKILLS = PACKAGE / "skills"
SRC = PACKAGE / "src"


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3, "SKILL.md must have YAML frontmatter delimited by ---"
    return parts[1]


def run_typescript(script: str) -> subprocess.CompletedProcess[str]:
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
    return result


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]


def test_extension_entry_points_exist() -> None:
    for name in ("index.ts", "monitor.ts", "types.ts"):
        assert (SRC / name).is_file(), f"Extension source {name} is missing"


def test_extension_declares_peer_dependencies() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    for dependency in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox"):
        assert manifest["peerDependencies"][dependency] == "*"


def test_single_skill_using_monitor_is_present() -> None:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert [skill.parent.name for skill in skills] == ["using-monitor"]


def test_skill_has_valid_frontmatter() -> None:
    metadata = frontmatter((SKILLS / "using-monitor" / "SKILL.md").read_text(encoding="utf-8"))
    assert "name: using-monitor" in metadata
    assert "description:" in metadata


def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not (PACKAGE / ".claude-plugin").exists()
    assert not list(PACKAGE.rglob("plugin.json"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.md"))
    for forbidden in ("allowed-tools:", "user-invocable:", "CLAUDE_PLUGIN_ROOT", "AskUserQuestion"):
        assert forbidden not in content


def test_no_emojis_in_shipped_documentation() -> None:
    for path in (SKILLS / "using-monitor" / "SKILL.md", PACKAGE / "README.md"):
        for char in path.read_text(encoding="utf-8"):
            assert not 0x1F600 < ord(char) < 0x1F9FF, f"Emoji found in {path.name}: {char}"


def test_extension_registers_result_contract_tools() -> None:
    extension = (SRC / "index.ts").read_text(encoding="utf-8")
    for tool in ("monitor_start", "monitor_read", "monitor_list", "monitor_stop"):
        assert f'name: "{tool}"' in extension
    assert 'registerCommand("monitor"' in extension


def test_start_schema_requires_result_pattern_and_has_optional_failure_pattern() -> None:
    schemas = (SRC / "types.ts").read_text(encoding="utf-8")
    assert "result_pattern: Type.String" in schemas
    assert "failure_pattern: Type.Optional" in schemas
    assert "MonitorReadParams" in schemas
    assert "match:" not in schemas


def test_guidance_teaches_result_contract_and_on_demand_diagnostics() -> None:
    extension = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "MONITOR_GUIDANCE" in extension
    assert "unique JSON sentinel" in extension
    assert "Progress logs never trigger turns" in extension
    assert "monitor_read" in extension
    assert 'pi.on("before_agent_start"' in extension


def test_only_terminal_results_are_injected_into_model_context() -> None:
    extension = (SRC / "index.ts").read_text(encoding="utf-8")
    manager = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert extension.count("pi.sendMessage(") == 1
    assert 'customType: "monitor-result"' in extension
    assert 'deliverAs: "steer"' in extension
    assert "triggerTurn: true" in extension
    assert "onTerminal" in manager
    assert "onEvent" not in manager


def test_monitor_uses_close_event_and_kills_detached_process_group() -> None:
    manager = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert 'child?.on("close"' in manager
    assert 'child?.on("exit"' not in manager
    assert "process.kill(-pid, signal)" in manager
    assert 'signalGroup("SIGTERM")' in manager
    assert 'signalGroup("SIGKILL")' in manager
    assert "monitor.killTimer.unref()" in manager


def test_monitor_bounds_raw_logs_and_read_results() -> None:
    manager = (SRC / "monitor.ts").read_text(encoding="utf-8")
    for constant in (
        "MAX_LINE_LENGTH",
        "MAX_LINE_BUFFER",
        "MAX_LOG_LINES",
        "MAX_LOG_BYTES",
        "MAX_READ_LINES",
        "MAX_READ_BYTES",
        "MAX_HISTORY",
    ):
        assert f"export const {constant}" in manager
    assert "trimLogs" in manager
    assert "boundedTail" in manager


def test_terminal_message_is_compact_plain_text() -> None:
    extension = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "formatTerminalMessage" in extension
    assert "status=${result.status}" in extension
    assert "elapsed=${formatElapsed(result.elapsedMs)}" in extension
    assert "result=${JSON.stringify(result.result)}" in extension
    assert "JSON.stringify({" not in extension
    assert "null, 2" not in extension
    assert "diagnostics=monitor_read" in extension


def test_widget_is_display_only_and_console_owns_input() -> None:
    extension = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'setWidget("monitor"' in extension
    assert 'placement: "belowEditor"' in extension
    assert "onTerminalInput" not in extension
    assert "ctx.ui.custom" in extension
    assert "handleInput" in extension


def test_success_sentinel_returns_one_structured_terminal_result() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'progress\\n__PI_MONITOR_RESULT__ {"ok":true,"count":3}\\n'`,
          description: "sentinel",
          resultPattern: String.raw`__PI_MONITOR_RESULT__ (?<json>\{.*\})`,
        });
        await new Promise((resolve) => setTimeout(resolve, 300));
        if (terminals.length !== 1) throw new Error(`terminal count ${terminals.length}`);
        const terminal = terminals[0];
        if (terminal.result.status !== "success") throw new Error(JSON.stringify(terminal));
        if (terminal.result.result.ok !== true || terminal.result.result.count !== 3) {
          throw new Error(JSON.stringify(terminal));
        }
        const read = manager.read(started.id, 100);
        if (!read || !read.lines.some((line) => line.includes("progress"))) {
          throw new Error(JSON.stringify(read));
        }
        if (manager.list().length !== 0) throw new Error("monitor remained active");
        ''',
    )


def test_failure_pattern_matches_stderr_and_returns_capture() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'deploy failed: broken config\\n' >&2; sleep 5`,
          description: "failure",
          resultPattern: "DEPLOY_COMPLETE",
          failurePattern: String.raw`deploy failed: (?<reason>.+)`,
        });
        await new Promise((resolve) => setTimeout(resolve, 300));
        if (terminals.length !== 1) throw new Error(`terminal count ${terminals.length}`);
        if (terminals[0].result.status !== "failure") throw new Error(JSON.stringify(terminals));
        if (terminals[0].result.captures.reason !== "broken config") {
          throw new Error(JSON.stringify(terminals));
        }
        const read = manager.read(started.id, 100);
        if (!read || !read.lines.some((line) => line.startsWith("[stderr]"))) {
          throw new Error(JSON.stringify(read));
        }
        ''',
    )


def test_progress_output_does_not_emit_notifications() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'step 1\\nstep 2\\n'; sleep 5`,
          description: "quiet progress",
          resultPattern: "NEVER_MATCHES",
          persistent: true,
        });
        await new Promise((resolve) => setTimeout(resolve, 200));
        if (terminals.length !== 0) throw new Error(JSON.stringify(terminals));
        const read = manager.read(started.id, 100);
        if (!read || read.lines.length !== 2) throw new Error(JSON.stringify(read));
        manager.stop(started.id);
        if (terminals.length !== 0) throw new Error("manual stop emitted a terminal result");
        ''',
    )


def test_unterminated_final_sentinel_matches_during_close_once() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'FINAL_RESULT id=42'`,
          description: "unterminated sentinel",
          resultPattern: String.raw`FINAL_RESULT id=(?<id>\d+)`,
        });
        await new Promise((resolve) => setTimeout(resolve, 250));
        if (terminals.length !== 1 || terminals[0].result.status !== "success") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.captures.id !== "42") throw new Error(JSON.stringify(terminals));
        ''',
    )


def test_clean_exit_without_result_reports_result_missing() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'done without contract\\n'`,
          description: "missing",
          resultPattern: "EXPECTED_SENTINEL",
        });
        await new Promise((resolve) => setTimeout(resolve, 250));
        if (terminals.length !== 1 || terminals[0].result.status !== "result_missing") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.expected !== "EXPECTED_SENTINEL") {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )


def test_timeout_scans_unterminated_buffer_before_reporting_timeout() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'READY url=http://localhost:3000'; sleep 5`,
          description: "timeout boundary",
          resultPattern: String.raw`READY url=(?<url>\S+)`,
          timeoutMs: 100,
        });
        await new Promise((resolve) => setTimeout(resolve, 350));
        if (terminals.length !== 1 || terminals[0].result.status !== "success") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.captures.url !== "http://localhost:3000") {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )


def test_nonzero_exit_and_timeout_report_one_failure_each() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ id: monitor.id, result }),
        });
        manager.start({
          command: `printf 'ordinary error\\n' >&2; exit 7`,
          description: "exit failure",
          resultPattern: "SUCCESS",
        });
        manager.start({
          command: `sleep 5`,
          description: "timeout",
          resultPattern: "SUCCESS",
          timeoutMs: 50,
        });
        await new Promise((resolve) => setTimeout(resolve, 350));
        if (terminals.length !== 2) throw new Error(JSON.stringify(terminals));
        const failure = terminals.find((entry) => entry.result.status === "failure");
        const timeout = terminals.find((entry) => entry.result.status === "timeout");
        if (!failure || failure.result.exitCode !== 7 || !timeout) {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )


def test_sigkill_escalates_to_term_resistant_descendant_after_shell_closes() -> None:
    run_typescript(
        r'''
        import { existsSync, readFileSync } from "node:fs";
        import { mkdtemp, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { KILL_GRACE_MS, MonitorManager } from "./packages/monitor/src/monitor.ts";

        const fixtureDirectory = await mkdtemp(join(tmpdir(), "pi-monitor-kill-tree-"));
        const fixture = join(fixtureDirectory, "ignore-term.mjs");
        const pidFile = join(fixtureDirectory, "pids.json");
        await writeFile(fixture, [
          'import { writeFileSync } from "node:fs";',
          'process.on("SIGTERM", () => {});',
          'writeFileSync(process.env.PID_FILE, JSON.stringify({ childPid: process.pid, shellPid: process.ppid }));',
          'setInterval(() => {}, 1000);',
        ].join("\n"));

        const terminals = [];
        let childPid;
        let shellPid;
        const isAlive = (pid) => {
          try {
            process.kill(pid, 0);
            return true;
          } catch (error) {
            return error?.code === "EPERM";
          }
        };
        const waitForPidFile = async () => {
          for (let attempt = 0; attempt < 40; attempt += 1) {
            if (existsSync(pidFile)) return JSON.parse(readFileSync(pidFile, "utf8"));
            await new Promise((resolve) => setTimeout(resolve, 25));
          }
          throw new Error("descendant did not publish its pids");
        };
        const manager = new MonitorManager({
          onTerminal: (_monitor, result) => terminals.push(result),
        });
        try {
          const started = manager.start({
            command: `PID_FILE=${JSON.stringify(pidFile)} ${JSON.stringify(process.execPath)} ${JSON.stringify(fixture)} & wait`,
            description: "term-resistant descendant",
            resultPattern: "NEVER_MATCHES",
          });
          ({ childPid, shellPid } = await waitForPidFile());
          manager.stop(started.id);
          await new Promise((resolve) => setTimeout(resolve, 150));
          if (terminals.length !== 0 || isAlive(shellPid) || !isAlive(childPid)) {
            throw new Error(`expected closed shell, live descendant, no result: ${JSON.stringify({ terminals, shellPid, childPid })}`);
          }
          await new Promise((resolve) => setTimeout(resolve, KILL_GRACE_MS + 500));
          if (isAlive(childPid)) throw new Error(`descendant ${childPid} survived SIGKILL escalation`);
        } finally {
          if (childPid && isAlive(childPid)) process.kill(childPid, "SIGKILL");
          if (shellPid && isAlive(shellPid)) process.kill(shellPid, "SIGKILL");
          await rm(fixtureDirectory, { recursive: true, force: true });
        }
        ''',
    )


def test_session_shutdown_waits_for_sigkill_escalation_before_parent_exit() -> None:
    run_typescript(
        r'''
        import { existsSync } from "node:fs";
        import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
        import { spawn } from "node:child_process";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { pathToFileURL } from "node:url";

        const fixtureDirectory = await mkdtemp(join(tmpdir(), "pi-monitor-shutdown-"));
        const descendant = join(fixtureDirectory, "ignore-term.mjs");
        const parent = join(fixtureDirectory, "shutdown-parent.mjs");
        const pidFile = join(fixtureDirectory, "pids.json");
        let childPid;
        let shellPid;
        const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const isRunning = (pid) => {
          try {
            process.kill(pid, 0);
            return true;
          } catch (error) {
            return error?.code === "EPERM";
          }
        };
        const waitForExit = (child) => new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("shutdown parent did not exit")), 5000);
          child.on("error", reject);
          child.on("close", (code) => {
            clearTimeout(timeout);
            code === 0 ? resolve(undefined) : reject(new Error(`shutdown parent exited ${code}`));
          });
        });

        await writeFile(descendant, [
          'import { writeFileSync } from "node:fs";',
          'process.on("SIGTERM", () => {});',
          'writeFileSync(process.env.PID_FILE, JSON.stringify({ childPid: process.pid, shellPid: process.ppid }));',
          'setInterval(() => {}, 1000);',
        ].join("\n"));
        const monitorModule = pathToFileURL(join(process.cwd(), "packages/monitor/src/monitor.ts")).href;
        const command = `PID_FILE=${JSON.stringify(pidFile)} ${JSON.stringify(process.execPath)} ${JSON.stringify(descendant)} & wait`;
        await writeFile(parent, [
          `import { existsSync, readFileSync } from "node:fs";`,
          `import { MonitorManager } from ${JSON.stringify(monitorModule)};`,
          `const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));`,
          `const manager = new MonitorManager({ onTerminal: () => {} });`,
          `manager.start({ command: ${JSON.stringify(command)}, description: "shutdown", resultPattern: "NEVER_MATCHES" });`,
          `for (let attempt = 0; attempt < 80 && !existsSync(${JSON.stringify(pidFile)}); attempt += 1) await delay(25);`,
          `if (!existsSync(${JSON.stringify(pidFile)})) throw new Error("descendant did not publish its pid");`,
          `await manager.stopAllOnShutdown();`,
          `JSON.parse(readFileSync(${JSON.stringify(pidFile)}, "utf8"));`,
        ].join("\n"));

        try {
          const shutdownParent = spawn(process.execPath, ["--import", "tsx", parent], {
            cwd: process.cwd(),
            stdio: "ignore",
          });
          await waitForExit(shutdownParent);
          ({ childPid, shellPid } = JSON.parse(await readFile(pidFile, "utf8")));
          await delay(100);
          if (isRunning(childPid)) {
            throw new Error(`SIGTERM-resistant descendant ${childPid} survived parent shutdown`);
          }
        } finally {
          if (childPid && isRunning(childPid)) process.kill(childPid, "SIGKILL");
          if (shellPid && isRunning(shellPid)) process.kill(shellPid, "SIGKILL");
          await rm(fixtureDirectory, { recursive: true, force: true });
        }
        ''',
    )


def test_raw_log_history_is_bounded_and_readable_after_completion() -> None:
    run_typescript(
        r'''
        import { MAX_LOG_LINES, MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `node -e "for(let i=0;i<3000;i++) console.log('line-' + i)"`,
          description: "bounded logs",
          resultPattern: "NEVER_MATCHES",
        });
        await new Promise((resolve) => setTimeout(resolve, 600));
        const read = manager.read(started.id, 500);
        if (!read) throw new Error("missing archived log");
        if (read.monitor.retainedLogLines > MAX_LOG_LINES) throw new Error(JSON.stringify(read.monitor));
        if (read.droppedLines <= 0 || !read.truncated) throw new Error(JSON.stringify(read));
        if (read.lines.length > 500) throw new Error(`too many lines ${read.lines.length}`);
        if (terminals.length !== 1 || terminals[0].result.status !== "result_missing") {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )

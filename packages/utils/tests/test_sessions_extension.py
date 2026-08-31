import json
import subprocess
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
SESSIONS_EXTENSION = UTILS_PKG_DIR / "extensions" / "sessions.ts"


class TestSessionsExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return SESSIONS_EXTENSION.read_text(encoding="utf-8")

    def test_extension_file_exists(self) -> None:
        self.assertTrue(
            SESSIONS_EXTENSION.exists(),
            f"Expected {SESSIONS_EXTENSION} to exist",
        )

    def test_registers_hooks_commands_and_tools(self) -> None:
        content = self.ext_source()
        self.assertIn('registerCommand("sessions"', content)
        self.assertIn('registerTool', content)
        self.assertIn('list_directory_sessions', content)
        self.assertIn('before_agent_start', content)
        self.assertIn('session_start', content)
        self.assertIn('session_shutdown', content)

    def test_list_directory_sessions_is_disclosed_only_while_peer_sessions_exist(self) -> None:
        script = f"""
import ext, {{ getSessionFileKey, writeSessionInfo }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const cwd = path.join(os.tmpdir(), "disclose-sessions-" + Date.now());
fs.mkdirSync(cwd, {{ recursive: true }});
let handlers = {{}};
let activeTools = ["read", "list_directory_sessions", "unrelated_tool"];
const pi = {{
  registerTool() {{}}, registerCommand() {{}},
  on(name, handler) {{ handlers[name] = handler; }},
  getActiveTools() {{ return activeTools; }},
  setActiveTools(names) {{ activeTools = names; }},
}};
ext(pi);
await handlers.session_start({{}}, {{ cwd, sessionManager: {{ getSessionFile: () => "self.jsonl" }} }});
const initiallyInactive = [...activeTools];
const sleeper = Bun.spawn(["sleep", "30"], {{ stdout: "ignore", stderr: "ignore" }});
writeSessionInfo({{
  sessionId: "peer", pid: sleeper.pid, cwd, startedAt: Date.now(), updatedAt: Date.now(), status: "idle",
}});
await handlers.before_agent_start({{ prompt: "work", systemPrompt: "base" }}, {{ cwd, sessionManager: {{ getSessionFile: () => "self.jsonl" }} }});
const peerActive = [...activeTools];
fs.rmSync(path.join(os.homedir(), ".pi", "agent", "directory-sessions", getSessionFileKey(cwd)), {{ recursive: true, force: true }});
await handlers.agent_settled({{}}, {{ cwd }});
console.log(JSON.stringify({{ initiallyInactive, peerActive, settled: activeTools }}));
sleeper.kill();
fs.rmSync(cwd, {{ recursive: true, force: true }});
"""
        result = subprocess.run(["bun", "run", "-"], cwd=REPO, input=script, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertNotIn("list_directory_sessions", data["initiallyInactive"])
        self.assertIn("list_directory_sessions", data["peerActive"])
        self.assertIn("unrelated_tool", data["peerActive"])
        self.assertNotIn("list_directory_sessions", data["settled"])
        self.assertIn("unrelated_tool", data["settled"])

    def test_list_directory_sessions_follows_compact_display_pattern(self) -> None:
        content = self.ext_source()
        # Monitor display pattern: tool renders its own shell, an empty call
        # slot, and exactly one compact result row delegated to the shared
        # pi-kit lifecycle band.
        self.assertIn('renderShell: "self"', content)
        self.assertIn("renderCall: () => new Container()", content)
        self.assertIn('eventToolLifecycle("sessions", summary, { label: "listed", details: rows })', content)
        # Style-free consumer: pi-kit owns the band geometry and styling; no
        # hand-built Box or theme calls remain in the sessions renderer.
        self.assertIn("createToolLifecycleResultRenderer(", content)
        self.assertIn('expandHint: keyHint("app.tools.expand", "to expand")', content)
        self.assertIn("fit: truncateToWidth", content)
        self.assertNotIn("new Box(", content)
        self.assertNotIn('theme.bg("customMessageBg"', content)
        # Expanded view reuses the shared task-name truncation for goals.
        self.assertIn("formatAgentTaskName", content)

    def test_ts_module_logic_via_bun(self) -> None:
        script = f"""
import {{ getRegistryDir, getSessionFileKey, formatCrossSessionRecap, SessionInfo }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};

const cwd = "/app/test-project";
const dirKey = getSessionFileKey(cwd);
const formatted = formatCrossSessionRecap([
  {{
    sessionId: "sess-1",
    sessionName: "Auth \u001b]0;pwned\u0007Feature",
    pid: 12345,
    cwd: cwd,
    startedAt: Date.now() - 60000,
    updatedAt: Date.now() - 5000,
    status: "running",
    latestGoal: "Fix login issue",
    recap: "Working on auth.ts",
  }}
]);

console.log(JSON.stringify({{
  dirKey,
  registryDir: getRegistryDir(),
  formatted,
}}));
"""
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("Auth Feature", data["formatted"])
        self.assertIn("Fix login issue", data["formatted"])
        self.assertIn("RUNNING", data["formatted"])
        # Recap output feeds both /sessions UI and the system prompt — no escapes survive.
        self.assertNotIn("\x1b", data["formatted"])
        self.assertNotIn("pwned", data["formatted"])

    def test_registry_write_read_clean_via_bun(self) -> None:
        script = f"""
import {{ writeSessionInfo, cleanAndListDirectorySessions, isProcessAlive, getSessionFileKey }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const tmpCwd = path.join(os.tmpdir(), "test-pi-session-dir-" + Date.now());
fs.mkdirSync(tmpCwd, {{ recursive: true }});
const sleeper = Bun.spawn(["sleep", "30"], {{ stdout: "ignore", stderr: "ignore" }});

// Write an active session (independent live process)
writeSessionInfo({{
  sessionId: "alive-1",
  sessionName: "Active Task",
  pid: sleeper.pid,
  cwd: tmpCwd,
  startedAt: Date.now(),
  updatedAt: Date.now(),
  status: "running",
  latestGoal: "Add tests",
}});

// Write a dead session (PID 9999999)
writeSessionInfo({{
  sessionId: "dead-1",
  sessionName: "Dead Task",
  pid: 9999999,
  cwd: tmpCwd,
  startedAt: Date.now() - 7200000,
  updatedAt: Date.now() - 7200000,
  status: "exited",
}});

const activeSessions = cleanAndListDirectorySessions(tmpCwd);
sleeper.kill();
console.log(JSON.stringify({{
  count: activeSessions.length,
  aliveSessionId: activeSessions[0]?.sessionId,
  isSelfAlive: isProcessAlive(process.pid),
  isFakeDead: isProcessAlive(9999999),
}}));
fs.rmSync(path.join(os.homedir(), ".pi", "agent", "directory-sessions", getSessionFileKey(tmpCwd)), {{ recursive: true, force: true }});
fs.rmSync(tmpCwd, {{ recursive: true, force: true }});
"""
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["aliveSessionId"], "alive-1")
        self.assertTrue(data["isSelfAlive"])
        self.assertFalse(data["isFakeDead"])
    def test_session_age_formatting_via_bun(self) -> None:
        script = f"""
import {{ formatSessionAge }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};

const now = Date.now();
console.log(JSON.stringify({{
  seconds: formatSessionAge(now - 5_000, now),
  minutes: formatSessionAge(now - 5 * 60_000, now),
  hours: formatSessionAge(now - 3 * 3_600_000, now),
}}));
"""
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertEqual(data, {
            "seconds": "5s ago",
            "minutes": "5m ago",
            "hours": "3h ago",
        })
    def test_list_directory_sessions_renders_event_styled_rows_via_bun(self) -> None:
        script = f"""
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import ext, {{ writeSessionInfo, getSessionFileKey }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};
import {{ initTheme }} from "@earendil-works/pi-coding-agent";

initTheme("dark");

const tmpCwd = path.join(os.tmpdir(), "sd-" + Date.now());
fs.mkdirSync(tmpCwd, {{ recursive: true }});
const now = Date.now();
const sleeper = Bun.spawn(["sleep", "30"], {{ stdout: "ignore", stderr: "ignore" }});
writeSessionInfo({{
  sessionId: "alive-1",
  sessionName: "Display \u001b]0;pwned\u0007Test",
  pid: sleeper.pid,
  cwd: tmpCwd,
  startedAt: now - 300_000,
  updatedAt: now - 60_000,
  status: "running",
  latestGoal: "Verify event-style listed row",
  recap: "Recap first line for display",
  modifiedFiles: ["packages/utils/extensions/sessions.ts", "packages/utils/features/sessions.feature"],
}});

let toolDef;
ext({{
  registerTool: (def) => {{ if (def.name === "list_directory_sessions") toolDef = def; }},
  registerCommand: () => {{}},
  on: () => {{}},
}});

const result = await toolDef.execute("t1", {{}}, undefined, undefined, {{ cwd: tmpCwd }});
const fgCalls = [];
const bgCalls = [];
const theme = {{
  fg: (color, t) => {{ fgCalls.push(color); return t; }},
  bg: (color, t) => {{ bgCalls.push(color); return t; }},
  bold: (t) => t,
}};
const renderState = (expanded) =>
  toolDef
    .renderResult({{ content: result.content, details: result.details }}, {{ expanded, isPartial: false }}, theme, {{ isError: false }})
    .render(100)
    .join("\\n");
const collapsed = renderState(false);
const collapsedBgCalls = bgCalls.length;
const expanded = renderState(true);
const expandedBgCalls = bgCalls.length - collapsedBgCalls;
const errorRow = toolDef
  .renderResult(
    {{ content: [{{ type: "text", text: "registry read boom\\nsecond line" }}], details: {{}} }},
    {{ expanded: false, isPartial: false }},
    theme,
    {{ isError: true }},
  )
  .render(100)
  .join("\\n");
console.log(JSON.stringify({{
  count: result.details.count,
  callLines: toolDef.renderCall().render(100).length,
  fgCalls,
  bgCalls,
  collapsed,
  collapsedBgCalls,
  expanded,
  expandedBgCalls,
  errorRow,
}}));

sleeper.kill();
fs.rmSync(path.join(os.homedir(), ".pi", "agent", "directory-sessions", getSessionFileKey(tmpCwd)), {{ recursive: true, force: true }});
fs.rmSync(tmpCwd, {{ recursive: true, force: true }});
"""
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["callLines"], 0)
        collapsed_lines = data["collapsed"].split("\n")
        # Collapsed: the shared band paints a blank full-width row above and
        # below the single "[sessions] listed · ..." row with its expand hint.
        self.assertTrue(len(collapsed_lines) >= 3)
        self.assertEqual(collapsed_lines[0].strip(), "")
        self.assertEqual(collapsed_lines[-1].strip(), "")
        self.assertIn("[sessions] listed · 1 other session in sd-", data["collapsed"])
        self.assertIn("to expand", collapsed_lines[1])
        self.assertEqual(data["collapsedBgCalls"], len(collapsed_lines) + 1)
        self.assertIn("customMessageLabel", data["fgCalls"])
        # Expanded: same band, one bounded block per session; all display
        # fields sanitized (no escape sequences survive).
        expanded_lines = data["expanded"].split("\n")
        self.assertEqual(expanded_lines[0].strip(), "")
        self.assertEqual(expanded_lines[-1].strip(), "")
        self.assertEqual(data["expandedBgCalls"], len(expanded_lines) + 1)
        self.assertIn("· RUNNING · pid ", data["expanded"])
        self.assertIn("Display Test", data["expanded"])
        self.assertIn("Goal  Verify event-style listed row", data["expanded"])
        self.assertIn("Recap Recap first line for display", data["expanded"])
        self.assertIn("Files packages/utils/extensions/sessions.ts, packages/utils/features/sessions.feature", data["expanded"])
        self.assertIn("customMessageText", data["fgCalls"])
        self.assertNotIn("to expand", data["expanded"])
        self.assertNotIn("\x1b", data["expanded"])
        self.assertNotIn("pwned", data["expanded"])
        # Error results key off the render-context flag and render one plain line.
        self.assertIn("registry read boom", data["errorRow"])
        self.assertNotIn("second line", data["errorRow"])

    def test_registry_merges_records_by_pid_and_excludes_self_via_bun(self) -> None:
        script = f"""
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {{ writeSessionInfo, cleanAndListDirectorySessions, getSessionFileKey }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};

const tmpCwd = path.join(os.tmpdir(), "sd-merge-" + Date.now());
fs.mkdirSync(tmpCwd, {{ recursive: true }});
const now = Date.now();
const sleeper = Bun.spawn(["sleep", "30"], {{ stdout: "ignore", stderr: "ignore" }});

// Same live process registered twice: utils-style rich record (older)
// and keyboard-style bare glow record (newer).
writeSessionInfo({{
  sessionId: "ts_111", pid: sleeper.pid, cwd: tmpCwd,
  startedAt: now - 600_000, updatedAt: now - 60_000, status: "running",
  latestGoal: "Goal A", recap: "Recap A",
  modifiedFiles: ["a.ts", "b.ts", "c.ts", "d.ts", "e.ts"],
}});
writeSessionInfo({{
  sessionId: "111", pid: sleeper.pid, cwd: tmpCwd,
  startedAt: now - 600_000, updatedAt: now - 10_000, status: "running",
}});
// Bare glow record owned by THIS process under a foreign id convention.
writeSessionInfo({{
  sessionId: "self-glow", pid: process.pid, cwd: tmpCwd,
  startedAt: now, updatedAt: now, status: "running",
}});
// Corrupt record written directly: OSC payload in status, string pid/timestamps.
// Must normalize (not crash/prune) and merge into the sleeper's logical session.
const regDir = path.join(os.homedir(), ".pi", "agent", "directory-sessions", getSessionFileKey(tmpCwd));
fs.writeFileSync(path.join(regDir, "corrupt-1.json"), JSON.stringify({{
  sessionId: "corrupt-1", pid: String(sleeper.pid), cwd: tmpCwd,
  startedAt: "x", updatedAt: "y", status: "\u001b]0;pwned\u0007running",
}}));

const sessions = cleanAndListDirectorySessions(tmpCwd);
console.log(JSON.stringify({{
  count: sessions.length,
  pid: sessions[0]?.pid,
  status: sessions[0]?.status,
  goal: sessions[0]?.latestGoal,
  recap: sessions[0]?.recap,
  files: sessions[0]?.modifiedFiles?.length ?? 0,
  startedAtIsEarliest: sessions[0]?.startedAt === now - 600_000,
  updatedAtIsNewest: sessions[0]?.updatedAt === now - 10_000,
  pidIsNumber: typeof sessions[0]?.pid === "number",
  statusIsKnown: ["running", "idle", "settled", "exited"].includes(sessions[0]?.status),
  selfExcluded: !sessions.some((s) => s.pid === process.pid),
  noPwnedAnywhere: !JSON.stringify(sessions).includes("pwned"),
}}));

sleeper.kill();
fs.rmSync(path.join(os.homedir(), ".pi", "agent", "directory-sessions", getSessionFileKey(tmpCwd)), {{ recursive: true, force: true }});
fs.rmSync(tmpCwd, {{ recursive: true, force: true }});
"""
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        self.assertEqual(data, {
            "count": 1,
            "pid": data["pid"],
            "status": "running",
            "goal": "Goal A",
            "recap": "Recap A",
            "files": 5,
            "startedAtIsEarliest": True,
            "updatedAtIsNewest": True,
            "pidIsNumber": True,
            "statusIsKnown": True,
            "selfExcluded": True,
            "noPwnedAnywhere": True,
        })


if __name__ == "__main__":
    unittest.main()

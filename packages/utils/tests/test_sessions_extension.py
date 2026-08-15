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

    def test_ts_module_logic_via_bun(self) -> None:
        script = f"""
import {{ getRegistryDir, getSessionFileKey, formatCrossSessionRecap, SessionInfo }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};

const cwd = "/app/test-project";
const dirKey = getSessionFileKey(cwd);
const formatted = formatCrossSessionRecap([
  {{
    sessionId: "sess-1",
    sessionName: "Auth Feature",
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

    def test_registry_write_read_clean_via_bun(self) -> None:
        script = f"""
import {{ writeSessionInfo, cleanAndListDirectorySessions, isProcessAlive }} from {json.dumps(SESSIONS_EXTENSION.as_uri())};
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const tmpCwd = path.join(os.tmpdir(), "test-pi-session-dir-" + Date.now());
fs.mkdirSync(tmpCwd, {{ recursive: true }});

// Write an active session (current process PID)
writeSessionInfo({{
  sessionId: "alive-1",
  sessionName: "Active Task",
  pid: process.pid,
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
console.log(JSON.stringify({{
  count: activeSessions.length,
  aliveSessionId: activeSessions[0]?.sessionId,
  isSelfAlive: isProcessAlive(process.pid),
  isFakeDead: isProcessAlive(9999999),
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
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["aliveSessionId"], "alive-1")
        self.assertTrue(data["isSelfAlive"])
        self.assertFalse(data["isFakeDead"])


if __name__ == "__main__":
    unittest.main()

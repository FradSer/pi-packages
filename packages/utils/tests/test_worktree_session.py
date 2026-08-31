import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
SESSION_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree-session.ts"


def run_ts(script: str) -> dict:
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


def make_git_repo(path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    (path / "README.md").write_text("main\n")
    git("add", "-A")
    git("commit", "-qm", "init")


class WorktreeSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="pi-wts-")).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.session_dir = self.base / "sessions"
        self.session_dir.mkdir()
        make_git_repo(self.repo)

    def test_parse_worktree_list_preserves_bare_and_branch_metadata(self) -> None:
        result = run_ts(f"""
import {{ parseWorktreeList }} from {json.dumps(SESSION_EXTENSION.as_uri())};
console.log(JSON.stringify(parseWorktreeList([
  "worktree /tmp/main",
  "HEAD abc",
  "branch refs/heads/main",
  "",
  "worktree /tmp/feature",
  "HEAD def",
  "branch refs/heads/feature",
  "",
  "worktree /tmp/store.git",
  "bare",
].join("\\n"))));
""")
        self.assertEqual(
            [
                {"bare": False, "branch": "main", "root": "/tmp/main"},
                {"bare": False, "branch": "feature", "root": "/tmp/feature"},
                {"bare": True, "root": "/tmp/store.git"},
            ],
            result,
        )

    def test_resolve_enter_target_creates_managed_path_and_rejects_unregistered_path(self) -> None:
        result = run_ts(f"""
import {{ resolveEnterTarget }} from {json.dumps(SESSION_EXTENSION.as_uri())};
const created = resolveEnterTarget({json.dumps(str(self.repo))}, {{ name: "feature/auth" }});
const rejected = resolveEnterTarget({json.dumps(str(self.repo))}, {{ path: "../not-a-worktree" }});
console.log(JSON.stringify({{ created, rejected }}));
""")
        self.assertTrue(result["created"]["created"])
        self.assertEqual("feature-auth", result["created"]["name"])
        self.assertTrue(result["created"]["path"].endswith("/.pi/worktrees/feature-auth"))
        self.assertIn("not a registered git worktree", result["rejected"]["error"])

    def test_new_worktree_path_is_shared_when_entering_from_an_existing_worktree(self) -> None:
        nested = self.base / "existing"
        subprocess.run(["git", "worktree", "add", str(nested), "-b", "existing"],
                       cwd=self.repo, capture_output=True, text=True, check=True)
        result = run_ts(f"""
import {{ resolveEnterTarget }} from {json.dumps(SESSION_EXTENSION.as_uri())};
console.log(JSON.stringify(resolveEnterTarget({json.dumps(str(nested))}, {{ name: "next" }})));
""")
        self.assertTrue(result["created"])
        self.assertTrue(result["path"].startswith(str(self.repo / ".pi" / "worktrees")))
        self.assertFalse(result["path"].startswith(str(nested / ".pi")))

    def test_enter_command_creates_worktree_forks_session_and_records_parent(self) -> None:
        script = f"""
import fs from "node:fs";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
source.appendMessage({{ role: "user", content: "start", timestamp: Date.now() }});
source.appendMessage({{ role: "assistant", content: [{{ type: "text", text: "ready" }}], api: "test", provider: "test", model: "test", usage: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }} }}, stopReason: "stop", timestamp: Date.now() }});
const sourceFile = source.getSessionFile();
let commands = {{}};
const fakePi = {{
  registerCommand(name, options) {{ commands[name] = options; }},
  registerTool() {{}},
  sendUserMessage() {{}},
}};
registerWorktreeSession(fakePi);
let switchedFile = null;
const notifications = [];
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ notifications.push({{ message, type }}); }},
    select: async () => "Keep worktree",
  }},
  async switchSession(file, options) {{
    switchedFile = file;
    await options.withSession({{ ui: {{ notify() {{}} }} }});
    return {{ cancelled: false }};
  }},
}};
await commands["enter-worktree"].handler("feature-auth", ctx);
const replacement = SessionManager.open(switchedFile);
const header = replacement.getHeader();
const entries = replacement.getBranch();
const state = entries.find((entry) => entry.type === "custom" && entry.customType === "pi-utils-worktree-session");
console.log(JSON.stringify({{
  switchedFile,
  cwd: header.cwd,
  parentSession: header.parentSession,
  state: state.data,
  worktreeExists: fs.existsSync(header.cwd),
  branch: state.data.branch,
  notifications,
}}));
"""
        result = run_ts(script)
        self.assertTrue(result["worktreeExists"])
        self.assertTrue(result["cwd"].endswith("/.pi/worktrees/feature-auth"))
        self.assertEqual(result["parentSession"], result["state"]["parentSession"])
        self.assertEqual("pi/worktree/feature-auth", result["branch"])
        self.assertEqual([], result["notifications"])

        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "remove", "--force", result["cwd"]],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "branch", "-D", result["branch"]],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_exit_worktree_is_disclosed_only_for_replacement_sessions(self) -> None:
        script = f"""
import ext from {json.dumps(SESSION_EXTENSION.as_uri())};
const handlers = {{}};
let activeTools = ["read", "enter_worktree", "exit_worktree", "unrelated_tool"];
const pi = {{
  registerCommand() {{}}, registerTool() {{}},
  on(name, handler) {{ handlers[name] = handler; }},
  getActiveTools() {{ return activeTools; }},
  setActiveTools(names) {{ activeTools = names; }},
}};
ext(pi);
await handlers.session_start({{}}, {{ sessionManager: {{ getBranch: () => [] }} }});
const initiallyInactive = [...activeTools];
const replacementState = {{
  baseCommit: "abc", created: true, parentSession: "/tmp/parent.jsonl", path: "/tmp/worktree", repoRoot: "/tmp/repo",
}};
await handlers.session_start({{}}, {{ sessionManager: {{ getBranch: () => [{{ type: "custom", customType: "pi-utils-worktree-session", data: replacementState }}] }} }});
const replacementActive = [...activeTools];
await handlers.session_shutdown({{}}, {{}});
console.log(JSON.stringify({{ initiallyInactive, replacementActive, shutdown: activeTools }}));
"""
        result = run_ts(script)
        self.assertIn("enter_worktree", result["initiallyInactive"])
        self.assertNotIn("exit_worktree", result["initiallyInactive"])
        self.assertIn("enter_worktree", result["replacementActive"])
        self.assertIn("exit_worktree", result["replacementActive"])
        self.assertIn("unrelated_tool", result["replacementActive"])
        self.assertIn("enter_worktree", result["shutdown"])
        self.assertNotIn("exit_worktree", result["shutdown"])
        self.assertIn("unrelated_tool", result["shutdown"])

    def test_tools_queue_transitions_instead_of_claiming_completion(self) -> None:
        script = f"""
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
initTheme("dark");
const tools = {{}};
const sent = [];
const fakePi = {{
  registerCommand() {{}},
  registerTool(tool) {{ tools[tool.name] = tool; }},
  sendUserMessage(message, options) {{ sent.push({{ message, options }}); }},
}};
registerWorktreeSession(fakePi);
const enter = await tools.enter_worktree.execute("1", {{ name: "feature-auth" }});
const exit = await tools.exit_worktree.execute("2", {{}});
const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
const enterRow = tools.enter_worktree.renderResult(
  enter,
  {{ expanded: false, isPartial: false }},
  theme,
  {{ args: {{ name: "feature-auth" }}, isError: false }},
).render(120).join("\\n");
const exitRow = tools.exit_worktree.renderResult(
  exit,
  {{ expanded: false, isPartial: false }},
  theme,
  {{ args: {{}}, isError: false }},
).render(120).join("\\n");
console.log(JSON.stringify({{ sent, enter, exit, enterRow, exitRow }}));
"""
        result = run_ts(script)
        self.assertEqual("/enter-worktree {\"name\":\"feature-auth\"}", result["sent"][0]["message"])
        self.assertTrue(result["sent"][0]["options"]["expandPromptTemplates"])
        self.assertEqual("/exit-worktree", result["sent"][1]["message"])
        self.assertTrue(result["sent"][1]["options"]["expandPromptTemplates"])
        self.assertEqual("queued", result["enter"]["details"]["status"])
        self.assertEqual("queued", result["exit"]["details"]["status"])
        self.assertTrue("[worktree] enter · feature-auth" in result["enterRow"])
        self.assertIn("to expand", result["enterRow"])
        self.assertTrue("[worktree] exit · current worktree" in result["exitRow"])
        self.assertIn("to expand", result["exitRow"])

    def test_exit_command_switches_to_parent_and_can_keep_worktree(self) -> None:
        script = f"""
import fs from "node:fs";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};
const repo = {json.dumps(str(self.repo))};
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
source.appendMessage({{ role: "user", content: "start", timestamp: Date.now() }});
source.appendMessage({{ role: "assistant", content: [{{ type: "text", text: "ready" }}], api: "test", provider: "test", model: "test", usage: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }} }}, stopReason: "stop", timestamp: Date.now() }});
const sourceFile = source.getSessionFile();
fs.mkdirSync({json.dumps(str(self.base / ".pi" / "worktrees" / "kept"))}, {{ recursive: true }});
const target = SessionManager.forkFrom(sourceFile, {json.dumps(str(self.base / ".pi" / "worktrees" / "kept"))});
const targetFile = target.getSessionFile();
target.appendCustomEntry("pi-utils-worktree-session", {{
  baseCommit: "HEAD", created: false, parentSession: sourceFile,
  path: {json.dumps(str(self.base / ".pi" / "worktrees" / "kept"))},
  repoRoot: repo,
}});
let commands = {{}};
let switched = null;
const fakePi = {{ registerCommand(name, options) {{ commands[name] = options; }}, registerTool() {{}}, sendUserMessage() {{}} }};
registerWorktreeSession(fakePi);
const ctx = {{
  cwd: {json.dumps(str(self.base / ".pi" / "worktrees" / "kept"))},
  hasUI: false,
  sessionManager: SessionManager.open(targetFile),
  ui: {{ notify() {{}} }},
  async switchSession(file) {{ switched = file; return {{ cancelled: false }}; }},
}};
await commands["exit-worktree"].handler("", ctx);
console.log(JSON.stringify({{ switched, sourceFile, exists: fs.existsSync(ctx.cwd) }}));
"""
        result = run_ts(script)
        self.assertEqual(result["sourceFile"], result["switched"])
        self.assertTrue(result["exists"])

    def test_render_result_survives_class_based_theme(self) -> None:
        script = f"""
import ext from {json.dumps(SESSION_EXTENSION.as_uri())};
import {{ initTheme }} from "@earendil-works/pi-coding-agent";

initTheme("dark");
let toolDef;
ext({{ registerTool: (def) => {{ if (def.name === "enter_worktree") toolDef = def; }}, registerCommand() {{}} }});
class ClassTheme {{
  constructor() {{ this.bgColors = new Map([["customMessageBg", "\\u001B[44m"]]); }}
  fg(_color, text) {{ return text; }}
  bold(text) {{ return text; }}
  bg(color, text) {{ return this.bgColors.get(color) + text + "\\u001B[49m"; }}
}}
const rendered = toolDef
  .renderResult(
    {{ content: [{{ type: "text", text: "Queued enter_worktree; the session transition is pending." }}], details: {{}} }},
    {{ expanded: true, isPartial: false }},
    new ClassTheme(),
    {{ isError: false, args: {{ name: "demo" }} }},
  )
  .render(100)
  .join("\\n");
console.log(JSON.stringify({{ painted: rendered.includes("\\u001B[44m"), rendered }}));
"""
        result = run_ts(script)
        self.assertTrue(result["painted"], result["rendered"])


if __name__ == "__main__":
    unittest.main()

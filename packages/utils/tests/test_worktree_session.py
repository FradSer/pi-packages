import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
SESSION_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree-session.ts"
GIT_EXTENSION = UTILS_PKG_DIR / "extensions" / "git" / "worktrees.ts"


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

    def test_real_runtime_keeps_all_edits_inside_replacement_worktree(self) -> None:
        for order in ("enter-first", "write-first", "malformed", "follow-up", "abort", "post-switch-error", "rebind-error"):
            with self.subTest(order=order):
                result = subprocess.run(
                    ["pnpm", "exec", "tsx", str(UTILS_PKG_DIR / "tests" / "worktree_lifecycle.mts"), order],
                    cwd=REPO, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_parse_worktree_list_preserves_bare_and_branch_metadata(self) -> None:
        result = run_ts(f"""
import {{ parseWorktreeList }} from {json.dumps(GIT_EXTENSION.as_uri())};
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
  isIdle: () => true,
  async waitForIdle() {{}},
  async switchSession(file, options) {{
    switchedFile = file;
    await options.withSession({{ ui: {{ notify() {{}} }}, async sendMessage() {{}} }});
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
        self.assertEqual("feature-auth", result["branch"])
        # This repository ignores nothing, so the unmanaged-directory risk is
        # reported instead of silently editing .gitignore.
        self.assertEqual(
            [(n["type"], n["message"]) for n in result["notifications"]],
            [("warning", ".pi/worktrees/ is not git-ignored in this repository — add it to .gitignore or the linked worktree shows up as untracked in the parent checkout")],
        )

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

    def test_enter_command_refuses_a_name_that_cannot_form_a_branch(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
const sourceFile = source.getSessionFile();
const notifications = [];
const commands = {{}};
registerWorktreeSession({{
  registerCommand(name, options) {{ commands[name] = options; }},
  registerTool() {{}},
  sendUserMessage() {{}},
}});
let switched = false;
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ notifications.push([type, message]); }},
    select: async () => "Keep worktree",
  }},
  isIdle: () => true,
  async waitForIdle() {{}},
  async switchSession() {{ switched = true; return {{ cancelled: false }}; }},
}};
await commands["enter-worktree"].handler(".hidden", ctx);
console.log(JSON.stringify({{
  notifications,
  switched,
  repoState: fs.existsSync(path.join(repo, ".pi")),
}}));
"""
        result = run_ts(script)
        # One clear reason, before git is asked to create anything: a leading dot
        # cannot form the branch this command would hand to `git worktree add -b`.
        self.assertEqual(
            [tuple(notification) for notification in result["notifications"]],
            [("error", "worktree name cannot form a valid git branch: .hidden")],
        )
        self.assertFalse(result["switched"])
        self.assertFalse(result["repoState"])
        branches = subprocess.run(
            ["git", "-C", str(self.repo), "branch", "--list", ".hidden"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual("", branches.stdout.strip())

    def test_enter_command_refuses_a_name_whose_branch_already_exists(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo), "branch", "feature-auth"],
            capture_output=True,
            text=True,
            check=True,
        )
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
const sourceFile = source.getSessionFile();
const notifications = [];
const commands = {{}};
registerWorktreeSession({{
  registerCommand(name, options) {{ commands[name] = options; }},
  registerTool() {{}},
  sendUserMessage() {{}},
}});
let switched = false;
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ notifications.push([type, message]); }},
    select: async () => "Keep worktree",
  }},
  isIdle: () => true,
  async waitForIdle() {{}},
  async switchSession() {{ switched = true; return {{ cancelled: false }}; }},
}};
await commands["enter-worktree"].handler("feature-auth", ctx);
console.log(JSON.stringify({{
  notifications,
  switched,
  repoState: fs.existsSync(path.join(repo, ".pi")),
  branches: Bun.spawnSync(["git", "-C", repo, "branch", "--list"]).stdout.toString().trim().split("\\n"),
}}));
"""
        result = run_ts(script)
        # The branch is the name itself, so an existing branch is refused with the
        # way out instead of git's `a branch named ... already exists` fatal.
        self.assertEqual(
            [tuple(notification) for notification in result["notifications"]],
            [("error", "branch already exists: feature-auth. Choose another name, or pass path to enter an existing worktree.")],
        )
        self.assertFalse(result["switched"])
        self.assertFalse(result["repoState"])
        self.assertEqual(["* main", "feature-auth"], sorted(result["branches"]))

    def test_enter_command_skips_the_ignore_warning_when_already_ignored(self) -> None:
        (self.repo / ".gitignore").write_text(".pi/\n", encoding="utf-8")
        report = run_ts(f"""
import fs from "node:fs";
import path from "node:path";
import {{ isManagedWorktreesIgnored, managedWorktreesDir }} from {json.dumps(GIT_EXTENSION.as_uri())};
const root = {json.dumps(str(self.repo))};
console.log(JSON.stringify({{
  ignored: isManagedWorktreesIgnored(root),
  managed: managedWorktreesDir(root),
}}));
""")
        self.assertTrue(report["ignored"])
        self.assertEqual(report["managed"], str(self.repo / ".pi" / "worktrees"))

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
const handlers = {{}};
const fakePi = {{
  on(name, handler) {{ handlers[name] = handler; }},
  registerCommand() {{}},
  registerTool(tool) {{ tools[tool.name] = tool; }},
  sendUserMessage(message, options) {{ sent.push({{ message, options }}); }},
}};
registerWorktreeSession(fakePi);
const enter = await tools.enter_worktree.execute("1", {{ name: "feature-auth" }});
if (sent.length !== 0) throw new Error("command dispatched before settlement");
await handlers.agent_settled();
const exit = await tools.exit_worktree.execute("2", {{}});
if (sent.length !== 1) throw new Error("exit dispatched before settlement");
await handlers.agent_settled();
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
        self.assertTrue(result["enter"]["terminate"])
        self.assertTrue(result["exit"]["terminate"])
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
  isIdle: () => true,
  async waitForIdle() {{}},
  async switchSession(file) {{ switched = file; return {{ cancelled: false }}; }},
}};
await commands["exit-worktree"].handler("", ctx);
console.log(JSON.stringify({{ switched, sourceFile, exists: fs.existsSync(ctx.cwd) }}));
"""
        result = run_ts(script)
        self.assertEqual(result["sourceFile"], result["switched"])
        self.assertTrue(result["exists"])

    def test_enter_command_settles_before_switching_and_cleans_a_cancelled_switch(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const worktreeRoot = fs.realpathSync(repo);
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
source.appendMessage({{ role: "user", content: "start", timestamp: Date.now() }});
source.appendMessage({{ role: "assistant", content: [{{ type: "text", text: "ready" }}], api: "test", provider: "test", model: "test", usage: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }} }}, stopReason: "stop", timestamp: Date.now() }});
const sourceFile = source.getSessionFile();
const events = [];
const commands = {{}};
registerWorktreeSession({{
  registerCommand(name, options) {{ commands[name] = options; }},
  registerTool() {{}},
  sendUserMessage() {{}},
}});
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ events.push(["notify", type, message]); }},
    select: async () => "Keep worktree",
  }},
  // A command runs even while the agent streams; the switch must wait for the
  // turn to finish so the fork includes it.
  isIdle: () => false,
  async waitForIdle() {{ events.push(["waited"]); }},
  async switchSession(file, options) {{
    events.push(["switch", file]);
    await options.withSession({{ ui: {{ notify() {{}} }}, async sendMessage() {{}} }});
    return {{ cancelled: true }};
  }},
}};
await commands["enter-worktree"].handler("cancelled-switch", ctx);

const worktree = path.join(worktreeRoot, ".pi", "worktrees", "cancelled-switch");
const switchFile = events.find((event) => event[0] === "switch")[1];
const waitingNotice = events.find((event) => event[0] === "notify" && event[2].includes("Waiting for the current turn"));
const branch = Bun.spawnSync(["git", "-C", repo, "branch", "--list", "cancelled-switch"]).stdout.toString().trim();
// An absent wait yields -1, which would satisfy a plain `<` comparison.
const waitedAt = events.findIndex((event) => event[0] === "waited");
const switchedAt = events.findIndex((event) => event[0] === "switch");
console.log(JSON.stringify({{
  order: events.map((event) => event[0]),
  waitedBeforeSwitch: waitedAt !== -1 && switchedAt !== -1 && waitedAt < switchedAt,
  waitingNotice: waitingNotice ? waitingNotice[1] : null,
  worktreeRemoved: !fs.existsSync(worktree),
  forkRemoved: !fs.existsSync(switchFile),
  branchRemoved: branch === "",
}}));
"""
        result = run_ts(script)
        self.assertTrue(result["waitedBeforeSwitch"], result["order"])
        self.assertEqual(result["waitingNotice"], "info")
        self.assertTrue(result["worktreeRemoved"])
        self.assertTrue(result["forkRemoved"])
        self.assertTrue(result["branchRemoved"])

    def test_failed_switch_keeps_and_reports_a_created_worktree(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const worktreeRoot = fs.realpathSync(repo);
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
source.appendMessage({{ role: "user", content: "start", timestamp: Date.now() }});
source.appendMessage({{ role: "assistant", content: [{{ type: "text", text: "ready" }}], api: "test", provider: "test", model: "test", usage: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }} }}, stopReason: "stop", timestamp: Date.now() }});
const sourceFile = source.getSessionFile();
const notifications = [];
const commands = {{}};
registerWorktreeSession({{
  registerCommand(name, options) {{ commands[name] = options; }},
  registerTool() {{}},
  sendUserMessage() {{}},
}});
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ notifications.push({{ message, type }}); }},
    select: async () => "Keep worktree",
  }},
  isIdle: () => true,
  async waitForIdle() {{}},
  // The runtime may already have been replaced when the host rebinding fails.
  async switchSession() {{ throw new Error("host rebind failed"); }},
}};
await commands["enter-worktree"].handler("kept-after-failure", ctx);

const worktree = path.join(worktreeRoot, ".pi", "worktrees", "kept-after-failure");
const warnings = notifications.filter((entry) => entry.type === "warning").map((entry) => entry.message);
console.log(JSON.stringify({{
  worktreeKept: fs.existsSync(worktree),
  warnings,
  errors: notifications.filter((entry) => entry.type === "error").map((entry) => entry.message),
}}));
"""
        result = run_ts(script)
        self.assertTrue(result["worktreeKept"])
        self.assertEqual(result["errors"], ["host rebind failed"])
        self.assertEqual(len(result["warnings"]), 2)
        self.assertTrue(any("created worktree is kept" in warning and "kept-after-failure" in warning for warning in result["warnings"]))

    def test_a_second_switch_is_refused_while_one_is_in_flight(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(SESSION_EXTENSION.as_uri())};

const repo = {json.dumps(str(self.repo))};
const worktreeRoot = fs.realpathSync(repo);
const source = SessionManager.create(repo, {json.dumps(str(self.session_dir))});
source.appendMessage({{ role: "user", content: "start", timestamp: Date.now() }});
source.appendMessage({{ role: "assistant", content: [{{ type: "text", text: "ready" }}], api: "test", provider: "test", model: "test", usage: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {{ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }} }}, stopReason: "stop", timestamp: Date.now() }});
const sourceFile = source.getSessionFile();
const notifications = [];
const commands = {{}};
let switches = 0;
let releaseWait = () => {{}};
// Both commands wait for the same streaming turn.
const gate = new Promise((resolve) => {{ releaseWait = resolve; }});
registerWorktreeSession({{ registerCommand(name, options) {{ commands[name] = options; }}, registerTool() {{}}, sendUserMessage() {{}} }});
const ctx = {{
  cwd: repo,
  hasUI: true,
  sessionManager: {{ getSessionFile: () => sourceFile, getBranch: () => [] }},
  ui: {{
    notify(message, type) {{ notifications.push({{ message, type }}); }},
    select: async () => "Keep worktree",
  }},
  isIdle: () => false,
  waitForIdle: () => gate,
  async switchSession(file, options) {{
    switches += 1;
    await options.withSession({{ ui: {{ notify() {{}} }}, async sendMessage() {{}} }});
    return {{ cancelled: true }};
  }},
}};
const first = commands["enter-worktree"].handler("one", ctx);
const second = commands["enter-worktree"].handler("two", ctx);
const refused = notifications.filter((entry) => entry.message.includes("still in progress"));
releaseWait();
await Promise.all([first, second]);
console.log(JSON.stringify({{
  switches,
  refused: refused.map((entry) => entry.type),
  firstWorktree: fs.existsSync(path.join(worktreeRoot, ".pi", "worktrees", "one")),
  secondWorktree: fs.existsSync(path.join(worktreeRoot, ".pi", "worktrees", "two")),
}}));
"""
        result = run_ts(script)
        self.assertEqual(result["switches"], 1, result)
        self.assertEqual(result["refused"], ["warning"])
        # The refused command never reaches the worktree it asked for.
        self.assertFalse(result["secondWorktree"])

    def test_render_result_survives_class_based_theme(self) -> None:
        script = f"""
import ext from {json.dumps(SESSION_EXTENSION.as_uri())};
import {{ initTheme }} from "@earendil-works/pi-coding-agent";

initTheme("dark");
let toolDef;
ext({{ registerTool: (def) => {{ if (def.name === "enter_worktree") toolDef = def; }}, registerCommand() {{}} }});
class ClassTheme {{
  constructor() {{ this.bgColors = new Map([["toolSuccessBg", "\\u001B[44m"]]); }}
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

    def test_queued_transition_blocks_siblings_and_survives_settlement(self) -> None:
        script = f"""
import ext from {json.dumps(SESSION_EXTENSION.as_uri())};

const handlers = {{}};
const commands = {{}};
const tools = {{}};
const sent = [];
const notifications = [];
const pi = {{
  on(name, handler) {{ handlers[name] = handler; }},
  registerCommand(name, spec) {{ commands[name] = spec; }},
  registerTool(spec) {{ tools[spec.name] = spec; }},
  sendUserMessage(content) {{ sent.push(content); }},
  getActiveTools() {{ return []; }},
  setActiveTools() {{}},
}};
ext(pi);

const ctx = {{ ui: {{ notify(message, type) {{ notifications.push({{ message, type }}); }} }} }};
const toolCall = (name, id) => ({{ type: "toolCall", id, name, arguments: {{}} }});
await handlers.message_end({{ message: {{ role: "assistant", content: [toolCall("enter_worktree", "call-1")] }} }}, ctx);

// A sibling tool in the same batch is refused and the run terminates.
const beforeSibling = handlers.tool_call({{ toolName: "bash", toolCallId: "call-2" }}, ctx);

// The queued transition itself succeeds and terminates the batch.
const queued = await tools.enter_worktree.execute("call-1", {{ name: "isolated" }}, undefined);
const afterQueue = handlers.tool_call({{ toolName: "read", toolCallId: "call-3" }}, ctx);

// Settling dispatches the queued command.
await handlers.agent_settled({{}}, ctx);
const dispatched = [...sent];
const afterSettle = [...notifications];

// A second command while a transition is queued must not race it.
sent.length = 0;
await handlers.message_end({{ message: {{ role: "assistant", content: [toolCall("exit_worktree", "call-4")] }} }}, ctx);
await tools.exit_worktree.execute("call-4", {{}}, undefined);
const blockedByPending = await commands["enter-worktree"].handler("other", ctx);
const blockedExit = await commands["exit-worktree"].handler("", ctx);

console.log(JSON.stringify({{
  beforeSibling,
  queuedDetails: queued.details,
  afterQueue,
  dispatched,
  afterSettle,
  blockedByPending: notifications.at(-1),
  blockedExitCount: notifications.length,
}}));
"""
        result = run_ts(script)
        # The batch barrier holds before and after the transition tool runs.
        self.assertTrue(result["beforeSibling"]["block"])
        self.assertTrue(result["beforeSibling"]["terminate"])
        self.assertIn("Worktree transition pending", result["beforeSibling"]["reason"])
        self.assertEqual(result["afterQueue"]["block"], True)
        self.assertEqual(result["queuedDetails"]["status"], "queued")
        # Settlement, not the tool call, dispatches the transition.
        self.assertEqual(result["dispatched"], ['/enter-worktree {"name":"isolated"}'])
        self.assertEqual(result["afterSettle"], [])
        # A command attempted while a transition is queued is refused.
        self.assertIn("is queued and has not been applied yet", result["blockedByPending"]["message"])
        self.assertEqual(result["blockedByPending"]["type"], "warning")
        self.assertEqual(result["blockedExitCount"], 2)

    def test_abort_drops_the_queued_transition_and_reports_it(self) -> None:
        script = f"""
import ext from {json.dumps(SESSION_EXTENSION.as_uri())};

const handlers = {{}};
const tools = {{}};
const sent = [];
const notifications = [];
const pi = {{
  on(name, handler) {{ handlers[name] = handler; }},
  registerCommand() {{}},
  registerTool(spec) {{ tools[spec.name] = spec; }},
  sendUserMessage(content) {{ sent.push(content); }},
  getActiveTools() {{ return []; }},
  setActiveTools() {{}},
}};
ext(pi);

const ctx = {{ ui: {{ notify(message, type) {{ notifications.push({{ message, type }}); }} }} }};
const controller = new AbortController();
controller.abort();
await tools.enter_worktree.execute("call-1", {{ name: "isolated" }}, controller.signal);
await handlers.agent_settled({{}}, ctx);
console.log(JSON.stringify({{ sent, notifications }}));
"""
        result = run_ts(script)
        # The model was told the transition was pending; an abort ends the run
        # without applying it, so nothing is dispatched and the user is told.
        self.assertEqual(result["sent"], [])
        self.assertEqual(len(result["notifications"]), 1)
        self.assertEqual(result["notifications"][0]["type"], "warning")
        self.assertIn("enter_worktree", result["notifications"][0]["message"])
        self.assertIn("dropped", result["notifications"][0]["message"])


if __name__ == "__main__":
    unittest.main()

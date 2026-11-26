# --- Merged from test_worktree_extension.py ---
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
WORKTREE_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree.ts"


def rewrite(command: str) -> str:
    script = f"""
import {{ planWorktreeAddRedirect }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
const cmd = {json.dumps(command)};
console.log(JSON.stringify(planWorktreeAddRedirect(cmd)?.command ?? cmd));
"""
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


def rewrite_in(command: str, cwd: str) -> str:
    script = f"""
import {{ planWorktreeAddRedirect }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
const cmd = {json.dumps(command)};
console.log(JSON.stringify(planWorktreeAddRedirect(cmd, {{ cwd: {json.dumps(cwd)} }})?.command ?? cmd));
"""
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


def run_ts(script: str) -> dict:
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
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
    (path / "README.md").write_text("main\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")


class TestWorktreeExtension(unittest.TestCase):
    def test_rewrites_plain_add_into_pi_worktrees(self) -> None:
        self.assertEqual(
            rewrite("git worktree add ../foo feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
        )

    def test_preserves_lock_reason_branch_and_commitish(self) -> None:
        command = 'git worktree add --lock --reason "active task" -b feature/foo ../foo HEAD~1'
        self.assertEqual(
            rewrite(command),
            'mkdir -p .pi/worktrees && git worktree add --lock --reason "active task" -b feature/foo .pi/worktrees/foo HEAD~1',
        )

    def test_preserves_orphan_as_a_valueless_flag(self) -> None:
        self.assertEqual(
            rewrite("git worktree add --orphan ../foo"),
            "mkdir -p .pi/worktrees && git worktree add --orphan .pi/worktrees/foo",
        )
        self.assertEqual(
            rewrite("git worktree add --orphan=topic ../foo"),
            "git worktree add --orphan=topic ../foo",
        )

    def test_preserves_every_documented_boolean_worktree_add_option(self) -> None:
        command = (
            "git worktree add --no-force --no-detach --no-checkout --no-lock "
            "--no-orphan --no-quiet --no-track --no-guess-remote "
            "--no-relative-paths -B topic ../foo HEAD"
        )
        self.assertEqual(
            rewrite(command),
            "mkdir -p .pi/worktrees && git worktree add --no-force --no-detach "
            "--no-checkout --no-lock --no-orphan --no-quiet --no-track "
            "--no-guess-remote --no-relative-paths -B topic .pi/worktrees/foo HEAD",
        )

    def test_handles_quoted_and_escaped_paths_without_splitting_them(self) -> None:
        self.assertEqual(
            rewrite('git worktree add "../feature branch" "feature/foo with space"'),
            "mkdir -p .pi/worktrees && git worktree add '.pi/worktrees/feature branch' \"feature/foo with space\"",
        )
        self.assertEqual(
            rewrite(r"git worktree add ../feature\ branch feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add '.pi/worktrees/feature branch' feature/foo",
        )

    def test_preserves_double_dash_before_a_dash_prefixed_path(self) -> None:
        self.assertEqual(
            rewrite("git worktree add -- ../-worktree feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add -- .pi/worktrees/-worktree feature/foo",
        )

    def test_already_redirected_and_unsafe_basename_paths_are_left_untouched(self) -> None:
        for command in (
            "git worktree add .pi/worktrees/foo feature/foo",
            "git worktree add ./.pi/worktrees/foo feature/foo",
            "git worktree add ../project/.pi/worktrees feature/foo",
            "git worktree add .pi/worktrees feature/foo",
            "git worktree add ../.. feature/foo",
        ):
            with self.subTest(command=command):
                self.assertEqual(rewrite(command), command)

    def test_unsupported_shell_syntax_and_unknown_options_are_left_untouched(self) -> None:
        commands = (
            "git worktree add ../foo feature/foo && git status",
            "git worktree add ../foo feature/foo; git status",
            "git worktree add ../foo feature/foo | tee output",
            "git worktree add ../foo feature/foo > output",
            "git worktree add ../foo $(git branch --show-current)",
            "git worktree add --unknown ../foo feature/foo",
            "git worktree add --reason= ../foo feature/foo",
            "git worktree add --reason --lock ../foo feature/foo",
            "git worktree add ../* feature/foo",
            "git -C repo worktree add ../foo feature/foo",
            "git worktree add '../unterminated feature/foo",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(rewrite(command), command)

    def test_non_worktree_commands_are_ignored(self) -> None:
        self.assertEqual(rewrite("git worktree list"), "git worktree list")

    def test_redirect_targets_the_repository_root_not_the_shell_cwd(self) -> None:
        # The bash tool runs in the session cwd, so a command issued from a
        # subdirectory must still land in the repository's own managed
        # directory — the same place /enter-worktree and the isolation filters
        # look.
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "repo"
            nested = root / "packages" / "app"
            nested.mkdir(parents=True)
            make_git_repo(root)
            canonical_root = Path(os.path.realpath(root))
            managed = canonical_root / ".pi" / "worktrees"

            from_root = rewrite_in("git worktree add ../foo feature/foo", str(root))
            self.assertEqual(
                from_root,
                "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
            )

            from_subdirectory = rewrite_in("git worktree add ../foo feature/foo", str(nested))
            self.assertEqual(
                from_subdirectory,
                f"mkdir -p {managed} && git worktree add {managed}/foo feature/foo",
            )
            # Neither spelling depends on where the shell happens to be.
            self.assertIn(str(managed), from_subdirectory)
            self.assertNotIn(str(nested / ".pi"), from_subdirectory)

    def test_outside_a_repository_the_relative_spelling_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(
                rewrite_in("git worktree add ../foo feature/foo", outside),
                "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
            )

    def test_notification_names_the_directory_the_worktree_lands_in(self) -> None:
        # From a subdirectory the redirect is absolute, so the report must not
        # repeat the relative spelling that the command did not use.
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "repo"
            nested = root / "packages" / "app"
            nested.mkdir(parents=True)
            make_git_repo(root)
            managed = Path(os.path.realpath(root)) / ".pi" / "worktrees"
            script = f"""
import fs from "node:fs";
import register from {json.dumps(WORKTREE_EXTENSION.as_uri())};
const handlers = new Map();
const notifications = [];
register({{ on: (name, handler) => handlers.set(name, handler) }});
const event = {{ toolName: "bash", input: {{ command: "git worktree add ../feature feature" }} }};
const ctx = {{
  cwd: {json.dumps(str(nested))},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
}};
const blocked = await handlers.get("tool_call")(event, ctx);
console.log(JSON.stringify({{
  command: event.input.command,
  blocked: blocked ?? null,
  notifications,
  managed: {json.dumps(str(managed))},
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
            if result.returncode:
                raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
            report = json.loads(result.stdout)
            self.assertIn(f"{report['managed']}/feature", report["command"])
            info = [entry for entry in report["notifications"] if entry["type"] == "info"]
            self.assertEqual(len(info), 1)
            self.assertIn(f"{report['managed']}/feature", info[0]["message"])
            self.assertNotIn("redirected to .pi/worktrees/", info[0]["message"])



SESSION_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree-session.ts"

AUTO_ENTRY_PRELUDE = """
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {session};
import registerWorktreeRedirect from {worktree};

const repo = {repo};
const sessions = {sessions};
const handlers = {};
const commands = {};
const tools = {};
const messageRenderers = {};
const sent = [];
const notifications = [];
let activeTools = ["read", "enter_worktree", "exit_worktree"];
// Pi calls some of these unbound, so the fake closes over its state instead of
// reading it from this.
const pi = {
  handlers, commands, tools, sent, notifications,
  on(name, handler) { (handlers[name] ||= []).push(handler); },
  registerCommand(name, options) { commands[name] = options; },
  registerTool(tool) { tools[tool.name] = tool; },
  registerMessageRenderer(type, renderer) { messageRenderers[type] = renderer; },
  sendUserMessage(message, options) { sent.push({ message, options }); },
  getActiveTools() { return activeTools; },
  setActiveTools(names) { activeTools = names; },
};
// index.ts registers the session extension first, so its message_end handler
// runs before the redirect reserves the barrier for the same message.
const entryHost = registerWorktreeSession(pi);
registerWorktreeRedirect(pi, entryHost);

async function emit(name, event, ctx) {
  const results = [];
  for (const handler of handlers[name] ?? []) results.push(await handler(event, ctx));
  return results;
}
function notify(message, type) { notifications.push({ message, type }); }
function assistantMessage(calls) { return { role: "assistant", content: calls }; }
function bashCall(id, command) { return { type: "toolCall", id, name: "bash", arguments: { command } }; }
function toolCall(id, name, input) { return { type: "tool_call", toolCallId: id, toolName: name, input }; }
function bashResult(id, exitCode) {
  return {
    type: "tool_result", toolCallId: id, toolName: "bash", input: { command: "bash" },
    content: [], isError: exitCode !== 0,
    structuredContent: { output: "", truncated: false, exit_code: exitCode, wall_time_seconds: 0.1 },
  };
}
function transitions() { return sent.map((entry) => entry.message); }
function blocked(results) { return results.some((entry) => entry?.block === true); }
function messages() { return notifications.map((entry) => entry.message); }
function sessionContext(sourceFile) {
  const ctx = {
    cwd: repo, hasUI: true,
    sessionManager: { getSessionFile: () => sourceFile, getBranch: () => [] },
    ui: { notify, select: async () => "Keep worktree" },
  };
  let switchedFile = null;
  ctx.isIdle = () => true;
  ctx.waitForIdle = async () => {};
  ctx.switchSession = async (file, options) => {
    switchedFile = file;
    await options.withSession({
      ui: { notify },
      async sendMessage(message, options2) { pi.applied = { message, options: options2 }; },
    });
    return { cancelled: false };
  };
  return { ctx, switched: () => switchedFile };
}
"""
AUTO_ENTRY_PRELUDE = AUTO_ENTRY_PRELUDE.replace("{session}", json.dumps(SESSION_EXTENSION.as_uri()))
AUTO_ENTRY_PRELUDE = AUTO_ENTRY_PRELUDE.replace("{worktree}", json.dumps(WORKTREE_EXTENSION.as_uri()))


def start_session(body: str) -> str:
    """Shared opening: one persisted Pi session whose session file is real."""
    return (
        "const source = SessionManager.create(repo, sessions);\n"
        'source.appendMessage({ role: "user", content: "start", timestamp: Date.now() });\n'
        "const sourceFile = source.getSessionFile();\n"
        "const session = sessionContext(sourceFile);\n"
        'const ctx = { cwd: repo, hasUI: true, sessionManager: source, ui: { notify } };\n'
    ) + body


class WorktreeAutoEntryTests(unittest.TestCase):
    """The redirect reserves a session move into the worktree it created."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="pi-wt-auto-")).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.session_dir = self.base / "sessions"
        self.session_dir.mkdir()
        make_git_repo(self.repo)
        subprocess.run(["git", "branch", "feature/foo"], cwd=self.repo, capture_output=True, text=True, check=True)

    def run_script(self, body: str) -> dict:
        script = AUTO_ENTRY_PRELUDE
        script = script.replace("{repo}", json.dumps(str(self.repo)))
        script = script.replace("{sessions}", json.dumps(str(self.session_dir)))
        script += start_session(body)
        return run_ts(script)

    def test_redirected_creation_reserves_the_batch_and_moves_the_session(self) -> None:
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const sibling = await emit("tool_call", toolCall("call-2", "write", { path: "leaked.txt", content: "wrong checkout" }), ctx);
const creation = { command: "git worktree add ../foo feature/foo" };
await emit("tool_call", toolCall("call-1", "bash", creation), ctx);
// The real bash tool created the worktree, so the test creates it the same way.
execFileSync("git", ["-C", repo, "worktree", "add", ".pi/worktrees/foo", "feature/foo"], { stdio: "pipe" });
await emit("tool_result", bashResult("call-1", 0), ctx);
const beforeSettle = transitions();
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
const command = pi.sent[pi.sent.length - 1].message;
await pi.commands["enter-worktree"].handler(command.slice(command.indexOf(" ") + 1), session.ctx);
const replacement = SessionManager.open(session.switched());
const state = replacement.getBranch().find((entry) => entry.type === "custom" && entry.customType === "pi-utils-worktree-session");
const theme = { fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text };
const appliedRow = messageRenderers["pi-utils-worktree-applied"](pi.applied.message, { expanded: false }, theme).render(120).join("\\n");
const appliedDetail = messageRenderers["pi-utils-worktree-applied"](pi.applied.message, { expanded: true }, theme).render(120).join("\\n");
console.log(JSON.stringify({
  blocked: blocked(sibling),
  rewritten: creation.command,
  beforeSettle,
  dispatched: transitions(),
  expandPromptTemplates: pi.sent[0]?.options?.expandPromptTemplates,
  cwd: replacement.getHeader().cwd,
  created: state?.data?.created,
  notifications: messages(),
  applied: pi.applied,
  appliedRow,
  appliedDetail,
}));
""")
        self.assertTrue(result["blocked"])
        self.assertEqual("mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo", result["rewritten"])
        self.assertEqual([], result["beforeSettle"])
        self.assertEqual(['/enter-worktree {"path":".pi/worktrees/foo"}'], result["dispatched"])
        self.assertTrue(result["expandPromptTemplates"])
        self.assertTrue(result["cwd"].endswith("/.pi/worktrees/foo"), result["cwd"])
        self.assertFalse(result["created"])
        self.assertTrue(any("moves there when the turn ends" in message for message in result["notifications"]), result["notifications"])
        self.assertIn("Active cwd:", result["applied"]["message"]["content"])
        self.assertTrue(result["applied"]["message"]["display"])
        self.assertTrue(result["applied"]["message"]["details"]["path"].endswith("/.pi/worktrees/foo"))
        self.assertEqual("feature/foo", result["applied"]["message"]["details"]["branch"])
        self.assertIn("[worktree] entered", result["appliedRow"])
        self.assertIn(".pi/worktrees/foo", result["appliedRow"])
        self.assertNotIn("Path:", result["appliedRow"])
        self.assertIn("Path: ", result["appliedDetail"])
        self.assertIn(".pi/worktrees/foo", result["appliedDetail"])

    def test_an_unconfirmed_creation_never_dispatches_a_move(self) -> None:
        # A reserved call can end without a result: a truncated assistant message
        # fails its tool calls, and a blocker stops them before execution. No
        # result means no evidence that the directory exists, so no move.
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const blockedSibling = await emit("tool_call", toolCall("call-2", "write", { path: "leaked.txt", content: "wrong checkout" }), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({ blocked: blocked(blockedSibling), dispatched: transitions(), notifications: messages() }));
""")
        self.assertTrue(result["blocked"])
        self.assertEqual([], result["dispatched"], result["notifications"])
        self.assertTrue(any("this session did not move" in message for message in result["notifications"]), result["notifications"])

    def test_session_start_releases_a_pending_transition(self) -> None:
        # A replacement session that starts while a reservation is outstanding
        # must not leave the barrier armed against every later tool.
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
await emit("session_start", { type: "session_start" }, { cwd: repo, sessionManager: source, ui: { notify } });
const later = await emit("tool_call", toolCall("call-3", "write", { path: "kept.txt", content: "kept" }), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({ blocked: blocked(later), dispatched: transitions() }));
""")
        self.assertFalse(result["blocked"], "the barrier stayed armed after session_start")
        self.assertEqual([], result["dispatched"])

    def test_a_creation_during_another_switch_is_blocked(self) -> None:
        # A user-invoked switch waits for idle. Until it applies, this session
        # still owns the old checkout, so a creation must not run in that window.
        result = self.run_script("""
const idle = new Promise((resolve) => { pi.releaseIdle = resolve; });
const switchCtx = {
  cwd: repo, hasUI: true,
  sessionManager: { getSessionFile: () => sourceFile, getBranch: () => [] },
  ui: { notify, select: async () => "Keep worktree" },
  isIdle: () => false,
  waitForIdle: () => idle,
  async switchSession() { return { cancelled: true }; },
};
void pi.commands["enter-worktree"].handler("feature-auth", switchCtx);
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const creation = await emit("tool_call", toolCall("call-1", "bash", { command: "git worktree add ../foo feature/foo" }), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({
  blocked: blocked(creation),
  reason: creation.map((entry) => entry?.reason ?? "").filter(Boolean).join(" "),
  dispatched: transitions(),
  notifications: messages(),
}));
""")
        self.assertTrue(result["blocked"], "a creation ran while another switch was in flight")
        self.assertIn("switch is in progress", result["reason"])
        self.assertEqual([], result["dispatched"])
        self.assertFalse(any("created" in message for message in result["notifications"]), result["notifications"])

    def test_a_queued_creation_refuses_a_newer_switch(self) -> None:
        # The reservation owns the turn: a switch that the user starts after it
        # is refused by name, and the creation still moves the session.
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const idle = new Promise((resolve) => { pi.releaseIdle = resolve; });
const switchCtx = {
  cwd: repo, hasUI: true,
  sessionManager: { getSessionFile: () => sourceFile, getBranch: () => [] },
  ui: { notify, select: async () => "Keep worktree" },
  isIdle: () => false,
  waitForIdle: () => idle,
  async switchSession() { return { cancelled: true }; },
};
void pi.commands["enter-worktree"].handler("feature-auth", switchCtx);
const creation = await emit("tool_call", toolCall("call-1", "bash", { command: "git worktree add ../foo feature/foo" }), ctx);
await emit("tool_result", bashResult("call-1", 0), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({
  blocked: blocked(creation),
  dispatched: transitions(),
  notifications: messages(),
}));
""")
        self.assertFalse(result["blocked"], "the reserved call must run")
        self.assertEqual(['/enter-worktree {"path":".pi/worktrees/foo"}'], result["dispatched"])
        self.assertTrue(any("has not been applied yet" in message for message in result["notifications"]), result["notifications"])
        self.assertTrue(any("moves there when the turn ends" in message for message in result["notifications"]), result["notifications"])


    def test_failed_creation_releases_the_batch_and_keeps_the_session(self) -> None:
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const blockedSibling = await emit("tool_call", toolCall("call-2", "write", { path: "leaked.txt", content: "wrong checkout" }), ctx);
await emit("tool_result", bashResult("call-1", 128), ctx);
const retried = await emit("tool_call", toolCall("call-3", "write", { path: "kept.txt", content: "kept" }), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({
  blockedSibling: blocked(blockedSibling),
  retried: blocked(retried),
  dispatched: transitions(),
  notifications: messages(),
}));
""")
        self.assertTrue(result["blockedSibling"])
        self.assertFalse(result["retried"])
        self.assertEqual([], result["dispatched"])
        self.assertTrue(any("was not created" in message for message in result["notifications"]), result["notifications"])
        self.assertFalse(any("moves there" in message for message in result["notifications"]), result["notifications"])

    def test_unpersisted_session_is_told_it_cannot_move(self) -> None:
        base = AUTO_ENTRY_PRELUDE
        base = base.replace("{repo}", json.dumps(str(self.repo)))
        base = base.replace("{sessions}", json.dumps(str(self.session_dir)))
        script = base + """
const ctx = { cwd: repo, hasUI: true, sessionManager: { getSessionFile: () => null, getBranch: () => [] }, ui: { notify } };
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const sibling = await emit("tool_call", toolCall("call-2", "write", { path: "leaked.txt", content: "wrong checkout" }), ctx);
await emit("tool_result", bashResult("call-1", 0), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({ blocked: blocked(sibling), dispatched: transitions(), notifications: messages() }));
"""
        result = run_ts(script)
        self.assertFalse(result["blocked"])
        self.assertEqual([], result["dispatched"])
        self.assertTrue(any("cannot switch to it" in message for message in result["notifications"]), result["notifications"])

    def test_commands_that_are_not_rewritten_never_move_the_session(self) -> None:
        for command in (
            "git worktree add ../foo feature/foo && git status --porcelain",
            "git worktree list --porcelain",
            "git worktree add .pi/worktrees/foo feature/foo",
        ):
            with self.subTest(command=command):
                result = self.run_script(f"""
await emit("message_end", {{ type: "message_end", message: assistantMessage([bashCall("call-1", {json.dumps(command)})]) }}, ctx);
const sibling = await emit("tool_call", toolCall("call-2", "write", {{ path: "leaked.txt", content: "wrong checkout" }}), ctx);
await emit("tool_result", bashResult("call-1", 0), ctx);
await emit("agent_settled", {{ type: "agent_settled", aborted: false }}, ctx);
console.log(JSON.stringify({{ blocked: blocked(sibling), dispatched: transitions(), notifications: messages() }}));
""")
                self.assertFalse(result["blocked"], command)
                self.assertEqual([], result["dispatched"], command)
                self.assertFalse(any("moves there" in message for message in result["notifications"]), command)

    def test_explicit_transition_wins_over_the_automatic_move(self) -> None:
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([
  { type: "toolCall", id: "call-tool", name: "enter_worktree", arguments: { name: "feature-auth" } },
  bashCall("call-1", "git worktree add ../foo feature/foo"),
]) }, ctx);
const creation = await emit("tool_call", toolCall("call-1", "bash", { command: "git worktree add ../foo feature/foo" }), ctx);
const transition = await emit("tool_call", toolCall("call-tool", "custom", {}), ctx);
await pi.tools["enter_worktree"].execute("call-tool", { name: "feature-auth" });
await emit("agent_settled", { type: "agent_settled", aborted: false }, ctx);
console.log(JSON.stringify({
  creation: blocked(creation),
  transition: blocked(transition),
  dispatched: transitions(),
  notifications: messages(),
}));
""")
        self.assertTrue(result["creation"])
        self.assertFalse(result["transition"])
        self.assertEqual(['/enter-worktree {"name":"feature-auth"}'], result["dispatched"])
        self.assertFalse(any("moves there" in message for message in result["notifications"]), result["notifications"])

    def test_aborted_run_drops_the_automatic_move_and_keeps_the_worktree(self) -> None:
        result = self.run_script("""
await emit("message_end", { type: "message_end", message: assistantMessage([bashCall("call-1", "git worktree add ../foo feature/foo")]) }, ctx);
const creation = { command: "git worktree add ../foo feature/foo" };
await emit("tool_call", toolCall("call-1", "bash", creation), ctx);
execFileSync("git", ["-C", repo, "worktree", "add", ".pi/worktrees/foo", "feature/foo"], { stdio: "pipe" });
await emit("tool_result", bashResult("call-1", 0), ctx);
await emit("agent_settled", { type: "agent_settled", aborted: true }, ctx);
console.log(JSON.stringify({
  dispatched: transitions(),
  notifications: messages(),
  kept: existsSync(repo + "/.pi/worktrees/foo/README.md"),
}));
""")
        self.assertEqual([], result["dispatched"])
        self.assertTrue(result["kept"])
        self.assertTrue(any("automatic worktree entry" in message for message in result["notifications"]), result["notifications"])
        self.assertTrue(any("was dropped" in message for message in result["notifications"]), result["notifications"])


class WorktreePrintTests(unittest.TestCase):
    def test_print_host_resumes_edits_only_in_replacement_worktree(self) -> None:
        import shutil
        if not shutil.which("pi"):
            self.skipTest("installed Pi CLI required")
        fixture = Path(__file__).with_name("worktree_print_fixture.ts").resolve()
        with tempfile.TemporaryDirectory(prefix="pi-worktree-print-") as temp:
            base = Path(temp).resolve()
            repo, agent = base / "repo", base / "agent"
            repo.mkdir()
            agent.mkdir()
            for args in (("init", "-q"), ("config", "user.name", "Test"), ("config", "user.email", "test@example.invalid")):
                subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
            (repo / "tracked.txt").write_text("original\n")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
            env = {key: value for key, value in os.environ.items() if not any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
            env["PI_CODING_AGENT_DIR"] = str(agent)
            result = subprocess.run(
                ["pi", "--print", "--mode", "json", "-ne", "-ns", "-np", "-nc", "--no-themes", "-e", str(fixture), "--model", "worktree-live/test", "Enter worktree and edit there"],
                cwd=repo, env=env, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = repo / ".pi" / "worktrees" / "live"
            self.assertTrue(target.exists(), result.stdout + result.stderr)
            self.assertEqual((repo / "tracked.txt").read_text(), "original\n")
            self.assertFalse((repo / "leaked.txt").exists())
            self.assertEqual((target / "tracked.txt").read_text(), "worktree\n")
            self.assertEqual((target / "new.txt").read_text(), "worktree only")
            self.assertEqual(Path((target / "actual-cwd.txt").read_text().strip()).resolve(), target.resolve())
            self.assertIn("WORKTREE_PRINT_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()


# --- Merged from test_worktree_session.py ---
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_m1_UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = _m1_UTILS_PKG_DIR.parents[1]
_m1_SESSION_EXTENSION = _m1_UTILS_PKG_DIR / "extensions" / "worktree-session.ts"
GIT_EXTENSION = _m1_UTILS_PKG_DIR / "extensions" / "git" / "worktrees.ts"


def _m1_run_ts(script: str) -> dict:
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


def _m1_make_git_repo(path: Path) -> None:
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
        _m1_make_git_repo(self.repo)

    def test_real_runtime_keeps_all_edits_inside_replacement_worktree(self) -> None:
        for order in ("enter-first", "write-first", "malformed", "follow-up", "abort", "post-switch-error", "rebind-error"):
            with self.subTest(order=order):
                result = subprocess.run(
                    ["bun", "x", "tsx", str(_m1_UTILS_PKG_DIR / "tests" / "worktree_lifecycle.mts"), order],
                    cwd=REPO, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_parse_worktree_list_preserves_bare_and_branch_metadata(self) -> None:
        result = _m1_run_ts(f"""
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
        result = _m1_run_ts(f"""
import {{ resolveEnterTarget }} from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
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
        result = _m1_run_ts(f"""
import {{ resolveEnterTarget }} from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
console.log(JSON.stringify(resolveEnterTarget({json.dumps(str(nested))}, {{ name: "next" }})));
""")
        self.assertTrue(result["created"])
        self.assertTrue(result["path"].startswith(str(self.repo / ".pi" / "worktrees")))
        self.assertFalse(result["path"].startswith(str(nested / ".pi")))

    def test_enter_command_creates_worktree_forks_session_and_records_parent(self) -> None:
        script = f"""
import fs from "node:fs";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
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
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
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
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
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
        report = _m1_run_ts(f"""
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
import ext from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
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
        result = _m1_run_ts(script)
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
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
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
        result = _m1_run_ts(script)
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
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
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
        result = _m1_run_ts(script)
        self.assertEqual(result["sourceFile"], result["switched"])
        self.assertTrue(result["exists"])

    def test_enter_command_settles_before_switching_and_cleans_a_cancelled_switch(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
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
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
        self.assertTrue(result["worktreeKept"])
        self.assertEqual(result["errors"], ["host rebind failed"])
        self.assertEqual(len(result["warnings"]), 2)
        self.assertTrue(any("created worktree is kept" in warning and "kept-after-failure" in warning for warning in result["warnings"]))

    def test_a_second_switch_is_refused_while_one_is_in_flight(self) -> None:
        script = f"""
import fs from "node:fs";
import path from "node:path";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
        self.assertEqual(result["switches"], 1, result)
        self.assertEqual(result["refused"], ["warning"])
        # The refused command never reaches the worktree it asked for.
        self.assertFalse(result["secondWorktree"])

    def test_render_result_survives_class_based_theme(self) -> None:
        script = f"""
import ext from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};
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
        result = _m1_run_ts(script)
        self.assertTrue(result["painted"], result["rendered"])

    def test_queued_transition_blocks_siblings_and_survives_settlement(self) -> None:
        script = f"""
import ext from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
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
import ext from {json.dumps(_m1_SESSION_EXTENSION.as_uri())};

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
        result = _m1_run_ts(script)
        # The model was told the transition was pending; an abort ends the run
        # without applying it, so nothing is dispatched and the user is told.
        self.assertEqual(result["sent"], [])
        self.assertEqual(len(result["notifications"]), 1)
        self.assertEqual(result["notifications"][0]["type"], "warning")
        self.assertIn("enter_worktree", result["notifications"][0]["message"])
        self.assertIn("dropped", result["notifications"][0]["message"])


if __name__ == "__main__":
    unittest.main()


# --- Merged from test_worktree_completion.py ---
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

_m2_UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = _m2_UTILS_PKG_DIR.parents[1]
COMPLETION_EXTENSION = _m2_UTILS_PKG_DIR / "extensions" / "worktree-completion.ts"


def _m2_run_ts(script: str) -> object:
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


GIT = shutil.which("git")


def _m2_make_git_repo(path: Path) -> None:
    def git(*args: str, cwd: Path | None = None) -> None:
        subprocess.run(["git", *args], cwd=cwd or path,
                       capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    (path / "src").mkdir()
    (path / "README.md").write_text("main readme\n")
    (path / "src" / "index.ts").write_text("export {};\n")
    git("add", "-A")
    git("commit", "-qm", "init")


class WorktreeCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="pi-wtc-")).resolve()
        self.main = self.base / "main-repo"
        self.main.mkdir()
        _m2_make_git_repo(self.main)
        self.wt_b = self.base / "wt-b"
        self.wt_c = self.base / "wt-c"
        for name in ("b", "c"):
            subprocess.run(["git", "worktree", "add", f"{self.base}/wt-{name}", "-b", name],
                           cwd=self.main, capture_output=True, text=True, check=True)

    def is_foreign(self, value: str, cwd: Path) -> bool:
        script = f"""
import {{ collectWorktreeRoots, isInForeignWorktree }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(cwd))});
console.log(JSON.stringify(isInForeignWorktree({json.dumps(value)}, {json.dumps(str(cwd))}, roots)));
"""
        return bool(_m2_run_ts(script))

    def test_main_checkout_collects_linked_worktrees_as_foreign(self) -> None:
        result = _m2_run_ts(f"""
import fs from "node:fs";
import {{ collectWorktreeRoots }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.main))});
console.log(JSON.stringify({{
  currentIsMain: roots.currentRoot === fs.realpathSync({json.dumps(str(self.main))}),
  foreignCount: roots.foreignRoots.length,
}}));
""")
        self.assertTrue(result["currentIsMain"])
        self.assertEqual(2, result["foreignCount"])

    def test_worktree_sees_siblings_and_main_as_foreign(self) -> None:
        result = _m2_run_ts(f"""
import fs from "node:fs";
import {{ collectWorktreeRoots }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.wt_b))});
const foreign = new Set(roots.foreignRoots);
console.log(JSON.stringify({{
  hasMain: foreign.has(fs.realpathSync({json.dumps(str(self.main))})),
  hasSibling: foreign.has(fs.realpathSync({json.dumps(str(self.wt_c))})),
  currentSelf: roots.currentRoot === fs.realpathSync({json.dumps(str(self.wt_b))}),
}}));
""")
        self.assertTrue(result["hasMain"])
        self.assertTrue(result["hasSibling"])
        self.assertTrue(result["currentSelf"])

    def test_non_git_directory_disables_filtering(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="pi-wtc-nogit-"))
        self.assertFalse(self.is_foreign("../anything/x.ts", outside))

    def test_main_hides_sibling_worktree_paths(self) -> None:
        self.assertTrue(self.is_foreign("../wt-b/src/index.ts", self.main))
        self.assertTrue(self.is_foreign("../wt-b/", self.main))
        self.assertFalse(self.is_foreign("src/index.ts", self.main))
        self.assertFalse(self.is_foreign("README.md", self.main))

    def test_nonexistent_leaf_under_symlinked_base_is_still_foreign(self) -> None:
        # macOS /var-style symlinks: realpath fails on missing leaves, but the
        # candidate must still resolve into the canonical worktree space.
        self.assertTrue(self.is_foreign("../wt-b/dir with space/x.ts", self.main))
        self.assertTrue(self.is_foreign(str(self.wt_b / "nope" / "x.ts"), self.main))

    def test_symlinked_base_fixture_resolves_before_filtering(self) -> None:
        # Deterministic cross-platform version of the ambient-symlink case: a
        # symlinked session path must not hide foreign roots behind it.
        linked = self.base.parent / "linked"
        os.symlink(self.base, linked, target_is_directory=True)
        try:
            via_link = linked / "main-repo"
            self.assertTrue(self.is_foreign("../wt-b/nope/x.ts", via_link))
            self.assertFalse(self.is_foreign("src/index.ts", via_link))
        finally:
            os.remove(linked)

    def test_nested_pi_worktrees_path_is_foreign_from_main(self) -> None:
        subprocess.run(["git", "worktree", "add", ".pi/worktrees/foo", "-b", "foo"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        self.assertTrue(self.is_foreign(".pi/worktrees/foo/src/index.ts", self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees/foo/src/index.ts"', self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees/foo/", self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees", self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees/", self.main))
        self.assertTrue(self.is_foreign("@.pi/worktrees", self.main))
        self.assertTrue(self.is_foreign("@.pi/worktrees/", self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees"', self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees/"', self.main))

    def test_read_guard_blocks_foreign_worktree_and_allows_own_files(self) -> None:
        subprocess.run(["git", "worktree", "add", ".pi/worktrees/foo", "-b", "foo"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        foreign = self.main / ".pi" / "worktrees" / "foo" / "src" / "index.ts"
        own = self.main / "src" / "index.ts"
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
registerWorktreeCompletion({{ on: (event, handler) => handlers.set(event, handler) }});
const guard = handlers.get("tool_call");
const ctx = {{ cwd: {json.dumps(str(self.main))} }};
const blocked = guard({{ toolName: "read", input: {{ path: {json.dumps(str(foreign))} }} }}, ctx);
const allowed = guard({{ toolName: "read", input: {{ path: {json.dumps(str(own))} }} }}, ctx);
console.log(JSON.stringify({{ blocked, allowed: allowed ?? null }}));
"""
        result = _m2_run_ts(script)
        self.assertTrue(result["blocked"]["block"])
        self.assertIn("enter_worktree", result["blocked"]["reason"])
        self.assertIsNone(result["allowed"])

    def test_main_repo_without_linked_worktrees_still_hides_pi_worktrees(self) -> None:
        clean_repo = self.base / "clean-repo"
        clean_repo.mkdir()
        _m2_make_git_repo(clean_repo)
        (clean_repo / ".pi" / "worktrees").mkdir(parents=True)
        (clean_repo / ".pi" / "worktrees" / "stale.txt").write_text("temp")
        self.assertTrue(self.is_foreign(".pi/worktrees", clean_repo))
        self.assertTrue(self.is_foreign(".pi/worktrees/", clean_repo))
        self.assertTrue(self.is_foreign(".pi/worktrees/stale.txt", clean_repo))
        self.assertFalse(self.is_foreign(".pi/agents", clean_repo))
        self.assertFalse(self.is_foreign("src/index.ts", clean_repo))

    def test_worktree_hides_main_and_siblings(self) -> None:
        self.assertTrue(self.is_foreign("../main-repo/README.md", self.wt_b))
        self.assertTrue(self.is_foreign("../wt-c/src/index.ts", self.wt_b))
        self.assertFalse(self.is_foreign("src/index.ts", self.wt_b))

    def test_absolute_and_home_relative_candidates_resolve_before_filtering(self) -> None:
        absolute = str(self.main / "src" / "index.ts")
        self.assertTrue(self.is_foreign(absolute, self.wt_b))
        self.assertFalse(self.is_foreign("~/outside-any-repo/file.ts", self.wt_b))

    def test_filter_drops_only_foreign_items_in_order(self) -> None:
        script = f"""
import {{ collectWorktreeRoots, filterForeignWorktreeItems }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.main))});
const items = [
  {{ value: "src/index.ts", label: "index.ts" }},
  {{ value: ".pi/worktrees/", label: "worktrees/" }},
  {{ value: ".pi/worktrees", label: "worktrees" }},
  {{ value: "@agent-teams-status", label: "agent-teams-status", description: ".pi/worktrees/pi-artifact-and-design/.changeset/agent-teams-status-truth-and-classifier.md" }},
  {{ value: "@agent-teams/", label: "agent-teams/", description: ".pi/worktrees/pi-artifact-and-design/packages/agent-teams/" }},
  {{ value: "../wt-b/src/index.ts", label: "index.ts", description: "../wt-b/src/index.ts" }},
  {{ value: "../wt-c/", label: "wt-c/" }},
  {{ value: ".pi/agents/", label: "agents/" }},
];
console.log(JSON.stringify(filterForeignWorktreeItems(items, {json.dumps(str(self.main))}, roots)));
"""
        result = _m2_run_ts(script)
        self.assertEqual(["src/index.ts", ".pi/agents/"], [item["value"] for item in result])

    def test_nested_pi_worktree_session_filters_sibling_and_parent_worktrees_dir(self) -> None:
        wt_foo = self.main / ".pi" / "worktrees" / "foo"
        wt_bar = self.main / ".pi" / "worktrees" / "bar"
        for name in ("foo", "bar"):
            subprocess.run(["git", "worktree", "add", f".pi/worktrees/{name}", "-b", f"branch-{name}"],
                           cwd=self.main, capture_output=True, text=True, check=True)

        self.assertFalse(self.is_foreign("src/index.ts", wt_foo))
        self.assertFalse(self.is_foreign("README.md", wt_foo))
        self.assertTrue(self.is_foreign("../bar/src/index.ts", wt_foo))
        self.assertTrue(self.is_foreign("../../.pi/worktrees", wt_foo))
        self.assertTrue(self.is_foreign("../../.pi/worktrees/", wt_foo))
        self.assertTrue(self.is_foreign("../../README.md", wt_foo))

    def test_in_repo_worktree_outside_managed_dir_keeps_own_files(self) -> None:
        # A linked worktree nested inside the main checkout must keep its own
        # files: the deepest enclosing worktree decides, not membership of the
        # main root alone.
        subprocess.run(["git", "worktree", "add", "vendor/wt", "-b", "vendorwt"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        wt = self.main / "vendor" / "wt"
        self.assertFalse(self.is_foreign("src/index.ts", wt))
        self.assertFalse(self.is_foreign(str(wt / "src" / "index.ts"), wt))
        self.assertTrue(self.is_foreign("vendor/wt/src/index.ts", self.main))
        self.assertTrue(self.is_foreign(str(wt / "src" / "index.ts"), self.main))

    def test_in_repo_worktree_session_may_edit_its_own_file(self) -> None:
        subprocess.run(["git", "worktree", "add", "vendor/wt", "-b", "vendorwt"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        wt = self.main / "vendor" / "wt"
        own = wt / "src" / "index.ts"
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
registerWorktreeCompletion({{ on: (event, handler) => handlers.set(event, handler) }});
const guard = handlers.get("tool_call");
const ownResult = guard({{ toolName: "edit", input: {{ path: {json.dumps(str(own))} }} }}, {{ cwd: {json.dumps(str(wt))} }});
const foreignResult = guard({{ toolName: "edit", input: {{ path: {json.dumps(str(own))} }} }}, {{ cwd: {json.dumps(str(self.main))} }});
console.log(JSON.stringify({{ own: ownResult ?? null, foreign: foreignResult ?? null }}));
"""
        result = _m2_run_ts(script)
        self.assertIsNone(result["own"])
        self.assertTrue(result["foreign"]["block"])

    def test_worktree_nested_under_the_managed_directory_is_foreign_to_its_parent(self) -> None:
        # A managed directory also contains worktrees, so its contents must not be
        # exempted before the enclosing-worktree rule runs.
        parent = self.main / ".pi" / "worktrees" / "parent"
        nested = parent / "vendor" / "wt"
        subprocess.run(["git", "worktree", "add", str(parent), "-b", "parent"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        nested.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "worktree", "add", str(nested), "-b", "nested"],
                       cwd=self.main, capture_output=True, text=True, check=True)

        self.assertTrue(self.is_foreign("vendor/wt/file.txt", parent))
        self.assertTrue(self.is_foreign(str(nested / "README.md"), parent))
        self.assertFalse(self.is_foreign("README.md", parent))
        self.assertFalse(self.is_foreign("src/index.ts", parent))
        self.assertTrue(self.is_foreign(str(nested / "README.md"), self.main))
        self.assertFalse(self.is_foreign("README.md", nested))

    def test_search_line_with_a_space_in_a_foreign_path_is_filtered(self) -> None:
        # A result line is `path:line: content`, and the path can contain a space.
        spaced = self.base / "spaced wt"
        subprocess.run(["git", "worktree", "add", str(spaced), "-b", "spaced"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        foreign_line = f"{spaced}/src/index.ts"
        script = f"""
import {{ collectWorktreeRoots, filterForeignWorktreeSearchLines }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.main))});
const text = [
  {json.dumps(foreign_line)} + ":1: foreign match",
  "src/index.ts:12: local match",
  "No matches found",
].join("\\n");
console.log(JSON.stringify({{ filtered: filterForeignWorktreeSearchLines(text, {json.dumps(str(self.main))}, roots).split("\\n") }}));
"""
        result = _m2_run_ts(script)
        self.assertEqual(result["filtered"], ["src/index.ts:12: local match", "No matches found"])

    def test_a_retargeted_symlink_into_a_foreign_worktree_is_blocked(self) -> None:
        # A symlink that resolved locally and later points into a foreign worktree
        # must not keep its old identity from a cached resolution.
        link = self.main / "alias"
        (self.main / "local.txt").write_text("local\n", encoding="utf-8")
        os.symlink(self.main / "local.txt", link)
        self.assertFalse(self.is_foreign("alias", self.main))
        os.remove(link)
        os.symlink(self.wt_b / "README.md", link)
        self.assertTrue(self.is_foreign("alias", self.main))

    def test_a_worktree_added_after_discovery_becomes_foreign(self) -> None:
        # Discovery is memoized per session; a worktree that appears later must
        # still be foreign, without running git on every completion round.
        script = f"""
import {{ getWorktreeRoots, isInForeignWorktree }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const main = {json.dumps(str(self.main))};
const before = getWorktreeRoots(main);
const beforeForeign = isInForeignWorktree("vendor/late/file.txt", main, before);
const unchanged = getWorktreeRoots(main) === before;
const added = Bun.spawnSync(["git", "-C", main, "worktree", "add", "vendor/late", "-b", "late"], {{ stdout: "pipe", stderr: "pipe" }});
if (added.exitCode !== 0) throw new Error(added.stderr.toString());
const after = getWorktreeRoots(main);
const afterForeign = isInForeignWorktree("vendor/late/file.txt", main, after);
const afterAbs = isInForeignWorktree(main + "/vendor/late/README.md", main, after);
const memoKept = getWorktreeRoots(main) === after;
const ownStillVisible = isInForeignWorktree("README.md", main, after);
console.log(JSON.stringify({{ beforeForeign, afterForeign, afterAbs, ownStillVisible, unchanged, memoKept }}));
"""
        result = _m2_run_ts(script)
        self.assertFalse(result["beforeForeign"])
        self.assertTrue(result["afterForeign"])
        self.assertTrue(result["afterAbs"])
        self.assertFalse(result["ownStillVisible"])
        # Unchanged discovery is still memoized: one object, no repeated git call.
        self.assertTrue(result["unchanged"])
        self.assertTrue(result["memoKept"])

    def test_search_results_are_resolved_against_the_search_root(self) -> None:
        # A search inside a foreign checkout returns paths relative to that root;
        # resolving them against the session cwd would keep them all.
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
const pi = {{ on: (event, handler) => handlers.set(event, handler), getAllTools: () => [] }};
registerWorktreeCompletion(pi);
const main = {json.dumps(str(self.main))};
const text = "src/index.ts:1: foreign match\\n";
const run = (input) => {{
  const result = handlers.get("tool_result")({{ toolName: "ffgrep", input, content: [{{ type: "text", text }}] }}, {{ cwd: main }});
  return result ? result.content[0].text : null;
}};
console.log(JSON.stringify({{
  fromForeignRoot: run({{ path: {json.dumps(str(self.wt_b))} }}),
  fromSessionRoot: run({{ path: "src" }}),
}}));
"""
        result = _m2_run_ts(script)
        # Relative to the foreign search root this is a foreign file: dropped.
        self.assertNotIn("foreign match", result["fromForeignRoot"] or "")
        # Relative to the session cwd the same line is this session's own file.
        self.assertIsNone(result["fromSessionRoot"])

    def test_bare_repository_session_filters_linked_worktrees(self) -> None:
        source = self.base / "bare-source"
        source.mkdir()
        _m2_make_git_repo(source)
        bare = self.base / "store.git"
        subprocess.run(["git", "clone", "--bare", str(source), str(bare)],
                       capture_output=True, text=True, check=True)
        wt_w = self.base / "wt-w"
        subprocess.run(["git", "worktree", "add", str(wt_w), "-b", "w"],
                       cwd=bare, capture_output=True, text=True, check=True)

        self.assertTrue(self.is_foreign(str(wt_w / "anything.ts"), bare))
        self.assertFalse(self.is_foreign("config", bare))

    def test_extension_registration_filters_and_delegates(self) -> None:
        script = f"""
process.env.PATH = "/nonexistent-shim:" + process.env.PATH;
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
registerWorktreeCompletion({{ on: (event, handler) => handlers.set(event, handler) }});
const handler = handlers.get("session_start");
if (!handler) throw new Error("session_start handler was not registered");

let factory = null;
const ctx = {{
  cwd: {json.dumps(str(self.main))},
  ui: {{ addAutocompleteProvider: (f) => {{ factory = f; }} }},
}};
handler({{}}, ctx);
handlers.get("resources_discover")({{ cwd: ctx.cwd, reason: "startup" }}, ctx);
if (!factory) throw new Error("autocomplete provider factory was not registered");

const current = {{
  async getSuggestions() {{
    return {{
      prefix: "@x",
      items: [
        {{ value: "@README.md", label: "README.md" }},
        {{ value: "@../wt-b/src/index.ts", label: "index.ts" }},
      ],
    }};
  }},
  applyCompletion(...args) {{ return args; }},
  shouldTriggerFileCompletion() {{ return "delegated"; }},
}};
const wrapped = factory(current);
const options = {{ signal: new AbortController().signal }};
const first = await wrapped.getSuggestions(["@x"], 0, 3, options);
const second = await wrapped.getSuggestions(["@x"], 0, 3, options);
console.log(JSON.stringify({{
  firstValues: first.items.map((i) => i.value),
  secondValues: second.items.map((i) => i.value),
  applyDelegates: JSON.stringify(wrapped.applyCompletion("L", 0, 1, {{}}, "@")) === JSON.stringify(["L", 0, 1, {{}}, "@"]),
  triggerDelegates: wrapped.shouldTriggerFileCompletion([], 0, 0) === "delegated",
}}));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertEqual(["@README.md"], report["firstValues"])
        self.assertEqual(["@README.md"], report["secondValues"])
        self.assertTrue(report["applyDelegates"])
        self.assertTrue(report["triggerDelegates"])

    def test_later_at_provider_cannot_bypass_worktree_filter(self) -> None:
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
const factories = [];
const pi = {{ on: (event, handler) => handlers.set(event, handler) }};
const ctx = {{
  cwd: {json.dumps(str(self.main))},
  ui: {{ addAutocompleteProvider: (factory) => factories.push(factory) }},
}};
registerWorktreeCompletion(pi);
handlers.get("session_start")({{}}, ctx);

// A later provider such as FFF can return its own @ results without delegating.
factories.push((current) => ({{
  async getSuggestions() {{
    return {{
      prefix: "@packages/utils/",
      items: [
        {{ value: "@packages/utils/", label: "utils/", description: "packages/utils/" }},
        {{ value: "@.pi/worktrees/pi-artifact-and-design/packages/utils/", label: "utils/", description: ".pi/worktrees/pi-artifact-and-design/packages/utils/" }},
      ],
    }};
  }},
  applyCompletion: (...args) => current.applyCompletion(...args),
  shouldTriggerFileCompletion: (...args) => current.shouldTriggerFileCompletion?.(...args) ?? true,
}}));
handlers.get("resources_discover")({{ cwd: ctx.cwd, reason: "startup" }}, ctx);

let provider = {{
  async getSuggestions() {{ return null; }},
  applyCompletion(...args) {{ return args; }},
  shouldTriggerFileCompletion() {{ return true; }},
}};
for (const factory of factories) provider = factory(provider);
const result = await provider.getSuggestions([], 0, 0, {{ signal: new AbortController().signal }});
console.log(JSON.stringify(result.items.map((item) => item.value)));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\\n{result.stderr}")
        self.assertEqual(["@packages/utils/"], json.loads(result.stdout))

    def test_filtering_follows_session_replacement_cwd(self) -> None:
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
let factory = null;
const pi = {{ on: (event, handler) => handlers.set(event, handler) }};
const makeCtx = (cwd) => ({{
  cwd,
  ui: {{ addAutocompleteProvider: (f) => {{ factory = f; }} }},
}});
registerWorktreeCompletion(pi);
const mainCtx = makeCtx({json.dumps(str(self.main))});
handlers.get("session_start")({{}}, mainCtx);
handlers.get("resources_discover")({{ cwd: mainCtx.cwd, reason: "startup" }}, mainCtx);
const current = {{ async getSuggestions() {{ return {{ items: [{{ value: "../main-repo/README.md" }}, {{ value: "src/index.ts" }}] }}; }} }};
const provider = factory(current);
const before = await provider.getSuggestions([], 0, 0, {{}});
const worktreeCtx = makeCtx({json.dumps(str(self.wt_b))});
handlers.get("session_start")({{}}, worktreeCtx);
const after = await provider.getSuggestions([], 0, 0, {{}});
console.log(JSON.stringify({{
  beforeKeptMainReadme: before.items.some((item) => item.value === "../main-repo/README.md"),
  afterDropsMainReadme: !after.items.some((item) => item.value === "../main-repo/README.md"),
  afterKeepsOwnSrc: after.items.some((item) => item.value === "src/index.ts"),
}}));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertTrue(report["beforeKeptMainReadme"])
        self.assertTrue(report["afterDropsMainReadme"])
        self.assertTrue(report["afterKeepsOwnSrc"])

    def test_discovery_runs_git_once_across_repeated_rounds(self) -> None:
        counter_bin = Path(tempfile.mkdtemp(prefix="pi-wtc-bin-"))
        counter = counter_bin / "count"
        counter.write_text("0\n")
        shim = counter_bin / "git"
        shim.write_text(
            "#!/bin/sh\n"
            f'echo $(($(cat "{counter}") + 1)) > "{counter}"\n'
            f'exec {json.dumps(GIT)} "$@"\n'
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

        script = f"""
process.env.PATH = {json.dumps(str(counter_bin))} + ":" + process.env.PATH;
const mod = await import({json.dumps(COMPLETION_EXTENSION.as_uri())});
const first = mod.getWorktreeRoots({json.dumps(str(self.main))});
const second = mod.getWorktreeRoots({json.dumps(str(self.main))});
console.log(JSON.stringify({{ sameRef: first === second }}));
"""
        # Bun snapshots PATH for child-process lookup, but pi runs on Node,
        # which re-resolves per spawn — run this scenario through node.
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        self.assertTrue(json.loads(result.stdout)["sameRef"])
        # One discovery = exactly two spawns (worktree list + rev-parse).
        self.assertEqual(2, int(counter.read_text()))

    def test_search_tool_filters_foreign_worktree_paths(self) -> None:
        foreign_file = f"{self.base}/wt-b/src/index.ts"
        own_file = f"{self.main}/src/index.ts"
        managed_file = f"{self.main}/.pi/worktrees/wt-sub/src/index.ts"

        script = f"""
import registerWorktreeCompletion, {{ filterForeignWorktreeSearchLines }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
const declaredTools = [
  {{ name: "fffind", parameters: {{ properties: {{ exclude: {{ type: "string" }} }} }} }},
  {{ name: "find", parameters: {{ properties: {{ path: {{ type: "string" }} }} }} }},
];
const pi = {{
  on: (event, handler) => handlers.set(event, handler),
  getAllTools: () => declaredTools,
}};
const ctx = {{ cwd: {json.dumps(str(self.main))} }};
registerWorktreeCompletion(pi);

// tool_call injects exclude only into a tool that declares it
const toolCallHandler = handlers.get("tool_call");
const fffindCall = {{ toolName: "fffind", input: {{ path: "src/" }} }};
toolCallHandler(fffindCall, ctx);
// `find` is filtered too, but declares no exclude parameter.
const undeclaredCall = {{ toolName: "find", input: {{ path: "src/" }} }};
toolCallHandler(undeclaredCall, ctx);

// Test tool_result filters lines
const rawSearchResult = [
  "packages/utils/src/index.ts",
  {json.dumps(foreign_file)},
  {json.dumps(managed_file)},
  "packages/utils/src/other.ts:12: const x = 1;",
  {json.dumps(managed_file)} + ":45: const bug = true;",
].join("\\n");

const toolResultHandler = handlers.get("tool_result");
const filteredResult = toolResultHandler({{
  toolName: "fffind",
  content: [{{ type: "text", text: rawSearchResult }}],
}}, ctx);

console.log(JSON.stringify({{
  excludeInjected: fffindCall.input.exclude,
  undeclaredInput: undeclaredCall.input,
  filteredText: filteredResult.content[0].text,
}}));
"""
        report = _m2_run_ts(script)
        self.assertIn(".pi/worktrees/**", report["excludeInjected"])
        # A search tool that declares no exclude is never given one; its output is
        # still filtered on the way back.
        self.assertEqual(report["undeclaredInput"], {"path": "src/"})
        self.assertNotIn("wt-b", report["filteredText"])
        self.assertNotIn("wt-sub", report["filteredText"])
        self.assertIn("packages/utils/src/index.ts", report["filteredText"])
        self.assertIn("packages/utils/src/other.ts:12:", report["filteredText"])



if __name__ == "__main__":
    unittest.main()

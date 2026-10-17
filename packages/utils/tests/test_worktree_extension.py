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
import {{ rewriteWorktreeAddCommand }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
console.log(JSON.stringify(rewriteWorktreeAddCommand({json.dumps(command)})));
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
import {{ rewriteWorktreeAddCommand }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
console.log(JSON.stringify(rewriteWorktreeAddCommand({json.dumps(command)}, {{ cwd: {json.dumps(cwd)} }})));
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

if __name__ == "__main__":
    unittest.main()

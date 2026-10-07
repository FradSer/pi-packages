"""Exercise continuation commands, input routing, and history recovery."""

import json
import tempfile
from pathlib import Path

from utils_helpers import run_typescript

EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "continue.ts"
PRELUDE = f"import ext, * as continuation from {json.dumps(EXTENSION.as_uri())};\n"
HARNESS = PRELUDE + """
const handlers = new Map();
const commands = new Map();
const messages = [];
const notices = [];
const pi = {
  on: (name, handler) => handlers.set(name, handler),
  registerCommand: (name, spec) => commands.set(name, spec),
  sendMessage: (message, options) => messages.push({ kind: "custom", message, options }),
  sendUserMessage: (text, options) => messages.push({ kind: "user", text, options }),
};
ext(pi);
const ctx = {
  isIdle: () => true,
  waitForIdle: async () => {},
  ui: { notify: (message, type) => notices.push({ message, type }) },
  sessionManager: {
    getSessionFile: () => undefined,
    getBranch: () => [],
  },
};
const run = (args = "") => commands.get("continue").handler(args, ctx);
"""


def test_command_routes_by_active_branch_and_custom_focus() -> None:
    report = run_typescript(HARNESS + """
const cases = [
  ["empty", [], ""],
  ["completed", [{ role: "assistant", stopReason: "stop" }], ""],
  ...["error", "aborted", "length", "pending", "toolUse"].map(stopReason =>
    [stopReason, [{ role: "assistant", stopReason, errorMessage: "invalid API key" }], ""]),
  ["tool error", [{ role: "toolResult", isError: true }], ""],
  ["focus", [{ role: "assistant", stopReason: "error" }], "  Check tests  "],
];
const results = {};
for (const [label, branch, args] of cases) {
  messages.length = notices.length = 0;
  ctx.sessionManager.getBranch = () => branch.map(message => ({ type: "message", message }));
  await run(args);
  results[label] = { messages: [...messages], notices: [...notices] };
}
console.log(JSON.stringify(results));
""")
    assert report["empty"]["messages"] == []
    assert report["empty"]["notices"][0]["type"] == "error"
    assert "no previous model request" in report["empty"]["notices"][0]["message"]
    assert report["completed"]["messages"][0]["kind"] == "user"
    for label in ("error", "aborted", "length", "pending", "toolUse", "tool error"):
        assert report[label]["notices"] == []
        assert report[label]["messages"] == [{
            "kind": "custom",
            "message": {"customType": "continue-extension", "content": "", "display": False},
            "options": {"triggerTurn": True},
        }]
    assert report["focus"]["messages"] == [{"kind": "user", "text": "Check tests"}]


def test_direct_continuation_reports_async_delivery_failure() -> None:
    # The feature says the command reports the failure, so a rejected host
    # delivery becomes a user notification instead of an unhandled rejection.
    report = run_typescript(HARNESS + """
ctx.sessionManager.getBranch = () => [{ type: "message", message: { role: "assistant", stopReason: "error" } }];
pi.sendMessage = async () => { throw new Error("Delivery failed"); };
await run();
console.log(JSON.stringify({ notices }));
""")
    assert report == {
        "notices": [{"message": "Continuation delivery failed: Delivery failed", "type": "error"}]
    }


def test_keyword_routing_preserves_idle_and_busy_delivery() -> None:
    report = run_typescript(HARNESS + """
const results = {};
for (const idle of [true, false]) {
  ctx.isIdle = () => idle;
  for (const text of ["continue", "Continue", "  continue.  ", "继续", "繼續", "", "cont", "continue work", "discontinue"]) {
    messages.length = 0;
    const outcome = await handlers.get("input")({ text }, ctx);
    results[`${idle}:${text}`] = { outcome, messages: [...messages] };
  }
}
console.log(JSON.stringify(results));
""")
    for idle in ("true", "false"):
        for text in ("continue", "Continue", "  continue.  ", "继续", "繼續"):
            result = report[f"{idle}:{text}"]
            assert result["outcome"] == {"action": "handled"}
            message = result["messages"][0]
            assert message["kind"] == "user"
            if idle == "true":
                assert message["text"] == "/continue"
                assert message["options"] == {"expandPromptTemplates": True}
            else:
                assert "continue execution" in message["text"]
                assert message["options"] == {"deliverAs": "followUp"}
        for text in ("", "cont", "continue work", "discontinue"):
            assert report[f"{idle}:{text}"] == {"outcome": {"action": "continue"}, "messages": []}


def test_context_removes_retry_attempts_without_breaking_tool_pairs() -> None:
    report = run_typescript(HARNESS + """
const user = { role: "user" };
const ok = { role: "assistant", stopReason: "stop" };
const failed = { role: "assistant", stopReason: "error" };
const toolCall = { role: "assistant", stopReason: "toolUse" };
const toolResult = { role: "toolResult" };
const marker = { role: "custom", customType: "continue-extension" };
const other = { role: "custom", customType: "other" };
const results = [];
for (const messages of [
  [user, ok, failed, failed, marker],
  [user, toolCall, toolResult, failed, marker],
  [user, ok, marker],
  [user, other, failed, marker],
]) {
  results.push((await handlers.get("context")({ messages })).messages);
}
console.log(JSON.stringify(results));
""")
    assert report == [
        [{"role": "user"}, {"role": "assistant", "stopReason": "stop"}],
        [{"role": "user"}, {"role": "assistant", "stopReason": "toolUse"}, {"role": "toolResult"}],
        [{"role": "user"}, {"role": "assistant", "stopReason": "stop"}],
        [{"role": "user"}, {"role": "custom", "customType": "other"}],
    ]


def test_disk_tip_handles_partial_lines_and_entries_larger_than_the_window() -> None:
    with tempfile.TemporaryDirectory() as directory:
        session = Path(directory) / "session.jsonl"
        reports = []
        for content in (
            "".join(json.dumps({"type": "message", "id": f"entry-{i}", "payload": "x" * 200}) + "\n" for i in range(4000)),
            json.dumps({"type": "message", "id": "large-tip", "payload": "x" * (600 * 1024)}) + "\n",
        ):
            session.write_text(content + '{"type":"message","id":"partial"', encoding="utf-8")
            reports.append(run_typescript(PRELUDE + f"""
console.log(JSON.stringify(continuation.readDiskTipEntryId({json.dumps(str(session))})));
"""))
        assert reports == ["entry-3999", "large-tip"]


def test_session_reload_keeps_known_selected_leaves_and_loads_unseen_tips() -> None:
    with tempfile.TemporaryDirectory() as directory:
        session = Path(directory) / "session.jsonl"
        session.write_text('{"type":"message","id":"disk-tip"}\n', encoding="utf-8")
        report = run_typescript(HARNESS + f"""
ctx.sessionManager.getSessionFile = () => {json.dumps(str(session))};
const results = [];
for (const mode of ["known", "unseen", "delivery failure"]) {{
  const known = mode === "known";
  messages.length = 0;
  notices.length = 0;
  ctx.sessionManager.getEntry = () => known ? {{ id: "disk-tip" }} : undefined;
  ctx.sessionManager.getBranch = () => [{{ type: "message", message: {{ role: "assistant", stopReason: "error" }} }}];
  let reloaded = false;
  ctx.switchSession = async (file, options) => {{
    reloaded = file === ctx.sessionManager.getSessionFile();
    await options.withSession({{
      ...ctx, ...pi,
      sendMessage: async () => {{ throw new Error("Replacement delivery failed"); }},
      sessionManager: {{ getBranch: () => [{{ type: "message", message: {{ role: "assistant", stopReason: mode === "delivery failure" ? "error" : "stop" }} }}] }},
    }});
  }};
  await run();
  results.push({{ reloaded, kind: messages[0]?.kind, notices: [...notices] }});
}}
console.log(JSON.stringify(results));
""")
        assert report == [
            {"reloaded": False, "kind": "custom", "notices": []},
            {"reloaded": True, "kind": "user", "notices": []},
            {
                "reloaded": True,
                "notices": [
                    {
                        "message": "Continuation delivery failed: Replacement delivery failed",
                        "type": "error",
                    }
                ],
            },
        ]

"""Behavioral tests for the /autoname extension.

These drive the registered command handler and the pure helpers against a fake
Pi host, so a change that breaks digest bounding, answer cleaning, or the
fail-closed paths reports a failure.
"""

import json
import subprocess
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
AUTONAME_EXTENSION = UTILS_PKG_DIR / "extensions" / "autoname.ts"


def run_autoname(script: str) -> dict:
    """Run an ESM snippet with the autoname extension importable as `autoname`."""
    prelude = f"import * as autoname from {json.dumps(AUTONAME_EXTENSION.as_uri())};\n"
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=prelude + script,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


HARNESS = """
const notifications = [];
const setCalls = [];
const commands = new Map();
const pi = {
  registerCommand: (name, spec) => commands.set(name, spec),
  setSessionName: (name) => setCalls.push(name),
};
autoname.default(pi);

function makeContext(overrides = {}) {
  return {
    model: { provider: "test", id: "test-model" },
    cwd: "/Users/dev/Developer/acme/widget-factory",
    signal: undefined,
    hasUI: true,
    ui: { notify: (message, type) => notifications.push({ message, type }) },
    sessionManager: {
      getSessionId: () => "sess-123",
      getBranch: () => [
        { type: "message", message: { role: "user", content: [{ type: "text", text: "fix the flaky worktree redirect" }] } },
        { type: "message", message: { role: "assistant", content: [{ type: "text", text: "Sure, I looked at the parser." }], stopReason: "stop" } },
      ],
    },
    modelRegistry: makeRegistry("Worktree Redirect Fix"),
    ...overrides,
  };
}

function answerOf(answer, options) {
  if (options.throwError) throw new Error("provider exploded");
  if (options.neverSettles) return new Promise(() => {});
  if (options.providerError) {
    return Promise.resolve({ role: "assistant", content: [], stopReason: "error", errorMessage: options.providerError });
  }
  if (options.thinkingOnly) {
    return Promise.resolve({ content: [{ type: "thinking", thinking: "We need answer 2 to 4 words." }], stopReason: "length" });
  }
  return Promise.resolve({ content: [{ type: "text", text: answer }] });
}

function makeRegistry(answer, options = {}) {
  const registry = {
    calls: [],
    getApiKeyAndHeaders: async () =>
      options.noAuth ? { ok: false } : { ok: true, apiKey: "k", headers: {} },
    // Both transport shapes are recorded, so a test states what the model
    // receives rather than which entry point the extension happens to call.
    streamSimple: (model, context, opts) => {
      registry.calls.push({ model, context, opts });
      return { result: () => answerOf(answer, options) };
    },
    complete: (model, context, opts) => {
      registry.calls.push({ model, context, opts });
      return answerOf(answer, options);
    },
  };
  return registry;
}

export async function run(args, ctx) {
  const spec = commands.get("autoname");
  if (!spec) throw new Error("autoname command was not registered");
  await spec.handler(args, ctx);
  return { setCalls: [...setCalls], notifications: [...notifications] };
}
export function reset() {
  setCalls.length = 0;
  notifications.length = 0;
}
export { makeContext, makeRegistry };
"""


def reasoning_script(body: str) -> str:
    """A harness whose model reasons first and shares one budget with the answer.

    The fake mirrors an OpenAI-compatible reasoning gateway: it emits thinking
    until the budget runs out, so a request that leaves no room for the answer
    comes back with a thinking block and no text.
    """
    prelude = """
function makeReasoningRegistry(answer) {
  const registry = {
    calls: [],
    getApiKeyAndHeaders: async () => ({ ok: true, apiKey: "k", headers: {} }),
    respond: (opts) =>
      opts.reasoning === "off"
        ? { content: [{ type: "text", text: answer }], stopReason: "stop" }
        : { content: [{ type: "thinking", thinking: "We need answer 2 to 4 words." }], stopReason: "length" },
    streamSimple: (model, context, opts) => {
      registry.calls.push({ model, context, opts });
      return { result: async () => registry.respond(opts) };
    },
    complete: (model, context, opts) => {
      registry.calls.push({ model, context, opts });
      return Promise.resolve(registry.respond(opts));
    },
  };
  return registry;
}
"""
    return HARNESS + prelude + "\n" + body


def autoname_script(body: str) -> str:
    return HARNESS + "\n" + body


class AutonameCommandTests(unittest.TestCase):
    def test_names_the_session_and_confirms(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext();
const result = await run("", ctx);
console.log(JSON.stringify({ result, digest: ctx.modelRegistry.calls[0].context }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], ["Worktree Redirect Fix"])
        infos = [n for n in report["result"]["notifications"] if n["type"] == "info"]
        self.assertEqual(len(infos), 1)
        self.assertIn("Worktree Redirect Fix", infos[0]["message"])
        # The name must be derived from the session, not the repository alone.
        digest = report["digest"]["messages"][0]["content"][0]["text"]
        self.assertIn("fix the flaky worktree redirect", digest)
        self.assertIn("widget-factory", digest)

    def test_argument_steers_the_generated_name(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext();
await run("release notes rewrite", ctx);
const sent = ctx.modelRegistry.calls[0].context.messages[0].content[0].text;
console.log(JSON.stringify({ sent }));
"""
            )
        )
        self.assertIn("release notes rewrite", report["sent"])

    def test_digest_keeps_only_user_requests_and_stays_bounded(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const long = "x".repeat(4000);
const entries = [
  { type: "message", message: { role: "user", content: [{ type: "text", text: "first request " + long }] } },
  { type: "message", message: { role: "assistant", content: [{ type: "text", text: "assistant answer " + long }], stopReason: "stop" } },
  { type: "message", message: { role: "toolResult", content: "tool output must never steer the name" } },
  { type: "custom", customType: "recap", data: { recap: "custom entry text" } },
];
for (let i = 0; i < 10; i++) {
  entries.push({ type: "message", message: { role: "user", content: [{ type: "text", text: "follow up " + i }] } });
}
const digest = autoname.buildDigest(entries, "/Users/dev/Developer/acme/widget-factory");
const requests = autoname.collectUserRequests(entries);
console.log(JSON.stringify({
  digest,
  limit: autoname.AUTONAME_DIGEST_LIMIT,
  requestCount: requests.length,
}));
"""
            )
        )
        digest = report["digest"]
        self.assertLessEqual(len(digest), report["limit"] + 3)
        self.assertIn("first request", digest)
        # Assistant answers, tool results, and custom entries must not appear.
        self.assertNotIn("assistant answer", digest)
        self.assertNotIn("tool output must never steer the name", digest)
        self.assertNotIn("custom entry text", digest)
        # Bounded to the request budget, not every request in a long session.
        self.assertEqual(report["requestCount"], 11)

    def test_digest_honours_a_smaller_budget(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const entries = [
  { type: "message", message: { role: "user", content: [{ type: "text", text: "a".repeat(500) }] } },
];
console.log(JSON.stringify({ small: autoname.buildDigest(entries, "/tmp/x", 100) }));
"""
            )
        )
        self.assertLessEqual(len(report["small"]), 103)

    def test_missing_model_fails_closed(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const result = await run("", makeContext({ model: undefined }));
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertEqual(report["result"]["notifications"][0]["type"], "error")

    def test_missing_credentials_fail_closed(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext({ modelRegistry: makeRegistry("Anything", { noAuth: true }) });
const result = await run("", ctx);
console.log(JSON.stringify({ result, calls: ctx.modelRegistry.calls.length }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertEqual(report["calls"], 0)
        self.assertEqual(report["result"]["notifications"][0]["type"], "error")

    def test_unusable_answer_sets_no_name(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const observed = {};
for (const answer of ["", "   ", "...", "***", "```"]) {
  reset();
  const ctx = makeContext({ modelRegistry: makeRegistry(answer) });
  observed[answer || "empty"] = await run("", ctx);
}
console.log(JSON.stringify({ observed }));
"""
            )
        )
        for label, result in report["observed"].items():
            with self.subTest(answer=label):
                self.assertEqual(result["setCalls"], [])
                self.assertEqual(result["notifications"][0]["type"], "error")


class AutonameReasoningTests(unittest.TestCase):
    def test_a_reasoning_model_still_names_the_session(self) -> None:
        """A gateway that reasons by default must not spend the whole budget."""
        report = run_autoname(
            reasoning_script(
                """
const registry = makeReasoningRegistry("Worktree Redirect Fix");
const result = await run("", makeContext({ modelRegistry: registry }));
const opts = registry.calls[0].opts;
console.log(JSON.stringify({ result, reasoning: opts.reasoning, maxTokens: opts.maxTokens }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], ["Worktree Redirect Fix"])
        self.assertEqual(report["reasoning"], "off")
        # The budget must exceed a reasoning phase, not just the answer itself.
        self.assertGreaterEqual(report["maxTokens"], 1024)

    def test_a_thinking_only_answer_names_its_own_cause(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const result = await run("", makeContext({ modelRegistry: makeRegistry("", { thinkingOnly: true }) }));
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertEqual(report["result"]["notifications"][0]["type"], "error")
        self.assertIn("reasoning", report["result"]["notifications"][0]["message"])


class AutonameNameCleaningTests(unittest.TestCase):
    def test_strips_decoration_and_keeps_the_first_line(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const cases = [
  ['"Worktree Redirect Fix"', "Worktree Redirect Fix"],
  ["'Worktree Redirect Fix'", "Worktree Redirect Fix"],
  ["`Worktree Redirect Fix`", "Worktree Redirect Fix"],
  ["**Worktree Redirect Fix**", "Worktree Redirect Fix"],
  ["- Worktree Redirect Fix", "Worktree Redirect Fix"],
  ["## Worktree Redirect Fix", "Worktree Redirect Fix"],
  ["Name: Worktree Redirect Fix", "Worktree Redirect Fix"],
  ["Session name - Worktree Redirect Fix", "Worktree Redirect Fix"],
  ["Worktree Redirect Fix.\\nThis is why I chose it.", "Worktree Redirect Fix"],
  ["\\n\\n  Worktree Redirect Fix  ", "Worktree Redirect Fix"],
];
const observed = {};
for (const [raw, expected] of cases) {
  observed[raw] = { got: autoname.cleanSessionName(raw), expected };
}
console.log(JSON.stringify({ observed }));
"""
            )
        )
        for raw, case in report["observed"].items():
            with self.subTest(raw=raw):
                self.assertEqual(case["got"], case["expected"])

    def test_cuts_an_over_long_name_at_a_word_boundary(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const raw = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet";
const got = autoname.cleanSessionName(raw);
const clipped = autoname.cleanSessionName("Supercalifragilisticexpialidocious", 10);
console.log(JSON.stringify({ got, length: got.length, limit: autoname.AUTONAME_NAME_LIMIT, clipped }));
"""
            )
        )
        self.assertLessEqual(len(report["got"]), report["limit"])
        self.assertEqual(report["got"], "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India")
        # A single unbroken token has no word boundary, so it is cut as-is
        # rather than discarded for having no space.
        self.assertEqual(report["clipped"], "Supercalif")

    def test_returns_empty_when_nothing_displayable_survives(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const cases = ["", "   ", "...", "***", "```", "---", "\\n\\n"];
const observed = {};
for (const raw of cases) observed[raw || "empty"] = autoname.cleanSessionName(raw);
console.log(JSON.stringify({ observed }));
"""
            )
        )
        for label, value in report["observed"].items():
            with self.subTest(raw=label):
                self.assertEqual(value, "")


class AutonameSettlementTests(unittest.TestCase):
    def test_provider_error_settles_without_a_name(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext({ modelRegistry: makeRegistry("Anything", { throwError: true }) });
const result = await run("", ctx);
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertEqual(report["result"]["notifications"][0]["type"], "error")

    def test_provider_that_never_answers_settles_on_the_deadline(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const started = Date.now();
const registry = makeRegistry("Anything", { neverSettles: true });
const outcome = await autoname.generateSessionName(
  registry,
  { provider: "test", id: "test-model" },
  "digest",
  undefined,
  undefined,
  250,
);
console.log(JSON.stringify({ outcome, elapsed: Date.now() - started }));
"""
            ),
        )
        self.assertFalse(report["outcome"]["ok"])
        self.assertEqual(report["outcome"]["reason"], "aborted")
        self.assertLess(report["elapsed"], 5000)

    def test_an_already_aborted_signal_short_circuits(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const registry = makeRegistry("Worktree Redirect Fix");
const controller = new AbortController();
controller.abort();
const outcome = await autoname.generateSessionName(
  registry,
  { provider: "test", id: "test-model" },
  "digest",
  undefined,
  controller.signal,
);
console.log(JSON.stringify({ outcome, calls: registry.calls.length }));
"""
            )
        )
        self.assertFalse(report["outcome"]["ok"])
        self.assertEqual(report["outcome"]["reason"], "aborted")
        self.assertEqual(report["calls"], 0)

    def test_aborting_mid_request_yields_no_name(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const registry = makeRegistry("Worktree Redirect Fix", { neverSettles: true });
const controller = new AbortController();
setTimeout(() => controller.abort(), 100);
const outcome = await autoname.generateSessionName(
  registry,
  { provider: "test", id: "test-model" },
  "digest",
  undefined,
  controller.signal,
  10_000,
);
console.log(JSON.stringify({ outcome }));
"""
            )
        )
        self.assertFalse(report["outcome"]["ok"])
        self.assertEqual(report["outcome"]["reason"], "aborted")


class AutonameRequestTests(unittest.TestCase):
    def test_the_session_id_is_forwarded_for_conversation_routing(self) -> None:
        """Gateways such as OpenCode reject a nested call with no session id."""
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext();
await run("", ctx);
console.log(JSON.stringify({ sessionId: ctx.modelRegistry.calls[0].opts.sessionId }));
"""
            )
        )
        self.assertEqual(report["sessionId"], "sess-123")

    def test_a_rejected_request_is_reported_as_a_provider_failure(self) -> None:
        """A provider rejection arrives as a message, not as a thrown error."""
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext({
  modelRegistry: makeRegistry("", { providerError: "400 MissingSessionID" }),
});
const result = await run("", ctx);
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertEqual(report["result"]["notifications"][0]["type"], "error")
        # The message must not blame the credentials for a routing failure.
        self.assertIn(
            "could not produce a session name",
            report["result"]["notifications"][0]["message"],
        )

    def test_the_request_asks_for_a_subject_not_a_restatement(self) -> None:
        """A model otherwise answers with the conversation restated as a command."""
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext();
await run("", ctx);
console.log(JSON.stringify({ sent: ctx.modelRegistry.calls[0].context.messages[0].content[0].text }));
"""
            )
        )
        sent = report["sent"]
        self.assertIn("Start with a noun", sent)
        self.assertIn("Never begin with a verb", sent)
        self.assertIn('Good: "Worktree root selection"', sent)
        self.assertIn('Bad: "Fix the utils package"', sent)

    def test_each_failure_names_its_own_cause(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const messages = {
  noCredentials: autoname.FAILURE_MESSAGES["no-credentials"],
  provider: autoname.FAILURE_MESSAGES["provider"],
  unusable: autoname.FAILURE_MESSAGES["unusable"],
  aborted: autoname.FAILURE_MESSAGES["aborted"],
};
console.log(JSON.stringify({ messages }));
"""
            )
        )
        messages = report["messages"]
        self.assertIn("credentials", messages["noCredentials"])
        for label in ("provider", "unusable", "aborted"):
            self.assertNotIn("credentials", messages[label], label)

    def test_the_request_is_a_bounded_one_shot_without_reasoning(self) -> None:
        report = run_autoname(
            autoname_script(
                """
const ctx = makeContext();
await run("", ctx);
const call = ctx.modelRegistry.calls[0];
console.log(JSON.stringify({
  systemPrompt: call.context.systemPrompt,
  maxTokens: call.opts.maxTokens,
  budget: autoname.AUTONAME_MAX_TOKENS,
  reasoning: call.opts.reasoning,
  temperature: call.opts.temperature,
  cacheRetention: call.opts.cacheRetention,
  role: call.context.messages[0].role,
  tools: call.context.tools ?? null,
}));
"""
            )
        )
        self.assertIn("session display names", report["systemPrompt"])
        self.assertEqual(report["maxTokens"], report["budget"])
        self.assertEqual(report["reasoning"], "off")
        self.assertEqual(report["temperature"], 0)
        self.assertEqual(report["cacheRetention"], "none")
        self.assertEqual(report["role"], "user")
        # A name request needs no tools, so none are declared.
        self.assertIsNone(report["tools"])


class AutonameManifestTests(unittest.TestCase):
    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertTrue((UTILS_PKG_DIR / "index.ts").is_file())
        self.assertIn("@earendil-works/pi-coding-agent", manifest["peerDependencies"])

    def test_index_wires_the_autoname_command(self) -> None:
        index = (UTILS_PKG_DIR / "index.ts").read_text(encoding="utf-8")
        self.assertIn("registerAutoname(pi)", index)
        self.assertIn("./extensions/autoname.ts", index)


if __name__ == "__main__":
    unittest.main()
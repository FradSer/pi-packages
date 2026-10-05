"""Behavioral tests for the /effort extension.

These drive the registered command handler against a fake Pi host, so a change
that breaks menu narrowing, alias resolution or rejection reports a failure.
A separate parity test pins the local mirror of pi's `getSupportedThinkingLevels`
against the function pi itself exports.
"""

import json
import subprocess
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
EFFORT_EXTENSION = UTILS_PKG_DIR / "extensions" / "effort.ts"


def run_effort(script: str) -> dict:
    """Run an ESM snippet with the effort extension importable as `effort`."""
    prelude = f"import * as effort from {json.dumps(EFFORT_EXTENSION.as_uri())};\n"
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=prelude + script,
        capture_output=True,
        text=True,
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
  getThinkingLevel: () => "high",
  setThinkingLevel: (level) => setCalls.push(level),
};
effort.default(pi);

function makeContext(overrides = {}) {
  return {
    model: undefined,
    thinkingLevel: "high",
    hasUI: true,
    ui: {
      select: async (_prompt, options) => options[0],
      notify: (message, type) => notifications.push({ message, type }),
    },
    ...overrides,
  };
}

export async function run(args, ctx) {
  const spec = commands.get("effort");
  if (!spec) throw new Error("effort command was not registered");
  await spec.handler(args, ctx);
  return { setCalls: [...setCalls], notifications: [...notifications] };
}
export function reset() {
  setCalls.length = 0;
  notifications.length = 0;
}
export async function completions(prefix) {
  return commands.get("effort").getArgumentCompletions(prefix);
}
"""


def effort_script(body: str) -> str:
    return HARNESS + "\n" + body


class EffortBehaviorTests(unittest.TestCase):
    def test_sets_canonical_level_and_alias(self) -> None:
        report = run_effort(
            effort_script(
                """
const cases = [["max", "max"], ["high", "high"], ["min", "minimal"], ["med", "medium"], ["xh", "xhigh"], ["none", "off"], ["0", "off"], ["MAX", "max"]];
const observed = [];
for (const [args, expected] of cases) {
  reset();
  const result = await run(args, makeContext());
  observed.push({ args, expected, setCalls: result.setCalls });
}
console.log(JSON.stringify({ observed }));
"""
            )
        )
        for case in report["observed"]:
            with self.subTest(args=case["args"]):
                self.assertEqual(case["setCalls"], [case["expected"]])

    def test_rejects_unknown_level_without_setting_anything(self) -> None:
        report = run_effort(
            effort_script(
                """
const result = await run("turbo", makeContext());
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], [])
        errors = [n for n in report["result"]["notifications"] if n["type"] == "error"]
        self.assertEqual(len(errors), 1)
        for level in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
            self.assertIn(level, errors[0]["message"])

    def test_menu_offers_only_levels_the_model_supports(self) -> None:
        report = run_effort(
            effort_script(
                """
const offered = {};
for (const [label, model] of [
  ["reasoning false", { reasoning: false }],
  ["reasoning undefined", {}],
  ["no map", { reasoning: true }],
  ["null entry hides level", { reasoning: true, thinkingLevelMap: { high: null } }],
  ["xhigh and max need entries", { reasoning: true, thinkingLevelMap: { xhigh: "xhigh", max: "max" } }],
  ["only xhigh entry", { reasoning: true, thinkingLevelMap: { xhigh: "xhigh" } }],
]) {
  const ctx = makeContext({ model });
  const options = [];
  ctx.ui.select = async (_prompt, items) => { options.push(...items); return undefined; };
  await run("", ctx);
  offered[label] = options;
}
console.log(JSON.stringify({ offered }));
"""
            )
        )
        offered = report["offered"]
        # The current level is "high" in this harness, so a menu without it
        # marks nothing.
        self.assertEqual(offered["reasoning false"], ["off"])
        # pi treats an absent `reasoning` flag as no reasoning support.
        self.assertEqual(offered["reasoning undefined"], ["off"])
        self.assertEqual(
            offered["no map"],
            ["off", "minimal", "low", "medium", "high (current)"],
        )
        # The null entry hides `high`, and `xhigh`/`max` stay hidden because the map
        # declares no entry for them. The current level ("high" here) is not in
        # the menu, so nothing is marked.
        self.assertEqual(
            offered["null entry hides level"],
            ["off", "minimal", "low", "medium"],
        )
        self.assertEqual(
            offered["xhigh and max need entries"],
            ["off", "minimal", "low", "medium", "high (current)", "xhigh", "max"],
        )
        self.assertEqual(
            offered["only xhigh entry"],
            ["off", "minimal", "low", "medium", "high (current)", "xhigh"],
        )

    def test_menu_marks_the_current_level_and_applies_the_selection(self) -> None:
        report = run_effort(
            effort_script(
                """
const ctx = makeContext({ model: { reasoning: true }, thinkingLevel: "low" });
ctx.ui.select = async (_prompt, options) => options[options.indexOf("high")];
const result = await run("", ctx);
console.log(JSON.stringify({ result }));
"""
            )
        )
        self.assertEqual(report["result"]["setCalls"], ["high"])
        infos = [n for n in report["result"]["notifications"] if n["type"] == "info"]
        self.assertEqual(len(infos), 1)
        self.assertIn("high", infos[0]["message"])

    def test_headless_session_reports_instead_of_opening_a_menu(self) -> None:
        report = run_effort(
            effort_script(
                """
const ctx = makeContext({ hasUI: false, thinkingLevel: "medium" });
let opened = false;
ctx.ui.select = async () => { opened = true; return undefined; };
const result = await run("", ctx);
console.log(JSON.stringify({ result, opened }));
"""
            )
        )
        self.assertFalse(report["opened"])
        self.assertEqual(report["result"]["setCalls"], [])
        self.assertIn("medium", report["result"]["notifications"][0]["message"])

    def test_argument_completions_offer_aliases(self) -> None:
        report = run_effort(
            effort_script(
                """
console.log(JSON.stringify({
  m: (await completions("m")).map((item) => item.value),
  x: (await completions("x")).map((item) => item.value),
}));
"""
            )
        )
        self.assertEqual(sorted(report["m"]), ["max", "med", "medium", "min", "minimal"])
        self.assertEqual(sorted(report["x"]), ["xh", "xhigh"])


class EffortParityTests(unittest.TestCase):
    """The menu mirror must not drift from the function pi exports."""

    def test_matches_pi_supported_thinking_levels(self) -> None:
        report = run_effort(
            f"""
import {{ getSupportedThinkingLevels }} from "@earendil-works/pi-ai";
const models = [
  {{ reasoning: true }},
  {{ reasoning: false }},
  {{}},
  {{ reasoning: true, thinkingLevelMap: {{}} }},
  {{ reasoning: true, thinkingLevelMap: {{ high: null }} }},
  {{ reasoning: true, thinkingLevelMap: {{ xhigh: "xhigh", max: "max" }} }},
  {{ reasoning: true, thinkingLevelMap: {{ max: null }} }},
  {{ reasoning: true, thinkingLevelMap: {{ minimal: "minimal", low: "low", medium: "medium" }} }},
];
const mismatches = [];
for (const model of models) {{
  const piLevels = getSupportedThinkingLevels(model);
  const localLevels = effort.supportedThinkingLevelsFor(model);
  if (JSON.stringify(piLevels) !== JSON.stringify(localLevels)) {{
    mismatches.push({{ model, piLevels, localLevels }});
  }}
}}
console.log(JSON.stringify({{ mismatches, checked: models.length }}));
"""
        )
        self.assertEqual(report["checked"], 8)
        self.assertEqual(report["mismatches"], [])


class EffortManifestTests(unittest.TestCase):
    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertTrue((UTILS_PKG_DIR / "index.ts").is_file())
        self.assertIn("@earendil-works/pi-coding-agent", manifest["peerDependencies"])

    def test_no_claude_only_artifacts(self) -> None:
        self.assertFalse((UTILS_PKG_DIR / ".claude-plugin").exists())


if __name__ == "__main__":
    unittest.main()
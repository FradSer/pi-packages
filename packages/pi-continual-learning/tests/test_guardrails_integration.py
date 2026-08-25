from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]

SCENARIOS = """
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const out = [];
function record(name, value) {
  out.push(JSON.stringify({ name, ...value }));
}

// ── mock ExtensionAPI ────────────────────────────────────────────────
const hooks = {};
const commands = {};
const pi = {
  on: (name, fn) => {
    (hooks[name] ??= []).push(fn);
  },
  registerCommand: (name, def) => {
    commands[name] = def;
  },
};

const mod = await import("./packages/pi-continual-learning/index.ts");
mod.default(pi);

async function callTool(toolName, args, ctx) {
  const results = [];
  for (const fn of hooks.tool_call ?? []) {
    results.push(await fn({ toolName, input: args }, ctx));
  }
  return results.filter(Boolean);
}

// ── temp project + isolated user dir ────────────────────────────────
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-e2e-"));
const project = path.join(tmp, "project");
fs.mkdirSync(path.join(project, ".pi"), { recursive: true });
const agentDir = path.join(tmp, "agent");
fs.mkdirSync(agentDir, { recursive: true });

process.env.PI_GUARDRAILS_AGENT_DIR = agentDir;
delete process.env.PI_GUARDRAILS_AGENT_DIR; // start from production state
const baseCtx = { cwd: project, hasUI: false };

// ── S1: built-in defaults active with no config files ────────────────
{
  const [login, normal] = await Promise.all([
    callTool("bash", { command: "npm login" }, baseCtx),
    callTool("bash", { command: "pnpm test" }, baseCtx),
  ]);
  record("defaults-block-login", {
    blocked: login.length === 1 && login[0].block === true,
    guided: /their own terminal/.test(login[0]?.reason ?? ""),
    passedThrough: normal.length === 0,
  });
}

// ── S2: project harness.json gates UI widths by require + paths ──────
fs.writeFileSync(
  path.join(project, ".pi", "harness.json"),
  JSON.stringify({
    policies: [
      {
        name: "ui-fixed-width",
        tools: ["edit", "write"],
        require: { path: "path", pattern: "\\\\.(tsx|css)$" },
        paths: ["content", "newText", "edits.newText"],
        patterns: ["width:\\\\s*\\\\d{3,}px"],
        action: "block",
        reason: "Use design tokens and min(100%, var(--token)).",
      },
      {
        name: "danger-wipe",
        tools: ["bash"],
        path: "command",
        pattern: "wipe--workspace",
        action: "confirm",
        reason: "Destructive workspace wipe needs confirmation.",
      },
    ],
  }),
);

{
  await new Promise((r) => setTimeout(r, 20)); // let mtime advance past cache
  const uiEdit = await callTool(
    "edit",
    { path: "src/Button.tsx", edits: [{ newText: "width: 480px;" }] },
    baseCtx,
  );
  const mdEdit = await callTool(
    "edit",
    { path: "docs/notes.md", edits: [{ newText: "width: 480px;" }] },
    baseCtx,
  );
  // oldText trap regression: fixing a violation quotes it as oldText
  const fixEdit = await callTool(
    "edit",
    {
      path: "src/Button.tsx",
      edits: [{ oldText: "width: 480px;", newText: "width: min(100%, var(--hud-card-width));" }],
    },
    baseCtx,
  );
  record("ui-policy-gated", {
    uiBlocked: uiEdit.length === 1 && uiEdit[0].block === true,
    tokensMentioned: /design tokens|min\(100%/.test(uiEdit[0]?.reason ?? ""),
    mdPassed: mdEdit.length === 0,
    oldTextTrapFixed: fixEdit.length === 0,
  });
}

// ── S3: confirm action blocks headlessly, allows when approved ───────
{
  const headless = await callTool(
    "bash",
    { command: "wipe--workspace now" },
    baseCtx,
  );
  const uiCtx = { ...baseCtx, hasUI: true, ui: { select: async () => "Allow once" } };
  const allowed = await callTool("bash", { command: "wipe--workspace now" }, uiCtx);
  const denyCtx = { ...baseCtx, hasUI: true, ui: { select: async () => "Block" } };
  const denied = await callTool("bash", { command: "wipe--workspace now" }, denyCtx);
  record("confirm-action", {
    headlessBlocked: headless[0]?.block === true && /no UI available/.test(headless[0]?.reason ?? ""),
    allowedOnce: allowed.length === 0,
    deniedBlocked: denied[0]?.block === true,
  });
}

// ── S4: user layer disables a built-in and adds its own rule ─────────
process.env.PI_GUARDRAILS_AGENT_DIR = agentDir;
fs.writeFileSync(
  path.join(agentDir, "harness.json"),
  JSON.stringify({
    disabled: ["no-interactive-auth-automation"],
    policies: [
      {
        name: "block-curl-prod",
        tools: ["bash"],
        path: "command",
        pattern: "curl .*prod\\.example\\.com",
        action: "block",
        reason: "Prod curl is forbidden.",
      },
    ],
  }),
);
await new Promise((r) => setTimeout(r, 20));
{
  const login = await callTool("bash", { command: "npm login" }, baseCtx);
  const prodCurl = await callTool(
    "bash",
    { command: "curl https://prod.example.com/api" },
    baseCtx,
  );
  record("user-layer", {
    disabledBuiltInGone: login.length === 0,
    userRuleFires:
      prodCurl.length === 1 &&
      prodCurl[0].block === true &&
      /Prod curl/.test(prodCurl[0].reason),
  });
}

// ── S5: cache invalidation on later user-file edit ───────────────────
{
  const later = JSON.parse(
    fs.readFileSync(path.join(agentDir, "harness.json"), "utf8"),
  );
  // Retarget the rule from prod to stage AND change its reason, so the
  // fresh-config effect is observable in both directions.
  later.policies[0].pattern = "curl .*stage\\.example\\.com";
  later.policies[0].reason = "Stage curl needs approval.";
  const future = new Date(Date.now() + 60_000);
  fs.writeFileSync(path.join(agentDir, "harness.json"), JSON.stringify(later));
  fs.utimesSync(path.join(agentDir, "harness.json"), future, future);
  const stage = await callTool(
    "bash",
    { command: "curl https://stage.example.com/api" },
    baseCtx,
  );
  const prod = await callTool(
    "bash",
    { command: "curl https://prod.example.com/api" },
    baseCtx,
  );
  record("cache-invalidation", {
    freshRuleSeen:
      stage.length === 1 &&
      stage[0].block === true &&
      /Stage curl needs approval/.test(stage[0].reason),
    oldRuleRetired: prod.length === 0,
  });
}

// ── S6: /guardrails command reports surface, headless-safe ──────────
{
  let notified = "";
  const cmdCtx = { ...baseCtx, ui: { notify: (msg) => (notified = msg) } };
  await commands.guardrails.handler("", cmdCtx);
  record("command-surface", {
    listsPolicies: notified.includes("ui-fixed-width") && notified.includes("block-curl-prod"),
    showsPaths: notified.includes("harness.json") && notified.includes(".local"),
  });
}

console.log(out.join("\\n"));
"""

result = subprocess.run(
    ["bun", "-e", SCENARIOS],
    cwd=REPO,
    capture_output=True,
    text=True,
    check=False,
    timeout=120,
)
assert result.returncode == 0, f"harness crashed:\n{result.stderr[-3000:]}"


def scenarios() -> dict[str, dict[str, object]]:
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    return {json.loads(line)["name"]: json.loads(line) for line in lines}


ALL = scenarios()


def test_s1_defaults_block_login_with_guidance() -> None:
    s = ALL["defaults-block-login"]
    assert s["blocked"] and s["guided"] and s["passedThrough"]


def test_s2_ui_policy_gated_by_require_and_paths() -> None:
    s = ALL["ui-policy-gated"]
    assert s["uiBlocked"] and s["tokensMentioned"]
    assert s["mdPassed"] and s["oldTextTrapFixed"]


def test_s3_confirm_action_headless_and_interactive() -> None:
    s = ALL["confirm-action"]
    assert s["headlessBlocked"] and s["allowedOnce"] and s["deniedBlocked"]


def test_s4_user_layer_disable_and_extend() -> None:
    s = ALL["user-layer"]
    assert s["disabledBuiltInGone"] and s["userRuleFires"]


def test_s5_cache_invalidates_on_later_user_edit() -> None:
    s = ALL["cache-invalidation"]
    assert s["freshRuleSeen"] and s["oldRuleRetired"]


def test_s6_command_reports_surface() -> None:
    s = ALL["command-surface"]
    assert s["listsPolicies"] and s["showsPaths"]

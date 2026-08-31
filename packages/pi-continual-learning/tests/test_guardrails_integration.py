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
import { initTheme } from "@earendil-works/pi-coding-agent";

initTheme("dark");
const out = [];
function record(name, value) {
  out.push(JSON.stringify({ name, ...value }));
}

// ── mock ExtensionAPI ────────────────────────────────────────────────
const hooks = {};
const commands = {};
const renderers = {};
const entryRenderers = {};
const entries = [];
const pi = {
  on: (name, fn) => {
    (hooks[name] ??= []).push(fn);
  },
  registerCommand: (name, def) => {
    commands[name] = def;
  },
  registerMessageRenderer: (name, renderer) => {
    renderers[name] = renderer;
  },
  registerEntryRenderer: (name, renderer) => {
    entryRenderers[name] = renderer;
  },
  appendEntry: (customType, data) => {
    entries.push({ customType, data });
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

async function callBefore(prompt, systemPrompt, ctx, onlyGuardrails = false) {
  let currentSystemPrompt = systemPrompt;
  const results = [];
  const handlers = onlyGuardrails ? (hooks.before_agent_start ?? []).slice(-1) : (hooks.before_agent_start ?? []);
  for (const fn of handlers) {
    // Pi retains one context for a turn but creates a new event per handler.
    const event = {
      type: "before_agent_start",
      prompt,
      images: undefined,
      systemPrompt: currentSystemPrompt,
      systemPromptOptions: {},
    };
    const result = await fn(event, ctx);
    results.push(result);
    if (result?.systemPrompt !== undefined) currentSystemPrompt = result.systemPrompt;
  }
  return { event: { systemPrompt: currentSystemPrompt }, results: results.filter(Boolean) };
}

// ── temp project + isolated user dir ────────────────────────────────
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-e2e-"));
const project = path.join(tmp, "project");
fs.mkdirSync(path.join(project, ".pi"), { recursive: true });
const agentDir = path.join(tmp, "agent");
fs.mkdirSync(agentDir, { recursive: true });

process.env.PI_CODING_AGENT_DIR = agentDir;
delete process.env.PI_CODING_AGENT_DIR; // start from production state
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
        paths: ["command"],
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
    tokensMentioned: /design tokens|min\\(100%/.test(uiEdit[0]?.reason ?? ""),
    mdPassed: mdEdit.length === 0,
    oldTextTrapFixed: fixEdit.length === 0,
  });
}

// ── S3: confirm action blocks headlessly, allows when approved, and
//      fails closed when the dialog expires unanswered ────────────────
{
  const headless = await callTool(
    "bash",
    { command: "wipe--workspace now" },
    baseCtx,
  );
  let askedTimeout;
  const selecting = (answer) => async (_title, _options, opts) => {
    askedTimeout = opts?.timeout;
    return answer; // undefined simulates the countdown expiring
  };
  const uiCtx = { ...baseCtx, hasUI: true, ui: { select: selecting("Allow once") } };
  const allowed = await callTool("bash", { command: "wipe--workspace now" }, uiCtx);
  const denyCtx = { ...baseCtx, hasUI: true, ui: { select: selecting("Block") } };
  const denied = await callTool("bash", { command: "wipe--workspace now" }, denyCtx);
  const expiredCtx = { ...baseCtx, hasUI: true, ui: { select: selecting(undefined) } };
  const expired = await callTool("bash", { command: "wipe--workspace now" }, expiredCtx);
  const lastPolicyEntry = entries.find((e) => e.data?.kind === "policy-matched" && e.data?.outcome === "allowed once");
  const renderer = entryRenderers["harness-event"];
  const renderedAllowed = renderer?.(lastPolicyEntry, { expanded: true }, {
    fg: (_c, t) => t,
    bg: (_c, t) => t,
    bold: (t) => t,
  })?.render(200).join("\\n") ?? "";
  record("confirm-action", {
    headlessBlocked: headless[0]?.block === true && /no UI available/.test(headless[0]?.reason ?? ""),
    dialogBounded: typeof askedTimeout === "number" && Number.isFinite(askedTimeout) && askedTimeout > 0,
    allowedOnce: allowed.length === 0,
    deniedBlocked: denied[0]?.block === true && /user choice/.test(denied[0]?.reason ?? ""),
    timeoutFailsClosed: expired[0]?.block === true && /timed out/.test(expired[0]?.reason ?? ""),
    singleEventForAllowed: entries.filter((e) => e.data?.kind === "policy-matched" && e.data?.policy === "danger-wipe" && e.data?.outcome === "allowed once").length === 1,
    entryRecorded: lastPolicyEntry?.data?.policy === "danger-wipe" && lastPolicyEntry?.data?.action === "confirm",
    entryRenderUsesReason: renderedAllowed.includes("[harness] policy allowed · Destructive workspace wipe needs confirmation") && renderedAllowed.includes("outcome=allowed once"),
  });
}

// ── S4: observe action records a matching call but proceeds ─────────
{
  const projectHarness = JSON.parse(fs.readFileSync(path.join(project, ".pi", "harness.json"), "utf8"));
  projectHarness.policies.push({
    name: "observe-live",
    tools: ["bash"],
    paths: ["command"],
    pattern: "live\\\\.mjs",
    action: "observe",
    reason: "Live boot uses the current helper state.",
  });
  fs.writeFileSync(path.join(project, ".pi", "harness.json"), JSON.stringify(projectHarness));
  await new Promise((r) => setTimeout(r, 20));
  const observed = await callTool("bash", { command: "node live.mjs" }, baseCtx);
  const observedEntry = entries.find((e) => e.data?.kind === "policy-matched" && e.data?.policy === "observe-live");
  record("observe-action", {
    proceeded: observed.length === 0,
    recorded: observedEntry?.data?.action === "observe" && observedEntry?.data?.outcome === "observed",
  });
}

// ── S5: standard agent-dir override shares memory's user layer ──────
process.env.PI_CODING_AGENT_DIR = agentDir;
fs.writeFileSync(
  path.join(agentDir, "harness.json"),
  JSON.stringify({
    disabled: ["no-interactive-auth-automation"],
    policies: [
      {
        name: "block-curl-prod",
        tools: ["bash"],
        paths: ["command"],
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
    standardDirHonored: process.env.PI_CODING_AGENT_DIR === agentDir,
    disabledBuiltInGone: login.length === 0,
    userRuleFires:
      prodCurl.length === 1 &&
      prodCurl[0].block === true &&
      /Prod curl/.test(prodCurl[0].reason),
  });
}

// ── S6: cache invalidation on later user-file edit ───────────────────
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

// ── S7: layered skill prompt injection uses Pi's expanded skill shape ──
fs.writeFileSync(
  path.join(agentDir, "harness.json"),
  JSON.stringify({
    skillPrompts: {
      review: { prompt: "outer guidance", target: "system" },
      usernote: { prompt: "user guidance", target: "user" },
      "bad--skill": { prompt: "must be rejected", target: "system" },
    },
    policies: [{
      name: "block-curl-prod",
      tools: ["bash"],
      paths: ["command"],
      pattern: "curl .*prod\\\\.example\\\\.com",
      action: "block",
      reason: "Prod curl is forbidden.",
    }],
  }),
);
fs.writeFileSync(
  path.join(project, ".pi", "harness.json"),
  JSON.stringify({
    skillPrompts: {
      review: { prompt: "inner guidance", target: "system" },
    },
    policies: [{
      name: "ui-fixed-width",
      tools: ["edit", "write"],
      require: { path: "path", pattern: "\\\\.(tsx|css)$" },
      paths: ["content", "newText", "edits.newText"],
      patterns: ["width:\\\\s*\\\\d{3,}px"],
      action: "block",
      reason: "Use design tokens and min(100%, var(--token)).",
    }],
  }),
);
await new Promise((r) => setTimeout(r, 20));
{
  const expanded = '<skill name="review" location="/tmp/review/SKILL.md">\\nReferences are relative to /tmp/review.\\n\\nReview body\\n</skill>\\n\\ncheck this';
  const first = await callBefore(expanded, "base system", baseCtx, true);
  const second = await callBefore(expanded, first.event.systemPrompt, baseCtx, true);
  const raw = await callBefore("/skill:review check this", "raw system", baseCtx, true);
  const fake = await callBefore("<skill name=\\\"review\\\">arbitrary</skill>", "fake system", baseCtx, true);
  const userExpanded = '<skill name="usernote" location="/tmp/usernote/SKILL.md">\\nReferences are relative to /tmp/usernote.\\n\\nBody\\n</skill>';
  const user = await callBefore(userExpanded, "user system", baseCtx, true);
  const userHandler = (hooks.before_agent_start ?? []).slice(-1)[0];
  const sharedTurnCtx = { ...baseCtx };
  const userEvent = () => ({
    type: "before_agent_start",
    prompt: userExpanded,
    images: undefined,
    systemPrompt: "user system",
    systemPromptOptions: {},
  });
  const firstUser = await userHandler(userEvent(), sharedTurnCtx);
  const duplicateUser = await userHandler(userEvent(), sharedTurnCtx);
  const nextTurnUser = await userHandler(userEvent(), { ...baseCtx });
  const systemEvent = entries.find((e) => e.data?.kind === "skill-prompt" && e.data?.prompt === "inner guidance");
  const renderer = entryRenderers["harness-event"];
  const theme = {
    fg: (_color, text) => text,
    bg: (_color, text) => text,
    bold: (text) => text,
  };
  const rendered = renderer?.(systemEvent, { expanded: true }, theme)?.render(200).join("\\n") ?? "";
  const longPrompt = "Live guidance requires one active poller and records every accepted event without truncating the expanded prompt.";
  const longEvent = {
    customType: "harness-event",
    data: {
      kind: "skill-prompt",
      skill: "impeccable",
      target: "system",
      prompt: longPrompt,
      source: "project.local",
      file: path.join(project, ".pi", "harness.local.json"),
    },
  };
  const collapsedRows = renderer?.(longEvent, { expanded: false }, theme)?.render(50) ?? [];
  const expandedRows = renderer?.(longEvent, { expanded: true }, theme)?.render(50) ?? [];
  record("skill-prompts", {
    projectWins: first.event.systemPrompt === "base system\\n\\ninner guidance",
    idempotent: second.event.systemPrompt === first.event.systemPrompt,
    rawIgnored: raw.event.systemPrompt === "raw system" && raw.results.length === 0,
    malformedIgnored: fake.results.length === 0,
    userMessage: user.results.length === 1 && user.results[0].message?.content === "user guidance" && user.results[0].message?.display === false && user.results[0].message?.details?.target === "user",
    userDedupedInTurn: firstUser?.message?.content === "user guidance" && duplicateUser === undefined,
    userReinjectedNextTurn: nextTurnUser?.message?.content === "user guidance",
    systemEventIsVisible: systemEvent?.customType === "harness-event",
    systemEventUsesPrompt: systemEvent?.data?.kind === "skill-prompt" && systemEvent?.data?.prompt === "inner guidance",
    systemEventIdentifiesSource: systemEvent?.data?.source === "project" && systemEvent?.data?.file === path.join(project, ".pi", "harness.json"),
    systemEventRenderUsesPrompt: rendered.includes("[harness] skill prompt · inner guidance") && rendered.includes("source=project"),
    expandHintUsesKeybinding: collapsedRows.some((row) => row.toLowerCase().includes("ctrl+o to expand")), 
    expandedPromptIsComplete: longPrompt.split(" ").every((word) => expandedRows.join("\\n").includes(word)),
  });
}

// ── S8: /harness command reports surface, headless-safe ───────────
{
  let notified = "";
  const messages = [];
  const cmdCtx = { ...baseCtx, ui: { notify: (msg) => (notified = msg) } };
  pi.sendUserMessage = (content, options) => messages.push({ content, options });
  await commands.harness.handler("", cmdCtx);
  await commands.harness.handler("Block edits that add hard-coded colors", cmdCtx);
  await commands.harness.handler("--global Block edits globally", cmdCtx);
  await commands.harness.handler("--shared Block edits in repo", cmdCtx);
  record("command-surface", {
    listsPolicies: notified.includes("ui-fixed-width") && notified.includes("block-curl-prod"),
    showsPaths: notified.includes("harness.json") && notified.includes(".local"),
    invalidSkillReported: notified.includes("bad--skill") && notified.includes("violates the Pi skill-name rules"),
    defaultTargetsProjectLocal: messages.length >= 1 && messages[0].options?.deliverAs === "followUp" &&
      messages[0].content.includes("Block edits that add hard-coded colors") &&
      messages[0].content.includes(path.join(project, ".pi", "harness.local.json")) &&
      !messages[0].content.includes(path.join(agentDir, "harness.local.json")),
    globalFlagTargetsUserLocal: messages.length >= 2 && messages[1].options?.deliverAs === "followUp" &&
      messages[1].content.includes("Block edits globally") &&
      messages[1].content.includes(path.join(agentDir, "harness.local.json")),
    sharedFlagTargetsProject: messages.length >= 3 && messages[2].options?.deliverAs === "followUp" &&
      messages[2].content.includes("Block edits in repo") &&
      messages[2].content.includes(path.join(project, ".pi", "harness.json")),
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


def test_s3_confirm_action_headless_interactive_and_bounded() -> None:
    s = ALL["confirm-action"]
    assert s["headlessBlocked"] and s["dialogBounded"]
    assert s["allowedOnce"] and s["deniedBlocked"] and s["timeoutFailsClosed"]
    assert s["singleEventForAllowed"]
    assert s["entryRecorded"] and s["entryRenderUsesReason"]


def test_s4_observe_action_records_without_blocking() -> None:
    s = ALL["observe-action"]
    assert s["proceeded"] and s["recorded"]


def test_s5_standard_agent_dir_user_layer_disable_and_extend() -> None:
    s = ALL["user-layer"]
    assert s["standardDirHonored"] and s["disabledBuiltInGone"] and s["userRuleFires"]


def test_s6_cache_invalidates_on_later_user_edit() -> None:
    s = ALL["cache-invalidation"]
    assert s["freshRuleSeen"] and s["oldRuleRetired"]


def test_s7_skill_prompts_are_layered_and_idempotent() -> None:
    s = ALL["skill-prompts"]
    assert s["projectWins"] and s["idempotent"]
    assert s["rawIgnored"] and s["malformedIgnored"] and s["userMessage"]
    assert s["userDedupedInTurn"] and s["userReinjectedNextTurn"]
    assert s["systemEventIsVisible"] and s["systemEventUsesPrompt"]
    assert s["systemEventIdentifiesSource"] and s["systemEventRenderUsesPrompt"]
    assert s["expandHintUsesKeybinding"] and s["expandedPromptIsComplete"]


def test_s8_command_reports_surface_and_routes_prompt() -> None:
    s = ALL["command-surface"]
    assert s["listsPolicies"] and s["showsPaths"] and s["invalidSkillReported"]
    assert s["defaultTargetsProjectLocal"]
    assert s["globalFlagTargetsUserLocal"]
    assert s["sharedFlagTargetsProject"]

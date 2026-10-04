/**
 * Dashboard geometry and interaction.
 *
 * These are the assertions a real terminal would force anyway: a panel that
 * overruns its width, wraps a double-width objective into garbage, or emits a
 * half-written ANSI sequence is broken in exactly the same way whether it was
 * drawn by a TTY or by a test. Widths below cover the range the extension claims
 * to support, including the narrow ones where ANSI-aware truncation is the only
 * thing standing between a goal and a mangled screen.
 */

import assert from "node:assert/strict";
import { matchesKey, visibleWidth } from "@earendil-works/pi-tui";
import { clearDashboard, refreshDashboard, createDashboardOverlay, renderDashboard } from "../src/dashboard.ts";
import type { GoalRecord } from "../src/record.ts";
import type { PiThemeStyle } from "@fradser/pi-kit";

const results: string[] = [];
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await body();
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

/** A theme that emits real ANSI, so truncation is tested against colour. */
const style: PiThemeStyle = {
  accent: (text) => `[36m${text}[39m`,
  muted: (text) => `[90m${text}[39m`,
  dim: (text) => `[2m${text}[22m`,
  border: (text) => `[90m${text}[39m`,
  success: (text) => `[32m${text}[39m`,
  error: (text) => `[31m${text}[39m`,
  fg: (_color, text) => text,
};

function goalWith(extra: Partial<GoalRecord> = {}): GoalRecord {
  return {
    id: "goal_abc123",
    objective: "Add CSV export to the reports page.",
    status: "active",
    autoContinue: true,
    usage: { tokensUsed: 12_345, activeSeconds: 3_725 },
    sisyphus: false,
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
    revision: 3,
    ...extra,
  };
}

const WIDTHS = [20, 40, 60, 80, 120, 240];

/**
 * A raw key press.
 *
 * `matchesKey(data, key)` takes the terminal's byte sequence, not the key name:
 * `Key.escape` is the string "escape", and comparing it to itself is false.
 * Driving the overlay therefore means sending what a terminal would send.
 */
function press(key: string): string {
  const raw: Record<string, string> = {
    escape: "\u001b",
    up: "\u001b[A",
    down: "\u001b[B",
    pageUp: "\u001b[5~",
    pageDown: "\u001b[6~",
    home: "\u001b[H",
    end: "\u001b[F",
  };
  const sequence = raw[key];
  assert.ok(sequence, `no raw sequence known for ${key}`);
  assert.ok(matchesKey(sequence, key as never), `pi-tui does not recognise ${key} as ${JSON.stringify(sequence)}`);
  return sequence;
}

/** `renderPiPanel` frames the body between a title row and a closing border, so
 * the footer is the second-to-last line rather than the last. */
function footerLine(lines: string[]): string {
  return lines[lines.length - 2] ?? "";
}

await scenario("every panel line fits the width it was given", () => {
  const goal = goalWith({
    objective: "Add CSV export to the reports page, with documentation and tests, and make it respect the active filter set without loading every row into memory at once.",
    verificationContract: "The download contains only rows matching the active filters, verified by a test that selects two of fifty rows.",
  });
  for (const width of WIDTHS) {
    const frame = renderDashboard({ width, rows: 40, scroll: 0, style, goal });
    assert.ok(frame.lines.length > 0, `no lines at width ${width}`);
    for (const [index, line] of frame.lines.entries()) {
      assert.ok(
        visibleWidth(line) <= width,
        `line ${index} is ${visibleWidth(line)} wide, over ${width}: ${JSON.stringify(line)}`,
      );
    }
  }
});

await scenario("a double-width objective wraps instead of overrunning", () => {
  const goal = goalWith({ objective: "实现报表页的CSV导出功能并确保只导出当前筛选条件下的行且有对应的测试覆盖".repeat(2) });
  for (const width of [20, 40, 60]) {
    const frame = renderDashboard({ width, rows: 40, scroll: 0, style, goal });
    for (const line of frame.lines) {
      assert.ok(visibleWidth(line) <= width, `overran at ${width}: ${visibleWidth(line)}`);
    }
  }
});

await scenario("truncation never leaves a half-written ANSI sequence", () => {
  const goal = goalWith({ objective: "x".repeat(400) });
  const frame = renderDashboard({ width: 40, rows: 40, scroll: 0, style, goal });
  const esc = String.fromCharCode(27);
  for (const line of frame.lines) {
    const opens = (line.match(new RegExp(`${esc}\\[`, "g")) ?? []).length;
    const closes = (line.match(new RegExp(`${esc}\\[\\d+m`, "g")) ?? []).length;
    assert.equal(opens, closes, `unbalanced colour codes in ${JSON.stringify(line)}`);
  }
});

await scenario("the panel owns its own input and closes on Escape", () => {
  let closed = 0;
  const overlay = createDashboardOverlay({
    goal: goalWith(),
    style,
    width: 80,
    rows: 24,
    onClose: () => { closed += 1; },
  });
  overlay.handleInput(press("escape"));
  assert.equal(closed, 1, "Escape closes the panel");
});

await scenario("the panel follows a terminal resize instead of keeping stale geometry", () => {
  const goal = goalWith({ objective: "y".repeat(300) });
  const overlay = createDashboardOverlay({ goal, style, width: 80, rows: 24, onClose: () => {} });
  for (const width of [120, 40, 200, 30]) {
    for (const line of overlay.render(width)) {
      assert.ok(visibleWidth(line) <= width, `after resize to ${width}: ${visibleWidth(line)}`);
    }
  }
});

await scenario("elapsed time is the progress the surface reports", async () => {
  // A goal is not partway through a list, so there is no fraction to show. Time
  // is the one figure that is both honest and useful.
  const cases: [number, string][] = [[0, "0m"], [45, "0m"], [59, "0m"], [60, "1m"], [3_725, "62m"], [5_400, "90m"]];
  for (const [seconds, expected] of cases) {
    const frame = renderDashboard({ width: 80, rows: 24, scroll: 0, style, goal: goalWith({ usage: { tokensUsed: 999_999, activeSeconds: seconds } }) });
    const body = frame.lines.join("\n");
    assert.match(body, new RegExp(expected.replace(":", "\\:")), `${seconds}s should read as ${expected}`);
  }
  // A large token count must not reach the surface: it is not progress.
  const frame = renderDashboard({ width: 80, rows: 24, scroll: 0, style, goal: goalWith({ usage: { tokensUsed: 12_345_678, activeSeconds: 120 } }) });
  assert.ok(!frame.lines.join("\n").includes("12345678"), "token spend is not shown as progress");
});

await scenario("the shared passive widget mounts below the editor and starts at zero minutes", () => {
  let placement: string | undefined;
  let lines: string[] = [];
  const theme = { fg: (_: string, text: string) => text, bg: (_: string, text: string) => text, bold: (text: string) => text };
  const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined, options?: { placement?: string }) => {
    if (!factory) return;
    placement = options?.placement;
    const component = factory({ requestRender() {} }, theme);
    lines = component.render(120);
  } } };
  const core = { goal: goalWith({ usage: { tokensUsed: 0, activeSeconds: 45 } }) };
  try {
    refreshDashboard(core as never, ctx as never);
    assert.equal(placement, "belowEditor");
    assert.ok(lines.every(line => !/^\s/.test(line)), "status rows align with the native footer without indentation");
    assert.match(lines.join("\n"), /0m/);
    assert.ok(!lines.join("\n").includes("45s"));
  } finally { clearDashboard(ctx as never); }
});

process.stdout.write(`${JSON.stringify(results)}\n`);

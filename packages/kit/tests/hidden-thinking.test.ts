import { describe, expect, test } from "bun:test";
import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  HIDDEN_THINKING_LABEL,
  hiddenThinkingEnabled,
  resolveLiveActivity,
  resolvePiCli,
  runPiWorker,
  visibleWorkerActivity,
  type PiWorkerProgressUpdate,
} from "../src/index.ts";

describe("shared hidden-thinking contract", () => {
  test("reads Pi's setting per refresh and tolerates a host without it", () => {
    expect(HIDDEN_THINKING_LABEL).toBe("Thinking...");
    expect(hiddenThinkingEnabled({ getSettings: () => ({ hideThinkingBlock: true }) })).toBe(true);
    expect(hiddenThinkingEnabled({ getSettings: () => ({ hideThinkingBlock: false }) })).toBe(false);
    expect(hiddenThinkingEnabled({ getSettings: () => ({}) })).toBe(false);
    expect(hiddenThinkingEnabled({})).toBe(false);
    expect(hiddenThinkingEnabled(undefined)).toBe(false);
    // Pi refuses getSettings() during extension loading; that must fail open.
    expect(hiddenThinkingEnabled({ getSettings: () => { throw new Error("Extension runtime not initialized"); } })).toBe(false);
    const settings = { hideThinkingBlock: false };
    const host = { getSettings: () => settings };
    expect(hiddenThinkingEnabled(host)).toBe(false);
    settings.hideThinkingBlock = true;
    expect(hiddenThinkingEnabled(host)).toBe(true);
  });

  test("one activity policy is shared by every above-editor row", () => {
    const lines = { tool: "read: notes.md", thinking: "private reasoning", text: "the answer" };
    expect(resolveLiveActivity(lines, false)).toBe("read: notes.md");
    expect(resolveLiveActivity(lines, true)).toBe("read: notes.md");
    expect(resolveLiveActivity({ thinking: "private reasoning", text: "the answer" }, false)).toBe("private reasoning");
    expect(resolveLiveActivity({ thinking: "private reasoning", text: "the answer" }, true)).toBe("the answer");
    expect(resolveLiveActivity({ thinking: "private reasoning" }, true)).toBe(HIDDEN_THINKING_LABEL);
    expect(resolveLiveActivity({ thinking: "private reasoning" }, false)).toBe("private reasoning");
    expect(resolveLiveActivity({ text: "the answer" }, true)).toBe("the answer");
    expect(resolveLiveActivity({}, true, "Working...")).toBe("Working...");
    expect(resolveLiveActivity({}, true)).toBeUndefined();
  });

  test("worker progress masks only thinking-derived activity", () => {
    const thinking = { activity: "private reasoning", activitySource: "thinking" } as PiWorkerProgressUpdate;
    const text = { activity: "the answer", activitySource: "text" } as PiWorkerProgressUpdate;
    const tool = { activity: "read: notes.md", activitySource: "tool" } as PiWorkerProgressUpdate;
    expect(visibleWorkerActivity(thinking, true)).toBe(HIDDEN_THINKING_LABEL);
    expect(visibleWorkerActivity(thinking, false)).toBe("private reasoning");
    expect(visibleWorkerActivity(text, true)).toBe("the answer");
    expect(visibleWorkerActivity(tool, true)).toBe("read: notes.md");
    expect(visibleWorkerActivity({ activity: undefined } as PiWorkerProgressUpdate, true)).toBeUndefined();
  });
});

/** A fake `pi --print --mode json` child. Writing the whole turn in one chunk
 *  keeps the progress source assertions independent of stream timing. */
async function lastProgress(events: readonly unknown[]): Promise<PiWorkerProgressUpdate> {
  const root = mkdtempSync(join(tmpdir(), "kit-hidden-thinking-"));
  const originalArgv = process.argv[1];
  try {
    writeFileSync(join(root, "package.json"), JSON.stringify({ name: "@earendil-works/pi-coding-agent" }));
    const cli = join(root, "cli.cjs");
    writeFileSync(cli, `process.stdout.write(${JSON.stringify(
      events.map((event) => JSON.stringify(event)).join("\n") + "\n",
    )});\n`);
    process.argv[1] = cli;
    const updates: PiWorkerProgressUpdate[] = [];
    const result = await runPiWorker({
      prompt: "think",
      cwd: root,
      minimal: true,
      onUpdate: (update) => { updates.push(update); },
    });
    // A silent worker means the fake CLI never ran, so name the resolved launch
    // and the worker's own verdict instead of reporting an empty list.
    if (updates.length === 0) {
      throw new Error(`fake CLI produced no progress: ${JSON.stringify({
        cli,
        argv1: process.argv[1],
        resolved: resolvePiCli(),
        execPath: process.execPath,
        platform: process.platform,
        tmpdir: realpathSync(tmpdir()),
        exitCode: result.exitCode,
        terminal: result.terminal,
        stderr: result.stderr.slice(0, 300),
      })}`);
    }
    expect(updates.length).toBeGreaterThan(0);
    return updates.at(-1) as PiWorkerProgressUpdate;
  } finally {
    process.argv[1] = originalArgv;
    rmSync(root, { recursive: true, force: true });
  }
}

test("runPiWorker names the stream that produced each activity line", async () => {
  // A settled turn with no answer text must not reclassify reasoning as text.
  const thinking = await lastProgress([
    { type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: "private reasoning" } },
    { type: "message_end", message: { role: "assistant", content: [{ type: "thinking", thinking: "private reasoning" }] } },
  ]);
  expect(thinking.activity).toBe("private reasoning");
  expect(thinking.turns).toBe(1);
  expect(thinking.activitySource).toBe("thinking");
  expect(visibleWorkerActivity(thinking, true)).toBe(HIDDEN_THINKING_LABEL);
  expect(visibleWorkerActivity(thinking, false)).toBe("private reasoning");

  const answer = await lastProgress([
    { type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "the answer" } },
    { type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "the answer" }] } },
  ]);
  expect(answer.activitySource).toBe("text");
  expect(visibleWorkerActivity(answer, true)).toBe("the answer");

  const tool = await lastProgress([
    { type: "tool_execution_start", toolName: "read", args: { path: "notes.md" } },
    { type: "tool_execution_end" },
  ]);
  expect(tool.activitySource).toBe("tool");
  expect(visibleWorkerActivity(tool, true)).toBe(tool.activity);
});

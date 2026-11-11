import { expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { stripVTControlCharacters } from "node:util";
import { initTheme } from "@earendil-works/pi-coding-agent";
import { registerContextTools } from "../extensions/context-tools.ts";

initTheme("dark", false);

const theme = {
  fg: (_color: string, text: string) => text,
  bold: (text: string) => text,
};

/** A child that only reasons: one stdout chunk keeps the test independent of
 *  stream timing, and the tool's documented no-answer retry is expected. */
const thinkingOnlyEvents = [
  { type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: "private reasoning" } },
  { type: "message_end", message: { role: "assistant", content: [{ type: "thinking", thinking: "private reasoning" }] } },
];

function fakeCli(root: string): string {
  const cli = join(root, "cli.cjs");
  writeFileSync(join(root, "package.json"), JSON.stringify({ name: "@earendil-works/pi-coding-agent" }));
  writeFileSync(cli, `process.stdout.write(${JSON.stringify(
    thinkingOnlyEvents.map((event) => JSON.stringify(event)).join("\n") + "\n",
  )});\n`);
  return cli;
}

async function researchRows(hideThinkingBlock: boolean): Promise<{ rows: string[]; partials: string[] }> {
  const root = mkdtempSync(join(tmpdir(), "context-hidden-thinking-"));
  const originalArgv = process.argv[1];
  try {
    process.argv[1] = fakeCli(root);
    type WidgetFactory = (tui: unknown, theme: unknown) => { render(width: number): string[]; invalidate(): void };
    const factories = new Map<string, WidgetFactory>();
    const ui = {
      setWidget: (key: string, factory: WidgetFactory | undefined) => {
        if (factory) factories.set(key, factory);
      },
    };
    const partials: string[] = [];
    const rows: string[] = [];
    let component: ReturnType<WidgetFactory> | undefined;
    let tool: {
      execute: (
        id: string,
        params: { query: string },
        signal: AbortSignal | undefined,
        onUpdate: (result: { content: Array<{ type: string; text?: string }> }) => void,
        ctx: unknown,
      ) => Promise<unknown>;
    } | undefined;
    registerContextTools({
      registerTool: (registered: typeof tool) => { tool = registered; },
      getSettings: () => ({ hideThinkingBlock }),
    } as never);
    expect(tool).toBeDefined();
    let failure: unknown;
    try {
      await (tool as NonNullable<typeof tool>).execute(
        "call-1",
        { query: "research this" },
        undefined,
        (result) => {
          partials.push(result.content[0]?.text ?? "");
          const factory = factories.get("context-research");
          if (!factory) return;
          component ??= factory({ requestRender: () => {} }, theme);
          rows.push(...component.render(80).map(stripVTControlCharacters));
        },
        { mode: "tui", cwd: root, ui },
      );
    } catch (error) {
      failure = error;
    }
    expect(failure).toBeInstanceOf(Error);
    expect(String(failure)).toContain("returned no answer after retry");
    return { rows, partials };
  } finally {
    process.argv[1] = originalArgv;
    rmSync(root, { recursive: true, force: true });
  }
}

test("hidden thinking replaces the researcher row's reasoning with Pi's label", async () => {
  const hidden = await researchRows(true);
  expect(hidden.rows.some((row) => row.includes("Thinking..."))).toBe(true);
  expect(hidden.rows.some((row) => row.includes("private reasoning"))).toBe(false);
  expect(hidden.partials).toContain("Thinking...");
  expect(hidden.partials.some((text) => text.includes("private reasoning"))).toBe(false);
});

test("visible thinking keeps streaming the researcher row's reasoning", async () => {
  const shown = await researchRows(false);
  expect(shown.rows.some((row) => row.includes("private reasoning"))).toBe(true);
  expect(shown.rows.some((row) => row.includes("Thinking..."))).toBe(false);
  expect(shown.partials).toContain("private reasoning");
});

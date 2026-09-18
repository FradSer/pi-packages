// Offline model transport; executes the real Pi tool, host row and shared renderers.
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import { initTheme, keyHint, ToolExecutionComponent, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { KeybindingsManager, ProcessTerminal, TuiMainScreen, setKeybindings, truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import { bindLifecycleRenderers, createToolLifecycleResultRenderer, eventToolLifecycle } from "../src/index.ts";

const longTitle = "Full lifecycle title " + Array.from({ length: 14 }, (_, i) => `evidence-${i}`).join(" ");
const longSummary = "Answer: " + Array.from({ length: 16 }, (_, i) => `answer-${i}`).join(" ");
const kinds = ["short", "empty", "title", "summary", "details"] as const;
const geometry = {
  fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi,
  expandHint: () => keyHint("app.tools.expand", "to expand"),
};
const rows = bindLifecycleRenderers(geometry);

export default function (pi: ExtensionAPI): void {
  const snapshots = process.env.PI_EXPANSION_SNAPSHOTS;
  assert.ok(snapshots, "An isolated snapshot path is required");
  const specFor = (kind: string) => eventToolLifecycle("probe", kind === "title" ? longTitle : kind, {
    summary: kind === "summary" ? [longSummary] : undefined,
    details: kind === "details" ? ["additional evidence"] : kind === "empty" ? [" ", "\n"] : [],
  });
  const parameters = Type.Object({ kind: Type.String() });
  const tool: ToolDefinition<typeof parameters> = {
    name: "expansion_probe", label: "Expansion probe", description: "Offline rendering verification only",
    parameters, renderShell: "self", renderCall: rows.emptyCall,
    async execute(_id, args) {
      return { content: [{ type: "text", text: "MODEL_ONLY_CONTENT" }], details: { kind: args.kind, internal: true } };
    },
    renderResult(result, options, theme, context) {
      const { kind } = context.args as { kind: string };
      const render = kind === "empty"
        ? createToolLifecycleResultRenderer({ ...geometry, expandHint: geometry.expandHint(), createSpec: () => specFor(kind) })
        : rows.result(() => specFor(kind));
      const component = render(result, options, theme, context);
      return {
        invalidate: () => component.invalidate(),
        render(width) {
          const lines = component.render(width);
          appendFileSync(snapshots, JSON.stringify({ kind, width, expanded: options.expanded,
            bounded: lines.every(line => !line.includes("\n") && visibleWidth(line) <= width),
            lines: lines.map(stripVTControlCharacters),
          }) + "\n");
          return lines;
        },
      };
    },
  };
  pi.registerTool(tool);
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode === "tui") return;
    initTheme("dark", false);
    setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
    // Never start this native host: only its row's render/mouse methods run.
    const ui = new TuiMainScreen(new ProcessTerminal());
    let mouseSupported = false;
    for (const kind of kinds) {
      const host = new ToolExecutionComponent("expansion_probe", `mouse-${kind}`, { kind }, {}, tool, ui, ctx.cwd);
      host.updateResult({ content: [{ type: "text", text: "MODEL_ONLY_CONTENT" }], details: { internal: true }, isError: false });
      const content = (width: number) => host.render(width).map(stripVTControlCharacters).map(line => line.trim()).filter(Boolean);
      for (const width of [48, 90, 240]) {
        host.setExpanded(false);
        const collapsed = content(width);
        const hasExtra = kind === "details" || ((kind === "title" || kind === "summary") && width < 240);
        assert.equal(collapsed.join("\n").includes("ctrl+o to expand"), hasExtra);
        if ("handleMouse" in host && typeof host.handleMouse === "function") {
          mouseSupported = true;
          assert.equal(host.handleMouse({ type: "click", button: "left", x: 5, y: 2, width, height: 10 })?.handled, true);
        } else {
          // Older Pi hosts still support keyboard expansion; do not claim a mouse check.
          host.setExpanded(true);
        }
        const expanded = content(width);
        const expected = [
          ...wrapTextWithAnsi(`[probe] ${kind === "title" ? longTitle : kind}`, width - 2),
          ...(kind === "summary" ? wrapTextWithAnsi(longSummary, width - 2) : []),
          ...(kind === "details" ? ["additional evidence"] : []),
        ].map(line => line.trim()).filter(Boolean);
        assert.deepEqual(expanded, expected);
        assert.ok(!expanded.join("\n").includes("MODEL_ONLY_CONTENT"));
      }
    }
    console.log("KIT_NATIVE_EXPANSION_OK");
    console.log(mouseSupported ? "KIT_NATIVE_MOUSE_OK" : "KIT_NATIVE_MOUSE_UNAVAILABLE");
  });
  let index = 0;
  pi.registerProvider("kit-expansion-fixture", {
    api: "kit-expansion-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_EXPANSION_AUTH,
    models: [{ id: "deterministic", name: "Kit expansion fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const kind = kinds[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: kind ? [{ type: "toolCall", id: `probe-${index}`, name: "expansion_probe", arguments: { kind } }]
          : [{ type: "text", text: "KIT_EXPANSION_READY" }],
        stopReason: kind ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: kind ? "toolUse" : "stop", message });
      stream.end();
      return stream;
    },
  });
}

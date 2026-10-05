import { appendFileSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createPiThemeStyle } from "@fradser/pi-kit";
import { createBtwOverlay } from "../src/overlay";

export default function (pi: ExtensionAPI) {
  pi.on("session_start", () => {
    const record = process.env.BTW_TUI_RECORD;
    if (record) appendFileSync(record, `${JSON.stringify({ type: "ready" })}\n`);
  });
  pi.registerCommand("btw-tui-test", {
    description: "Test the btw overlay without a model request.",
    async handler(_args, ctx) {
      const record = process.env.BTW_TUI_RECORD;
      if (!record || ctx.mode !== "tui") throw new Error("The TUI test requires a record path and TUI mode.");
      const log = (event: unknown) => appendFileSync(record, `${JSON.stringify(event)}\n`);
      await ctx.ui.custom<void>((tui, theme, _keys, done) => {
        const overlay = createBtwOverlay(tui, createPiThemeStyle(theme), {
          question: "initial",
          onCancel: () => done(),
          onAsk: async (question, history, signal) => {
            log({ type: "ask", question, history });
            if (question === "cancel") {
              return new Promise((resolve) => signal.addEventListener("abort", () => {
                log({ type: "abort" });
                resolve({ text: "late cancelled answer", timedOut: false, exitCode: 1, stderr: "", cancelled: true });
              }, { once: true }));
            }
            return {
              text: question === "long" ? Array.from({ length: 60 }, (_, i) => `line-${i}`).join("\n\n") : `answer-${question}`,
              timedOut: false,
              exitCode: 0,
              stderr: "",
            };
          },
        });
        const render = overlay.render.bind(overlay);
        overlay.render = (width) => {
          const lines = render(width);
          log({ type: "render", width, rows: tui.terminal.rows, lines });
          return lines;
        };
        return overlay;
      }, {
        overlay: true,
        overlayOptions: { anchor: "bottom-center", width: "100%", maxHeight: "80%", margin: { bottom: 0 } },
      });
      log({ type: "closed", branch: ctx.sessionManager.getBranch() });
    },
  });
}

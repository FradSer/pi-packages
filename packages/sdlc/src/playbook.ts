import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldLine } from "@fradser/pi-kit";
import { Type } from "typebox";

const engine = fileURLToPath(new URL("../scripts/sdlc.py", import.meta.url));
const rows = bindLifecycleRenderers({
  fit: truncateToWidth, visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

/** Commands share the same packaged engine as Codex; adapters run without a shell. */
export function registerPlaybook(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "sdlc", label: "SDLC",
    description: "Run the SDLC stage engine: init, status, handoff, advance, rewind, archive, check, eval, review, deploy or metric. Approvals come from a managed verifier; this tool cannot approve its own work. Read references/playbook.md and commands.md first. Deploy and paid evaluations require the user's authorization.",
    parameters: Type.Object({
      action: Type.String({ description: "Engine action" }),
      args: Type.Optional(Type.String({ description: "JSON object with action arguments" })),
    }),
    async execute(_id, params, signal, _update, ctx) {
      const result = await pi.exec("python3", [engine, params.action, "--cwd", ctx.cwd, "--args", params.args ?? "{}"], { cwd: ctx.cwd, signal, timeout: 900_000 });
      return {
        content: [{ type: "text", text: result.stdout || result.stderr || "SDLC engine returned no evidence." }],
        details: { action: params.action, passed: result.code === 0, exit: result.code },
        isError: result.code !== 0,
      };
    },
    renderShell: "self",
    renderCall: () => rows.emptyCall(),
    renderResult: rows.result<{ content: unknown; details?: { action: string; passed: boolean; exit: number } }>((result) =>
      eventToolLifecycle("sdlc", result.details?.action ?? "operation", {
        label: result.details?.passed ? "passed" : "needs review",
        details: [fieldLine("exit", result.details?.exit ?? "unknown")], detailLimit: 1,
      })),
  });
  pi.on("tool_call", async (event, ctx) => {
    if (!fs.existsSync(path.join(ctx.cwd, ".sdlc/state.json")) || event.toolName === "sdlc") return;
    if (!["edit", "write", "apply_patch"].includes(event.toolName) && !/(?:^|__)release$/.test(event.toolName)) return;
    try {
      const result = await pi.exec("python3", [engine, "guard", "--cwd", ctx.cwd, "--args", JSON.stringify({ tool: event.toolName, input: event.input })], { cwd: ctx.cwd, timeout: 10_000 });
      if (result.code !== 0) return { block: true, reason: result.stderr || "SDLC stage check failed" };
    } catch (error) {
      return { block: true, reason: `SDLC guard could not run: ${error instanceof Error ? error.message : String(error)}` };
    }
  });
  pi.on("agent_before_settle", async (_event, ctx) => {
    if (!fs.existsSync(path.join(ctx.cwd, ".sdlc/state.json"))) return;
    const result = await pi.exec("python3", [engine, "handoff", "--cwd", ctx.cwd], { cwd: ctx.cwd, timeout: 10_000 });
    if (result.code !== 0) {
      if (ctx.hasUI) ctx.ui.notify("SDLC handoff is incomplete: " + result.stderr, "warning");
      else console.error("SDLC handoff is incomplete: " + result.stderr);
    }
  });
}

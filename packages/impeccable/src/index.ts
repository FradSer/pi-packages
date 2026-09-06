import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { Container, type Component, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleResultRenderer, eventToolLifecycle, safeDisplayText } from "@fradser/pi-kit";
import { Type } from "typebox";
import { resolver, type Bundle, type Resolver } from "./resolver.ts";

function feedback(pi: ExtensionAPI, ctx: ExtensionCommandContext, text: string): void {
  const content = safeDisplayText(text);
  if (ctx.hasUI) ctx.ui.notify(content, "warning");
  else pi.sendMessage({ customType: "impeccable-usage", content, display: true }, { triggerTurn: false });
}

async function command(pi: ExtensionAPI, loader: Resolver, args: string, ctx: ExtensionCommandContext): Promise<void> {
  const usage = `Usage: /impeccable <${loader.capabilities.map(entry => entry.id).join("|")}> <target/request>, or any freeform request`;
  const match = args.match(/^\s*(\S+)(?:\s([\s\S]*))?$/);
  const capability = match?.[1];
  const request = match?.[2] ?? "";
  const implemented = capability !== undefined && loader.capabilities.some(entry => entry.id === capability);
  if (match && !implemented) {
    const guidance = [
      "Design request without a chosen capability. Pick and load the matching guidance first with impeccable_load, then perform the work within the user's request.",
      `Capabilities: ${loader.capabilities.map(entry => entry.id).join(" ")}. Start from polish for general refinement, clarify for product copy questions, live for browser variant iteration.`,
      `User target/request:\n${args.trim()}`,
    ].join("\n\n");
    pi.sendUserMessage(guidance, { deliverAs: "followUp" });
    return;
  }
  if (!capability) {
    if (!ctx.hasUI) return feedback(pi, ctx, usage);
    const selected = await ctx.ui.select("Impeccable capability", loader.capabilities.map(entry => entry.id));
    if (!selected) return;
    try {
      const bundle = loader.load(selected, "user");
      pi.sendUserMessage(`${bundle.content}\n\nUser target/request:\n`, { deliverAs: "followUp" });
    } catch (error) {
      feedback(pi, ctx, `${error instanceof Error ? error.message : String(error)}\n${usage}`);
    }
    return;
  }
  try {
    const bundle = loader.load(capability, "user");
    pi.sendUserMessage(`${bundle.content}\n\nUser target/request:\n${request}`, { deliverAs: "followUp" });
  } catch (error) {
    feedback(pi, ctx, `${error instanceof Error ? error.message : String(error)}\n${usage}`);
  }
}

export function registerImpeccable(pi: ExtensionAPI, loader: Resolver): void {
  pi.registerCommand("impeccable", {
    description: "Load a design procedure or choose an implemented capability",
    handler: (args, ctx) => command(pi, loader, args, ctx),
  });
  pi.registerTool({
    name: "impeccable_load",
    label: "Impeccable",
    description: `Load design guidance without executing scripts or triggering a turn. Capabilities: ${loader.capabilities.filter(entry => entry.invocation === "model").map(entry => entry.id).join(", ")}. References must be reachable from the capability graph. Rejects bundles above 64 KiB; never truncates rules.`,
    promptSnippet: "Load canonical interface-polish or animation guidance",
    promptGuidelines: ["Use impeccable_load for interface polish or animation requests; load disclosed references only when their conditions apply. Reference loading never authorizes edits, installs, variants, or promotion."],
    parameters: Type.Object({
      capability: Type.String({ description: "Model-reachable capability id" }),
      reference: Type.Optional(Type.String({ description: "Canonical reference id reachable from that capability" })),
    }),
    async execute(_id, params, signal) {
      const bundle = loader.load(params.capability, "model", params.reference, signal);
      return { content: [{ type: "text", text: bundle.content }], details: bundle };
    },
    renderShell: "self",
    renderCall: () => new Container(),
    renderResult: createStaticToolLifecycleResultRenderer<{ content: unknown; details?: Bundle }, Component>({
      createSpec: result => eventToolLifecycle("impeccable", result.details?.root ?? "loading", {
        label: "loaded",
        details: [
          `Loaded: ${result.details?.loaded.join(", ") ?? "none"}`,
          `References: ${result.details?.availableReferences.map(edge => `${edge.id}: ${edge.when}`).join("; ") || "none"}`,
          `Bytes: ${result.details?.byteLength ?? 0}; no scripts executed; pending: none`,
        ],
        detailLimit: 3,
      }),
      fit: truncateToWidth,
      visibleWidth,
      renderError: (line, theme) => ({
        render: width => [truncateToWidth(theme.fg("error", safeDisplayText(line)), width)],
        invalidate() {},
      }),
    }),
  });
}

export default function impeccable(pi: ExtensionAPI): void {
  registerImpeccable(pi, resolver);
}

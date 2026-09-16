import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldLine, safeDisplayText, startedToolLifecycle } from "@fradser/pi-kit";
import { Type } from "typebox";
import { resolver, type Bundle, type Resolver } from "./resolver.ts";
import { loadTriggers, routeFreeform, type TriggerEntry } from "./routing.ts";

const PROCEDURE_ENTRY = "impeccable-procedure";

/** Geometry bound once: every impeccable row shares hint and wrapping. */
const impeccableRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

function capabilityLabel(loader: Resolver, id: string): string {
  return loader.capabilities.find(entry => entry.id === id)?.label ?? id;
}

interface LoadedBundle {
  id: string;
  label: string;
  byteLength: number;
}

interface ProcedureDetails {
  request: string;
  loaded: LoadedBundle[];
  routing: string[];
}

function stripRepeatedHeader(content: string): string {
  const dropPrefixes = ["Capability: ", "State: stateless", "Loading does not authorize"];
  let dropped = 0;
  return content.split("\n").filter((line, index) => {
    if (index < 10 && dropped < dropPrefixes.length && dropPrefixes.some(prefix => line.startsWith(prefix))) {
      dropped += 1;
      return false;
    }
    return true;
  }).join("\n");
}

function dedupeSharedSources(contents: string[]): string[] {
  const seen = new Set<string>();
  return contents.map((content, index) => {
    const body = index === 0 ? content : stripRepeatedHeader(content);
    return body.replace(/<impeccable-source id="([^"]+)">[\s\S]*?<\/impeccable-source>/g, (block, id: string) => {
      if (seen.has(id)) return `<!-- shared source ${id} already loaded above -->`;
      seen.add(id);
      return block;
    });
  });
}

function planNotes(targets: string[], triggers: TriggerEntry[], request: string): string[] {
  const byId = new Map(triggers.map(entry => [entry.id, entry]));
  return [
    `Plan${request ? ` for "${request}"` : ""} (in order):`,
    ...targets.map((target, index) => `${index + 1}. /impeccable ${target} — ${byId.get(target)?.does ?? target}`),
  ];
}

function sendProcedure(pi: ExtensionAPI, loader: Resolver, bundles: Bundle[], notes: string[], request: string): void {
  const sections = dedupeSharedSources(bundles.map(bundle => bundle.content))
    .map((section, index) => index === 0 ? section : `--- Next capability: ${bundles[index].capability} ---\n\n${section}`)
    .join("\n\n");
  const content = `${notes.length ? `${notes.join("\n")}\n\n` : ""}${sections}\n\nUser target/request:\n${request}`;
  const details: ProcedureDetails = {
    request,
    loaded: bundles.map(bundle => ({ id: bundle.capability, label: capabilityLabel(loader, bundle.capability), byteLength: bundle.byteLength })),
    routing: notes,
  };
  pi.sendMessage({ customType: PROCEDURE_ENTRY, content, display: true, details }, { deliverAs: "followUp", triggerTurn: true });
}

function feedback(pi: ExtensionAPI, ctx: ExtensionCommandContext, text: string): void {
  const content = safeDisplayText(text);
  if (ctx.hasUI) ctx.ui.notify(content, "warning");
  else pi.sendMessage({ customType: "impeccable-usage", content, display: true }, { triggerTurn: false });
}

async function command(pi: ExtensionAPI, loader: Resolver, args: string, ctx: ExtensionCommandContext, triggers: TriggerEntry[]): Promise<void> {
  const usage = `Usage: /impeccable <${loader.capabilities.map(entry => entry.id).join("|")}> <target/request>, or any freeform request`;
  const match = args.match(/^\s*(\S+)(?:\s([\s\S]*))?$/);
  const capability = match?.[1];
  const request = match?.[2] ?? "";
  const implemented = capability !== undefined && loader.capabilities.some(entry => entry.id === capability);
  if (match && !implemented) {
    const isImplemented = (id: string): boolean => loader.capabilities.some(entry => entry.id === id);
    const routed = routeFreeform(args, triggers, isImplemented);
    if (routed && routed.target) {
      const targets = [routed.target, ...(routed.queued ? [routed.queued] : [])].slice(0, 2);
      const notes = planNotes(targets, triggers, args.trim());
      if (routed.aliasNote) notes.push(`${routed.aliasNote}.`);
      if (routed.unported) notes.push(`${routed.unported} is not yet ported; closest implemented capability loaded.`);
      if (routed.runnerUp) notes.push(`Runner-up alternative (not loaded): ${routed.runnerUp}.`);
      const bundles: Bundle[] = [];
      for (const target of targets) {
        try {
          bundles.push(loader.load(target, "user"));
        } catch (error) {
          notes.push(`Skipped ${target}: ${error instanceof Error ? error.message : String(error)}`);
        }
      }
      if (!bundles.length) {
        feedback(pi, ctx, `${notes.join(" ")}\n${usage}`);
        return;
      }
      sendProcedure(pi, loader, bundles, notes, args.trim());
      return;
    }
    const pack = [
      "No command trigger matched. Judge the request semantically (it may paraphrase; Chinese included) and load guidance with impeccable_load, then perform the work within the user's request.",
      "Routing rules: an explicit or clearly implied command loads it (max 2 capabilities per request; evaluate first, audit/critique before fix/polish). Two fit loads the top-ranked and names the runner-up. craft is a deprecated alias of shape. Otherwise do general design work on the incumbent implementation without inventing product truth. Loading never authorizes scripts, installs, or agents beyond this session's tools.",
      `Commands:\n${loader.capabilities.map(entry => {
        const trigger = triggers.find(candidate => candidate.id === entry.id);
        const signals = trigger ? [...trigger.en.slice(0, 4), ...trigger.zh.slice(0, 4)].join("/") : "";
        return `- /impeccable ${entry.id}${trigger?.hint ? ` ${trigger.hint}` : ""} — ${signals}`;
      }).join("\n")}`,
      ...(routed && routed.aliasNote ? [`${routed.aliasNote}.`] : []),
      ...(routed && routed.recognized ? [`Recognized intent: ${routed.recognized} (not yet ported and no close equivalent loaded).`] : []),
      `User target/request:\n${args.trim()}`,
    ].join("\n\n");
    pi.sendUserMessage(pack, { deliverAs: "followUp" });
    return;
  }
  if (!capability) {
    if (!ctx.hasUI) return feedback(pi, ctx, usage);
    const selected = await ctx.ui.select("Impeccable capability", loader.capabilities.map(entry => entry.id));
    if (!selected) return;
    try {
      sendProcedure(pi, loader, [loader.load(selected, "user")], planNotes([selected], triggers, ""), "");
    } catch (error) {
      feedback(pi, ctx, `${error instanceof Error ? error.message : String(error)}\n${usage}`);
    }
    return;
  }
  try {
    sendProcedure(pi, loader, [loader.load(capability, "user")], planNotes([capability], triggers, request), request);
  } catch (error) {
    feedback(pi, ctx, `${error instanceof Error ? error.message : String(error)}\n${usage}`);
  }
}

export function registerImpeccable(pi: ExtensionAPI, loader: Resolver, triggers: TriggerEntry[] = loadTriggers()): void {
  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(PROCEDURE_ENTRY, (message, { expanded }, theme) => {
      const details = (message.details ?? {}) as Partial<ProcedureDetails>;
      const loaded = details.loaded ?? [];
      const subject = safeDisplayText(details.request?.trim() || loaded.map(entry => entry.label).join(" + ") || "procedure");
      return impeccableRows.message(() => startedToolLifecycle("impeccable", subject, { label: "started" }))(message, { expanded }, theme);
    });
  }
  pi.registerCommand("impeccable", {
    description: "Load one or two design procedures matching the request, or choose an implemented capability",
    handler: (args, ctx) => command(pi, loader, args, ctx, triggers),
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
    renderCall: () => impeccableRows.emptyCall(),
    renderResult: impeccableRows.result<{ content: unknown; details?: Bundle }>((result) => eventToolLifecycle("impeccable", result.details?.root ?? "loading", {
      label: "loaded",
      details: [
        fieldLine("loaded", result.details?.loaded.join(", ") || "none"),
        fieldLine("references", result.details?.availableReferences.map(edge => `${edge.id} — ${edge.when}`).join("; ") || "none"),
        fieldLine("bytes", result.details?.byteLength ?? 0),
        fieldLine("scripts", "none executed"),
      ],
      detailLimit: 4,
    })),
  });
}

export default function impeccable(pi: ExtensionAPI): void {
  registerImpeccable(pi, resolver);
}

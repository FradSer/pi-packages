/**
 * The subagent worker extension: what this package contributes to a child it
 * spawns.
 *
 * Loaded with `-e` alongside any other package's worker extension. `--extension`
 * is repeatable and `--no-extensions` still loads explicit paths, so a child can
 * carry this package's Agent Memory capability and a consumer's coordination
 * capability at the same time without either package knowing about the other.
 *
 * This module declares the tool it registers in `SUBAGENT_CAPABILITY_TOOLS`. The
 * spawner hardcodes no capability set: declaring tools with no extension to
 * register them is refused, so a contribution is always paired with the code that
 * implements it.
 */

import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  appendMemoryEntry,
  buildAgentMemoryBlock,
  writeMemoryProposal,
} from "./memory.ts";

/** Env the spawner's caller supplies. Absent means this is not a subagent child
 * and the extension does nothing, so it is safe to load anywhere. */
export const SUBAGENT_ROLE_ENV = "PI_SUBAGENT_ROLE";
export const SUBAGENT_TOOLS_ENV = "PI_SUBAGENT_TOOLS";
export const SUBAGENT_MEMORY_ENV = "PI_SUBAGENT_MEMORY";

/** Tool ids this extension registers in a child. */
export const SUBAGENT_CAPABILITY_TOOLS: readonly string[] = ["agent_memory"];

/** This extension's entry, passed to a spawned child with `-e`. */
export const SUBAGENT_WORKER_EXTENSION_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "worker-extension.ts",
);

const MEMORY_TOOL_PARAMS = {
  type: "object",
  properties: {
    action: { type: "string", enum: ["append", "propose"], description: "append writes a capability entry; propose records a candidate for review" },
    name: { type: "string", description: "Entry filename stem for append (lowercase, digits, dots, dashes, underscores)" },
    description: { type: "string", description: "One-line relevance cue: when this capability applies" },
    body: { type: "string", description: "The capability, its applicability, and its limits" },
    title: { type: "string", description: "Proposal title" },
    applicability: { type: "string", description: "Where the capability applies" },
    limits: { type: "string", description: "Where it does not, and what it assumes" },
    evidence: { type: "string", description: "What the claim rests on" },
  },
  required: ["action"],
  additionalProperties: false,
} as const;

export default function subagentWorkerExtension(pi: ExtensionAPI): void {
  const agentName = process.env[SUBAGENT_ROLE_ENV]?.trim();
  if (!agentName) return;
  const tools = (process.env[SUBAGENT_TOOLS_ENV] ?? "").split(",").map((tool) => tool.trim()).filter(Boolean);
  const memoryEnabled = process.env[SUBAGENT_MEMORY_ENV] === "enabled";
  const block = memoryEnabled ? buildAgentMemoryBlock({ agentName, tools }) : undefined;

  if (block?.text) {
    pi.on("before_agent_start", async (event) => ({
      systemPrompt: `${event.systemPrompt}\n\n=== AGENT MEMORY (${agentName}) ===\n${block.text}`,
    }));
  }

  if (!memoryEnabled) return;
  const root = block?.root;
  const writable = block?.writable ?? false;

  pi.registerTool({
    name: "agent_memory",
    label: "Agent Memory",
    promptSnippet: "Record or propose a reusable capability",
    description:
      "Record a durable capability of this Agent, or propose one for review. Capability only: methods, judgment criteria, operating patterns. Project facts, decisions, and history belong to Project Memory, not here.",
    parameters: MEMORY_TOOL_PARAMS as never,
    async execute(_toolCallId, params: Record<string, unknown>) {
      if (!root) {
        return refuse("This Agent has no memory folder. A Temporary Agent owns no Agent Memory; promotion creates one.");
      }
      const action = String(params.action ?? "");
      if (action === "propose") {
        const title = String(params.title ?? "").trim() || String(params.name ?? "proposal").trim();
        const capability = String(params.body ?? "").trim();
        if (!capability) return refuse("A proposal needs `body` describing the capability.");
        const result = writeMemoryProposal(root, {
          title,
          capability,
          applicability: String(params.applicability ?? params.description ?? "").trim(),
          limits: String(params.limits ?? "").trim(),
          ...(params.evidence ? { evidence: String(params.evidence) } : {}),
        });
        return result.ok
          ? accept(`PROPOSAL RECORDED · ${path.basename(result.file)}\nNEXT · review and merge are separate decisions; a proposal is not memory yet.`)
          : refuse(result.error);
      }
      if (action !== "append") return refuse(`Unknown action "${action}". Use append or propose.`);
      if (!writable) {
        return refuse(
          "This Agent's tool grant is read-only, so it cannot write Agent Memory. Record the lesson in your result, or use action=propose.",
        );
      }
      const name = String(params.name ?? "").trim();
      const description = String(params.description ?? "").trim();
      const body = String(params.body ?? "").trim();
      if (!name || !body) return refuse("An append needs `name` and `body`.");
      const result = appendMemoryEntry(root, { name, description, body }, { writable });
      return result.ok
        ? accept(`ENTRY APPENDED · ${path.basename(result.file)}\nNEXT · the index is regenerated; later sessions see it without reloading anything.`)
        : refuse(result.error);
    },
  });
}

function accept(text: string) {
  return { content: [{ type: "text" as const, text }], details: { outcome: "recorded" } };
}

function refuse(error: string) {
  return { content: [{ type: "text" as const, text: `REFUSED · ${error}` }], details: { outcome: "refused", error }, isError: true };
}

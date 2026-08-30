import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { eventToolLifecycle, renderToolLifecycle } from "@fradser/pi-kit";

const PKG_DIR =
  typeof __dirname === "string"
    ? __dirname
    : dirname(fileURLToPath(import.meta.url));

const WORKFLOW_PATH = join(PKG_DIR, "..", "references", "workflow.md");

const METHOD_FLAG = "--method=";
const ALL_METHODS = ["deepwiki", "context7", "exa", "clone", "web", "all"] as const;
const MANIFEST_FILES = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"];
const CONTEXT_WORKFLOW_MESSAGE_TYPE = "context-workflow";

const CONTEXT_GUIDANCE = `
## Context retrieval

Use these tools proactively — do not answer from memory when a lookup would be more accurate:

- The user asks to search/搜索/查找 something on the web, or you need current facts, real-world code patterns, or comparisons: call \`context_exa\` immediately. It works without an API key (public Exa endpoint); EXA_API_KEY upgrades it to full-text results.
- You are about to answer how to use a library or framework API: call \`context_context7\` first (optionally focused by topic) and answer from the fetched docs.
- The user asks about a public GitHub repository (architecture, how it works, targeted Q&A): call \`context_deepwiki\` (structure/contents/ask) before considering a clone.
- Private repos or deep line-level inspection: \`git clone --depth=1\` to /tmp plus \`read\`/\`bash\`; always clean up.
- Prefer small intermediate summaries over dumping raw API payloads into the conversation.
- The \`/context <targets...> [--method=...]\` command loads the full workflow when the user asks to research or understand code.
`;

interface ParsedArgs {
  targets: string[];
  methods: string[];
}

interface ContextWorkflowDetails {
  targets: string[];
  methods: string[];
}

function parseArgs(raw: string): ParsedArgs {
  const targets: string[] = [];
  let methods: string[] = ["all"];
  const tokens = raw.match(/(?:[^\s"]+|"[^"]*")+/g) ?? [];
  for (const token of tokens) {
    if (token.startsWith(METHOD_FLAG)) {
      methods = token
        .slice(METHOD_FLAG.length)
        .split(",")
        .map((m) => m.trim().toLowerCase())
        .filter((m) => (ALL_METHODS as readonly string[]).includes(m));
      if (methods.length === 0) methods = ["all"];
      continue;
    }
    targets.push(token.replace(/^"|"$/g, ""));
  }
  return { targets, methods };
}

function detectDependencies(cwd: string): string[] {
  const deps = new Set<string>();
  for (const file of MANIFEST_FILES) {
    try {
      const text = readFileSync(join(cwd, file), "utf8");
      if (file === "package.json") {
        const json = JSON.parse(text) as {
          dependencies?: Record<string, string>;
          devDependencies?: Record<string, string>;
        };
        for (const name of Object.keys(json.dependencies ?? {})) deps.add(name);
        for (const name of Object.keys(json.devDependencies ?? {})) deps.add(name);
      } else if (file === "pyproject.toml") {
        for (const match of text.matchAll(/^\s*"([A-Za-z0-9_.-]+)"\s*[>=<~!]/gm)) {
          deps.add(match[1]);
        }
      } else if (file === "go.mod") {
        for (const match of text.matchAll(/^\s*([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\s+v/gm)) {
          deps.add(match[1]);
        }
      } else if (file === "Cargo.toml") {
        for (const match of text.matchAll(/^([A-Za-z0-9_-]+)\s*=\s*"[^"]+"/gm)) {
          deps.add(match[1]);
        }
      }
    } catch {
      // Missing or unreadable manifest — skip.
    }
  }
  return [...deps];
}

function loadWorkflow(): string {
  return readFileSync(WORKFLOW_PATH, "utf8");
}

function buildWorkflowPrompt(args: ParsedArgs, cwd: string): { prompt: string; details: ContextWorkflowDetails } {
  const workflow = loadWorkflow();
  const targets = args.targets.length > 0 ? args.targets : detectDependencies(cwd);
  const header = [
    "Run the /context workflow.",
    "",
    `Targets: ${targets.length > 0 ? targets.join(", ") : "(none provided and no dependencies detected in cwd)"}`,
    `Allowed methods: ${args.methods.join(",")}`,
    "",
    "---",
    "",
  ].join("\n");
  return { prompt: header + workflow, details: { targets, methods: args.methods } };
}

function workflowSubject(details: ContextWorkflowDetails): string {
  const targets = details.targets.length > 0 ? details.targets.join(", ") : "no targets";
  return `${targets} · ${details.methods.join(",")}`;
}

function sendWorkflow(pi: ExtensionAPI, prompt: string, details: ContextWorkflowDetails): void {
  pi.sendMessage(
    {
      customType: CONTEXT_WORKFLOW_MESSAGE_TYPE,
      content: prompt,
      display: true,
      details,
    },
    { deliverAs: "followUp", triggerTurn: true },
  );
}

export function registerContextCommand(pi: ExtensionAPI): void {
  pi.registerMessageRenderer(CONTEXT_WORKFLOW_MESSAGE_TYPE, (message, { expanded }, theme) => {
    const details = message.details as ContextWorkflowDetails;
    return {
      render: (width: number) => renderToolLifecycle(
        eventToolLifecycle("context", workflowSubject(details), {
          label: "workflow",
          details: String(message.content).split("\n"),
          detailLimit: "all",
        }),
        {
          width,
          expanded,
          expandHint: "ctrl+o to expand",
          theme,
          fit: truncateToWidth,
          visibleWidth,
        },
      ),
      invalidate: () => {},
    };
  });

  pi.on("before_agent_start", async (event) => ({
    systemPrompt: event.systemPrompt + CONTEXT_GUIDANCE,
  }));

  pi.registerCommand("context", {
    description:
      "Retrieve code context for repos, libraries, or a natural-language question via DeepWiki, Context7, Exa, clone, or web.",
    handler: async (rawArgs, ctx) => {
      const args = parseArgs(rawArgs.trim());
      const { prompt, details } = buildWorkflowPrompt(args, ctx.cwd);
      sendWorkflow(pi, prompt, details);
      await ctx.waitForIdle();
    },
  });
}

export default function register(pi: ExtensionAPI): void {
  registerContextCommand(pi);
}

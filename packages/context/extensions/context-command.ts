import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PKG_DIR =
  typeof __dirname === "string"
    ? __dirname
    : dirname(fileURLToPath(import.meta.url));

const WORKFLOW_PATH = join(PKG_DIR, "..", "references", "workflow.md");

const METHOD_FLAG = "--method=";
const ALL_METHODS = ["deepwiki", "context7", "exa", "clone", "web", "all"] as const;
const MANIFEST_FILES = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"];

const CONTEXT_GUIDANCE = `
## Context retrieval

- Use \`context_deepwiki\` for public GitHub repo architecture and DeepWiki Q&A.
- Use \`context_context7\` for up-to-date library/API docs (optionally focused by topic).
- Use \`context_exa\` for web/code search when EXA_API_KEY is set; otherwise fall back to \`bash\` + \`curl\`.
- Use \`git clone --depth=1\` to /tmp plus \`read\`/\`bash\` for private repos or deep inspection; always clean up.
- Prefer small intermediate summaries over dumping raw API payloads into the conversation.
- The \`/context <targets...> [--method=...]\` command loads the full workflow when the user asks to research or understand code.
`;

interface ParsedArgs {
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

function buildUserPrompt(args: ParsedArgs, cwd: string): string {
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
  return header + workflow;
}

export function registerContextCommand(pi: ExtensionAPI): void {
  pi.on("before_agent_start", async (event) => ({
    systemPrompt: event.systemPrompt + CONTEXT_GUIDANCE,
  }));

  pi.registerCommand("context", {
    description:
      "Retrieve code context for repos, libraries, or a natural-language question via DeepWiki, Context7, Exa, clone, or web.",
    handler: async (rawArgs, ctx) => {
      const args = parseArgs(rawArgs.trim());
      const prompt = buildUserPrompt(args, ctx.cwd);
      pi.sendUserMessage(prompt, { deliverAs: "followUp" });
    },
  });
}

export default function register(pi: ExtensionAPI): void {
  registerContextCommand(pi);
}

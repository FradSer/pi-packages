/**
 * Declarative agent definitions: Markdown files with YAML-style frontmatter.
 *
 * Discovery scopes (later scopes override earlier ones for the same name):
 *   1. bundled  — agents shipped with this package (agents/)
 *   2. user     — ~/.pi/agent/agents/  (respects PI_CODING_AGENT_DIR)
 *   3. project  — <cwd>/.pi/agents/
 *
 * Frontmatter fields:
 *   name        — unique agent id (required)
 *   description — routing contract: when the leader should choose this agent
 *   tools       — comma-separated list or YAML list of Pi tool ids
 *   model       — optional provider/model pin
 * The Markdown body is the worker's role prompt.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface AgentDefinition {
  name: string;
  description: string;
  tools: string[];
  model?: string;
  /** The Markdown body, trimmed; used as the worker role prompt. */
  prompt: string;
  /** Scope that supplied this definition ("bundled" | "user" | "project"). */
  scope: "bundled" | "user" | "project";
  /** Absolute path of the definition file. */
  source: string;
}

const BUNDLED_AGENTS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "agents");

function agentsDir(scope: "user" | "project", cwd?: string): string {
  if (scope === "user") {
    const base = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
    return path.join(base, "agents");
  }
  return path.join(cwd || process.cwd(), ".pi", "agents");
}

function parseFrontmatter(raw: string): { fields: Record<string, string | string[]>; body: string } {
  const fields: Record<string, string | string[]> = {};
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!match) return { fields, body: raw.trim() };
  for (const line of match[1].split("\n")) {
    const separator = line.indexOf(":");
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    // Strip inline YAML comments (# ...) and surrounding whitespace/quotes.
    let value = line.slice(separator + 1).replace(/\s+#.*$/, "").trim();
    if (key === "tools") {
      const tools = value
        .replace(/^\[|\]$/g, "")
        .split(",")
        .map((tool) => tool.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean);
      fields.tools = tools;
      continue;
    }
    fields[key] = value.replace(/^["']|["']$/g, "");
  }
  return { fields, body: match[2].trim() };
}

function loadDir(scope: "bundled" | "user" | "project", dir: string, agents: Map<string, AgentDefinition>): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return; // A missing agents directory is not an error.
  }
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".md")) continue;
    const source = path.join(dir, entry.name);
    let raw: string;
    try {
      raw = fs.readFileSync(source, "utf8");
    } catch {
      continue;
    }
    const { fields, body } = parseFrontmatter(raw);
    const name = typeof fields.name === "string" ? fields.name : entry.name.replace(/\.md$/, "");
    if (!name || !body) continue;
    const tools = Array.isArray(fields.tools) ? fields.tools : [];
    const model = typeof fields.model === "string" && fields.model ? fields.model : undefined;
    agents.set(name, {
      name,
      description: typeof fields.description === "string" ? fields.description : "",
      tools,
      model,
      prompt: body,
      scope,
      source,
    });
  }
}

/**
 * Resolve all agent definitions visible from the given cwd, with later scopes
 * overriding earlier ones per name: project > user > bundled.
 */
export function discoverAgents(cwd?: string): Map<string, AgentDefinition> {
  const agents = new Map<string, AgentDefinition>();
  loadDir("bundled", BUNDLED_AGENTS_DIR, agents);
  loadDir("user", agentsDir("user", cwd), agents);
  loadDir("project", agentsDir("project", cwd), agents);
  return agents;
}

/** Resolve one agent by name, or undefined when no scope defines it. */
export function resolveAgent(name: string, cwd?: string): AgentDefinition | undefined {
  return discoverAgents(cwd).get(name);
}

/** True when the agent name is defined in any scope. */
export function hasAgent(name: string, cwd?: string): boolean {
  return resolveAgent(name, cwd) !== undefined;
}

/**
 * Format discovered agents as Markdown for prompt injection in before_agent_start.
 */
export function formatAgentGuidance(cwd?: string): string {
  const agents = discoverAgents(cwd);
  if (agents.size === 0) return "(none found in bundled, user, or project scopes)";
  const lines: string[] = [];
  for (const agent of agents.values()) {
    const model = agent.model ? ` | Model: ${agent.model}` : "";
    lines.push(`- **${agent.name}** (${agent.scope})`);
    if (agent.description) lines.push(`  ${agent.description}`);
    lines.push(`  Tools: ${agent.tools.join(", ") || "(role defaults)"}${model}`);
  }
  return lines.join("\n");
}

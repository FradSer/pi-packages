/**
 * Declarative agent definitions: Markdown files with YAML-style frontmatter.
 *
 * Discovery scopes (later scopes override earlier ones for the same name):
 *   1. user          — ~/.pi/agent/agents/ (respects PI_CODING_AGENT_DIR)
 *   2. project       — <cwd>/.pi/agents/<name>.md
 *   3. project-local — <cwd>/.pi/agents/<name>.local.md (personal override)
 *
 * There are no built-in roles: references/agent-roles.md ships template
 * shapes that the leader consults when generating a new definition on demand.
 *
 * Frontmatter fields:
 *   name        — unique agent id (required)
 *   description — routing contract: when the leader should choose this agent
 *   tools       — comma-separated list or YAML list of Pi tool ids
 *   model       — optional provider/model pin
 *   verify      — optional role-default completion gate command (zero exit passes)
 *   worktree    — optional role-default Git worktree isolation (true/false)
 * The Markdown body is the worker's role prompt.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

export type AgentScope = "user" | "project" | "project-local" | "session";

export interface AgentDefinition {
  name: string;
  description: string;
  tools: string[];
  model?: string;
  /** Role-default completion gate; task-level verify overrides this. */
  verify?: string;
  /** Whether this role always receives a dedicated Git worktree. */
  worktree: boolean;
  /** The Markdown body, trimmed; used as the teammate's role prompt. */
  prompt: string;
  /** Scope that supplied this definition (precedence: project-local > project > user > bundled). */
  scope: AgentScope;
  /** True only for the shared project scope that is expected to be git-managed.
   * user and project-local definitions are machine/personal by definition. */
  gitManaged: boolean;
  /** Absolute path of the definition file; absent for session-only roles. */
  source?: string;
}

export interface AgentDefinitionInput {
  name: string;
  description: string;
  tools: string[];
  model?: string;
  verify?: string;
  worktree?: boolean;
  prompt: string;
}

const sessionAgents = new Map<string, AgentDefinition>();
const AGENT_NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

function normalizeAgentInput(input: AgentDefinitionInput): AgentDefinitionInput {
  const name = input.name.trim();
  if (!AGENT_NAME_PATTERN.test(name)) {
    throw new Error(`Invalid agent name "${name}". Use letters, digits, dots, dashes, underscores.`);
  }
  const prompt = input.prompt.trim();
  if (!prompt) throw new Error(`Agent "${name}" prompt must not be empty.`);
  return {
    ...input,
    name,
    description: input.description.trim(),
    tools: input.tools.map((tool) => tool.trim()).filter(Boolean),
    model: input.model?.trim() || undefined,
    verify: input.verify?.trim() || undefined,
    worktree: input.worktree ?? false,
    prompt,
  };
}

/** Register a generated role for this session without writing a definition file. */
export function registerSessionAgent(input: AgentDefinitionInput): AgentDefinition {
  const normalized = normalizeAgentInput(input);
  const definition: AgentDefinition = {
    ...normalized,
    worktree: normalized.worktree ?? false,
    scope: "session",
    gitManaged: false,
    source: undefined,
  };
  sessionAgents.set(definition.name, definition);
  return definition;
}

/** Persist a generated role only when the user explicitly requests it. */
export function persistAgentDefinition(
  input: AgentDefinitionInput,
  scope: "project" | "project-local",
  cwd = process.cwd(),
): AgentDefinition {
  const normalized = normalizeAgentInput(input);
  const directory = agentsDir("project", cwd);
  fs.mkdirSync(directory, { recursive: true });
  const filename = `${normalized.name}${scope === "project-local" ? LOCAL_DEFINITION_SUFFIX : ".md"}`;
  const source = path.join(directory, filename);
  const frontmatter = [
    "---",
    `name: ${normalized.name}`,
    `description: ${normalized.description.replace(/[\\r\\n]+/g, " ")}`,
    `tools: ${normalized.tools.join(", ")}`,
    ...(normalized.model ? [`model: ${normalized.model}`] : []),
    ...(normalized.verify ? [`verify: ${normalized.verify.replace(/[\\r\\n]+/g, " ")}`] : []),
    `worktree: ${normalized.worktree ? "true" : "false"}`,
    "---",
    normalized.prompt,
    "",
  ].join("\n");
  fs.writeFileSync(source, frontmatter, { encoding: "utf8", mode: 0o600 });
  sessionAgents.delete(normalized.name);
  return {
    ...normalized,
    worktree: normalized.worktree ?? false,
    scope,
    gitManaged: scope === "project",
    source,
  };
}

/** Drop generated session roles; persistent user/project definitions remain discoverable. */
export function clearSessionAgents(): void {
  sessionAgents.clear();
}

/** Shipped role templates: reference material for generating new definitions
 * on demand — never discovered and never spawnable directly. */
export const AGENT_REFERENCE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "..", "references", "agent-roles.md",
);

/** Files named `xxx.local.md` in the project agents directory are personal
 * overrides: same teammate name as `xxx.md`, project-local scope, never git-
 * managed by convention. */
export const LOCAL_DEFINITION_SUFFIX = ".local.md";

function agentsDir(scope: "user" | "project", cwd?: string): string {
  if (scope === "user") {
    return path.join(getAgentDir(), "agents");
  }
  return path.join(cwd || process.cwd(), ".pi", "agents");
}

function parseFrontmatter(raw: string): { fields: Record<string, string | string[]>; body: string } {
  const fields: Record<string, string | string[]> = {};
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!match) return { fields, body: raw.trim() };
  const lines = match[1].split("\n");
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const separator = line.indexOf(":");
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    // Strip inline YAML comments (# ...) and surrounding whitespace/quotes.
    let value = line.slice(separator + 1).replace(/\s+#.*$/, "").trim();
    if (key === "tools") {
      if (value === "") {
        // YAML block sequence: "- item" lines, flush-left or indented,
        // possibly interleaved with blank or comment-only lines.
        const items: string[] = [];
        index += 1;
        while (index < lines.length) {
          const trimmed = lines[index].trim();
          if (trimmed === "" || trimmed.startsWith("#")) {
            index += 1;
            continue;
          }
          if (!/^-.+/.test(trimmed)) break;
          const rawItem = trimmed.replace(/^-\s*/, "");
          const item = rawItem
            .replace(/\s+#.*$/, "")
            .trim()
            .replace(/^["']|["']$/g, "");
          // "- # comment" is a comment-only entry, not a tool.
          if (item && !rawItem.trimStart().startsWith("#")) items.push(item);
          index += 1;
        }
        index -= 1; // The for-loop steps past the last consumed line.
        fields.tools = items;
        continue;
      }
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

function loadDir(baseScope: AgentScope, dir: string, agents: Map<string, AgentDefinition>): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return; // A missing agents directory is not an error.
  }
  // Dedup by name within the directory: plain .md first so a same-name
  // xxx.local.md (personal override) overwrites it in the map.
  const ordered = [...entries].sort((left, right) =>
    Number(left.name.endsWith(LOCAL_DEFINITION_SUFFIX)) - Number(right.name.endsWith(LOCAL_DEFINITION_SUFFIX))
    || left.name.localeCompare(right.name),
  );
  for (const entry of ordered) {
    if (!entry.isFile() || !entry.name.endsWith(".md")) continue;
    const source = path.join(dir, entry.name);
    let raw: string;
    try {
      raw = fs.readFileSync(source, "utf8");
    } catch {
      continue;
    }
    const { fields, body } = parseFrontmatter(raw);
    const isLocal = baseScope === "project" && entry.name.endsWith(LOCAL_DEFINITION_SUFFIX);
    const baseName = isLocal
      ? entry.name.slice(0, -LOCAL_DEFINITION_SUFFIX.length)
      : entry.name.replace(/\.md$/, "");
    const name = typeof fields.name === "string" ? fields.name : baseName;
    if (!name || !body) continue;
    agents.set(name, {
      name,
      description: typeof fields.description === "string" ? fields.description : "",
      tools: Array.isArray(fields.tools) ? fields.tools : [],
      model: typeof fields.model === "string" && fields.model ? fields.model : undefined,
      verify: typeof fields.verify === "string" && fields.verify ? fields.verify : undefined,
      worktree: fields.worktree === "true",
      prompt: body,
      scope: isLocal ? "project-local" : baseScope,
      gitManaged: scopeIsGitManaged(isLocal ? "project-local" : baseScope),
      source,
    });
  }
}

/** Only the shared project layer is expected to be git-managed. */
function scopeIsGitManaged(scope: AgentScope): boolean {
  return scope === "project";
}

/**
 * Resolve all agent definitions visible from the given cwd, with later scopes
 * overriding earlier ones per name: project-local > project > user.
 */
export function discoverAgents(cwd?: string): Map<string, AgentDefinition> {
  const agents = new Map<string, AgentDefinition>();
  loadDir("user", agentsDir("user", cwd), agents);
  loadDir("project", agentsDir("project", cwd), agents);
  for (const [name, definition] of sessionAgents) agents.set(name, definition);
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
  if (agents.size === 0) return "(none defined yet — create one on demand from the shipped templates)";
  const lines: string[] = [];
  for (const agent of agents.values()) {
    const extras = [
      agent.model ? `Model: ${agent.model}` : "",
      agent.verify ? `Verify: ${agent.verify}` : "",
      agent.worktree ? "Worktree: true" : "",
      agent.scope === "session" ? "in-memory" : agent.gitManaged ? "git-managed" : "local",
    ].filter(Boolean);
    lines.push(`- **${agent.name}** (${agent.scope})`);
    if (agent.description) lines.push(`  ${agent.description}`);
    lines.push(`  Tools: ${agent.tools.join(", ") || "(role defaults)"}${extras.length > 0 ? ` | ${extras.join(" | ")}` : ""}`);
  }
  return lines.join("\n");
}

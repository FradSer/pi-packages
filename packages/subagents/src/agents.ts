/** Disk agent.md declarations and session-only inline roles.
 * Precedence: project-local > project > user > session. Discovery never writes
 * or reads legacy flat roles; migration is an explicit, separate library call.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { assertAgentName, assertAgentStoragePath } from "./workspace.ts";

export type AgentScope = "user" | "project" | "project-local" | "session";

export interface AgentDefinitionInput {
  name: string;
  description: string;
  tools: string[];
  model?: string;
  verify?: string;
  prompt: string;
}

export interface AgentDefinition extends AgentDefinitionInput {
  scope: AgentScope;
  /** Only shared project definitions are git-managed by convention. */
  gitManaged: boolean;
  /** Absolute declaration path; absent for session roles. */
  source?: string;
}

export const MODEL_INHERIT_ALIAS = "inherit";
/** Suffix of the project-local directory, not of a Markdown filename. */
export const LOCAL_DEFINITION_SUFFIX = ".local";
export const AGENT_REFERENCE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "..", "references", "agent-roles.md",
);

const sessionAgents = new Map<string, AgentDefinition>();

function normalizeAgentInput(input: AgentDefinitionInput): AgentDefinitionInput {
  const name = input.name.trim();
  assertAgentName(name);
  // Select fields explicitly: JavaScript callers cannot smuggle deprecated
  // settings or a forged source/scope through a spread of the input object.
  return {
    name,
    description: input.description.trim(),
    tools: input.tools.map(tool => tool.trim()).filter(Boolean),
    model: input.model?.trim() || undefined,
    verify: input.verify?.trim() || undefined,
    prompt: input.prompt.trim(),
  };
}

export function registerSessionAgent(input: AgentDefinitionInput): AgentDefinition {
  const definition: AgentDefinition = {
    ...normalizeAgentInput(input),
    // Session instructions are authored content, not filesystem identifiers.
    // Persisted definition normalization is a separate, unchanged operation.
    description: input.description,
    prompt: input.prompt,
    scope: "session", gitManaged: false,
  };
  sessionAgents.set(definition.name, definition);
  return definition;
}

/** Explicit user-authorized library operation; never called by the agent tool. */
export function persistAgentDefinition(
  input: AgentDefinitionInput,
  scope: "user" | "project" | "project-local",
  cwd = process.cwd(),
): AgentDefinition {
  const normalized = normalizeAgentInput(input);
  if (!["user", "project", "project-local"].includes(scope)) throw new Error("Invalid definition scope.");
  if ([normalized.model, ...normalized.tools].some(value => value !== undefined && /[\r\n]/.test(value))) {
    throw new Error("Persisted model and tool ids must be single-line values.");
  }
  const root = path.resolve(scope === "user" ? getAgentDir() : cwd);
  const directory = path.join(root, ...(scope === "user" ? ["agents"] : [".pi", "agents"]),
    normalized.name + (scope === "project-local" ? LOCAL_DEFINITION_SUFFIX : ""));
  const source = path.join(directory, "agent.md");
  assertAgentStoragePath(root, source);
  const frontmatter = [
    "---",
    `name: ${normalized.name}`,
    `description: ${normalized.description.replace(/[\r\n]+/g, " ")}`,
    `tools: ${normalized.tools.join(", ")}`,
    ...(normalized.model ? [`model: ${normalized.model}`] : []),
    ...(normalized.verify ? [`verify: ${normalized.verify.replace(/[\r\n]+/g, " ")}`] : []),
    "---", normalized.prompt, "",
  ].join("\n");
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  assertAgentStoragePath(root, source);
  writeDefinitionFile(root, source, frontmatter);
  sessionAgents.delete(normalized.name);
  return { ...normalized, scope, gitManaged: scope === "project", source };
}

function writeDefinitionFile(root: string, source: string, content: string): void {
  try {
    const stat = fs.lstatSync(source);
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
      throw new Error(`Refusing linked or non-regular Agent definition: ${source}`);
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  const temporary = `${source}.${process.pid}.${randomUUID()}.tmp`;
  let descriptor: number | undefined;
  try {
    descriptor = fs.openSync(temporary, fs.constants.O_WRONLY | fs.constants.O_CREAT
      | fs.constants.O_EXCL | (fs.constants.O_NOFOLLOW ?? 0), 0o600);
    fs.writeFileSync(descriptor, content, { encoding: "utf8" });
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    assertAgentStoragePath(root, source);
    try {
      const stat = fs.lstatSync(source);
      if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
        throw new Error(`Refusing linked or non-regular Agent definition: ${source}`);
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    fs.renameSync(temporary, source);
  } finally {
    if (descriptor !== undefined) {
      try { fs.closeSync(descriptor); } catch { /* preserve the write failure */ }
    }
    fs.rmSync(temporary, { force: true });
  }
}

export function clearSessionAgents(): void {
  sessionAgents.clear();
}

function parseFrontmatter(raw: string): { fields: Record<string, string | string[]>; body: string } | undefined {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!match) return undefined;
  const fields: Record<string, string | string[]> = Object.create(null);
  const lines = match[1].split("\n");
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const separator = line.indexOf(":");
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).replace(/\s+#.*$/, "").trim();
    if (key === "tools") {
      if (value === "") {
        const items: string[] = [];
        index += 1;
        while (index < lines.length) {
          const trimmed = lines[index].trim();
          if (trimmed === "" || trimmed.startsWith("#")) { index += 1; continue; }
          if (!/^-.+/.test(trimmed)) break;
          const rawItem = trimmed.replace(/^-\s*/, "");
          const item = rawItem.replace(/\s+#.*$/, "").trim().replace(/^["']|["']$/g, "");
          if (item && !rawItem.trimStart().startsWith("#")) items.push(item);
          index += 1;
        }
        index -= 1;
        fields.tools = items;
      } else {
        fields.tools = value.replace(/^\[|\]$/g, "").split(",")
          .map(tool => tool.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
      }
    } else {
      fields[key] = value.replace(/^["']|["']$/g, "");
    }
  }
  return { fields, body: match[2].trim() };
}

/** The same validity check is used by discovery and explicit legacy migration.
 * The expected name binds a declaration to its canonical directory.
 */
export function parseAgentDefinition(
  raw: string, name: string, scope: Exclude<AgentScope, "session">, source?: string,
): AgentDefinition | undefined {
  try { assertAgentName(name); } catch { return undefined; }
  const parsed = parseFrontmatter(raw);
  if (!parsed || parsed.fields.name !== name || typeof parsed.fields.description !== "string"
    || !Array.isArray(parsed.fields.tools)) return undefined;
  return {
    name, description: parsed.fields.description, tools: parsed.fields.tools,
    model: typeof parsed.fields.model === "string" && parsed.fields.model ? parsed.fields.model : undefined,
    verify: typeof parsed.fields.verify === "string" && parsed.fields.verify ? parsed.fields.verify : undefined,
    prompt: parsed.body, scope, gitManaged: scope === "project", ...(source ? { source } : {}),
  };
}

function loadDir(scope: "user" | "project", root: string, dir: string, agents: Map<string, AgentDefinition>): void {
  let entries: fs.Dirent[];
  try {
    assertAgentStoragePath(root, dir);
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch { return; }
  const ordered = entries.sort((a, b) =>
    Number(a.name.endsWith(LOCAL_DEFINITION_SUFFIX)) - Number(b.name.endsWith(LOCAL_DEFINITION_SUFFIX))
    || a.name.localeCompare(b.name));
  for (const entry of ordered) {
    if (!entry.isDirectory()) continue;
    const isLocal = scope === "project" && entry.name.endsWith(LOCAL_DEFINITION_SUFFIX);
    const name = isLocal ? entry.name.slice(0, -LOCAL_DEFINITION_SUFFIX.length) : entry.name;
    const source = path.join(dir, entry.name, "agent.md");
    try {
      assertAgentStoragePath(root, source);
      const stat = fs.lstatSync(source);
      if (!stat.isFile() || stat.nlink !== 1) continue;
      const definition = parseAgentDefinition(fs.readFileSync(source, "utf8"), name, isLocal ? "project-local" : scope, source);
      if (definition) agents.set(name, definition);
    } catch { /* Invalid/unreadable declarations are not identities. */ }
  }
}

export function discoverAgents(cwd = process.cwd()): Map<string, AgentDefinition> {
  const agents = new Map<string, AgentDefinition>();
  const userRoot = path.resolve(getAgentDir());
  const projectRoot = path.resolve(cwd);
  loadDir("user", userRoot, path.join(userRoot, "agents"), agents);
  loadDir("project", projectRoot, path.join(projectRoot, ".pi", "agents"), agents);
  for (const [name, definition] of sessionAgents) if (!agents.has(name)) agents.set(name, definition);
  return agents;
}

export function resolveAgent(name: string, cwd?: string): AgentDefinition | undefined {
  return discoverAgents(cwd).get(name);
}

/** Disk declarations always outrank inline input; session residue can be replaced. */
export function inlineDefinitionApplies(resolved: AgentDefinition | undefined): boolean {
  return !resolved || resolved.scope === "session";
}

export function formatAgentGuidance(cwd?: string): string {
  const agents = discoverAgents(cwd);
  if (agents.size === 0) return "(none defined; pass description and role_prompt to define one inline)";
  const lines: string[] = [];
  for (const agent of agents.values()) {
    const extras = [
      agent.model ? `Model: ${agent.model}` : "",
      agent.verify ? `Verify: ${agent.verify}` : "",
      agent.scope === "session" ? "in-memory" : "disk identity; private Memory/history/scratch; project cwd",
      agent.gitManaged ? "git-managed definition" : "",
    ].filter(Boolean);
    lines.push(`- **${agent.name}** (${agent.scope})`);
    if (agent.description) lines.push(`  ${agent.description}`);
    lines.push(`  Tools: ${agent.tools.join(", ") || "(none)"} | ${extras.join(" | ")}`);
  }
  return lines.join("\n");
}

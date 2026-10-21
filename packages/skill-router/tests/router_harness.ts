import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Skill } from "@earendil-works/pi-coding-agent";

interface HarnessResult {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

type Handler = (event: never, ctx: never) => Promise<unknown> | unknown;

/** The subset of a registered tool this harness reads back. */
interface RegisteredTool {
  name: string;
  description?: string;
  exposure?: string;
  namespace?: { name: string; aliases?: readonly string[]; description?: string; instructions?: string };
  parameters?: unknown;
  promptGuidelines?: string[];
  reachesTools?: (input: Record<string, unknown>) => unknown;
  execute?: (
    toolCallId: string,
    params: unknown,
    signal: AbortSignal | undefined,
    onUpdate: unknown,
    ctx: unknown,
  ) => Promise<unknown>;
}

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>;
  structuredContent?: unknown;
  isError?: boolean;
}

/** How the session's tool set presents codemode: active, registered but inactive, or absent. */
function codemodeState(flags: Record<string, string>): string {
  return flags.codemode ?? "absent";
}

/**
 * Model the session's tool allowlist (`--tools`, `--exclude-tools`): an entry is
 * an exact name or a prefix ending in `*`. Pi filters extension tools with it, so
 * a registered tool can be missing from `getAllTools()` and from every codemode
 * script. Real Pi treats `*` anywhere in an entry and also accepts `+name`/`-name`;
 * this harness models the exact-name and trailing-`*` forms the tests use.
 */
function allowlistFilter(value: string | undefined): ((name: string) => boolean) | undefined {
  if (!value) return undefined;
  const entries = value.split(",").map((entry) => entry.trim()).filter(Boolean);
  if (entries.length === 0) return undefined;
  return (name: string) =>
    entries.some((entry) => (entry.endsWith("*") ? name.startsWith(entry.slice(0, -1)) : name === entry));
}

/** Model the codemode tool so the entry's availability gate can be exercised.
 * `misdeclared` declares `reachesTools` but names nothing, and `throwing` fails
 * the call: the gate must neither read the declaration alone nor lose the turn to
 * an exception. */
function installCodemode(state: string, tools: Map<string, RegisteredTool>, active: string[]): void {
  if (state === "absent") return;
  const reaches = () => {
    if (state === "throwing") throw new Error("reachesTools is unavailable");
    return state === "misdeclared" ? [] : "all";
  };
  tools.set("codemode", {
    name: "codemode",
    description: "Write a JavaScript script that calls other tools.",
    exposure: "model-only",
    parameters: { type: "object", properties: {} },
    reachesTools: reaches,
    execute: async () => ({ content: [{ type: "text", text: "" }] }),
  });
  if (state !== "registered") active.push("codemode");
}

function agentRoot(): string {
  const agentDir = process.env.PI_CODING_AGENT_DIR;
  if (!agentDir) throw new Error("PI_CODING_AGENT_DIR is required");
  return agentDir;
}

function parseFlags(args: string[]): { positional: string[]; flags: Record<string, string> } {
  const positional: string[] = [];
  const flags: Record<string, string> = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg.startsWith("--")) {
      flags[arg.slice(2)] = args[index + 1] ?? "";
      index += 1;
    } else {
      positional.push(arg);
    }
  }
  return { positional, flags };
}

function frontmatterValue(frontmatter: string, key: string): string | undefined {
  const match = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match?.[1]?.trim().replace(/^["']|["']$/g, "");
}

function scanSkillDir(root: string, dir: string, skills: Skill[]): void {
  const directSkillFile = join(dir, "SKILL.md");
  if (existsSync(directSkillFile) && statSync(directSkillFile).isFile()) {
    try {
      const content = readFileSync(directSkillFile, "utf8");
      const frontmatter = content.split("---", 3)[1] ?? "";
      const name = frontmatterValue(frontmatter, "name");
      if (name) {
        skills.push({
          name,
          description: frontmatterValue(frontmatter, "description") ?? "",
          filePath: directSkillFile,
          baseDir: dir,
          disableModelInvocation: frontmatter.includes("disable-model-invocation: true"),
          sourceInfo: { path: root, source: "test", scope: "temporary" as const, origin: "top-level" as const },
        });
        return;
      }
    } catch {
      // ignore
    }
  }

  for (const entry of readdirSync(dir)) {
    if (entry === ".git" || entry === "node_modules") continue;
    const full = join(dir, entry);
    if (!statSync(full).isDirectory()) continue;
    scanSkillDir(root, full, skills);
  }
}

async function loadExtension(state = "absent", allowlist?: string) {
  const hooks: Record<string, Handler[]> = {};
  const commands: Record<string, unknown> = {};
  const tools = new Map<string, RegisteredTool>();
  const active: string[] = [];
  const allowed = allowlistFilter(allowlist);
  installCodemode(state, tools, active);
  /** What the session sees: registrations minus the allowlist's removals. */
  const visibleTools = () =>
    [...tools.values()]
      .filter((tool) => allowed?.(tool.name) ?? true)
      .map((tool) => ({
        name: tool.name,
        description: tool.description,
        exposure: tool.exposure,
        namespace: tool.namespace,
        parameters: tool.parameters,
        promptGuidelines: tool.promptGuidelines,
        reachesTools: tool.reachesTools,
      }));
  const exposures = () => [...tools.values()].map((tool) => ({
    name: tool.name,
    exposure: tool.exposure,
    namespaceDescription: tool.namespace?.description,
    instructions: tool.namespace?.instructions,
  }));
  const pi = {
    on(name: string, handler: Handler) {
      (hooks[name] ??= []).push(handler);
    },
    registerCommand(name: string, options: unknown) {
      commands[name] = options;
    },
    registerTool(tool: RegisteredTool) {
      tools.set(tool.name, tool);
    },
    getActiveTools: () => [...active],
    setActiveTools(names: string[]) {
      active.splice(0, active.length, ...names);
    },
    getAllTools: () => visibleTools(),
  };
  const mod = await import("../index.ts");
  mod.default(pi as never);
  return { hooks, commands, tools, active, visibleTools, pi, exposures };
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  const { positional, flags } = parseFlags(rest);
  const root = join(agentRoot(), "skill-router");
  mkdirSync(root, { recursive: true });

  const sync = await import("../src/sync");
  const { hooks, commands, tools, active, visibleTools, pi, exposures } = await loadExtension(codemodeState(flags), flags["tool-allowlist"]);

  /** Drive the entry's before_agent_start handlers exactly as a user turn does. */
  async function driveRoute(prompt: string, messageType: "user" | "custom"): Promise<HarnessResult> {
    let skillPaths: string[] = [];
    for (const handler of hooks.resources_discover ?? []) {
      const discovered = (await handler(
        { type: "resources_discover", cwd: process.cwd(), reason: "startup" } as never,
        { cwd: process.cwd() } as never,
      )) as { skillPaths?: string[] } | undefined;
      if (discovered?.skillPaths) skillPaths = [...skillPaths, ...discovered.skillPaths];
    }
    const skills: Skill[] = [];
    for (const path of skillPaths) scanSkillDir(path, path, skills);

    let systemPrompt = "base system prompt";
    const systemPromptOptions = { cwd: process.cwd(), skills, sections: { other: "retained" }, customPrompt: "base system prompt", promptGuidelines: ["existing guideline"] };
    const message: unknown = undefined;
    for (const handler of hooks.before_agent_start ?? []) {
      const handled = (await handler(
        {
          type: "before_agent_start",
          ...(messageType === "custom" ? { messageType } : { messageType, prompt }),
          images: undefined,
          systemPrompt,
          systemPromptOptions,
        } as never,
        { cwd: process.cwd(), hasUI: false } as never,
      )) as { systemPrompt?: string; message?: unknown } | undefined;
      if (handled?.systemPrompt !== undefined) throw new Error("Routing must not override the system prompt");
      if (handled?.message !== undefined) throw new Error("Routing must not inject a custom message");
    }
    const { buildSystemPrompt } = await import(process.env.PI_PROMPT_BUILDER ?? "../../../node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
    const contribution = Reflect.get(systemPromptOptions.sections, "skill_router");
    if (typeof contribution === "string") {
      for (const customPrompt of [undefined, "base system prompt"]) {
        const rendered = buildSystemPrompt({ ...systemPromptOptions, customPrompt });
        if (!rendered.includes(contribution)) throw new Error("Builder lost the routing section");
        if (customPrompt && !rendered.startsWith(customPrompt)) throw new Error("Builder lost the owner prompt");
      }
    }
    systemPrompt = contribution ? buildSystemPrompt(systemPromptOptions) : "base system prompt";
    return { ok: true, prompt, systemPrompt, sections: systemPromptOptions.sections, promptGuidelines: systemPromptOptions.promptGuidelines, message: message ?? null };
  }

  let result: HarnessResult;

  switch (command) {
    case "add": {
      const [repo] = positional;
      try {
        const added = await sync.addCollection(root, {
          repo,
          id: flags.id,
          gateway: flags.gateway,
          description: flags.description,
          skills: flags.skills ? flags.skills.split(",").filter(Boolean) : "all",
        });
        result = { ok: true, ...added };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "update": {
      try {
        const updated = await sync.updateCollection(root, positional[0]);
        result = { ok: true, ...updated };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "select": {
      try {
        const selected = await sync.updateCollectionSelection(root, positional[0], positional.slice(1));
        result = { ok: true, ...selected };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "describe": {
      try {
        const collection = await sync.updateCollectionDescription(root, positional[0], positional.slice(1).join(" "));
        result = { ok: true, description: collection.description };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "remove": {
      try {
        await sync.removeCollection(root, positional[0]);
        result = { ok: true };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "toggle": {
      try {
        const collection = await sync.setCollectionEnabled(root, positional[0], positional[1] === "on");
        result = { ok: true, enabled: collection.enabled };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "menu-add": {
      const prompts: string[] = [];
      const defaults: string[] = [];
      const confirmations: string[] = [];
      const notifications: Array<{ message: string; level: string }> = [];
      let opened = false;
      const choices = flags.skills ? [...flags.skills.split(","), "Finish selection"] : [];
      const context = {
        hasUI: false,
        model: flags.mode === "missing" ? undefined : { id: "test-model" },
        modelRegistry: {
          getApiKeyAndHeaders: async () => ({ ok: flags.mode !== "unauthenticated" }),
          complete: async (_model: unknown, context: { messages: Array<{ content: Array<{ text: string }> }> }) => {
            const prompt = context.messages[0].content[0].text;
            prompts.push(prompt);
            if (flags.mode === "error") throw new Error("Provider unavailable");
            return { stopReason: "stop", content: [{ type: "text", text: prompt.includes("array of objects") ? "[]" : flags.mode === "invalid" ? "" : "Improve software reliability through systematic diagnosis and careful code review." }] };
          },
        },
        ui: {
          select: async (title: string) => title === "Skill Router"
            ? opened ? undefined : (opened = true, "Add collection")
            : choices.shift(),
          confirm: async (title: string) => {
            confirmations.push(title);
            return !flags.skills;
          },
          input: async (title: string, value: string) => {
            if (title === "Add collection") return positional[0];
            if (title.startsWith("Collection skill name")) return value;
            defaults.push(value);
            return "";
          },
          notify: (message: string, level: string) => notifications.push({ message, level }),
        },
      };
      // Drive the registered command, so the extension's own wiring — including
      // the tools refresh the menu performs — is what runs.
      const command = commands["skill-router"] as { handler: (args: unknown, ctx: unknown) => Promise<void> };
      await command.handler(undefined, context as never);
      result = { ok: true, prompts, defaults, confirmations, notifications, registered: exposures() };
      break;
    }
    // A registry read happens again and the tools are refreshed in place, as the
    // menu does after its own mutations.
    case "refresh": {
      if (flags.remove) await sync.removeCollection(root, flags.remove);
      if (flags.disable) await sync.setCollectionEnabled(root, flags.disable, false);
      if (flags.describe) await sync.updateCollectionDescription(root, flags.describe, positional.join(" "));
      const { refreshSkillTools } = await import("../src/skills");
      refreshSkillTools(pi as never, root);
      result = { ok: true, registered: exposures() };
      break;
    }
    case "menu-registered": {
      result = { ok: true, command: "skill-router" in commands };
      break;
    }
    case "discover": {
      let skillPaths: string[] = [];
      for (const handler of hooks.resources_discover ?? []) {
        const discovered = (await handler(
          { type: "resources_discover", cwd: process.cwd(), reason: "startup" } as never,
          { cwd: process.cwd() } as never,
        )) as { skillPaths?: string[] } | undefined;
        if (discovered?.skillPaths) skillPaths = [...skillPaths, ...discovered.skillPaths];
      }
      const skills: Skill[] = [];
      for (const path of skillPaths) scanSkillDir(path, path, skills);
      result = {
        ok: true,
        skillPaths,
        skills: skills.map((skill) => ({
          name: skill.name,
          filePath: skill.filePath,
          disableModelInvocation: skill.disableModelInvocation,
        })),
      };
      break;
    }
    case "tools": {
      result = {
        ok: true,
        activeTools: [...active],
        sessionTools: visibleTools().map((tool) => tool.name),
        tools: [...tools.values()].map((tool) => ({
          name: tool.name,
          exposure: tool.exposure,
          description: tool.description,
          namespace: tool.namespace,
          parameterKeys: Object.keys(
            (tool.parameters as { properties?: Record<string, unknown> } | undefined)?.properties ?? {},
          ),
          promptGuidelines: tool.promptGuidelines ?? [],
          reachesTools: typeof tool.reachesTools === "function",
        })),
      };
      break;
    }
    case "call":
    case "call-after-remove": {
      const [name, collectionId] = positional;
      const tool = tools.get(name);
      if (!tool?.execute) {
        result = { ok: false, error: `unknown tool: ${name}` };
        break;
      }
      // A tool the allowlist removed is unreachable in a real session; refusing it
      // here keeps a test from calling what the session cannot reach.
      if (!visibleTools().some((visible) => visible.name === name)) {
        result = { ok: false, error: `tool is not in this session: ${name}` };
        break;
      }
      try {
        if (command === "call-after-remove") await sync.removeCollection(root, collectionId);
        const called = (await tool.execute("call-1", {}, undefined, undefined, {
          cwd: process.cwd(),
        })) as ToolCallResult;
        result = {
          ok: true,
          isError: called.isError === true,
          text: (called.content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "").join("\n"),
          structuredContent: called.structuredContent ?? null,
        };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "route-custom":
      result = await driveRoute(positional.join(" "), "custom");
      break;
    case "route":
      result = await driveRoute(positional.join(" "), "user");
      break;
    // A collection added while the session is live: the extension registered its
    // tools at load, so the new collection's skill tools do not exist yet.
    case "route-after-add": {
      const [repo, ...promptParts] = positional;
      const added = await sync.addCollection(root, { repo, description: flags.description, skills: "all" });
      result = {
        ...(await driveRoute(promptParts.join(" "), "user")),
        added: added.id,
        registered: [...tools.keys()],
      };
      break;
    }
    default:
      result = { ok: false, error: `unknown command: ${command}` };
  }

  console.log(JSON.stringify(result));
}

void main();

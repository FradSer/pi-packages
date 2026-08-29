import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Skill } from "@earendil-works/pi-coding-agent";

interface HarnessResult {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

type Handler = (event: never, ctx: never) => Promise<unknown> | unknown;

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

async function loadExtension() {
  const hooks: Record<string, Handler[]> = {};
  const commands: Record<string, unknown> = {};
  const pi = {
    on(name: string, handler: Handler) {
      (hooks[name] ??= []).push(handler);
    },
    registerCommand(name: string, options: unknown) {
      commands[name] = options;
    },
  };
  const mod = await import("../index.ts");
  mod.default(pi as never);
  return { hooks, commands };
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  const { positional, flags } = parseFlags(rest);
  const root = join(agentRoot(), "skill-router");
  mkdirSync(root, { recursive: true });

  const sync = await import("../src/sync");
  const { hooks, commands } = await loadExtension();

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
    case "remove": {
      try {
        sync.removeCollection(root, positional[0]);
        result = { ok: true };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
      break;
    }
    case "toggle": {
      try {
        const collection = sync.setCollectionEnabled(root, positional[0], positional[1] === "on");
        result = { ok: true, enabled: collection.enabled };
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
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
    case "route": {
      const prompt = positional.join(" ");
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
      let message: unknown;
      for (const handler of hooks.before_agent_start ?? []) {
        const handled = (await handler(
          {
            type: "before_agent_start",
            prompt,
            images: undefined,
            systemPrompt,
            systemPromptOptions: { cwd: process.cwd(), skills },
          } as never,
          { cwd: process.cwd(), hasUI: false } as never,
        )) as { systemPrompt?: string; message?: unknown } | undefined;
        if (handled?.systemPrompt !== undefined) systemPrompt = handled.systemPrompt;
        if (handled?.message !== undefined) message = handled.message;
      }
      result = { ok: true, prompt, systemPrompt, message: message ?? null };
      break;
    }
    default:
      result = { ok: false, error: `unknown command: ${command}` };
  }

  console.log(JSON.stringify(result));
}

void main();

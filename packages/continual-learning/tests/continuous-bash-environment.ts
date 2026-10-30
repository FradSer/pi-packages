/** Study-only native Bash definition. Parent learning authentication stays private. */
import {createBashToolDefinition, createReadToolDefinition, createEditToolDefinition, createWriteToolDefinition, type ExtensionAPI} from "@earendil-works/pi-coding-agent";
import {createHash} from "node:crypto";
import {lstatSync, realpathSync} from "node:fs";
import {isAbsolute, join, resolve, sep} from "node:path";
import {Type} from "typebox";

/** Initial source work is read-only. This is an explicit study tool boundary,
 * identical in both arms, not a general Bash sandbox or a learned rule. */
export function installInitialSourceBoundary(pi: ExtensionAPI, files: readonly string[]) {
  if (!files.length || new Set(files).size !== files.length || files.some(file =>
    !file || file.startsWith("/") || file.includes("\\") || file.split("/").some(part =>
      !part || part === "." || part === ".." || [".git", ".pi", ".memory", "node_modules"].includes(part)
      || part === ".env" || part.startsWith(".env.")))) throw new Error("Invalid initial source inventory");
  const paths = files.flatMap(file => [file, `/work/p-limit/${file}`]);
  const commands = ["node observed-idle-failure.mjs", "pnpm test"];
  const parameters = {
    bash: Type.Object({command: Type.String({enum: commands}), timeout: Type.Optional(Type.Number())}, {additionalProperties: false}),
    read: Type.Object({path: Type.String({enum: paths}), offset: Type.Optional(Type.Integer({minimum: 1})),
      limit: Type.Optional(Type.Integer({minimum: 1}))}, {additionalProperties: false}),
  };
  pi.on("before_provider_request", (event, ctx) => {
    if (ctx.model?.api !== "openai-completions") return;
    const request = event.payload as Record<string, unknown>;
    if (!request || !Array.isArray(request.tools)) return;
    return {...request, tools: request.tools.map(value => {
      const tool = value as {type?: string; function?: {name?: string; parameters?: Record<string, unknown>}};
      const fn = tool.function;
      if (tool.type !== "function" || !fn || !["read", "bash"].includes(fn.name ?? "")) return value;
      return {...tool, function: {...fn, parameters: fn.name === "bash" ? parameters.bash : parameters.read}};
    })};
  });
  pi.on("tool_call", event => {
    const input = event.input;
    const allowed = event.toolName === "read"
      ? "path" in input && paths.includes(String(input.path)) && Object.keys(input).every(key => ["path", "offset", "limit"].includes(key))
      : event.toolName === "bash" && "command" in input && commands.includes(String(input.command))
        && Object.keys(input).every(key => ["command", "timeout"].includes(key));
    if (allowed) return;
    pi.appendEntry("continuous-study-source-boundary", {version: 1, toolCallId: event.toolCallId,
      inputDigest: createHash("sha256").update(JSON.stringify(input)).digest("hex"), outcome: "blocked"});
    return {block: true, reason: "Initial source task permits only declared public-file reads and the two standalone verification commands. Configuration, environment discovery, other commands and writes are outside this task."};
  });
  return parameters;
}

export interface SourceTaskBoundary {
  version: 2;
  readPaths: string[];
  writePaths: string[];
  commands: string[];
}

/** Prospective source/example boundary. It does not change the historical v1
 * read-only contract and is not a shell or filesystem sandbox for example code. */
export function installSourceTaskBoundary(pi: ExtensionAPI, value: unknown, cwd = process.cwd()) {
  const validPath = (file: unknown): file is string => typeof file === "string" && !!file
    && !isAbsolute(file) && !file.includes("\\") && !/[\x00-\x1f\x7f]/u.test(file)
    && file.split("/").every(part => !!part && part !== "." && part !== ".."
      && ![".git", ".pi", ".memory", "node_modules"].includes(part)
      && part !== ".env" && !part.startsWith(".env."));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid v2 source boundary");
  const config = value as SourceTaskBoundary;
  const keys = Object.keys(config).sort();
  if (JSON.stringify(keys) !== JSON.stringify(["commands", "readPaths", "version", "writePaths"])
    || config.version !== 2 || ![config.readPaths, config.writePaths, config.commands].every(items =>
      Array.isArray(items) && items.length > 0 && new Set(items).size === items.length)
    || !config.readPaths.every(validPath) || !config.writePaths.every(validPath)
    || config.writePaths.some(file => !/^examples\/native-wrapper-v[12]\.js$/u.test(file))
    || config.commands.some(command => typeof command !== "string"
      || (command !== "pnpm test" && !config.writePaths.some(file => command === `node ${file}`)))) {
    throw new Error("Invalid v2 source boundary");
  }
  const root = resolve(cwd);
  if (!lstatSync(root).isDirectory() || lstatSync(root).isSymbolicLink() || realpathSync(root) !== root) {
    throw new Error("Source boundary root must be a real directory");
  }
  const readFiles = [...new Set([...config.readPaths, ...config.writePaths])];
  const aliases = (files: readonly string[]) => files.flatMap(file => [file, join(root, file)]);
  const readable = aliases(readFiles), writable = aliases(config.writePaths);
  const parameters = {
    read: Type.Object({path: Type.String({enum: readable}), offset: Type.Optional(Type.Integer({minimum: 1})),
      limit: Type.Optional(Type.Integer({minimum: 1}))}, {additionalProperties: false}),
    bash: Type.Object({command: Type.String({enum: config.commands}), timeout: Type.Optional(Type.Number())}, {additionalProperties: false}),
    edit: Type.Object({path: Type.String({enum: writable}), edits: Type.Array(
      Type.Object({oldText: Type.String(), newText: Type.String()}, {additionalProperties: false}), {minItems: 1})}, {additionalProperties: false}),
    write: Type.Object({path: Type.String({enum: writable}), content: Type.String()}, {additionalProperties: false}),
  };
  const safeFile = (file: string, mayCreate: boolean): boolean => {
    const target = isAbsolute(file) ? file : join(root, file);
    if (!target.startsWith(root + sep)) return false;
    const relative = target.slice(root.length + 1), parts = relative.split(sep);
    let current = root;
    try {
      if (realpathSync(root) !== root || !lstatSync(root).isDirectory()) return false;
      for (let index = 0; index < parts.length; index++) {
        current = join(current, parts[index]!);
        let status;
        try { status = lstatSync(current); }
        catch (error) {
          if (mayCreate && (error as NodeJS.ErrnoException).code === "ENOENT") return true;
          return false;
        }
        if (status.isSymbolicLink() || (index === parts.length - 1 ? !status.isFile() : !status.isDirectory())) return false;
      }
      return true;
    } catch { return false; }
  };
  pi.on("before_provider_request", (event, ctx) => {
    const responses = ctx.model?.api === "openai-responses";
    if (!responses && ctx.model?.api !== "openai-completions") return;
    const request = event.payload as Record<string, unknown>;
    if (!request || !Array.isArray(request.tools)) return;
    return {...request, tools: request.tools.map(value => {
      if (!value || typeof value !== "object") return value;
      const tool = value as Record<string, unknown>;
      const fn = (responses ? tool : tool.function) as Record<string, unknown> | undefined;
      if (tool.type !== "function" || !fn || !Object.hasOwn(parameters, String(fn.name))) return value;
      const schema = parameters[fn.name as keyof typeof parameters];
      return responses ? {...tool, parameters: schema} : {...tool, function: {...fn, parameters: schema}};
    })};
  });
  pi.on("tool_call", event => {
    const input = event.input as Record<string, unknown>;
    const exactKeys = (required: string[], optional: string[] = []) => required.every(key => Object.hasOwn(input, key))
      && Object.keys(input).every(key => [...required, ...optional].includes(key));
    const path = typeof input.path === "string" ? input.path : "";
    const positive = (field: string) => input[field] === undefined || (Number.isInteger(input[field]) && Number(input[field]) >= 1);
    let allowed = false;
    if (event.toolName === "read") allowed = exactKeys(["path"], ["offset", "limit"])
      && readable.includes(path) && positive("offset") && positive("limit") && safeFile(path, false);
    if (event.toolName === "write") allowed = exactKeys(["path", "content"])
      && writable.includes(path) && typeof input.content === "string" && safeFile(path, true);
    if (event.toolName === "edit") allowed = exactKeys(["path", "edits"])
      && writable.includes(path) && Array.isArray(input.edits) && input.edits.length > 0
      && input.edits.every(edit => edit && typeof edit === "object" && !Array.isArray(edit)
        && Object.keys(edit).length === 2 && typeof edit.oldText === "string" && typeof edit.newText === "string")
      && safeFile(path, false);
    if (event.toolName === "bash") allowed = exactKeys(["command"], ["timeout"])
      && typeof input.command === "string" && config.commands.includes(input.command)
      && (input.timeout === undefined || (typeof input.timeout === "number" && Number.isFinite(input.timeout)))
      && (input.command === "pnpm test" || safeFile(input.command.slice("node ".length), false));
    if (allowed) return;
    pi.appendEntry("continuous-study-source-boundary", {version: 2, toolCallId: event.toolCallId,
      inputDigest: createHash("sha256").update(JSON.stringify(input)).digest("hex"), outcome: "blocked"});
    return {block: true, reason: "Source v2 permits only declared public-file reads, exact example writes/edits, and declared standalone verification commands. Other files, symlinks, metadata discovery and shell commands are outside this task."};
  });
  return parameters;
}

export default function studyBashEnvironment(pi: ExtensionAPI): void {
  const bash = createBashToolDefinition(process.cwd(), {
    spawnHook: context => {
      const env = {...context.env};
      delete env.TYPESAFE_API_KEY;
      return {...context, env};
    },
  });
  if (process.env.PI_STUDY_SOURCE_TASK_BOUNDARY !== undefined) {
    if (process.env.PI_STUDY_INITIAL_SOURCE_FILES !== undefined) throw new Error("Ambiguous source boundary versions");
    const parameters = installSourceTaskBoundary(pi, JSON.parse(process.env.PI_STUDY_SOURCE_TASK_BOUNDARY));
    pi.registerTool({...createReadToolDefinition(process.cwd()), parameters: parameters.read,
      description: "Read a declared public project file or the exact declared source-task example.",
      promptSnippet: "Read declared public source and example files.", promptGuidelines: []});
    pi.registerTool({...bash, parameters: parameters.bash,
      description: "Run only the exact standalone verification commands listed in this source task's parameters.",
      promptSnippet: "Run declared source-task verification commands.", promptGuidelines: []});
    pi.registerTool({...createEditToolDefinition(process.cwd()), parameters: parameters.edit,
      description: "Edit only the exact declared source-task example file with an exact text replacement.",
      promptSnippet: "Edit the declared source-task example.", promptGuidelines: []});
    pi.registerTool({...createWriteToolDefinition(process.cwd()), parameters: parameters.write,
      description: "Create or replace only the exact declared source-task example file.",
      promptSnippet: "Write the declared source-task example.", promptGuidelines: []});
  } else if (process.env.PI_STUDY_INITIAL_SOURCE_FILES !== undefined) {
    const files: unknown = JSON.parse(process.env.PI_STUDY_INITIAL_SOURCE_FILES);
    if (!Array.isArray(files) || files.some(file => typeof file !== "string")) throw new Error("Invalid initial source inventory");
    const parameters = installInitialSourceBoundary(pi, files);
    // Keep native tool context and provider schemas consistent. The final wire
    // guard alone cannot replace the broad definitions stored in Pi's context.
    pi.registerTool({...createReadToolDefinition(process.cwd()), parameters: parameters.read,
      description: "Read a declared public project file using an exact path listed in this tool's parameters.",
      promptSnippet: "Read declared public project files.", promptGuidelines: []});
    pi.registerTool({...bash, parameters: parameters.bash,
      description: "Run the declared standalone verification commands: node observed-idle-failure.mjs or pnpm test. General shell execution is unavailable for this initial source task.",
      promptSnippet: "Run the two declared source verification commands.", promptGuidelines: []});
  } else {
    pi.registerTool(bash);
  }
}

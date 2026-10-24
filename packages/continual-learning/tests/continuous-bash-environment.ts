/** Study-only native Bash definition. Parent learning authentication stays private. */
import {createBashToolDefinition, createReadToolDefinition, type ExtensionAPI} from "@earendil-works/pi-coding-agent";
import {createHash} from "node:crypto";
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

export default function studyBashEnvironment(pi: ExtensionAPI): void {
  const bash = createBashToolDefinition(process.cwd(), {
    spawnHook: context => {
      const env = {...context.env};
      delete env.TYPESAFE_API_KEY;
      return {...context, env};
    },
  });
  if (process.env.PI_STUDY_INITIAL_SOURCE_FILES !== undefined) {
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

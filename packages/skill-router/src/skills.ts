/**
 * The tools channel: one codemode-callable tool per routed leaf skill.
 *
 * A leaf skill is prose, so the tool exists to be found and called: its name and
 * description are the skill's searchable identity, its namespace is the
 * collection, and its call returns the wrapped instructions with the directory
 * that resolves the skill's references and scripts.
 *
 * Registration reads the registry once, at extension load. A call re-resolves the
 * collection, so a tool whose collection was removed fails instead of serving a
 * path captured at registration. Nothing here activates codemode: a session that
 * does not declare it keeps the routing-suggestion fallback.
 */

import { closeSync, constants, fstatSync, lstatSync, openSync, readFileSync, realpathSync, type Stats } from "node:fs";
import { join, sep } from "node:path";
import { Type, type Static } from "typebox";
import { defineTool, keyHint, type AgentToolResult, type ExtensionAPI, type ToolNamespace } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, emptyToolCall } from "@fradser/pi-kit";
import { cacheDir, collectionNamespaceName, exposedCollectionsDir, gatewayDir, leafSkillDir, leafSkillFile, skillToolName } from "./paths";
import { loadCollections, type RegistryCollection, type RegistryRoute } from "./registry";
import { scanSkills } from "./sync";

/** Instructions one call returns. A longer file is cut at this bound, and the
 * returned body names the file that keeps all of it. */
const MAX_SKILL_BODY_CHARS = 20000;

const TOOL_TAG = "skill-router";
const CODEMODE_TOOL_NAME = "codemode";
/** `O_NOFOLLOW` is absent on platforms that cannot express it, where it contributes nothing. */
const NO_FOLLOW = constants.O_NOFOLLOW ?? 0;

const SKILL_TOOL_PARAMS = Type.Object({}, { additionalProperties: false });

const SKILL_TOOL_OUTPUT = Type.Object({
  ok: Type.Boolean(),
  collection: Type.String(),
  skill: Type.String(),
  tool: Type.String(),
  directory: Type.Optional(Type.String()),
  skillFile: Type.Optional(Type.String()),
  body: Type.Optional(Type.String()),
  truncated: Type.Optional(Type.Boolean()),
  error: Type.Optional(Type.String()),
}, { additionalProperties: false });

type SkillToolOutput = Static<typeof SKILL_TOOL_OUTPUT>;

/** What the transcript row reads back from a completed call. */
interface SkillToolDetails {
  subject?: string;
  summary?: string;
  label?: string;
  details?: readonly string[];
  tone?: "success" | "warning" | "error";
}

type SkillToolResult = AgentToolResult<SkillToolDetails> & { structuredContent: SkillToolOutput };

/** A script that searches: `reachesTools` must answer it for every tool a script
 * can call, so what it names is what the session can actually reach. */
const DISCOVERY_SCRIPT = { code: "await searchTools('')" };

/** Whether one skill's tool is reachable from a codemode script: codemode is
 * active, answers a discovery script by naming that exact tool, and the tool
 * survived the session's tool allowlist. A session allowlist (`--tools`,
 * `--exclude-tools`) filters an extension tool out of the registry entirely, so
 * codemode can be active while every call fails. The check is per skill, not per
 * collection: a surviving sibling tool must not stand in for the one the prompt
 * matched, and a collection added after load has no tool at all until a refresh.
 *
 * A `codemode` that declares `reachesTools` but names nothing keeps the fallback:
 * Pi's contract lets it answer per script, and the suggestion is then the only
 * working path. */
export function codemodeReachesSkillTool(
  pi: Pick<ExtensionAPI, "getActiveTools" | "getAllTools">,
  toolName: string,
): boolean {
  if (!pi.getActiveTools().includes(CODEMODE_TOOL_NAME)) return false;
  const tools = pi.getAllTools();
  const codemode = tools.find((tool) => tool.name === CODEMODE_TOOL_NAME);
  if (typeof codemode?.reachesTools !== "function") return false;
  if (!tools.some((tool) => tool.name === toolName)) return false;
  // A word refers to every tool or namespace whose name contains it.
  let reach: "all" | readonly string[] | undefined;
  try {
    reach = codemode.reachesTools(DISCOVERY_SCRIPT);
  } catch {
    // A `codemode` that cannot answer keeps the fallback: this is the conservative
    // direction, and an exception must not cost the turn its only working path.
    return false;
  }
  return reach === "all" || (Array.isArray(reach) && reach.some((word) => typeof word === "string" && toolName.includes(word)));
}

/** Skill tools one loaded extension instance has registered. Pi cannot
 * unregister a tool, so a refresh withdraws the names a registry change removed
 * by re-registering them hidden. */
const registeredSkillTools = new WeakMap<ExtensionAPI, string[]>();

/** Register every routed leaf skill of every enabled collection, and withdraw the
 * tools of a collection that is gone or disabled since the last refresh. The
 * extension calls this when it loads and after every `/skill-router` mutation, so
 * the tools channel follows the registry without a reload. */
export function refreshSkillTools(pi: ExtensionAPI, root: string): void {
  const names = new Set<string>();
  const definitions = loadCollections(root)
    .filter((collection) => collection.enabled)
    .flatMap((collection) => {
      const namespace = collectionNamespace(root, collection);
      const upstream = upstreamDescriptions(root, collection);
      return collection.routes.map((route) => {
        const tool = skillTool(root, collection, route, searchableSkillText(route, upstream.get(route.skill) ?? ""), namespace);
        names.add(tool.name);
        return tool;
      });
    });

  for (const tool of definitions) pi.registerTool(tool);
  for (const name of registeredSkillTools.get(pi) ?? []) {
    if (!names.has(name)) pi.registerTool(withdrawnSkillTool(name));
  }
  registeredSkillTools.set(pi, [...names]);
}

/** A withdrawn skill tool: unreachable, and kept only because Pi cannot
 * unregister a name. */
function withdrawnSkillTool(name: string) {
  return defineTool<typeof SKILL_TOOL_PARAMS, SkillToolDetails>({
    name,
    label: name,
    description: "Withdrawn skill tool.",
    parameters: SKILL_TOOL_PARAMS,
    outputSchema: SKILL_TOOL_OUTPUT,
    exposure: "hidden",
    renderShell: "self",
    renderCall: () => emptyToolCall(),
    renderResult: skillResultBand,
    async execute(): Promise<SkillToolResult> {
      return refuse(name, "", "", `Skill tool "${name}" is withdrawn: its collection is no longer routed.`);
    },
  });
}

/** Read a regular file, refusing a symlink that appears after the caller's own
 * checks and before this open. */
function readRegularFile(path: string, validated: Stats): string {
  const descriptor = openSync(path, constants.O_RDONLY | NO_FOLLOW);
  try {
    const opened = fstatSync(descriptor);
    if (!opened.isFile()) throw new Error(`Not a regular file: ${path}`);
    // The descriptor must be the very file that was validated: a directory swapped
    // between the checks and this open would otherwise redirect the read.
    if (opened.dev !== validated.dev || opened.ino !== validated.ino) {
      throw new Error(`File changed between validation and read: ${path}`);
    }
    return readFileSync(descriptor, "utf8");
  } finally {
    closeSync(descriptor);
  }
}

/** The searchable text of one route: the workflow summary and the skill author's
 * own description, without repeating one inside the other. The summary judges
 * relevance; the upstream description carries the words a request uses. */
function searchableSkillText(route: RegistryRoute, upstreamDescription: string): string {
  const oneLine = (value: string) => value.replace(/\s+/g, " ").trim();
  const summary = oneLine(route.summary ?? "");
  const upstream = oneLine(upstreamDescription);
  if (!upstream || upstream.startsWith(summary.replace(/\.$/, ""))) return upstream || summary;
  return summary ? `${summary} ${upstream}` : upstream;
}

/** One namespace per collection: its capability summary and gateway index answer
 * "what is in this collection" through one lookup. */
function collectionNamespace(root: string, collection: RegistryCollection): ToolNamespace {
  const gateway = managedFile(root, join(gatewayDir(root, collection.id, collection.gateway), "SKILL.md"));
  return {
    name: collectionNamespaceName(collection.id),
    aliases: [collection.id],
    description: collection.description,
    ...(gateway === undefined ? {} : { instructions: gateway }),
  };
}

/** Upstream descriptions by skill name, from the collection's clone. A missing or
 * unreadable clone leaves the workflow summaries as the searchable text. */
function upstreamDescriptions(root: string, collection: RegistryCollection): Map<string, string> {
  try {
    const skills = scanSkills(cacheDir(root, collection.source.cacheKey));
    return new Map(skills.map((skill) => [skill.name, skill.description]));
  } catch {
    return new Map();
  }
}

function skillTool(
  root: string,
  collection: RegistryCollection,
  route: RegistryRoute,
  searchable: string,
  namespace: ToolNamespace,
) {
  const name = skillToolName(collection.id, route.skill);
  const subject = `${collection.id}/${route.skill}`;
  return defineTool<typeof SKILL_TOOL_PARAMS, SkillToolDetails>({
    name,
    label: route.skill,
    description: searchable,
    promptGuidelines: [
      `Loads the \`${route.skill}\` workflow of the \`${collection.id}\` skill collection. Follow the returned instructions and use the returned directory for its files.`,
      "Call the workflow these instructions load; do not act on the collection's other workflows.",
    ],
    parameters: SKILL_TOOL_PARAMS,
    outputSchema: SKILL_TOOL_OUTPUT,
    exposure: "codemode",
    namespace,
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    renderShell: "self",
    renderCall: () => emptyToolCall(),
    renderResult: skillResultBand,
    async execute(_toolCallId, _params, signal): Promise<SkillToolResult> {
      signal?.throwIfAborted();
      const current = loadCollections(root).find((entry) => entry.id === collection.id && entry.enabled);
      const currentRoute = current?.routes.find((candidate) => candidate.skill === route.skill);
      if (!current || !currentRoute) {
        return refuse(
          name,
          collection.id,
          route.skill,
          `Collection "${collection.id}" is no longer installed and enabled, so "${route.skill}" is unavailable. Run /reload after changing collections.`,
        );
      }
      try {
        const leaf = readLeafSkill(root, current, currentRoute);
        const { body, truncated } = boundSkillBody(leaf.content, leaf.skillFile);
        return {
          content: [{ type: "text", text: body }],
          details: {
            subject,
            label: "loaded",
            details: [leaf.skillFile],
            ...(truncated ? { summary: `The body is cut at ${MAX_SKILL_BODY_CHARS} characters; the file above holds all of it.` } : {}),
          },
          structuredContent: {
            ok: true,
            collection: collection.id,
            skill: route.skill,
            tool: name,
            directory: leaf.directory,
            skillFile: leaf.skillFile,
            body,
            truncated,
          },
        };
      } catch (error) {
        return refuse(name, collection.id, route.skill, error instanceof Error ? error.message : String(error));
      }
    },
  });
}

function refuse(tool: string, collection: string, skill: string, error: string): SkillToolResult {
  return {
    content: [{ type: "text", text: `REFUSED · ${error}` }],
    details: { subject: `${collection}/${skill}`, label: "refused", summary: error, tone: "error" },
    structuredContent: { ok: false, collection, skill, tool, error },
    isError: true,
  };
}

interface LeafSkill {
  directory: string;
  skillFile: string;
  content: string;
}

/** Read one materialized leaf skill, refusing anything that is not a regular file
 * inside the router's exposed collection tree. Containment is anchored on the
 * router root, because a symlinked `exposed` would otherwise move the base that
 * the leaf's own resolution is compared against. */
function readLeafSkill(root: string, collection: RegistryCollection, route: RegistryRoute): LeafSkill {
  const exposedTree = join(root, "exposed");
  const exposed = exposedCollectionsDir(root);
  if (!isRealDirectory(exposedTree) || !isRealDirectory(exposed)) {
    throw new Error(`Skill Router's exposed collections are unavailable at ${exposed}`);
  }
  const directory = leafSkillDir(root, collection.id, route.skill);
  if (!isRealDirectory(directory)) {
    throw new Error(`Skill "${route.skill}" of collection "${collection.id}" is not materialized at ${directory}`);
  }
  const skillFile = leafSkillFile(root, collection.id, route.skill);
  let stats: Stats;
  try {
    stats = lstatSync(skillFile);
  } catch {
    throw new Error(`Skill "${route.skill}" of collection "${collection.id}" has no instruction file at ${skillFile}`);
  }
  if (!stats.isFile()) {
    throw new Error(`Skill "${route.skill}" of collection "${collection.id}" has an unusable instruction file at ${skillFile}`);
  }
  const resolved = realpathSync(skillFile);
  if (!resolved.startsWith(realpathSync(exposed) + sep) || !resolved.startsWith(realpathSync(root) + sep)) {
    throw new Error(`Skill "${route.skill}" of collection "${collection.id}" resolves outside the exposed collections`);
  }
  return { directory, skillFile, content: readRegularFile(skillFile, stats) };
}

/** Cut a body at the bound and name the file that keeps the rest. */
function boundSkillBody(content: string, skillFile: string): { body: string; truncated: boolean } {
  if (content.length <= MAX_SKILL_BODY_CHARS) return { body: content, truncated: false };
  let end = MAX_SKILL_BODY_CHARS;
  // Never split a UTF-16 surrogate pair at the cut.
  if (/[\uD800-\uDBFF]/.test(content[end - 1] ?? "")) end -= 1;
  const omitted = content.length - end;
  return { body: `${content.slice(0, end)}\n\n…${omitted} chars truncated…\nComplete instructions: ${skillFile}`, truncated: true };
}

function isRealDirectory(path: string): boolean {
  try {
    const stats = lstatSync(path);
    return stats.isDirectory() && !stats.isSymbolicLink();
  } catch {
    return false;
  }
}

/** Read a managed file only when it is a regular file inside the router root. */
function managedFile(root: string, path: string): string | undefined {
  try {
    const stats = lstatSync(path);
    if (!stats.isFile()) return undefined;
    if (!realpathSync(path).startsWith(realpathSync(root) + sep)) return undefined;
    return readRegularFile(path, stats);
  } catch {
    return undefined;
  }
}

/** One lifecycle geometry for every skill row, owned by pi-kit. */
const rows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

const skillResultBand = rows.result<AgentToolResult<SkillToolDetails>>((value) => {
  const details = (value.details ?? {}) as SkillToolDetails;
  return {
    tool: TOOL_TAG,
    kind: "event" as const,
    label: details.label,
    subject: details.subject ?? "",
    ...(details.summary ? { summary: [details.summary] } : {}),
    ...(details.details ? { details: details.details } : {}),
    ...(details.tone ? { tone: details.tone } : {}),
  };
});
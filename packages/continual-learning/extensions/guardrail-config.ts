/** Built-in defaults < user shared < user scoped to this project < project
 *  shared < project personal flat rules. */
import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { DEFAULT_RULES, mergeLayers, validateRuleContainer } from "./guardrail-engine.ts";
import { escapedProjectPath } from "./memory-paths.ts";
import type { ResolvedHarnessConfig, RuleLayer } from "./guardrail-types.ts";

export interface ConfigPaths {
  /** Personal rules for every project. */
  user: string;
  /** Personal rules for one project, named by the same scope key Memory uses. */
  userScoped: string;
  project: string;
  projectLocal: string;
}
export interface ResolvedHarnessConfigWithPaths { config: ResolvedHarnessConfig; paths: ConfigPaths }

/**
 * Where a project's personal Harness configuration lives.
 *
 * Memory already scopes private state per canonical project path, so rules
 * authored for one project cannot silently govern another. The user layer is
 * scoped the same way, in a directory parallel to `memory/` rather than inside
 * it: a Memory root admits only regular `.md` children, so placing a JSON
 * configuration there fails consolidation's privacy validation and aborts the
 * run. The same escaped-canonical-path key is reused so the two are easy to
 * correlate, and the global file is kept as the lowest user layer so a
 * cross-project rule still applies everywhere.
 */
function scopedUserConfigPath(agentDir: string, cwd: string): string {
  return path.join(agentDir, "harness", `${escapedProjectPath(cwd)}.json`);
}

export function configPaths(cwd: string, agentDir?: string): ConfigPaths {
  const root = agentDir ?? getAgentDir();
  return {
    user: path.join(root, "harness.json"),
    userScoped: scopedUserConfigPath(root, cwd),
    project: path.join(cwd, ".pi", "harness.json"),
    projectLocal: path.join(cwd, ".pi", "harness.local.json"),
  };
}

export function assertHarnessConfigContainers(value: unknown): asserts value is Record<string, unknown> {
  const errors = validateRuleContainer(value);
  if (errors.length) throw new Error(errors.join("; "));
}

/** Snapshots retain raw declarations in both formats, including invalid and
 * disabled identities, so stale fallback cannot revive an older definition. */
const snapshots = new Map<string, RuleLayer>();

function staleFallback(source: string, file: string, reason: string): RuleLayer {
  const snapshot = snapshots.get(file);
  return {
    ...snapshot,
    source, stale: true, unavailable: !snapshot,
    errors: [`${reason}${snapshot ? " (using previous valid snapshot; current file not verified)" : " (no previous valid snapshot; layer unavailable)"}`],
  };
}

function readLayer(source: string, file: string): RuleLayer | undefined {
  let raw: string;
  try { raw = fs.readFileSync(file, "utf8"); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") { snapshots.delete(file); return undefined; }
    return staleFallback(source, file, `could not read harness file: ${(error as Error).message}`);
  }
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch (error) { return staleFallback(source, file, `invalid JSON: ${(error as Error).message}`); }
  try { assertHarnessConfigContainers(parsed); }
  catch (error) { return staleFallback(source, file, (error as Error).message); }
  const layer: RuleLayer = { ...parsed, source } as RuleLayer;
  snapshots.set(file, layer);
  return layer;
}

export function loadLayers(cwd: string, agentDir?: string): RuleLayer[] {
  const paths = configPaths(cwd, agentDir);
  // Nearest wins: project personal, then project shared, then this project's
  // personal user layer, then the all-projects user layer, then built-ins.
  return ([
    ['user', paths.user],
    ['user.scoped', paths.userScoped],
    ['project', paths.project],
    ['project.local', paths.projectLocal],
  ] as const)
    .flatMap(([source, file]) => { const layer = readLayer(source, file); return layer ? [layer] : []; });
}

/** Read current bytes on each resolution. A stat-only cache cannot establish
 * that a same-size/same-mtime edit or newly unreadable layer is unchanged. */
export function resolveHarnessConfig(cwd: string, agentDir?: string, availableSkills?: ReadonlySet<string>): ResolvedHarnessConfigWithPaths {
  return {
    config: mergeLayers([{ source: "built-in defaults", rules: DEFAULT_RULES as unknown as Array<Record<string, unknown>> }, ...loadLayers(cwd, agentDir)], availableSkills),
    paths: configPaths(cwd, agentDir),
  };
}

/** Explicit copy-only migration. Discovery/startup never call this module.
 * A plan binds one selected identity to complete source bytes and destinations;
 * apply rebuilds it before writes. Originals and legacy Git workspaces stay put.
 */
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { parseAgentDefinition, type AgentScope } from "./agents.ts";
import { assertAgentName, assertAgentStoragePath } from "./workspace.ts";

type DiskScope = Exclude<AgentScope, "session">;
export interface AgentMigrationOptions {
  agentName: string;
  scope: DiskScope;
  cwd: string;
  /** Ordinary legacy scratch project slugs explicitly selected for copying. */
  workspaceProjects?: string[];
}
export interface AgentMigrationFile {
  kind: "definition" | "memory" | "session" | "workspace";
  source: string;
  destination: string;
  sourceSha256: string;
  targetSha256: string;
}
export interface AgentMigrationBlock {
  kind: "conflict" | "unsafe" | "manual" | "invalid";
  message: string;
}
export interface AgentMigrationPlan {
  version: 1;
  agentName: string;
  scope: DiskScope;
  cwd: string;
  agentDir: string;
  workspaceProjects: string[];
  status: "ready" | "blocked";
  files: AgentMigrationFile[];
  blocked: AgentMigrationBlock[];
}
export interface AgentMigrationOutcome {
  status: "dry-run" | "applied";
  copied: string[];
}
const hash = (bytes: Buffer): string => createHash("sha256").update(bytes).digest("hex");
const allowedFields = new Set(["name", "description", "tools", "model", "verify"]);

function canonicalDefinition(bytes: Buffer, name: string, scope: DiskScope): Buffer {
  const raw = bytes.toString("utf8");
  if (!Buffer.from(raw, "utf8").equals(bytes)) throw new Error("Legacy definition cannot round-trip losslessly through UTF-8.");
  const match = /^---(\r?\n)([\s\S]*?)(\r?\n)---(\r?\n|$)/.exec(raw);
  if (!match) throw new Error("Legacy identity has no valid definition frontmatter.");
  // Retain each line's own terminator, including mixed LF/CRLF headers. Keys
  // follow the runtime parser's trimming, not YAML's stricter colon spacing.
  const lines = (match[2] + match[3]).match(/[^\n]*\n/g) ?? [];
  const kept: string[] = [];
  const seen = new Set<string>();
  let include = false;
  for (const line of lines) {
    const key = /^[ \t]*([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:/.exec(line);
    if (key) {
      if (seen.has(key[1])) throw new Error(`Unsupported duplicate legacy frontmatter field: ${key[1]}.`);
      seen.add(key[1]);
      include = allowedFields.has(key[1]);
    } else if (line.includes(":") && !/^\s*(?:#|-)/.test(line)) {
      throw new Error("Unsupported legacy frontmatter field syntax.");
    }
    if (include) kept.push(line);
  }
  // Missing legacy defaults are the only semantic additions. Check both
  // documents with the actual parser so filtering cannot silently alter a role.
  const defaults = [
    ...(!seen.has("description") ? [`description: ${match[1]}`] : []),
    ...(!seen.has("tools") ? [`tools: ${match[1]}`] : []),
  ].join("");
  const prefix = `---${match[1]}`;
  const suffix = `---${match[4]}` + raw.slice(match[0].length);
  // Prefix defaults only in the comparison document: appending them could
  // change how the runtime parser treats an authored final CRLF/comment line.
  const original = prefix + defaults + lines.join("") + suffix;
  const canonical = prefix + kept.join("") + defaults + suffix;
  if (JSON.stringify(parseAgentDefinition(original, name, scope)) !== JSON.stringify(parseAgentDefinition(canonical, name, scope))) {
    throw new Error("Legacy definition filtering would change supported field or body semantics.");
  }
  return Buffer.from(canonical, "utf8");
}

function exists(candidate: string): boolean {
  try { fs.lstatSync(candidate); return true; } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}
function directory(root: string, candidate: string): boolean {
  assertAgentStoragePath(root, candidate);
  if (!exists(candidate)) return false;
  if (!fs.lstatSync(candidate).isDirectory()) throw new Error(`Expected a migration source directory: ${candidate}`);
  return true;
}

/** Read-only inventory. Blocked diagnostics name paths, never private bodies. */
export function planAgentMigration(options: AgentMigrationOptions): AgentMigrationPlan {
  assertAgentName(options.agentName);
  if (!["user", "project", "project-local"].includes(options.scope)) throw new Error("Invalid migration definition scope.");
  const workspaceProjects = [...(options.workspaceProjects ?? [])].sort();
  if (new Set(workspaceProjects).size !== workspaceProjects.length
    || workspaceProjects.some(slug => !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(slug))) {
    throw new Error("Workspace project selections must be distinct single directory names.");
  }
  const agentDir = path.resolve(getAgentDir());
  const cwd = path.resolve(options.cwd);
  const home = path.join(agentDir, "agents", options.agentName);
  const definitionRoot = options.scope === "user" ? agentDir : cwd;
  const library = options.scope === "user" ? path.join(agentDir, "agents") : path.join(cwd, ".pi", "agents");
  const localSuffix = options.scope === "project-local" ? ".local" : "";
  const expectedSource = path.join(library, `${options.agentName}${localSuffix}.md`);
  const definitionTarget = path.join(library, `${options.agentName}${localSuffix}`, "agent.md");
  const plan: AgentMigrationPlan = { version: 1, agentName: options.agentName, scope: options.scope,
    cwd, agentDir, workspaceProjects, status: "ready", files: [], blocked: [] };
  const block = (kind: AgentMigrationBlock["kind"], message: string, fatal = true): void => {
    plan.blocked.push({ kind, message });
    if (fatal) plan.status = "blocked";
  };
  const guard = (action: () => void): void => {
    try { action(); } catch (error) { block("unsafe", error instanceof Error ? error.message : String(error)); }
  };
  const add = (kind: AgentMigrationFile["kind"], source: string, destination: string,
    sourceRoot: string, targetRoot: string): void => {
    assertAgentStoragePath(sourceRoot, source);
    assertAgentStoragePath(targetRoot, destination);
    const sourceStat = fs.lstatSync(source);
    if (!sourceStat.isFile() || sourceStat.nlink !== 1) {
      throw new Error(`Refusing linked or non-regular migration source: ${source}`);
    }
    const bytes = fs.readFileSync(source);
    let target: Buffer = bytes;
    if (kind === "definition") {
      try { target = canonicalDefinition(bytes, options.agentName, options.scope); } catch (error) {
        block("invalid", `${error instanceof Error ? error.message : "Invalid legacy definition."} Source: ${source}`);
        return;
      }
    }
    if (kind === "definition" && !parseAgentDefinition(target.toString("utf8"), options.agentName, options.scope)) {
      block("invalid", `Invalid or mismatched legacy definition: ${source}`);
      return;
    }
    if (exists(destination)) { block("conflict", `Migration destination already exists: ${destination}`); return; }
    if (plan.files.some(file => file.destination === destination)) {
      block("conflict", `Multiple migration sources target: ${destination}`); return;
    }
    plan.files.push({ kind, source, destination, sourceSha256: hash(bytes), targetSha256: hash(target) });
  };
  const walk = (kind: AgentMigrationFile["kind"], source: string, destination: string): void => {
    assertAgentStoragePath(agentDir, source);
    if (!exists(source)) return;
    const stat = fs.lstatSync(source);
    if (stat.isFile()) { add(kind, source, destination, agentDir, agentDir); return; }
    if (!stat.isDirectory()) throw new Error(`Unsupported migration source: ${source}`);
    for (const entry of fs.readdirSync(source).sort()) walk(kind, path.join(source, entry), path.join(destination, entry));
  };

  guard(() => {
    if (!directory(definitionRoot, library)) { block("invalid", `Legacy definition library is absent: ${library}`); return; }
    // Bind the filename and frontmatter identity; reject ambiguous same-scope
    // aliases rather than deciding which role the user intended to save.
    const candidates: string[] = [];
    for (const entry of fs.readdirSync(library, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (!entry.name.endsWith(".md")) continue;
      const isLocal = entry.name.endsWith(".local.md");
      if (isLocal !== (options.scope === "project-local")) continue;
      const source = path.join(library, entry.name);
      assertAgentStoragePath(definitionRoot, source);
      if (!entry.isFile()) continue;
      const bytes = fs.readFileSync(source);
      let normalized: Buffer;
      try { normalized = canonicalDefinition(bytes, options.agentName, options.scope); } catch (error) {
        if (source === expectedSource || parseAgentDefinition(bytes.toString("utf8"), options.agentName, options.scope)) {
          block("invalid", `${error instanceof Error ? error.message : "Invalid legacy definition."} Source: ${source}`);
        }
        continue;
      }
      if (parseAgentDefinition(normalized.toString("utf8"), options.agentName, options.scope)) candidates.push(source);
    }
    if (candidates.length !== 1 || candidates[0] !== expectedSource) {
      block(candidates.length > 1 ? "conflict" : "invalid", `Legacy identity must have one matching source at ${expectedSource}.`);
      return;
    }
    add("definition", expectedSource, definitionTarget, definitionRoot, definitionRoot);
  });
  guard(() => {
    if (!directory(agentDir, home)) return;
    for (const entry of fs.readdirSync(home, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const source = path.join(home, entry.name);
      if (entry.name.endsWith(".md") && entry.name !== "agent.md") {
        add("memory", source, path.join(home, "memory", entry.name), agentDir, agentDir);
      } else if (entry.name === "proposals") walk("memory", source, path.join(home, "memory", "proposals"));
    }
  });
  guard(() => {
    const sessions = path.join(agentDir, "subagent-sessions", options.agentName);
    if (!directory(agentDir, sessions)) return;
    for (const project of fs.readdirSync(sessions).sort()) {
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(project)) throw new Error(`Invalid legacy project directory: ${project}`);
      walk("session", path.join(sessions, project), path.join(home, "projects", project, "session"));
    }
  });
  guard(() => {
    const workspaces = path.join(agentDir, "workspaces", options.agentName);
    if (!directory(agentDir, workspaces)) {
      if (workspaceProjects.length) block("invalid", `Selected legacy workspace root is absent: ${workspaces}`);
      return;
    }
    const present = fs.readdirSync(workspaces).sort();
    for (const project of present) {
      const source = path.join(workspaces, project);
      if (!directory(agentDir, source)) continue;
      if (exists(path.join(source, ".git"))) {
        block("manual", `Legacy workspace contains .git and requires manual handling: ${source}`, workspaceProjects.includes(project));
      } else if (workspaceProjects.includes(project)) walk("workspace", source, path.join(home, "workspace", project));
    }
    for (const project of workspaceProjects) if (!present.includes(project)) block("invalid", `Selected legacy workspace is absent: ${project}`);
  });
  plan.files.sort((a, b) => a.destination.localeCompare(b.destination));
  return plan;
}

/** Explicit approval is the caller's responsibility. A blocked, stale or edited
 * plan grants nothing. Exclusive writes preserve existing destinations; source
 * bytes are fully read/revalidated before the first destination is created.
 */
export function applyAgentMigration(plan: AgentMigrationPlan, options: { dryRun?: boolean } = {}): AgentMigrationOutcome {
  const rebuilt = planAgentMigration({ agentName: plan.agentName, scope: plan.scope, cwd: plan.cwd,
    workspaceProjects: plan.workspaceProjects });
  if (plan.status !== "ready" || rebuilt.status !== "ready") throw new Error("Migration is blocked; originals were preserved.");
  if (JSON.stringify(rebuilt) !== JSON.stringify(plan)) throw new Error("Migration plan is stale or was altered; no files copied.");
  if (options.dryRun) return { status: "dry-run", copied: [] };
  const content = plan.files.map(file => {
    const sourceRoot = file.kind === "definition" && plan.scope !== "user" ? plan.cwd : plan.agentDir;
    assertAgentStoragePath(sourceRoot, file.source);
    const bytes = fs.readFileSync(file.source);
    const target = file.kind === "definition" ? canonicalDefinition(bytes, plan.agentName, plan.scope) : bytes;
    if (hash(bytes) !== file.sourceSha256 || hash(target) !== file.targetSha256) throw new Error("Migration source changed during validation.");
    const targetRoot = file.kind === "definition" && plan.scope !== "user" ? plan.cwd : plan.agentDir;
    assertAgentStoragePath(targetRoot, file.destination);
    if (exists(file.destination)) throw new Error(`Migration destination appeared: ${file.destination}`);
    return { file, bytes: target, root: targetRoot };
  });
  // Metadata identifies only writes from this invocation for bounded rollback.
  // Path checks are not atomic against concurrent source/ancestor replacement
  // or replacement between rollback's lstat and unlink; this is no OS sandbox.
  const created: Array<{ destination: string; dev: number; ino: number }> = [];
  const operationDiagnostics: Error[] = [];
  try {
    for (const { file, bytes, root } of content) {
      assertAgentStoragePath(root, file.destination);
      fs.mkdirSync(path.dirname(file.destination), { recursive: true, mode: 0o700 });
      assertAgentStoragePath(root, file.destination);
      const fd = fs.openSync(file.destination, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL
        | (fs.constants.O_NOFOLLOW ?? 0), 0o600);
      let ownershipVerified = false;
      let failure: { error: unknown } | undefined;
      try {
        const stat = fs.fstatSync(fd);
        created.push({ destination: file.destination, dev: stat.dev, ino: stat.ino });
        ownershipVerified = true;
        fs.writeFileSync(fd, bytes);
        fs.fsyncSync(fd);
      } catch (error) {
        failure = { error };
        if (!ownershipVerified) {
          // Exclusive open created a path, but inspection failed before we could
          // record its inode. Never infer current-path ownership to delete it.
          operationDiagnostics.push(new Error(`Migration retained unverified destination at ${file.destination}: created-file ownership could not be confirmed; the path may remain.`,
            { cause: error }));
        }
      } finally {
        try { fs.closeSync(fd); } catch (error) {
          operationDiagnostics.push(new Error(`Migration descriptor close failed at ${file.destination}; descriptor state is uncertain.`,
            { cause: error }));
          failure ??= { error };
          // A failed close may already have closed/recycled this descriptor; a
          // retry could close an unrelated fd. Preserve diagnostics, not guesses.
        }
      }
      if (failure) throw failure.error;
    }
  } catch (error) {
    const rollbackErrors: Error[] = [...operationDiagnostics];
    for (const entry of created.reverse()) {
      let operation = "lstat";
      try {
        const stat = fs.lstatSync(entry.destination);
        if (stat.dev !== entry.dev || stat.ino !== entry.ino || stat.isSymbolicLink()) {
          rollbackErrors.push(new Error(`Rollback retained replacement at ${entry.destination}; the created inode no longer owns this path.`));
          continue;
        }
        operation = "unlink";
        fs.unlinkSync(entry.destination);
      } catch (cleanupError) {
        const code = (cleanupError as NodeJS.ErrnoException).code;
        if (code === "ENOENT") continue; // Already absent, including disappearance during unlink.
        rollbackErrors.push(new Error(`Rollback ${operation} failed at ${entry.destination}${code ? ` (${code})` : ""}; destination may remain.`,
          { cause: cleanupError }));
      }
    }
    if (rollbackErrors.length) {
      throw new AggregateError([error, ...rollbackErrors], `Migration failed; rollback or descriptor cleanup incomplete. ${rollbackErrors.map(issue => issue.message).join(" ")}`,
        { cause: error });
    }
    throw error;
  }
  return { status: "applied", copied: content.map(item => item.file.destination) };
}

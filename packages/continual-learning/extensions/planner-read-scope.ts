import { locatedMemoryEvidence } from "./memory-citation-locations";
import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs/promises";
import { constants } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { containsSensitiveMemoryMaterial } from "./consolidation-run";

export interface PlannerReadScope { cwd: string; files: string[]; roots: string[]; indexedEvidence?: boolean; excludedComponents?: string[]; regularFilesOnly?: boolean; excludedPaths?: string[] }
/** Render an already-authorized source read without changing its byte/line bound. */
export function formatPlannerFileRead(text: string, offset: number, limit: number): string {
  const lines = text.split("\n");
  const selected = lines.slice(offset - 1, offset - 1 + limit).join("\n");
  const bounded = Buffer.from(selected).subarray(0, 64_000).toString("utf8");
  return `${bounded}\n[lines ${offset}-${Math.min(lines.length, offset + limit - 1)} of ${lines.length}${bounded.length < selected.length ? "; byte limit reached" : ""}]`;
}
const FORBIDDEN = /^(?:\.git|\.env(?:\..*)?|auth\.json|credentials(?:\..*)?|id_(?:rsa|ed25519)|.*\.(?:pem|key))$/i;
function inside(file: string, root: string): boolean {
  const relative = path.relative(root, file);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}
async function safePath(input: string, scope: PlannerReadScope): Promise<string> {
  const file = path.resolve(scope.cwd, input);
  if (scope.excludedPaths?.some(item => inside(file, path.resolve(item)))) throw new Error("Planner read refused: excluded managed path");
  const exact = scope.files.some(item => path.resolve(item) === file);
  if (!exact && path.relative(scope.cwd, file).split(path.sep).some(part => scope.excludedComponents?.includes(part))) throw new Error("Planner read refused: excluded source root");
  const root = scope.roots.map(item => path.resolve(item)).filter(item => inside(file, item)).sort((a, b) => b.length - a.length)[0];
  if (!exact && !root) throw new Error("Planner read refused: outside the parent-approved scope");
  // Check every component, including the approved root. realpath containment
  // alone would allow a symlink to another sensitive file inside that root.
  const parts = file.slice(path.parse(file).root.length).split(path.sep);
  // A missing ancestor must not conceal a later forbidden path component.
  if (parts.some(part => FORBIDDEN.test(part))) throw new Error("Planner read refused: sensitive path");
  let current = path.parse(file).root;
  for (const part of parts) {
    current = path.join(current, part);
    if ((await fs.lstat(current)).isSymbolicLink()) throw new Error("Planner read refused: symbolic link");
  }
  return file;
}
export async function readPlannerFileSnapshot(input: string, scope: PlannerReadScope, offset = 1, limit = 200, signal?: AbortSignal): Promise<{text: string; sha256?: string}> {
  if (!Number.isSafeInteger(offset) || offset < 1 || !Number.isSafeInteger(limit) || limit < 1 || limit > 2000) throw new Error("Invalid planner read range");
  signal?.throwIfAborted();
  const file = await safePath(input, scope);
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat();
    if (before.isDirectory()) {
      if (scope.regularFilesOnly) throw new Error("Planner read refused: regular files only; use the parent source inventory for discovery");
      const entries = (await fs.readdir(file, {withFileTypes:true})).filter(entry => !entry.isSymbolicLink() && !FORBIDDEN.test(entry.name)
        && !scope.excludedComponents?.includes(entry.name) && (entry.isFile() || entry.isDirectory())).sort((a,b) => a.name.localeCompare(b.name));
      await safePath(input, scope);
      signal?.throwIfAborted();
      const named = await fs.lstat(file);
      if (named.dev !== before.dev || named.ino !== before.ino) throw new Error("Planner directory changed");
      return {text: entries.slice(offset - 1, offset - 1 + limit).map(entry => `${entry.name}${entry.isDirectory() ? "/" : ""}`).join("\n").slice(0, 64_000) + `\n[${entries.length} entries; use offset/limit to page]`};
    }
    if (!before.isFile() || before.size > 32 * 1024 * 1024) throw new Error("Planner read refused: unsupported file");
    const bytes = Buffer.alloc(before.size);
    let offsetBytes = 0;
    while (offsetBytes < bytes.length) {
      signal?.throwIfAborted();
      const read = await handle.read(bytes, offsetBytes, bytes.length - offsetBytes, offsetBytes);
      if (!read.bytesRead) break;
      offsetBytes += read.bytesRead;
    }
    if (offsetBytes !== before.size) throw new Error("Planner file changed during read");
    signal?.throwIfAborted();
    await safePath(input, scope);
    const after = await handle.stat();
    const named = await fs.lstat(file);
    if (named.dev !== after.dev || named.ino !== after.ino || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) throw new Error("Planner read refused: file changed");
    const text = bytes.toString("utf8");
    if (text.includes("\0") || containsSensitiveMemoryMaterial(text)) throw new Error("Planner read refused: sensitive or binary content");
    const shown = scope.indexedEvidence ? JSON.stringify(locatedMemoryEvidence(JSON.parse(text)), null, 2) : text;
    return {text: formatPlannerFileRead(shown, offset, limit),
      sha256: createHash("sha256").update(bytes).digest("hex")};
  } finally { await handle.close(); }
}
/** Bounded path discovery, never file content or independently observed facts. */
export async function discoverPlannerSources(scope: PlannerReadScope, signal?: AbortSignal): Promise<{
  paths: string[]; truncated: boolean; discoveryOnly: true; bodiesIncluded: false;
}> {
  const paths: string[] = [];
  const pending = [{file: path.resolve(scope.cwd), depth: 0}];
  let visited = 0;
  let directories = 0;
  let truncated = false;
  while (pending.length) {
    signal?.throwIfAborted();
    if (directories >= 128 || visited >= 2048 || paths.length >= 512) { truncated = true; break; }
    const {file, depth} = pending.shift()!;
    try {
      await safePath(file, scope);
      const before = await fs.lstat(file);
      if (!before.isDirectory()) throw new Error("Source inventory directory changed");
      directories++;
      const directory = await fs.opendir(file);
      try {
        for await (const entry of directory) {
          signal?.throwIfAborted();
          if (++visited > 2048 || paths.length >= 512) { truncated = true; break; }
          if (entry.isSymbolicLink() || FORBIDDEN.test(entry.name) || scope.excludedComponents?.includes(entry.name)) continue;
          const child = path.join(file, entry.name);
          if (scope.excludedPaths?.some(item => inside(child, path.resolve(item)))) continue;
          if (entry.isDirectory()) {
            if (depth < 3) pending.push({file: child, depth: depth + 1});
            else truncated = true;
          } else if (entry.isFile()) {
            await safePath(child, scope);
            if (!(await fs.lstat(child)).isFile()) throw new Error("Source inventory file changed");
            paths.push(path.relative(scope.cwd, child));
          }
        }
      } finally {
        // for-await closes its handle on normal completion and early exit.
        await directory.close().catch(error => { if (error.code !== "ERR_DIR_CLOSED") throw error; });
      }
      await safePath(file, scope);
      const after = await fs.lstat(file);
      if (before.dev !== after.dev || before.ino !== after.ino) throw new Error("Source inventory directory changed");
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error ? error.code : undefined;
      if (file !== path.resolve(scope.cwd) && ["ENOENT", "EACCES", "EPERM"].includes(String(code))) truncated = true;
      else throw error;
    }
  }
  return {paths: paths.sort(), truncated, discoveryOnly: true, bodiesIncluded: false};
}
export async function readPlannerFile(input: string, scope: PlannerReadScope, offset = 1, limit = 200, signal?: AbortSignal): Promise<string> {
  return (await readPlannerFileSnapshot(input, scope, offset, limit, signal)).text;
}
export interface PlannerReadObservation { toolCallId?: string; path: string; offset: number; limit: number; result?: string; sha256?: string; error?: string }
export function registerPlannerRead(pi: ExtensionAPI, scope: PlannerReadScope, observe?: (read: PlannerReadObservation) => Promise<void>, maxReads?: number): void {
  let reads = 0;
  pi.registerTool({
    name: "learning_read", label: "Read scoped evidence", description: scope.regularFilesOnly
      ? "Read a parent-approved regular text file. Directories are refused; use the parent source inventory for discovery. Paths outside the frozen scope, symlinks and sensitive files are refused. Use offset/limit to page."
      : "Read a parent-approved regular text file or list an approved directory. Paths outside the frozen scope, symlinks and sensitive files are refused. Use offset/limit to page.",
    parameters: Type.Object({ path: Type.String(), offset: Type.Optional(Type.Integer({minimum:1})), limit: Type.Optional(Type.Integer({minimum:1,maximum:2000})) }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      const read = {toolCallId: _id, path: path.resolve(scope.cwd, params.path), offset: params.offset ?? 1, limit: params.limit ?? 200};
      reads += 1;
      if (maxReads !== undefined && reads >= maxReads) pi.setActiveTools([]);
      if (maxReads !== undefined && reads > maxReads) {
        await observe?.({...read, error: "Source audit read budget exceeded"});
        ctx?.abort();
        throw new Error("Source audit read budget exceeded");
      }
      let snapshot: {text: string; sha256?: string};
      try { snapshot = await readPlannerFileSnapshot(params.path, scope, params.offset, params.limit, signal); }
      catch (error) {
        const missing = error && typeof error === "object" && "code" in error && error.code === "ENOENT";
        await observe?.({...read, error: missing ? "Scoped source path missing" : "Scoped source read refused"});
        // A missing scoped path supplies no fact; return a parent-controlled
        // error result so trusted collection can bind and recheck the miss.
        if (missing) throw new Error("Scoped source path missing");
        throw error;
      }
      await observe?.({...read, result: snapshot.text, sha256: snapshot.sha256});
      return {content:[{type:"text", text: snapshot.text}], details:{}};
    },
  });
  pi.on("before_provider_request", (event, ctx) => {
    if (maxReads === undefined || reads < maxReads || ctx.model?.api !== "openai-completions"
      || pi.getActiveTools().length !== 0) return;
    const payload = event.payload;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
    const request = payload as Record<string, unknown>;
    if (!Array.isArray(request.messages) || request.tools !== undefined
      && (!Array.isArray(request.tools) || request.tools.length !== 0)) return;
    // Past tool calls remain as evidence; an empty definition list alone can
    // still make some providers request unavailable tools repeatedly.
    return {...request, tool_choice: "none"};
  });
  pi.on("session_start", async () => { pi.setActiveTools(["learning_read"]); });
}
/** Explicit extension is loaded even with -ne; no native filesystem tool is
 * granted. The extension's only operation enforces the parent-owned policy. */
export async function plannerReadArgs(directory: string, scope: PlannerReadScope): Promise<string[]> {
  const extension = path.join(directory, `planner-read-${randomUUID()}.mjs`);
  const module = fileURLToPath(import.meta.url);
  await fs.writeFile(extension, `import { registerPlannerRead } from ${JSON.stringify(module)};\nexport default pi => registerPlannerRead(pi, ${JSON.stringify(scope)});\n`, {mode:0o600, flag:"wx"});
  return ["-e", extension];
}

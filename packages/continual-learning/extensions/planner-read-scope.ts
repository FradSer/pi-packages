import { locatedMemoryEvidence } from "./memory-citation-locations";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs/promises";
import { constants } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { containsSensitiveMemoryMaterial } from "./consolidation-run";

export interface PlannerReadScope { cwd: string; files: string[]; roots: string[]; indexedEvidence?: boolean }
const FORBIDDEN = /^(?:\.git|\.env(?:\..*)?|auth\.json|credentials(?:\..*)?|id_(?:rsa|ed25519)|.*\.(?:pem|key))$/i;
function inside(file: string, root: string): boolean {
  const relative = path.relative(root, file);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}
async function safePath(input: string, scope: PlannerReadScope): Promise<string> {
  const file = path.resolve(scope.cwd, input);
  const exact = scope.files.some(item => path.resolve(item) === file);
  const root = scope.roots.map(item => path.resolve(item)).filter(item => inside(file, item)).sort((a, b) => b.length - a.length)[0];
  if (!exact && !root) throw new Error("Planner read refused: outside the parent-approved scope");
  // Check every component, including the approved root. realpath containment
  // alone would allow a symlink to another sensitive file inside that root.
  const parts = file.slice(path.parse(file).root.length).split(path.sep);
  let current = path.parse(file).root;
  for (const part of parts) {
    if (FORBIDDEN.test(part)) throw new Error("Planner read refused: sensitive path");
    current = path.join(current, part);
    if ((await fs.lstat(current)).isSymbolicLink()) throw new Error("Planner read refused: symbolic link");
  }
  return file;
}
export async function readPlannerFile(input: string, scope: PlannerReadScope, offset = 1, limit = 200, signal?: AbortSignal): Promise<string> {
  if (!Number.isSafeInteger(offset) || offset < 1 || !Number.isSafeInteger(limit) || limit < 1 || limit > 2000) throw new Error("Invalid planner read range");
  signal?.throwIfAborted();
  const file = await safePath(input, scope);
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat();
    if (before.isDirectory()) {
      const entries = (await fs.readdir(file, {withFileTypes:true})).filter(entry => !entry.isSymbolicLink() && !FORBIDDEN.test(entry.name) && (entry.isFile() || entry.isDirectory())).sort((a,b) => a.name.localeCompare(b.name));
      await safePath(input, scope);
      signal?.throwIfAborted();
      const named = await fs.lstat(file);
      if (named.dev !== before.dev || named.ino !== before.ino) throw new Error("Planner directory changed");
      return entries.slice(offset - 1, offset - 1 + limit).map(entry => `${entry.name}${entry.isDirectory() ? "/" : ""}`).join("\n").slice(0, 64_000) + `\n[${entries.length} entries; use offset/limit to page]`;
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
    const lines = shown.split("\n");
    const selected = lines.slice(offset - 1, offset - 1 + limit).join("\n");
    const bounded = Buffer.from(selected).subarray(0, 64_000).toString("utf8");
    return `${bounded}\n[lines ${offset}-${Math.min(lines.length, offset + limit - 1)} of ${lines.length}${bounded.length < selected.length ? "; byte limit reached" : ""}]`;
  } finally { await handle.close(); }
}
export function registerPlannerRead(pi: ExtensionAPI, scope: PlannerReadScope): void {
  pi.registerTool({
    name: "learning_read", label: "Read scoped evidence", description: "Read a parent-approved regular text file or list an approved directory. Paths outside the frozen scope, symlinks and sensitive files are refused. Use offset/limit to page.",
    parameters: Type.Object({ path: Type.String(), offset: Type.Optional(Type.Integer({minimum:1})), limit: Type.Optional(Type.Integer({minimum:1,maximum:2000})) }),
    async execute(_id, params, signal) {
      return {content:[{type:"text", text:await readPlannerFile(params.path, scope, params.offset, params.limit, signal)}], details:{}};
    },
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

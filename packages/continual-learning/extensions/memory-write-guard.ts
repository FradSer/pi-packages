import { realpathSync } from "node:fs";
import path from "node:path";
import { resolveToolTargetPath } from "./tool-target-path";
import { resolveMemoryPaths } from "./memory-paths";

// Resolve the nearest existing parent too: a new filename may sit below an
// existing symlink. This is a tool boundary, not a shell/filesystem sandbox.
function physicalPath(file: string): string {
  try { return realpathSync(file); }
  catch {
    const parent = path.dirname(file);
    return parent === file ? file : path.join(physicalPath(parent), path.basename(file));
  }
}

function within(file: string, root: string): boolean {
  const relative = path.relative(root, file);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

/** Ordinary model tools consume reference Memory; only the parent maintains it. */
export function memoryWriteBlock(cwd: string, toolName: string, input: unknown): string | undefined {
  if (toolName !== "write" && toolName !== "edit") return;
  if (!input || typeof input !== "object" || !("path" in input) || typeof input.path !== "string") return;
  const paths = resolveMemoryPaths(cwd);
  const file = resolveToolTargetPath(input.path, cwd);
  for (const root of [paths.harnessDir, paths.publicDir]) {
    if (root && (within(file, root) || within(physicalPath(file), physicalPath(root)))) {
      return "Memory entries and indexes are read-only references for ordinary task tools. Write task output in the project working directory. Use /memory <request> or /consolidate for parent-validated Memory changes with history and undo.";
    }
  }
}

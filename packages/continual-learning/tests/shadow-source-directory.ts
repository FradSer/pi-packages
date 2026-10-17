/** Temporary research sources must not enter concurrent source inventories. */
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export async function createShadowSourceDirectory(prefix: string): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  try {
    // Resolve the exact installed workspace dependencies, without copying them.
    const dependencies = await fs.realpath(new URL("../node_modules/", import.meta.url));
    await fs.symlink(dependencies, path.join(directory, "node_modules"), "dir");
    return directory;
  } catch (error) {
    await fs.rm(directory, { recursive: true, force: true });
    throw error;
  }
}

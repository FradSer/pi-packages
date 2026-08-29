import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const procedureDirectory = fileURLToPath(new URL("../procedures/", import.meta.url));

export function procedurePath(procedure: string): string {
  const normalized = procedure.trim().replace(/\.md$/i, "");
  if (!/^[a-zA-Z0-9-]+$/.test(normalized)) {
    throw new Error(`Unknown Matt Pocock procedure: ${procedure}`);
  }
  const exactPath = `${procedureDirectory}${normalized}.md`;
  if (existsSync(exactPath)) {
    return exactPath;
  }
  const lowerPath = `${procedureDirectory}${normalized.toLowerCase()}.md`;
  if (existsSync(lowerPath)) {
    return lowerPath;
  }
  throw new Error(`Procedure file not found for ${procedure}`);
}

export function loadProcedure(procedure: string): string {
  return readFileSync(procedurePath(procedure), "utf8");
}

export function procedurePrompt(route: string, procedure: string, phase: string): string {
  return `# Matt Pocock workflow procedure

Route: ${route}
Phase: ${phase}

${loadProcedure(procedure)}`;
}

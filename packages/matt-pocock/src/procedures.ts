import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const procedureDirectory = fileURLToPath(new URL("../procedures/", import.meta.url));

export function procedurePath(procedure: string): string {
  if (!/^[a-z0-9-]+$/.test(procedure)) {
    throw new Error(`Unknown Matt Pocock procedure: ${procedure}`);
  }
  return `${procedureDirectory}${procedure}.md`;
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

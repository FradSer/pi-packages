import { readFileSync } from "node:fs";
import { isAbsolute, normalize } from "node:path";

export interface Disclosure { id: string; when: string }
export interface CatalogEntry {
  id: string;
  kind: "capability" | "procedure" | "reference";
  invocation: "model" | "user" | "internal";
  file: string;
  label: string;
  requires?: string[];
  discloses?: Disclosure[];
}

function validateRequiredCycles(entries: CatalogEntry[]): void {
  const byId = new Map(entries.map(entry => [entry.id, entry]));
  const visiting = new Set<string>(), visited = new Set<string>();
  const visit = (id: string): void => {
    if (visiting.has(id)) throw new Error(`Cyclic Impeccable dependency: ${id}`);
    if (visited.has(id)) return;
    visiting.add(id);
    for (const next of byId.get(id)?.requires ?? []) visit(next);
    visiting.delete(id);
    visited.add(id);
  };
  for (const entry of entries) visit(entry.id);
}

export function validateCatalog(entries: CatalogEntry[]): void {
  const ids = new Set<string>();
  const files = new Set<string>();
  for (const entry of entries) {
    if (!/^[a-z][a-z0-9-]*$/.test(entry.id) || ids.has(entry.id)) throw new Error(`Invalid or duplicate catalog id: ${entry.id}`);
    if (isAbsolute(entry.file) || normalize(entry.file).startsWith("..") || files.has(entry.file)) throw new Error(`Invalid or duplicate catalog file: ${entry.file}`);
    if (entry.kind === "reference" && !entry.file.startsWith("references/taste/")) throw new Error(`Reference ${entry.id} must live under references/taste/`);
    ids.add(entry.id);
    files.add(entry.file);
  }
  for (const entry of entries) {
    for (const id of [...(entry.requires ?? []), ...(entry.discloses ?? []).map(edge => edge.id)]) {
      if (!ids.has(id)) throw new Error(`${entry.id}: unknown catalog target ${id}`);
    }
    for (const edge of entry.discloses ?? []) {
      const target = entries.find(candidate => candidate.id === edge.id);
      if (!edge.when.trim() || !(target?.kind === "reference" || (target?.kind === "procedure" && target.invocation === "internal"))) throw new Error(`${entry.id}: disclosure ${edge.id} requires a reference or internal procedure and loading condition`);
    }
  }
  validateRequiredCycles(entries);
}

export const catalog = JSON.parse(readFileSync(new URL("./catalog.json", import.meta.url), "utf8")) as CatalogEntry[];

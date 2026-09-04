import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  findProcedure,
  findProcedureByFile,
  normalizeProcedureId,
  type ProcedureDefinition,
} from "./catalog.ts";

export const MAX_PROCEDURE_BUNDLE_BYTES = 64 * 1024;

export interface ResolvedProcedureBundle {
  root: string;
  loaded: string[];
  availableReferences: string[];
  content: string;
  byteLength: number;
}

const procedureDirectory = fileURLToPath(new URL("../procedures/", import.meta.url));

function requireDefinition(id: string): ProcedureDefinition {
  const definition = findProcedure(id);
  if (!definition) throw new Error(`Unknown Matt Pocock procedure: ${id}`);
  return definition;
}

function loadContent(definition: ProcedureDefinition): string {
  const body = readFileSync(`${procedureDirectory}${definition.file}`, "utf8").trim();
  return body.replace(/\]\((\.\/)?([A-Za-z0-9.-]+)(#[^)]+)?\)/g, (match, _prefix, file, anchor = "") => {
    const target = findProcedureByFile(file);
    return target ? `](procedure:${target.id}${anchor})` : match;
  });
}

function dependencyClosure(root: string): ProcedureDefinition[] {
  const ordered: ProcedureDefinition[] = [];
  const visiting = new Set<string>();
  const visited = new Set<string>();

  const visit = (id: string): void => {
    const definition = requireDefinition(id);
    if (visited.has(definition.id)) return;
    if (visiting.has(definition.id)) {
      throw new Error(`Cyclic Matt Pocock procedure dependency at ${definition.id}`);
    }
    visiting.add(definition.id);
    ordered.push(definition);
    for (const dependency of definition.requires ?? []) visit(dependency);
    visiting.delete(definition.id);
    visited.add(definition.id);
  };

  visit(root);
  return ordered;
}

function renderSource(definition: ProcedureDefinition): string {
  const body = loadContent(definition);
  return `<procedure-source id="${definition.id}" source="procedure/${definition.id}">\n${body}\n</procedure-source>`;
}

function resolvedBundle(root: string, definitions: ProcedureDefinition[]): ResolvedProcedureBundle {
  const unique = definitions.filter((definition, index) => (
    definitions.findIndex((candidate) => candidate.id === definition.id) === index
  ));
  const content = unique.map(renderSource).join("\n\n");
  const byteLength = Buffer.byteLength(content, "utf8");
  if (byteLength > MAX_PROCEDURE_BUNDLE_BYTES) {
    throw new Error(
      `Matt Pocock procedure bundle ${root} is ${byteLength} bytes; maximum is ${MAX_PROCEDURE_BUNDLE_BYTES}`,
    );
  }
  const loaded = unique.map((definition) => definition.id);
  const availableReferences = [
    ...new Set(unique.flatMap((definition) => definition.discloses ?? [])),
  ].filter((reference) => !loaded.includes(reference));
  return { root, loaded, availableReferences, content, byteLength };
}

export function resolveProcedureBundle(id: string): ResolvedProcedureBundle {
  const definitions = dependencyClosure(id);
  return resolvedBundle(definitions[0].id, definitions);
}

export function resolveWorkflowContext(
  activeProcedure: string,
  loadedReferences: string[],
): ResolvedProcedureBundle {
  const root = normalizeProcedureId(activeProcedure);
  const definitions = [...dependencyClosure(root)];
  const loaded = new Set(definitions.map((definition) => definition.id));
  let available = new Set(definitions.flatMap((definition) => definition.discloses ?? []));

  for (const requested of loadedReferences.map(normalizeProcedureId)) {
    if (loaded.has(requested)) continue;
    if (!available.has(requested)) {
      throw new Error(
        `Reference ${requested} is not disclosed by the restored workflow context. Available references: ${[...available].join(", ") || "none"}`,
      );
    }
    for (const definition of dependencyClosure(requested)) {
      if (!loaded.has(definition.id)) {
        definitions.push(definition);
        loaded.add(definition.id);
      }
    }
    available = new Set(definitions.flatMap((definition) => definition.discloses ?? []));
  }

  return resolvedBundle(root, definitions);
}

export function resolveAccessibleReference(
  activeProcedure: string,
  loadedReferences: string[],
  reference: string,
): ResolvedProcedureBundle {
  const context = resolveWorkflowContext(activeProcedure, loadedReferences);
  const target = requireDefinition(reference);
  if (!context.availableReferences.includes(target.id)) {
    throw new Error(
      `Reference ${target.id} is not disclosed by ${activeProcedure}. Available references: ${context.availableReferences.join(", ") || "none"}`,
    );
  }
  return resolveProcedureBundle(target.id);
}

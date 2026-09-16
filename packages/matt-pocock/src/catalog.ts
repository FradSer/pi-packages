import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export type ProcedureKind = "workflow" | "utility" | "reference" | "asset";
export type InvocationMode = "model" | "user" | "internal";

export interface WorkflowPlacement {
  route: string;
  phase: string;
  entry?: boolean;
  allowedNext: string[];
  title?: string;
  label?: string;
  description?: string;
}

export interface ProcedureDefinition {
  id: string;
  file: string;
  kind: ProcedureKind;
  invocation: InvocationMode;
  label: string;
  description?: string;
  aliases?: string[];
  standalone?: boolean;
  requires?: string[];
  discloses?: string[];
  workflows?: WorkflowPlacement[];
}

const procedureDirectory = fileURLToPath(new URL("../procedures/", import.meta.url));
const catalogPath = fileURLToPath(new URL("./catalog.json", import.meta.url));

export const procedureCatalog = JSON.parse(readFileSync(catalogPath, "utf8")) as ProcedureDefinition[];
const definitionsById = new Map(procedureCatalog.map((definition) => [definition.id, definition]));

export function catalogFiles(): string[] {
  return procedureCatalog.map((definition) => definition.file);
}

export function findProcedure(id: string): ProcedureDefinition | undefined {
  return definitionsById.get(normalizeProcedureId(id));
}

export function findProcedureByFile(file: string): ProcedureDefinition | undefined {
  const normalized = file.replace(/^\.\//, "");
  return procedureCatalog.find((definition) => definition.file === normalized);
}

export function normalizeProcedureId(id: string): string {
  const normalized = id.trim().replace(/\.md$/i, "");
  for (const definition of procedureCatalog) {
    if (definition.id === normalized || definition.aliases?.includes(normalized)) return definition.id;
  }
  return normalized;
}

export function workflowDefinitions(route?: string): ProcedureDefinition[] {
  return procedureCatalog.filter((definition) => definition.workflows?.some((workflow) => !route || workflow.route === route));
}

export function workflowPlacement(route: string, procedure: string): WorkflowPlacement | undefined {
  return findProcedure(procedure)?.workflows?.find((workflow) => workflow.route === route);
}

export function workflowEntry(route: string): ProcedureDefinition | undefined {
  return workflowDefinitions(route).find((definition) => workflowPlacement(route, definition.id)?.entry);
}

export interface WorkflowRouteDefinition {
  route: string;
  title: string;
  label: string;
  description: string;
}

export function workflowRoutes(): WorkflowRouteDefinition[] {
  return procedureCatalog.flatMap((definition) => (definition.workflows ?? [])
    .filter((workflow) => workflow.entry)
    .map((workflow) => ({
      route: workflow.route,
      title: workflow.title ?? workflow.route,
      label: workflow.label ?? definition.label,
      description: workflow.description ?? definition.description ?? definition.id,
    })));
}

export function allowedTransitions(route: string, procedure: string): string[] {
  return workflowPlacement(route, procedure)?.allowedNext ?? [];
}

export function standaloneCapabilities(): ProcedureDefinition[] {
  return procedureCatalog.filter((definition) => definition.standalone);
}

export function modelStandaloneCapabilities(): ProcedureDefinition[] {
  return standaloneCapabilities().filter((definition) => definition.invocation === "model");
}

export function validateProcedureCatalog(): string[] {
  const errors: string[] = [];
  const ids = new Set<string>();
  const files = new Set<string>();

  for (const definition of procedureCatalog) {
    if (ids.has(definition.id)) errors.push(`${definition.id}: duplicate catalog id`);
    if (files.has(definition.file)) errors.push(`${definition.file}: classified more than once`);
    ids.add(definition.id);
    files.add(definition.file);

    if (!existsSync(`${procedureDirectory}${definition.file}`)) {
      errors.push(`${definition.id}: file not found: ${definition.file}`);
    }
    for (const dependency of [...(definition.requires ?? []), ...(definition.discloses ?? [])]) {
      if (!findProcedure(dependency)) errors.push(`${definition.id}: unknown catalog target: ${dependency}`);
    }
    for (const workflow of definition.workflows ?? []) {
      for (const next of workflow.allowedNext) {
        if (!workflowPlacement(workflow.route, next)) errors.push(`${definition.id}: invalid ${workflow.route} transition: ${next}`);
      }
    }
    for (const alias of definition.aliases ?? []) {
      if (findProcedure(alias)?.id !== definition.id) errors.push(`${definition.id}: alias does not resolve: ${alias}`);
    }
  }

  const routes = new Map<string, WorkflowPlacement[]>();
  for (const definition of procedureCatalog) {
    for (const workflow of definition.workflows ?? []) {
      const placements = routes.get(workflow.route) ?? [];
      placements.push(workflow);
      routes.set(workflow.route, placements);
    }
  }
  for (const [route, placements] of routes) {
    const entries = placements.filter((workflow) => workflow.entry);
    if (entries.length !== 1) errors.push(`${route}: expected exactly one workflow entry, found ${entries.length}`);
    const entry = entries[0];
    if (entry && (!entry.title || !entry.label || !entry.description)) {
      errors.push(`${route}: workflow entry requires title, label, and description`);
    }

    const entryDefinition = workflowEntry(route);
    if (entryDefinition) {
      const reachable = new Set<string>([entryDefinition.id]);
      const queue = [entryDefinition.id];
      while (queue.length > 0) {
        const current = queue.shift()!;
        const currentPlacement = workflowPlacement(route, current);
        for (const next of currentPlacement?.allowedNext ?? []) {
          if (!reachable.has(next)) {
            reachable.add(next);
            queue.push(next);
          }
        }
      }
      for (const definition of workflowDefinitions(route)) {
        if (!reachable.has(definition.id)) {
          errors.push(`${route}: unreachable workflow procedure: ${definition.id}`);
        }
      }
    }
  }

  const inbound = new Set(procedureCatalog.flatMap((definition) => [
    ...(definition.requires ?? []),
    ...(definition.discloses ?? []),
  ]));
  for (const definition of procedureCatalog) {
    if (definition.kind === "reference" && !inbound.has(definition.id)) {
      errors.push(`${definition.id}: internal reference has no inbound catalog edge`);
    }
  }

  return errors;
}

import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { catalog, validateCatalog, type CatalogEntry, type Disclosure } from "./catalog.ts";
import { fileURLToPath } from "node:url";

export const MAX_BUNDLE_BYTES = 64 * 1024;
export interface Bundle {
  root: string;
  capability: string;
  loaded: string[];
  availableReferences: Disclosure[];
  content: string;
  byteLength: number;
}
export interface Resolver {
  capabilities: CatalogEntry[];
  load(capability: string, actor: "model" | "user", reference?: string, signal?: AbortSignal): Bundle;
}

function closure(root: string, entries: Map<string, CatalogEntry>, actor: "model" | "user", optional = false): CatalogEntry[] {
  const ordered: CatalogEntry[] = [], visiting = new Set<string>(), visited = new Set<string>();
  const visit = (id: string): void => {
    if (visiting.has(id)) {
      if (optional) return;
      throw new Error(`Cyclic Impeccable dependency: ${id}`);
    }
    if (visited.has(id)) return;
    const entry = entries.get(id);
    if (!entry) throw new Error(`Unknown Impeccable resource: ${id}`);
    if (actor === "model" && entry.invocation === "user") throw new Error(`Requires explicit user action: /impeccable ${entry.id}`);
    visiting.add(id);
    ordered.push(entry);
    for (const next of entry.requires ?? []) visit(next);
    if (optional) for (const edge of entry.discloses ?? []) visit(edge.id);
    visiting.delete(id);
    visited.add(id);
  };
  visit(root);
  return ordered;
}

function source(root: string, entry: CatalogEntry, entries: CatalogEntry[]): string {
  const path = realpathSync(resolve(root, entry.file));
  if (relative(realpathSync(root), path).startsWith("..")) throw new Error(`Resource escapes package: ${entry.id}`);
  if (statSync(path).size > MAX_BUNDLE_BYTES) throw new Error(`Impeccable bundle exceeds ${MAX_BUNDLE_BYTES} bytes; narrow the required catalog closure.`);
  const body = readFileSync(path, "utf8").replace(/\]\(([^\s)]+)(#[^)]*)?\)/g, (match, link: string) => {
    const [file, anchor] = link.split("#");
    const target = entries.find(candidate => resolve(root, candidate.file) === resolve(root, dirname(entry.file), file));
    return target ? `](impeccable:${target.id}${anchor ? `#${anchor}` : ""})` : match;
  }).replaceAll("{{PKG_DIR}}", resolve(root));
  return `<impeccable-source id="${entry.id}">\n${body.trim()}\n</impeccable-source>`;
}

function renderBundle(root: string, capability: string, selected: CatalogEntry[], entries: CatalogEntry[]): Bundle {
  const loaded = selected.map(entry => entry.id);
  const disclosures = new Map<string, Disclosure>();
  for (const entry of selected) for (const edge of entry.discloses ?? []) if (!loaded.includes(edge.id)) disclosures.set(edge.id, edge);
  const availableReferences = [...disclosures.values()];
  const guidance = `Capability: ${capability}\nState: stateless; guidance loaded synchronously. No scripts executed.\nLoading does not authorize edits, installs, variants, or promotion. Pending: none. Next actor: agent, within the user's request.\nFor impeccable:<id> links, call impeccable_load with {"capability":"${capability}","reference":"<id>"}.\nDisclosed references: ${availableReferences.map(edge => `${edge.id} (${edge.when})`).join("; ") || "none"}`;
  const content = `${guidance}\n\n${selected.map(entry => source(root, entry, entries)).join("\n\n")}`;
  const byteLength = Buffer.byteLength(content, "utf8");
  if (byteLength > MAX_BUNDLE_BYTES) throw new Error(`Impeccable bundle is ${byteLength} bytes; maximum ${MAX_BUNDLE_BYTES}. Narrow the required catalog closure.`);
  return { root: selected[0].id, capability, loaded, availableReferences, content, byteLength };
}

export function createResolver(packageRoot: string, entries: CatalogEntry[]): Resolver {
  validateCatalog(entries);
  const byId = new Map(entries.map(entry => [entry.id, entry]));
  const capabilities = entries.filter(entry => entry.kind === "capability" && entry.invocation !== "internal");
  return {
    capabilities,
    load(capability, actor, reference, signal) {
      signal?.throwIfAborted();
      const capId = capability.trim().replace(/^impeccable:/, "");
      const entry = capabilities.find(candidate => candidate.id === capId);
      if (!entry) throw new Error(`Unknown Impeccable capability: ${capability}. Use /impeccable ${capabilities.map(item => item.id).join("|")} <target/request>.`);
      if (actor === "model" && entry.invocation === "user") throw new Error(`Requires explicit user action: /impeccable ${capId}`);
      const refId = reference !== undefined ? reference.trim().replace(/^impeccable:/, "").split("#")[0] : undefined;
      if (refId !== undefined) {
        const reachable = closure(capId, byId, actor, true).filter(item => item.kind === "reference" || item.invocation === "internal");
        if (!reachable.some(item => item.id === refId)) throw new Error(`Reference ${reference} is not reachable from ${capId}. Available references: ${reachable.map(item => item.id).join(", ") || "none"}`);
      }
      const targetId = refId ?? capId;
      const selected = closure(targetId, byId, actor);
      return renderBundle(packageRoot, capId, selected, entries);
    },
  };
}

export const resolver = createResolver(fileURLToPath(new URL("../", import.meta.url)), catalog);

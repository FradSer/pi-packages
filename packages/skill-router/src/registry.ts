import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { registryPath } from "./paths";

export interface RegistryRoute {
  skill: string;
  path: string;
  terms: string[];
  summary?: string;
}

export interface CollectionSource {
  repo: string;
  url: string;
  ref: string;
  cacheKey: string;
}

export interface RegistryCollection {
  id: string;
  gateway: string;
  mode: "suggest";
  enabled: boolean;
  description: string;
  source: CollectionSource;
  routes: RegistryRoute[];
}

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const RESERVED_COLLECTION_IDS = new Set(["collections"]);

export function isSlug(value: unknown): value is string {
  return typeof value === "string" && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value);
}

export function isCollectionId(value: unknown): value is string {
  return isSlug(value) && !RESERVED_COLLECTION_IDS.has(value);
}

function isSafeRelativePath(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !value.startsWith("/") &&
    !value.includes("\\") &&
    !value.split("/").includes("..")
  );
}

function parseRoute(value: unknown): RegistryRoute | undefined {
  if (!isRecord(value) || !isSlug(value.skill) || !isSafeRelativePath(value.path)) return;
  if (!Array.isArray(value.terms)) return;
  const terms = value.terms.filter((term): term is string => typeof term === "string" && term.trim().length > 0);
  if (typeof value.summary !== "undefined" && (typeof value.summary !== "string" || !value.summary.trim())) return;
  return terms.length > 0 ? { skill: value.skill, path: value.path, terms, summary: value.summary?.trim() } : undefined;
}

export function isSafeGitRef(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(value) &&
    !value.includes("..") &&
    !value.includes("//") &&
    !value.endsWith(".") &&
    !value.endsWith("/")
  );
}

function isSafeSourceUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.includes("\0")) return false;
  return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\.git$/.test(value)
    || value.startsWith("/");
}

function isSafeCacheKey(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(value) &&
    !value.includes("..")
  );
}

function parseSource(value: unknown): CollectionSource | undefined {
  if (!isRecord(value)) return;
  const { repo, url, cacheKey } = value;
  if (typeof repo !== "string" || !isSafeSourceUrl(url) || !isSafeGitRef(value.ref)) return;
  if (!repo || !isSafeCacheKey(cacheKey)) return;
  const ref = value.ref;
  return { repo, url, ref, cacheKey };
}

function parseCollection(value: unknown): RegistryCollection | undefined {
  if (!isRecord(value)) return;
  if (!isCollectionId(value.id) || !isSlug(value.gateway) || value.mode !== "suggest") return;
  if (typeof value.description !== "string" || !Array.isArray(value.routes)) return;
  if (value.enabled !== undefined && typeof value.enabled !== "boolean") return;
  const source = parseSource(value.source);
  if (!source) return;

  const parsedRoutes = value.routes.map(parseRoute);
  if (parsedRoutes.some((route) => route === undefined)) return;
  const routes = parsedRoutes as RegistryRoute[];
  const routeSkillNames = routes.map((route) => route.skill);
  if (new Set(routeSkillNames).size !== routeSkillNames.length) return;

  return {
    id: value.id,
    gateway: value.gateway,
    mode: "suggest",
    enabled: value.enabled !== false,
    description: value.description,
    source,
    routes,
  };
}

/** Load the registry, dropping structurally invalid entries and duplicate gateways or ids. */
export function loadCollections(root: string): RegistryCollection[] {
  const path = registryPath(root);
  if (!existsSync(path)) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return [];
  }
  if (!isRecord(parsed) || !Array.isArray(parsed.collections)) return [];

  const collections = parsed.collections
    .map(parseCollection)
    .filter((collection): collection is RegistryCollection => collection !== undefined);

  const idCounts = new Map<string, number>();
  const gatewayCounts = new Map<string, number>();
  const cacheCounts = new Map<string, number>();
  const sourceCounts = new Map<string, number>();
  for (const collection of collections) {
    idCounts.set(collection.id, (idCounts.get(collection.id) ?? 0) + 1);
    gatewayCounts.set(collection.gateway, (gatewayCounts.get(collection.gateway) ?? 0) + 1);
    cacheCounts.set(collection.source.cacheKey, (cacheCounts.get(collection.source.cacheKey) ?? 0) + 1);
    const sourceKey = `${collection.source.url}\0${collection.source.ref}`;
    sourceCounts.set(sourceKey, (sourceCounts.get(sourceKey) ?? 0) + 1);
  }
  return collections.filter((collection) => {
    const sourceKey = `${collection.source.url}\0${collection.source.ref}`;
    return (
      idCounts.get(collection.id) === 1 &&
      gatewayCounts.get(collection.gateway) === 1 &&
      cacheCounts.get(collection.source.cacheKey) === 1 &&
      sourceCounts.get(sourceKey) === 1
    );
  });
}

export function saveCollections(root: string, collections: RegistryCollection[]): void {
  const path = registryPath(root);
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  writeFileSync(temporary, `${JSON.stringify({ collections }, null, 2)}\n`, "utf8");
  renameSync(temporary, path);
}

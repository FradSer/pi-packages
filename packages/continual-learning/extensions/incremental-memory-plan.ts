import fs from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import {
  CONSOLIDATION_SCHEMA_VERSION,
  MAX_MEMORY_FILES,
  MAX_MEMORY_BYTES,
  MAX_SNAPSHOT_BYTES,
  normalizeNewMemoryProposals,
  sha256Digest,
  validatePlanIdentity,
  type ConsolidationRun,
  type NewMemoryProposal,
} from "./consolidation-run";
import { isMemoryFilename } from "./memory-files";

const PRIVATE_MARKER_RE = /\(\s*harness[\s_-]+only\s*\)/i;
const INDEX_MEMORY_RE = /(?:\[[^\]]*\]\(([^)]+)\)|\b([A-Za-z0-9][A-Za-z0-9_-]*\.md)\b)/i;
const MAX_GROUNDING_REASON_CHARS = 300;
const DELETE_VERDICTS = new Set<IncrementalDeleteVerdict>(["CONTRADICTED", "SUPERSEDED", "SUBSUMED"]);
const OBSERVATION_STATUSES = new Set<RepositoryObservationStatus>(["found", "missing", "updated"]);

export type IncrementalMemoryClassification = "safe" | "private";
export type IncrementalMemoryOperationKind = "create" | "rewrite" | "delete";
export type IncrementalDeleteVerdict = "CONTRADICTED" | "SUPERSEDED" | "SUBSUMED";
export type RepositoryObservationStatus = "found" | "missing" | "updated";

export interface RepositoryObservation {
  path: string;
  status: RepositoryObservationStatus;
}

export interface IncrementalMemoryOperation {
  name: string;
  kind: IncrementalMemoryOperationKind;
  classification: IncrementalMemoryClassification;
  content?: string;
  contentSha256?: string;
  verdict?: IncrementalDeleteVerdict;
  preservedIn?: string[];
  observations?: RepositoryObservation[];
}

export interface IncrementalNewMemoryEvidence {
  index: number;
  quote: string;
  role?: "user" | "toolResult";
}

export interface IncrementalNewMemoryProposal {
  name: string;
  kind: "preference" | "project";
  classification?: IncrementalMemoryClassification;
  content: string;
  evidence: IncrementalNewMemoryEvidence[];
}

export interface IncrementalMemoryDeltaPlan {
  kind: "incremental-memory-plan";
  version: typeof CONSOLIDATION_SCHEMA_VERSION;
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  scopeDigest: string;
  artifactHash: string;
  snapshotDigest?: string;
  operations: IncrementalMemoryOperation[];
  newMemories: IncrementalNewMemoryProposal[];
}

export interface FullIncrementalMemoryPlan {
  kind: "memory-consolidation-plan";
  version: typeof CONSOLIDATION_SCHEMA_VERSION;
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  scopeDigest: string;
  artifactHash: string;
  snapshotDigest: string;
  selected: string[];
  operations: IncrementalMemoryOperation[];
  newMemories: NewMemoryProposal[];
  inventory: Array<{ name: string; classification: IncrementalMemoryClassification }>;
  clusters: Array<{ name: "incremental-selected"; files: string[] }>;
  staleness: Array<{ name: string; verdict: IncrementalDeleteVerdict | "KEEP" }>;
  grounding: Array<{
    name: string;
    status: "VERIFIED" | "UNVERIFIABLE" | "N/A";
    reason: string;
    observations: RepositoryObservation[];
  }>;
  report: Array<{ name: string; status: IncrementalDeleteVerdict | "KEEP"; summary: string }>;
}

function assertRecord(value: unknown, label: string): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be an object`);
}

function assertExactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const allowedKeys = new Set(allowed);
  const unknown = Object.keys(value).find((key) => !allowedKeys.has(key));
  if (unknown) throw new Error(`${label} contains unsupported field ${unknown}`);
}

function assertSelectedNames(selected: readonly string[]): string[] {
  if (!Array.isArray(selected) || selected.length > MAX_MEMORY_FILES) throw new Error("Incremental Memory plan has an invalid selected scope");
  const names: string[] = [];
  const seen = new Set<string>();
  for (const value of selected) {
    if (typeof value !== "string" || !isMemoryFilename(value)) throw new Error(`Invalid selected Memory name: ${String(value)}`);
    const key = value.toLowerCase();
    if (seen.has(key)) throw new Error(`Incremental Memory plan has duplicate selected name: ${value}`);
    seen.add(key);
    names.push(value);
  }
  return names;
}

async function readBoundedRegularFile(file: string, maxBytes: number, label: string): Promise<Buffer> {
  let handle: fs.FileHandle | undefined;
  try {
    handle = await fs.open(file, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
    const stat = await handle.stat();
    if (!stat.isFile()) throw new Error(`${label} is not a regular file: ${file}`);
    if (stat.size > maxBytes) throw new Error(`${label} exceeds ${maxBytes} bytes`);
    return await handle.readFile();
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function readPrivateClassifications(root: string, selected: readonly string[]): Promise<Map<string, IncrementalMemoryClassification>> {
  if (selected.length === 0) return new Map();
  const indexPath = path.join(root, "MEMORY.md");
  const index = (await readBoundedRegularFile(indexPath, MAX_MEMORY_BYTES, "Private Memory index")).toString("utf8");
  const indexed = new Map<string, { name: string; classification: IncrementalMemoryClassification }>();
  for (const line of index.split(/\r?\n/)) {
    const match = INDEX_MEMORY_RE.exec(line);
    const name = match?.[1] ?? match?.[2];
    if (!name || !isMemoryFilename(name)) continue;
    const key = name.toLowerCase();
    if (indexed.has(key)) throw new Error(`Private Memory index contains duplicate name: ${name}`);
    indexed.set(key, { name, classification: PRIVATE_MARKER_RE.test(line) ? "private" : "safe" });
  }
  const classifications = new Map<string, IncrementalMemoryClassification>();
  for (const name of selected) {
    const entry = indexed.get(name.toLowerCase());
    if (!entry || entry.name !== name) throw new Error(`Selected Memory is absent from private MEMORY.md with exact casing: ${name}`);
    const memoryPath = path.join(root, name);
    const memoryStat = await fs.lstat(memoryPath);
    if (memoryStat.isSymbolicLink() || !memoryStat.isFile()) throw new Error(`Selected Memory is not a regular file: ${name}`);
    classifications.set(name.toLowerCase(), entry.classification);
  }
  return classifications;
}

function validateDeltaIdentity(run: ConsolidationRun, delta: unknown): Record<string, unknown> {
  assertRecord(delta, "Incremental Memory delta plan");
  assertExactKeys(delta, [
    "kind", "version", "schemaVersion", "runId", "scopeKey", "scopeDigest", "artifactHash", "snapshotDigest",
    "operations", "newMemories",
  ], "Incremental Memory delta plan");
  if (delta.kind !== "incremental-memory-plan") throw new Error("Incremental Memory delta plan kind is invalid");
  if (delta.version !== CONSOLIDATION_SCHEMA_VERSION || delta.schemaVersion !== CONSOLIDATION_SCHEMA_VERSION) {
    throw new Error(`Incremental Memory delta plan schemaVersion must be ${CONSOLIDATION_SCHEMA_VERSION}`);
  }
  const errors = validatePlanIdentity(delta, run.manifest);
  if (errors.length) throw new Error(errors.join("; "));
  if (delta.scopeKey !== run.manifest.scopeKey) throw new Error("plan scope key mismatch");
  if (delta.snapshotDigest !== undefined && delta.snapshotDigest !== delta.artifactHash) {
    throw new Error("plan snapshot digest alias mismatch");
  }
  return delta;
}

function repositoryCandidate(repoRoot: string, observationPath: string): string {
  if (!observationPath || path.isAbsolute(observationPath) || observationPath.split(/[\\/]/).includes("..")) {
    throw new Error(`Repository observation path must be repository-relative: ${observationPath}`);
  }
  const root = path.resolve(repoRoot);
  const candidate = path.resolve(root, observationPath);
  const relative = path.relative(root, candidate);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Repository observation path must be repository-relative: ${observationPath}`);
  }
  return candidate;
}

async function normalizeObservations(value: unknown, repoRoot: string, label: string): Promise<RepositoryObservation[]> {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length === 0 || value.length > 32) throw new Error(`${label} must contain 1..32 repository observations`);
  const observations: RepositoryObservation[] = [];
  const seen = new Set<string>();
  for (let index = 0; index < value.length; index += 1) {
    const item = value[index];
    assertRecord(item, `${label}[${index}]`);
    assertExactKeys(item, ["path", "status"], `${label}[${index}]`);
    if (typeof item.path !== "string") throw new Error(`${label}[${index}].path must be a string`);
    if (typeof item.status !== "string" || !OBSERVATION_STATUSES.has(item.status as RepositoryObservationStatus)) {
      throw new Error(`${label}[${index}].status must be found, missing, or updated`);
    }
    const candidate = repositoryCandidate(repoRoot, item.path);
    const key = `${item.status}\u0000${item.path}`;
    if (seen.has(key)) throw new Error(`${label} contains a duplicate repository observation`);
    seen.add(key);
    if (item.status === "found" || item.status === "updated") {
      let stat: Awaited<ReturnType<typeof fs.lstat>>;
      try {
        stat = await fs.lstat(candidate);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") {
          throw new Error(`${label}[${index}] must cite an existing regular file for ${item.status}: ${item.path}`);
        }
        throw error;
      }
      if (stat.isSymbolicLink() || !stat.isFile()) {
        throw new Error(`${label}[${index}] must cite an existing regular file for ${item.status}: ${item.path}`);
      }
    }
    observations.push({ path: item.path, status: item.status as RepositoryObservationStatus });
  }
  return observations;
}

async function normalizeOperations(
  raw: unknown,
  selected: readonly string[],
  classifications: ReadonlyMap<string, IncrementalMemoryClassification>,
  repoRoot: string,
): Promise<IncrementalMemoryOperation[]> {
  if (!Array.isArray(raw)) throw new Error("Incremental Memory delta has invalid operations");
  const selectedByKey = new Map(selected.map((name) => [name.toLowerCase(), name]));
  const seen = new Set<string>();
  const operations: IncrementalMemoryOperation[] = [];
  for (let index = 0; index < raw.length; index += 1) {
    const value = raw[index];
    assertRecord(value, `operations[${index}]`);
    assertExactKeys(value, [
      "name", "kind", "classification", "content", "contentSha256", "verdict", "preservedIn", "observations",
    ], `operations[${index}]`);
    const name = value.name;
    if (typeof name !== "string" || !isMemoryFilename(name)) throw new Error(`operations[${index}].name is invalid`);
    const key = name.toLowerCase();
    if (selectedByKey.get(key) !== name) throw new Error(`Operation is outside selected scope: ${name}`);
    if (seen.has(key)) throw new Error(`Incremental Memory operation is duplicated: ${name}`);
    seen.add(key);
    if (value.kind !== "create" && value.kind !== "rewrite" && value.kind !== "delete") {
      throw new Error(`Invalid operation kind for ${name}`);
    }
    if (value.classification !== "safe" && value.classification !== "private") {
      throw new Error(`Invalid classification for ${name}`);
    }
    if (value.classification !== classifications.get(key)) {
      throw new Error(`Operation classification disagrees with parent-derived inventory for ${name}`);
    }
    if (value.kind === "delete") {
      if ("content" in value || "contentSha256" in value) throw new Error(`Delete operation cannot contain content for ${name}`);
      if (typeof value.verdict !== "string" || !DELETE_VERDICTS.has(value.verdict as IncrementalDeleteVerdict)) {
        throw new Error(`Delete operation requires an allowed explicit staleness verdict for ${name}`);
      }
      if (!Array.isArray(value.preservedIn) || value.preservedIn.length === 0 || value.preservedIn.some((item) => typeof item !== "string" || !item)) {
        throw new Error(`Delete operation requires non-empty preservedIn for ${name}`);
      }
    } else {
      if (typeof value.content !== "string") throw new Error(`Write operation requires content for ${name}`);
      if (Buffer.byteLength(value.content, "utf8") > MAX_MEMORY_BYTES) throw new Error(`Write operation exceeds ${MAX_MEMORY_BYTES} bytes for ${name}`);
      if ("verdict" in value) throw new Error(`Only delete operations may provide a staleness verdict for ${name}`);
      if ("preservedIn" in value) throw new Error(`Only delete operations may provide preservedIn for ${name}`);
      if (value.contentSha256 !== undefined) {
        if (typeof value.contentSha256 !== "string" || !/^(?:sha256:)?[0-9a-f]{64}$/i.test(value.contentSha256)) {
          throw new Error(`Invalid contentSha256 for ${name}`);
        }
        if (value.contentSha256.replace(/^sha256:/i, "").toLowerCase() !== sha256Digest(value.content)) {
          throw new Error(`contentSha256 mismatch for ${name}`);
        }
      }
    }
    const observations = await normalizeObservations(value.observations, repoRoot, `operations[${index}].observations`);
    operations.push({
      name,
      kind: value.kind,
      classification: value.classification,
      ...(value.kind === "delete" ? {
        verdict: value.verdict as IncrementalDeleteVerdict,
        preservedIn: [...value.preservedIn as string[]],
      } : { content: value.content as string }),
      ...(typeof value.contentSha256 === "string" ? { contentSha256: value.contentSha256 } : {}),
      ...(observations.length > 0 ? { observations } : {}),
    });
  }
  await validateDeletePreservation(operations, repoRoot);
  return operations;
}

async function validateDeletePreservation(operations: readonly IncrementalMemoryOperation[], repoRoot: string): Promise<void> {
  const rewritten = new Set(
    operations
      .filter((operation) => operation.kind === "create" || operation.kind === "rewrite")
      .map((operation) => operation.name),
  );
  for (const operation of operations) {
    if (operation.kind !== "delete") continue;
    for (const target of operation.preservedIn ?? []) {
      if (rewritten.has(target)) continue;
      const candidate = repositoryCandidate(repoRoot, target);
      let stat: Awaited<ReturnType<typeof fs.lstat>>;
      try {
        stat = await fs.lstat(candidate);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") {
          throw new Error(`Delete preservedIn target must be an existing regular file or same-plan rewrite: ${target}`);
        }
        throw error;
      }
      if (stat.isSymbolicLink() || !stat.isFile()) {
        throw new Error(`Delete preservedIn target must be an existing regular file or same-plan rewrite: ${target}`);
      }
    }
  }
}

async function normalizeNewMemories(
  value: unknown,
  selected: readonly string[],
  run: ConsolidationRun,
): Promise<NewMemoryProposal[]> {
  if (!Array.isArray(value)) throw new Error("Incremental Memory delta newMemories must be an array");
  if (value.length === 0) return [];
  const snapshotFile = run.paths.snapshotFile || run.manifest.snapshotPath;
  const snapshotBytes = await readBoundedRegularFile(snapshotFile, MAX_SNAPSHOT_BYTES, "Incremental Memory snapshot");
  if (sha256Digest(snapshotBytes) !== run.manifest.snapshotDigest) {
    throw new Error("Incremental Memory snapshot digest does not match the consolidation run");
  }
  let snapshot: unknown;
  try {
    snapshot = JSON.parse(snapshotBytes.toString("utf8")) as unknown;
  } catch {
    throw new Error("Incremental Memory snapshot is not valid JSON");
  }
  if (
    !snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
    (snapshot as Record<string, unknown>).schemaVersion !== CONSOLIDATION_SCHEMA_VERSION ||
    (snapshot as Record<string, unknown>).runId !== run.manifest.runId ||
    (snapshot as Record<string, unknown>).scopeKey !== run.manifest.scopeKey
  ) {
    throw new Error("Incremental Memory snapshot identity does not match the consolidation run");
  }
  return normalizeNewMemoryProposals({ newMemories: value }, snapshot, selected);
}

function groundingReason(name: string): string {
  const reason = name.startsWith("project_")
    ? "No validated repository observation was supplied by the incremental operation."
    : "This Memory does not make a repository claim requiring path verification.";
  return reason.slice(0, MAX_GROUNDING_REASON_CHARS);
}

/**
 * Expand an untrusted delta-only incremental Memory plan into the exhaustive
 * shape consumed by validate-consolidate.py and applyConsolidationPlan.
 */
export async function expandIncrementalMemoryPlan(
  run: ConsolidationRun,
  selectedNames: readonly string[],
  deltaPlan: unknown,
): Promise<FullIncrementalMemoryPlan> {
  const selected = assertSelectedNames(selectedNames);
  const delta = validateDeltaIdentity(run, deltaPlan);
  const classifications = await readPrivateClassifications(run.manifest.harnessDir, selected);
  const operations = await normalizeOperations(delta.operations, selected, classifications, run.manifest.cwd);
  const newMemories = await normalizeNewMemories(delta.newMemories, selected, run);
  const operationByName = new Map(operations.map((operation) => [operation.name.toLowerCase(), operation]));
  const inventory = selected.map((name) => ({ name, classification: classifications.get(name.toLowerCase())! }));
  const staleness = selected.map((name) => {
    const operation = operationByName.get(name.toLowerCase());
    return { name, verdict: operation?.kind === "delete" ? operation.verdict! : "KEEP" as const };
  });
  const grounding = selected.map((name) => {
    const observations = operationByName.get(name.toLowerCase())?.observations ?? [];
    return {
      name,
      status: observations.length > 0 ? "VERIFIED" as const : name.startsWith("project_") ? "UNVERIFIABLE" as const : "N/A" as const,
      reason: observations.length > 0 ? "Repository observations were validated by the parent." : groundingReason(name),
      observations,
    };
  });
  const report = selected.map((name) => {
    const operation = operationByName.get(name.toLowerCase());
    const status = operation?.kind === "delete" ? operation.verdict! : "KEEP" as const;
    const summary = operation?.kind === "rewrite" || operation?.kind === "create"
      ? "Parent validated a bounded incremental rewrite."
      : operation?.kind === "delete"
        ? "Parent accepted a preservation-bound incremental deletion proposal."
        : "No incremental operation was proposed; Memory remains unchanged.";
    return { name, status, summary };
  });
  return {
    kind: "memory-consolidation-plan",
    version: CONSOLIDATION_SCHEMA_VERSION,
    schemaVersion: CONSOLIDATION_SCHEMA_VERSION,
    runId: run.manifest.runId,
    scopeKey: run.manifest.scopeKey,
    scopeDigest: run.manifest.scopeDigest,
    artifactHash: run.manifest.snapshotDigest,
    snapshotDigest: run.manifest.snapshotDigest,
    selected,
    operations,
    newMemories,
    inventory,
    clusters: selected.length > 0 ? [{ name: "incremental-selected", files: [...selected] }] : [],
    staleness,
    grounding,
    report,
  };
}

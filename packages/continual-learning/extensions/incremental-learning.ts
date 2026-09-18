import { constants as fsConstants } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { runPiWorker, type PiWorkerUsage } from "@fradser/pi-kit";
import { isMemoryFilename } from "./memory-files";
import { MAX_MEMORY_BYTES, MAX_MEMORY_FILES, sha256Digest, writeFileAtomic } from "./consolidation-run";
import { resolveMemoryPaths } from "./memory-paths";
import { buildMemorySelectorPrompt } from "./planner-prompts";

const MAX_TASK_SLICE_ENTRIES = 96;
const MAX_TASK_SLICE_BYTES = 512_000;
const MAX_SELECTOR_REASON_CHARS = 600;
const MAX_METADATA_DESCRIPTION_CHARS = 300;
const MAX_METADATA_TYPE_CHARS = 80;
const MAX_METADATA_PREFIX_BYTES = 8_192;
const MAX_MEMORY_INDEX_BYTES = 512_000;

export interface TaskSlice {
  kind: "learning-task-slice";
  version: 1;
  entries: unknown[];
}

export interface MemoryMetadata {
  name: string;
  classification: "safe" | "private";
  type: string;
  description: string;
}

export interface MemorySelection {
  kind: "incremental-memory-selection";
  version: 1;
  contextDigest: string;
  selected: string[];
  memory: boolean;
  harness: boolean;
  agents: boolean;
  reason: string;
}

export interface SelectedMemory extends MemoryMetadata {
  content: string;
}

export interface LearningDossier {
  kind: "incremental-learning-dossier";
  version: 1;
  contextDigest: string;
  taskSlice: TaskSlice;
  selectedMemories: SelectedMemory[];
  touchedPaths: string[];
  harnessEvents: string[];
  registeredSkills: string[];
  selection: MemorySelection;
}

export interface MemorySelectionResult {
  outcome: "selected" | "failed" | "cancelled";
  durationMs: number;
  selection?: MemorySelection;
  dossierPath?: string;
  dossierDigest?: string;
  usage?: PiWorkerUsage;
  error?: string;
}

interface FileIdentity {
  device: number;
  inode: number;
  size: number;
  modifiedMs: number;
}

interface IndexedMemory {
  metadata: MemoryMetadata;
  file: string;
  identity: FileIdentity;
}

function entryRole(entry: unknown): string {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return "";
  const record = entry as Record<string, unknown>;
  const message = record.message;
  if (message && typeof message === "object" && !Array.isArray(message)) {
    const role = (message as Record<string, unknown>).role;
    if (typeof role === "string") return role;
  }
  return typeof record.role === "string" ? record.role : "";
}

function jsonBytes(value: unknown): number {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

/** Extract exactly the newest completed user task from a session snapshot. */
export function currentTaskSlice(entries: readonly unknown[]): TaskSlice {
  const userIndexes = entries
    .map((entry, index) => entryRole(entry) === "user" ? index : -1)
    .filter((index) => index >= 0);
  if (userIndexes.length === 0) return { kind: "learning-task-slice", version: 1, entries: [] };

  let start = userIndexes[userIndexes.length - 1];
  if (start === entries.length - 1 && userIndexes.length > 1) start = userIndexes[userIndexes.length - 2];
  let end = entries.length;
  for (let index = start + 1; index < entries.length; index += 1) {
    if (entryRole(entries[index]) === "user") {
      end = index;
      break;
    }
  }
  const taskEntries = entries.slice(start, end);
  if (taskEntries.length <= MAX_TASK_SLICE_ENTRIES && jsonBytes(taskEntries) <= MAX_TASK_SLICE_BYTES) {
    return { kind: "learning-task-slice", version: 1, entries: [...taskEntries] };
  }
  const head: unknown[] = [];
  let totalBytes = 0;
  const finalEntry = taskEntries.at(-1);
  const finalBytes = finalEntry === undefined ? 0 : jsonBytes(finalEntry);
  for (const entry of taskEntries.slice(0, -1)) {
    const bytes = jsonBytes(entry);
    if (head.length >= MAX_TASK_SLICE_ENTRIES - 1 || totalBytes + bytes + finalBytes > MAX_TASK_SLICE_BYTES) break;
    head.push(entry);
    totalBytes += bytes;
  }
  return { kind: "learning-task-slice", version: 1, entries: finalEntry === undefined ? head : [...head, finalEntry] };
}

function frontmatterValue(content: string, key: string, maxChars: number): string {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
  if (!match) return "";
  const prefix = `${key}:`;
  const line = match[1].split(/\r?\n/).find((entry) => entry.startsWith(prefix));
  if (!line) return "";
  const raw = line.slice(prefix.length).trim();
  const unquoted = raw.length >= 2 && ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'")))
    ? raw.slice(1, -1)
    : raw;
  return unquoted.slice(0, maxChars);
}

function metadataFromContent(
  name: string,
  classification: MemoryMetadata["classification"],
  content: string,
  description?: string,
): MemoryMetadata {
  return {
    name,
    classification,
    type: frontmatterValue(content, "type", MAX_METADATA_TYPE_CHARS),
    description: (description ?? frontmatterValue(content, "description", MAX_METADATA_DESCRIPTION_CHARS))
      .slice(0, MAX_METADATA_DESCRIPTION_CHARS),
  };
}

async function readRegularPrefix(
  file: string,
  maxBytes: number,
  rejectTruncated = false,
): Promise<{ content: string; identity: FileIdentity } | undefined> {
  let handle: fs.FileHandle | undefined;
  try {
    handle = await fs.open(file, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
    const stat = await handle.stat();
    if (!stat.isFile() || (rejectTruncated && stat.size > maxBytes)) return undefined;
    const buffer = Buffer.alloc(Math.min(maxBytes, stat.size));
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    if (rejectTruncated && bytesRead < stat.size) return undefined;
    return {
      content: buffer.subarray(0, bytesRead).toString("utf8"),
      identity: { device: stat.dev, inode: stat.ino, size: stat.size, modifiedMs: stat.mtimeMs },
    };
  } catch {
    return undefined;
  } finally {
    await handle?.close().catch(() => {});
  }
}

function sameIdentity(left: FileIdentity, right: FileIdentity): boolean {
  return left.device === right.device && left.inode === right.inode &&
    left.size === right.size && left.modifiedMs === right.modifiedMs;
}

async function regularMemoryNames(root: string): Promise<string[]> {
  try {
    const stat = await fs.lstat(root);
    if (stat.isSymbolicLink() || !stat.isDirectory()) return [];
    return (await fs.readdir(root, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && !entry.isSymbolicLink() && isMemoryFilename(entry.name))
      .map((entry) => entry.name)
      .sort((left, right) => left.localeCompare(right))
      .slice(0, MAX_MEMORY_FILES);
  } catch {
    return [];
  }
}

function privateNamesFromIndex(index: string): Set<string> {
  const names = new Set<string>();
  for (const line of index.split(/\r?\n/)) {
    if (!/\(\s*harness[\s_-]+only\s*\)/i.test(line)) continue;
    const name = /[A-Za-z0-9][A-Za-z0-9_-]*\.md/.exec(line)?.[0];
    if (name && isMemoryFilename(name)) names.add(name.toLowerCase());
  }
  return names;
}

async function indexRoot(
  root: string,
  classification: (name: string) => MemoryMetadata["classification"],
): Promise<IndexedMemory[]> {
  const indexed: IndexedMemory[] = [];
  for (const name of await regularMemoryNames(root)) {
    const prefix = await readRegularPrefix(path.join(root, name), MAX_METADATA_PREFIX_BYTES);
    if (prefix === undefined) continue;
    indexed.push({
      metadata: metadataFromContent(name, classification(name), prefix.content),
      file: path.join(root, name),
      identity: prefix.identity,
    });
  }
  return indexed;
}

async function indexMemoryCorpus(cwd: string): Promise<IndexedMemory[]> {
  const paths = resolveMemoryPaths(cwd);
  const indexed = new Map<string, IndexedMemory>();
  if (paths.publicDir) {
    for (const entry of await indexRoot(paths.publicDir, () => "safe")) {
      indexed.set(entry.metadata.name.toLowerCase(), entry);
    }
  }

  const harnessIndex = await readRegularPrefix(path.join(paths.harnessDir, "MEMORY.md"), MAX_MEMORY_INDEX_BYTES);
  const privateNames = privateNamesFromIndex(harnessIndex?.content ?? "");
  for (const entry of await indexRoot(paths.harnessDir, (name) => {
    const key = name.toLowerCase();
    return privateNames.has(key) || !indexed.has(key) ? "private" : "safe";
  })) {
    indexed.set(entry.metadata.name.toLowerCase(), entry);
  }
  return [...indexed.values()].sort((left, right) => left.metadata.name.localeCompare(right.metadata.name));
}

function balancedObjects(text: string): string[] {
  const objects: string[] = [];
  let start = -1;
  let depth = 0;
  let quoted = false;
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (depth === 0) {
      if (char === "{") {
        start = index;
        depth = 1;
      }
      continue;
    }
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === "{") depth += 1;
    else if (char === "}") depth -= 1;
    if (depth === 0 && start >= 0) {
      objects.push(text.slice(start, index + 1));
      start = -1;
    }
  }
  return depth === 0 ? objects : [];
}

function isExactKeys(value: Record<string, unknown>): boolean {
  const expected = ["agents", "contextDigest", "harness", "kind", "memory", "reason", "selected", "version"];
  return Object.keys(value).sort().join("\0") === expected.join("\0");
}

function parseSelectionObject(
  raw: string,
  contextDigest: string,
  available: ReadonlyMap<string, string>,
): MemorySelection | undefined {
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (
      !value || typeof value !== "object" || Array.isArray(value) ||
      !isExactKeys(value) ||
      value.kind !== "incremental-memory-selection" ||
      value.version !== 1 ||
      value.contextDigest !== contextDigest ||
      !Array.isArray(value.selected) ||
      typeof value.memory !== "boolean" ||
      typeof value.harness !== "boolean" ||
      typeof value.agents !== "boolean" ||
      typeof value.reason !== "string" ||
      value.reason.length > MAX_SELECTOR_REASON_CHARS
    ) return undefined;

    const selected: string[] = [];
    const seen = new Set<string>();
    for (const rawName of value.selected) {
      if (typeof rawName !== "string" || !isMemoryFilename(rawName)) return undefined;
      const lower = rawName.toLowerCase();
      const exact = available.get(lower);
      if (!exact || exact !== rawName || seen.has(lower)) return undefined;
      seen.add(lower);
      selected.push(rawName);
    }
    return { ...value, selected } as unknown as MemorySelection;
  } catch {
    return undefined;
  }
}

function parseSelection(
  text: string,
  contextDigest: string,
  available: ReadonlyMap<string, string>,
): MemorySelection | undefined {
  const objects = balancedObjects(text);
  if (objects.length !== 1) return undefined;
  return parseSelectionObject(objects[0], contextDigest, available);
}

function taskSliceMetadata(taskSlice: TaskSlice): { touchedPaths: string[]; harnessEvents: string[] } {
  const paths = new Set<string>();
  const harnessEvents: string[] = [];
  const visit = (value: unknown): void => {
    if (typeof value === "string") {
      if (/harness|blocked|confirmation|policy|violation/i.test(value) && harnessEvents.length < 32) harnessEvents.push(value.slice(0, 1_000));
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    for (const key of ["path", "file", "filename"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && !path.isAbsolute(candidate) && !candidate.split(/[\\/]/).includes("..")) paths.add(candidate);
    }
    Object.values(record).forEach(visit);
  };
  taskSlice.entries.forEach(visit);
  return { touchedPaths: [...paths].slice(0, 64), harnessEvents };
}

async function buildDossier(
  contextDigest: string,
  taskSlice: TaskSlice,
  selection: MemorySelection,
  indexed: readonly IndexedMemory[],
  registeredSkills: readonly string[],
): Promise<LearningDossier | undefined> {
  const byName = new Map(indexed.map((entry) => [entry.metadata.name.toLowerCase(), entry]));
  const selectedMemories: SelectedMemory[] = [];
  for (const name of selection.selected) {
    const entry = byName.get(name.toLowerCase());
    if (!entry) return undefined;
    const body = await readRegularPrefix(entry.file, MAX_MEMORY_BYTES, true);
    if (!body || !sameIdentity(entry.identity, body.identity)) return undefined;
    selectedMemories.push({ ...entry.metadata, content: body.content });
  }
  const metadata = taskSliceMetadata(taskSlice);
  return {
    kind: "incremental-learning-dossier",
    version: 1,
    contextDigest,
    taskSlice,
    selectedMemories,
    touchedPaths: metadata.touchedPaths,
    harnessEvents: metadata.harnessEvents,
    registeredSkills: [...new Set(registeredSkills)].sort(),
    selection,
  };
}

export async function selectIncrementalLearning(input: {
  cwd: string;
  taskSlice: TaskSlice;
  contextDigest: string;
  outputDir: string;
  model?: string;
  signal?: AbortSignal;
  registeredSkills?: readonly string[];
}): Promise<MemorySelectionResult> {
  const startedAt = Date.now();
  const indexed = await indexMemoryCorpus(input.cwd);
  const metadata = indexed.map((entry) => entry.metadata);
  const available = new Map(metadata.map((entry) => [entry.name.toLowerCase(), entry.name]));
  const task = [
    "Task: select the minimum sufficient scope for one small incremental learning run.",
    `- Context digest: ${input.contextDigest}`,
    "- Current task slice:",
    JSON.stringify(input.taskSlice),
    "- Memory metadata index (filename, classification, type, description only):",
    JSON.stringify(metadata),
    "- Do not use tools, read Memory bodies, inspect read paths, or perform repository discovery.",
    "- Return delta-routing selection only; never propose or request full-corpus exploration.",
  ].join("\n");
  const prompt = buildMemorySelectorPrompt({ task });
  const result = await runPiWorker({
    prompt,
    cwd: input.cwd,
    tools: [],
    model: input.model,
    signal: input.signal,
    minimal: true,
  });
  const durationMs = Date.now() - startedAt;
  if (result.cancelled) return { outcome: "cancelled", durationMs, usage: result.usage, error: result.stderr };
  if (result.exitCode !== 0) return { outcome: "failed", durationMs, usage: result.usage, error: result.stderr };

  const selection = parseSelection(result.text, input.contextDigest, available);
  if (!selection) {
    return {
      outcome: "failed",
      durationMs,
      usage: result.usage,
      error: "selector returned an invalid or ambiguous incremental selection",
    };
  }

  const dossier = await buildDossier(input.contextDigest, input.taskSlice, selection, indexed, input.registeredSkills ?? []);
  if (!dossier) {
    return {
      outcome: "failed",
      durationMs: Date.now() - startedAt,
      usage: result.usage,
      error: "selected Memory changed or exceeded the bounded body limit",
    };
  }
  const text = `${JSON.stringify(dossier, null, 2)}\n`;
  const dossierPath = path.join(input.outputDir, "incremental-learning-dossier.json");
  await fs.mkdir(input.outputDir, { recursive: true });
  await writeFileAtomic(dossierPath, text, 0o600);
  return {
    outcome: "selected",
    durationMs: Date.now() - startedAt,
    selection,
    dossierPath,
    dossierDigest: sha256Digest(text),
    usage: result.usage,
  };
}

import { constants as fsConstants } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { runPiWorker, type PiWorkerUsage } from "@fradser/pi-kit";
import { isMemoryFilename } from "./memory-files";
import { MAX_MEMORY_BYTES, MAX_MEMORY_FILES, sha256Digest, writeFileAtomic } from "./consolidation-run";
import { resolveMemoryPaths } from "./memory-paths";
import { buildMemorySelectorPrompt, learningPlannerArgs } from "./planner-prompts";

const MAX_TASK_SLICE_ENTRIES = 96;
const MAX_TASK_SLICE_BYTES = 512_000;
const MAX_SELECTOR_REASON_CHARS = 600;
const MAX_METADATA_DESCRIPTION_CHARS = 300;
const MAX_METADATA_TYPE_CHARS = 80;
const MAX_METADATA_PREFIX_BYTES = 8_192;
const MAX_MEMORY_INDEX_BYTES = 512_000;
const CONTINUATION_REQUEST = /^(?:(?:please\s+)?(?:continue|go\s+on|go\s+ahead|proceed|retry|try\s+again)(?:\s+please)?|(?:请)?(?:继续(?:执行)?|接着|重试)(?:吧)?)[.!?。！？]*$/iu;

export interface TaskSlice {
  kind: "learning-task-slice";
  version: 1;
  entries: unknown[];
  /** Whole original entries omitted to keep the serialized evidence bounded. */
  omittedEntries?: number;
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

function isContinuationRequest(entry: unknown): boolean {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return false;
  const record = entry as Record<string, unknown>;
  const message = record.message && typeof record.message === "object" && !Array.isArray(record.message)
    ? record.message as Record<string, unknown> : record;
  const content = message.content;
  const text = typeof content === "string" ? content : Array.isArray(content)
    ? content.flatMap(block => block && typeof block === "object" && block.type === "text" && typeof block.text === "string" ? [block.text] : []).join("\n")
    : "";
  return CONTINUATION_REQUEST.test(text.trim());
}

/** Keep explicit continuation chains, without treating a new substantive request as the same task. */
export function currentTaskSlice(entries: readonly unknown[]): TaskSlice {
  const userIndexes = entries
    .map((entry, index) => entryRole(entry) === "user" ? index : -1)
    .filter((index) => index >= 0);
  if (userIndexes.length === 0) return { kind: "learning-task-slice", version: 1, entries: [] };

  let userPosition = userIndexes.length - 1;
  if (userIndexes[userPosition] === entries.length - 1 && userPosition > 0) userPosition -= 1;
  const end = userIndexes[userPosition + 1] ?? entries.length;
  while (userPosition > 0 && isContinuationRequest(entries[userIndexes[userPosition]])) {
    userPosition -= 1;
  }
  const taskEntries = entries.slice(userIndexes[userPosition], end);
  const slice: TaskSlice = { kind: "learning-task-slice", version: 1, entries: taskEntries };
  if (taskEntries.length <= MAX_TASK_SLICE_ENTRIES && jsonBytes(slice) <= MAX_TASK_SLICE_BYTES) return slice;

  // Reserve the entire JSON envelope, including omission metadata. Preserve
  // source entries byte-for-byte: clipping their text could alter quote evidence.
  const envelopeBytes = jsonBytes({ ...slice, entries: [], omittedEntries: taskEntries.length });
  let bytes = envelopeBytes + jsonBytes(taskEntries[0]);
  if (bytes > MAX_TASK_SLICE_BYTES) {
    throw new Error(`Original task request exceeds the ${MAX_TASK_SLICE_BYTES}-byte learning evidence limit.`);
  }
  const selected = new Set([0]);
  // Prefer the result and recent verification over early exploratory output.
  for (let index = taskEntries.length - 1; index > 0 && selected.size < MAX_TASK_SLICE_ENTRIES; index -= 1) {
    const size = jsonBytes(taskEntries[index]) + 1; // Array separator.
    if (bytes + size > MAX_TASK_SLICE_BYTES) continue;
    selected.add(index);
    bytes += size;
  }
  return {
    ...slice,
    entries: taskEntries.filter((_entry, index) => selected.has(index)),
    omittedEntries: taskEntries.length - selected.size,
  };
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

type ParsedSelection = { ok: true; selection: MemorySelection } | { ok: false; error: string };

function parseSelectionObject(
  raw: string,
  contextDigest: string,
  available: ReadonlyMap<string, string>,
): ParsedSelection {
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (!value || typeof value !== "object" || Array.isArray(value) || !isExactKeys(value)) {
      return { ok: false, error: "fields do not match the selection schema" };
    }
    if (value.kind !== "incremental-memory-selection" || value.version !== 1) {
      return { ok: false, error: "kind or version does not match the selection schema" };
    }
    if (value.contextDigest !== contextDigest) {
      return { ok: false, error: "context digest does not match this run" };
    }
    if (!Array.isArray(value.selected)) return { ok: false, error: "selected must be an array" };
    if (typeof value.memory !== "boolean" || typeof value.harness !== "boolean" || typeof value.agents !== "boolean") {
      return { ok: false, error: "phase routing flags must be booleans" };
    }
    if (typeof value.reason !== "string") {
      return { ok: false, error: "reason must be a string" };
    }
    // The reason is diagnostic prose carried inside a bounded artifact, so it is
    // clipped from the head instead of rejecting an otherwise valid selection:
    // a model that wrote more than the prompt asked for discarded a whole run
    // and reported only a formatting complaint. Structural violations — digest,
    // filenames, phase flags, exact keys, non-string reason — still fail closed.
    const reason =
      value.reason.length > MAX_SELECTOR_REASON_CHARS
        ? `${value.reason.slice(0, MAX_SELECTOR_REASON_CHARS - 1)}…`
        : value.reason;

    const selected: string[] = [];
    const seen = new Set<string>();
    for (const rawName of value.selected) {
      if (typeof rawName !== "string" || !isMemoryFilename(rawName)) {
        return { ok: false, error: "selected contains an invalid Memory filename" };
      }
      const lower = rawName.toLowerCase();
      const exact = available.get(lower);
      if (!exact || exact !== rawName) {
        return { ok: false, error: "selected filename is not an exact indexed Memory name" };
      }
      if (seen.has(lower)) return { ok: false, error: "selected contains a duplicate Memory filename" };
      seen.add(lower);
      selected.push(rawName);
    }
    return {
      ok: true,
      selection: {
        kind: value.kind, version: value.version, contextDigest, selected,
        memory: value.memory, harness: value.harness, agents: value.agents, reason,
      },
    };
  } catch {
    return { ok: false, error: "selection is not valid JSON" };
  }
}

function parseSelection(
  text: string,
  contextDigest: string,
  available: ReadonlyMap<string, string>,
): ParsedSelection {
  const objects = balancedObjects(text);
  if (objects.length !== 1) return { ok: false, error: "expected exactly one JSON object" };
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
  const prompt = buildMemorySelectorPrompt({ task, contextDigest: input.contextDigest });
  const result = await runPiWorker({
    prompt,
    cwd: input.cwd,
    tools: [],
    model: input.model,
    signal: input.signal,
    minimal: true,
    extraArgs: learningPlannerArgs(),
  });
  const durationMs = Date.now() - startedAt;
  if (result.cancelled) return { outcome: "cancelled", durationMs, usage: result.usage, error: result.stderr };
  if (result.exitCode !== 0) return { outcome: "failed", durationMs, usage: result.usage, error: result.stderr };

  const parsed = parseSelection(result.text, input.contextDigest, available);
  if (!parsed.ok) {
    return {
      outcome: "failed",
      durationMs,
      usage: result.usage,
      error: `selector rejected: ${parsed.error}`,
    };
  }
  const selection = parsed.selection;

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

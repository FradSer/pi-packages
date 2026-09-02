import { execFileSync } from "node:child_process";
import type { Api, Model, UserMessage } from "@earendil-works/pi-ai";
import type { ModelRegistry } from "@earendil-works/pi-coding-agent";
import { createHash, randomUUID } from "node:crypto";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { cacheDir, exposedDir, gatewayDir, leafSkillFile, legacyExposedDir } from "./paths";
import { isCollectionId, isSafeGitRef, isSlug, loadCollections, saveCollections, type RegistryCollection, type RegistryRoute } from "./registry";

export interface RepoSpec {
  repo: string;
  url: string;
  ref?: string;
  name: string;
  cacheKey: string;
}

export interface UpstreamSkill {
  name: string;
  description: string;
  path: string;
}

export interface WorkflowSummary {
  skill: string;
  summary: string;
}

export interface AddCollectionOptions {
  repo: string;
  id?: string;
  gateway?: string;
  description?: string;
  skills: "all" | string[];
  summaries?: WorkflowSummary[];
}

export interface AddCollectionResult {
  id: string;
  gateway: string;
  skills: string[];
  exposedDir: string;
}

export interface UpdateCollectionResult {
  id: string;
  kept: string[];
  dropped: string[];
  newUpstream: string[];
}

export interface SelectionUpdateResult {
  id: string;
  selected: string[];
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function cacheKeyWithRef(base: string, ref: string | undefined): string {
  if (!ref) return base;
  const digest = createHash("sha1").update(ref).digest("hex").slice(0, 10);
  return `${base}__ref-${digest}`;
}

export function parseRepoSpec(input: string): RepoSpec {
  const trimmed = input.trim();
  if (!trimmed) throw new Error("Repository is required");

  const directLocal = resolve(trimmed);
  const localRefMatch = trimmed.match(/^(.*?)[@#]([A-Za-z0-9_./-]+)$/);
  const localCandidate = localRefMatch?.[1] ?? trimmed;
  const local = existsSync(directLocal) ? directLocal : resolve(localCandidate);
  const localRef = existsSync(directLocal) ? undefined : localRefMatch?.[2];
  if (localRef && !isSafeGitRef(localRef)) throw new Error(`Unsupported git ref "${localRef}"`);
  if (existsSync(local) && statSync(local).isDirectory()) {
    const name = slugify(basename(local));
    if (!name) throw new Error(`Cannot derive a collection name from ${trimmed}`);
    const canonical = realpathSync(local);
    const digest = createHash("sha1").update(canonical).digest("hex").slice(0, 10);
    return { repo: canonical, url: canonical, ref: localRef, name, cacheKey: cacheKeyWithRef(`local__${name}__${digest}`, localRef) };
  }

  const match = trimmed.match(/^(?:https:\/\/github\.com\/)?([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[@#]([A-Za-z0-9_./-]+))?$/);
  if (!match) {
    throw new Error(`Unsupported repository spec "${trimmed}". Use owner/repo[@ref], a GitHub URL, or a local path.`);
  }
  const [, owner, name, ref] = match;
  if (ref && !isSafeGitRef(ref)) throw new Error(`Unsupported git ref "${ref}"`);
  return {
    repo: `${owner}/${name}`,
    url: `https://github.com/${owner}/${name}.git`,
    ref,
    name: slugify(name),
    cacheKey: cacheKeyWithRef(`github.com__${owner}__${name}`, ref),
  };
}

function git(args: string[], cwd?: string): string {
  return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function ensureDirectoryNotSymlink(path: string, label: string): void {
  try {
    const stats = lstatSync(path);
    if (stats.isSymbolicLink()) throw new Error(`Refusing symlinked managed ${label} directory: ${path}`);
    if (!stats.isDirectory()) throw new Error(`Managed ${label} path is not a directory: ${path}`);
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") {
      mkdirSync(path, { recursive: true });
      return;
    }
    throw error;
  }
}

function prepareManagedDirectories(root: string): void {
  ensureDirectoryNotSymlink(root, "root");
  ensureDirectoryNotSymlink(join(root, "cache"), "cache");
  ensureDirectoryNotSymlink(join(root, "exposed"), "exposed");
  ensureDirectoryNotSymlink(join(root, "exposed", "collections"), "collection exposure");
}

function copySkillFiles(source: string, destination: string): void {
  mkdirSync(destination, { recursive: true });
  for (const entry of readdirSync(source)) {
    if (entry === "SKILL.md") continue;
    const sourceEntry = join(source, entry);
    const destinationEntry = join(destination, entry);
    const stats = lstatSync(sourceEntry);
    if (stats.isSymbolicLink()) throw new Error(`Refusing symlinked skill resource: ${sourceEntry}`);
    if (stats.isDirectory()) copySkillFiles(sourceEntry, destinationEntry);
    else cpSync(sourceEntry, destinationEntry);
  }
}

function copyWrappedSkill(source: string, destination: string, skillName: string): void {
  const sourceSkillFile = join(source, "SKILL.md");
  if (!existsSync(sourceSkillFile) || lstatSync(sourceSkillFile).isSymbolicLink()) {
    throw new Error(`Selected skill "${skillName}" has an unsafe SKILL.md`);
  }
  copySkillFiles(source, destination);
  writeFileSync(join(destination, "SKILL.md"), wrapSkillContent(readFileSync(sourceSkillFile, "utf8"), skillName), "utf8");
}

function assertSafeCacheDirectory(destination: string): void {
  if (!existsSync(destination)) return;
  if (lstatSync(destination).isSymbolicLink()) {
    throw new Error(`Refusing symlinked cache directory: ${destination}`);
  }
  const gitDir = join(destination, ".git");
  if (!existsSync(gitDir)) return;
  const gitStats = lstatSync(gitDir);
  if (gitStats.isSymbolicLink() || !gitStats.isDirectory()) {
    throw new Error(`Refusing non-directory or symlinked cache metadata: ${gitDir}`);
  }
  if (containsSymlink(gitDir)) {
    throw new Error(`Refusing cache metadata containing symlinks: ${gitDir}`);
  }
}

function cloneOrUpdate(spec: RepoSpec, destination: string, ref?: string): string {
  assertSafeCacheDirectory(destination);
  const gitDir = join(destination, ".git");
  if (existsSync(gitDir)) {
    const configuredOrigin = git(["remote", "get-url", "origin"], destination);
    if (configuredOrigin !== spec.url) {
      rmSync(destination, { recursive: true, force: true });
    }
  }

  if (existsSync(join(destination, ".git"))) {
    const target = ref ?? spec.ref ?? "HEAD";
    if (target !== "HEAD" && !isSafeGitRef(target)) throw new Error(`Unsupported git ref "${target}"`);
    git(["fetch", "--quiet", "--depth", "1", "origin", "--", target], destination);
    git(["reset", "--quiet", "--hard", "FETCH_HEAD"], destination);
  } else {
    mkdirSync(dirname(destination), { recursive: true });
    rmSync(destination, { recursive: true, force: true });
    const branchArgs = spec.ref ? ["--branch", spec.ref] : [];
    git(["clone", "--quiet", "--depth", "1", ...branchArgs, spec.url, destination]);
  }
  return git(["rev-parse", "--abbrev-ref", "HEAD"], destination);
}

/** Clone (or refresh) the collection cache and return the scanned upstream skills. */
export function fetchCollectionSkills(root: string, spec: RepoSpec): { cache: string; ref: string; skills: UpstreamSkill[] } {
  return withLock(root, () => {
    prepareManagedDirectories(root);
    const cache = cacheDir(root, spec.cacheKey);
    const resolvedRef = cloneOrUpdate(spec, cache, spec.ref);
    return { cache, ref: spec.ref ?? resolvedRef, skills: scanSkills(cache) };
  });
}

function frontmatterValue(frontmatter: string, key: string): string | undefined {
  const match = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match?.[1]?.trim().replace(/^["']|["']$/g, "");
}

const FRONTMATTER_BLOCK = /^(---\r?\n)([\s\S]*?)(\r?\n---)(?=\r?\n|$)/;

function isIgnoredSkillDirectory(entry: string): boolean {
  return entry === ".git" || entry === "node_modules" || entry === "test" || entry === "tests" || entry === "testdata" || entry === "fixtures";
}

export function scanSkills(repoDir: string, dir = repoDir): UpstreamSkill[] {
  const skills: UpstreamSkill[] = [];
  for (const entry of readdirSync(dir)) {
    if (isIgnoredSkillDirectory(entry)) continue;
    const full = join(dir, entry);
    const stats = lstatSync(full);
    if (stats.isSymbolicLink()) {
      // Repositories such as marketingskills use symlinked metadata files
      // (for example CLAUDE.md). They are outside the skill tree and do not
      // need to be copied; directory symlinks remain rejected to avoid
      // traversing outside the cloned repository.
      let targetStats: ReturnType<typeof statSync>;
      try {
        targetStats = statSync(full);
      } catch {
        throw new Error(`Refusing broken symlink inside the repository: ${full.slice(repoDir.length + 1)}`);
      }
      if (targetStats.isDirectory()) {
        throw new Error(`Refusing symlinked entry inside the repository: ${full.slice(repoDir.length + 1)}`);
      }
      continue;
    }
    if (!stats.isDirectory()) continue;
    const skillFile = join(full, "SKILL.md");
    try {
      if (lstatSync(skillFile).isSymbolicLink()) {
        throw new Error(`Refusing symlinked SKILL.md: ${full.slice(repoDir.length + 1)}`);
      }
    } catch (error) {
      if (error instanceof Error && "code" in error && error.code === "ENOENT") {
        // This directory does not contain a SKILL.md file.
      } else if (error instanceof Error && error.message.startsWith("Refusing symlinked")) {
        throw error;
      }
    }
    if (existsSync(skillFile)) {
      const frontmatter = readFileSync(skillFile, "utf8").match(FRONTMATTER_BLOCK)?.[2];
      const name = frontmatter && frontmatterValue(frontmatter, "name");
      const description = frontmatter && frontmatterValue(frontmatter, "description");
      if (name && description && isSlug(name)) {
        const relative = full.slice(repoDir.length + 1).split(sep).join("/");
        skills.push({ name, description, path: relative });
      }
    }
    skills.push(...scanSkills(repoDir, full));
  }
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

function assertUniqueUpstreamNames(skills: UpstreamSkill[]): void {
  const seen = new Map<string, string>();
  for (const skill of skills) {
    const existing = seen.get(skill.name);
    if (existing) {
      throw new Error(`Duplicate upstream skill name "${skill.name}" at ${existing} and ${skill.path}`);
    }
    seen.set(skill.name, skill.path);
  }
}

const STOP_WORDS = new Set([
  "and", "the", "for", "with", "from", "that", "this", "use", "when", "you",
  "your", "can", "are", "all", "its", "into", "skill", "skills",
]);

/** Derive routing terms from a skill name and optional description. */
export function deriveTerms(name: string, description = ""): string[] {
  const tokens = name.split("-");
  const terms = new Set<string>([tokens.join(" "), ...tokens]);
  for (const token of tokens) {
    if (token.length > 3 && token.endsWith("s") && !/(ss|is|us)$/.test(token)) {
      terms.add(token.slice(0, -1));
    }
    if (token === "doc" || token === "docs") {
      terms.add("doc");
      terms.add("docs");
      terms.add("document");
      terms.add("documents");
    }
  }

  if (description) {
    const descWords = description.toLowerCase().match(/[a-z0-9]{3,}/g) ?? [];
    for (const word of descWords) {
      if (!STOP_WORDS.has(word)) terms.add(word);
    }
  }

  return [...terms];
}

function wrapSkillContent(content: string, name: string): string {
  const match = content.match(FRONTMATTER_BLOCK);
  if (!match) throw new Error(`Skill ${name} has no frontmatter block`);
  const eol = match[1].includes("\r") ? "\r\n" : "\n";
  let frontmatter = match[2].replace(/^name:[^\r\n]*/m, `name: ${name}`);
  if (/^disable-model-invocation:/m.test(frontmatter)) {
    frontmatter = frontmatter.replace(/^disable-model-invocation:[^\r\n]*/m, "disable-model-invocation: true");
  } else {
    frontmatter += `${eol}disable-model-invocation: true`;
  }
  return content.replace(match[0], `${match[1]}${frontmatter}${match[3]}`);
}

function yamlScalar(value: string): string {
  return JSON.stringify(value);
}

function fallbackWorkflowSummary(description: string): string {
  const primary = description.match(/^.*?[.!?](?=\s|$)/)?.[0]?.trim() ?? description.trim();
  const summary = primary
    .replace(/^When the user wants to\s+/i, "")
    .replace(/^When the user needs to\s+/i, "")
    .replace(/^When the user asks to\s+/i, "")
    .replace(/^Use when the user wants to\s+/i, "")
    .replace(/^Write\s+/i, "Write ")
    .replace(/\.$/, "");
  if (!summary) return "Apply this workflow.";
  return `${summary.charAt(0).toUpperCase()}${summary.slice(1)}.`;
}

function gatewayContent(root: string, collection: RegistryCollection, leaves: UpstreamSkill[]): string {
  const gateway = gatewayDir(root, collection.id, collection.gateway);
  const workflows = leaves.map((skill) => [
    `- \`${skill.name}\` — ${collection.routes.find((route) => route.skill === skill.name)?.summary ?? fallbackWorkflowSummary(skill.description)}`,
    `  Read \`${relative(gateway, leafSkillFile(root, collection.id, skill.name))}\` before applying this workflow.`,
  ]).flat();

  return [
    "---",
    `name: ${yamlScalar(collection.gateway)}`,
    `description: ${yamlScalar(collection.description)}`,
    "---",
    "",
    "## Available workflows",
    "",
    "Select the one workflow that best fits the user's request, then read its SKILL.md before proceeding.",
    "",
    ...workflows,
    "",
    "If no workflow clearly fits, ask the user to choose. Do not load unrelated workflows.",
    "",
  ].join("\n");
}

interface ExposedSwap {
  exposed: string;
  commit(): void;
  rollback(): void;
}

function swapExposed(temporary: string, exposed: string): ExposedSwap {
  const backup = `${exposed}.backup-${process.pid}-${randomUUID()}`;
  const hadPrevious = existsSync(exposed);
  if (hadPrevious) renameSync(exposed, backup);
  try {
    renameSync(temporary, exposed);
  } catch (error) {
    if (hadPrevious && existsSync(backup)) renameSync(backup, exposed);
    throw error;
  }
  return {
    exposed,
    commit: () => {
      try {
        rmSync(backup, { recursive: true, force: true });
      } catch {
        // The committed exposed tree and registry remain valid if backup cleanup fails.
      }
    },
    rollback: () => {
      rmSync(exposed, { recursive: true, force: true });
      if (hadPrevious && existsSync(backup)) renameSync(backup, exposed);
    },
  };
}

function materialize(root: string, collection: RegistryCollection, leaves: UpstreamSkill[], repoDir: string): ExposedSwap {
  ensureDirectoryNotSymlink(root, "root");
  ensureDirectoryNotSymlink(join(root, "exposed"), "exposed");
  ensureDirectoryNotSymlink(join(root, "exposed", "collections"), "collection exposure");
  const names = collection.routes.map((route) => route.skill);
  if (new Set(names).size !== names.length) {
    throw new Error(`Skill name collision in collection "${collection.id}": duplicate upstream skill names`);
  }

  const exposed = exposedDir(root, collection.id);
  const legacy = legacyExposedDir(root, collection.id);
  const temporary = join(root, "exposed", "collections", `.tmp-${collection.id}-${process.pid}`);
  rmSync(temporary, { recursive: true, force: true });
  mkdirSync(temporary, { recursive: true });
  const temporaryReal = realpathSync(temporary);
  try {
    for (const route of collection.routes) {
      const source = join(repoDir, route.path);
      const skillFile = join(source, "SKILL.md");
      if (!existsSync(skillFile)) {
        throw new Error(`Selected skill "${route.skill}" no longer exists at ${route.path}`);
      }
      const destination = join(temporary, "leaves", route.skill);
      copyWrappedSkill(source, destination, route.skill);
      const destinationReal = realpathSync(destination);
      if (!destinationReal.startsWith(temporaryReal + sep)) {
        throw new Error(`Refusing materialization escaping the exposed directory: ${route.path}`);
      }
    }
    const gateway = join(temporary, "gateway");
    mkdirSync(gateway, { recursive: true });
    writeFileSync(join(gateway, "SKILL.md"), gatewayContent(root, collection, leaves), "utf8");
    const swap = swapExposed(temporary, exposed);
    return {
      exposed,
      commit: () => {
        swap.commit();
        if (legacy !== join(root, "exposed", "collections")) {
          rmSync(legacy, { recursive: true, force: true });
        }
      },
      rollback: () => swap.rollback(),
    };
  } catch (error) {
    rmSync(temporary, { recursive: true, force: true });
    throw error;
  }
}

function pause(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function processIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function withLock<T>(root: string, action: () => T): T {
  ensureDirectoryNotSymlink(root, "root");
  const lock = join(root, ".lock");
  const ownerPath = join(lock, "owner");
  let acquired = false;
  for (let attempt = 0; attempt < 200 && !acquired; attempt += 1) {
    try {
      mkdirSync(lock);
      try {
        writeFileSync(ownerPath, `${process.pid}\n`, "utf8");
      } catch (error) {
        rmSync(lock, { recursive: true, force: true });
        throw error;
      }
      acquired = true;
    } catch (error) {
      if (acquired) throw error;
      try {
        const age = Date.now() - statSync(lock).mtimeMs;
        let owner: number | undefined;
        try {
          owner = Number.parseInt(readFileSync(ownerPath, "utf8"), 10);
        } catch {
          // An ownerless lock may be left by a process killed during initialization.
        }
        if (Number.isInteger(owner)) {
          if (processIsAlive(owner as number)) {
            pause(50);
            continue;
          }
          rmSync(lock, { recursive: true, force: true });
        } else if (age > 1_000) {
          rmSync(lock, { recursive: true, force: true });
        }
      } catch {
        // lock vanished or is still being initialized
      }
      pause(50);
    }
  }
  if (!acquired) throw new Error("Another skill-router operation is in progress; try again later");
  try {
    return action();
  } finally {
    rmSync(lock, { recursive: true, force: true });
  }
}

function summaryPrompt(skills: UpstreamSkill[]): string {
  return [
    "Write a compact navigation summary for each external workflow below.",
    "Return JSON only: an array of objects with exactly skill and summary string fields.",
    "Each summary is one sentence, 8–18 words, imperative or declarative, task-oriented, and preserves the source meaning.",
    "Do not use trigger wrappers such as 'When the user wants to'. Do not include quoted trigger phrases, cross-workflow references, file paths, Markdown, or extra keys.",
    "Include each listed skill exactly once, without inventing workflows.",
    "", "Workflows:",
    ...skills.map((skill) => `- ${skill.name}: ${skill.description}`),
  ].join("\n");
}

function responseText(response: { content: Array<{ type: string; text?: string }> }): string {
  return response.content.filter((part) => part.type === "text").map((part) => part.text ?? "").join("\n").trim();
}

function validWorkflowSummary(value: unknown): value is WorkflowSummary {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  if (keys.length !== 2 || !keys.includes("skill") || !keys.includes("summary")) return false;
  const { skill, summary } = value as WorkflowSummary;
  if (typeof skill !== "string" || typeof summary !== "string") return false;
  if (summary.includes("\n") || /[`*_#[\]<>]/.test(summary)) return false;
  if (/^(when the user|use when|also use)/i.test(summary)) return false;
  const words = summary.trim().split(/\s+/);
  return words.length >= 8 && words.length <= 18 && /[.!?]$/.test(summary.trim());
}

function fallbackWorkflowSummaries(skills: UpstreamSkill[]): WorkflowSummary[] {
  return skills.map((skill) => ({ skill: skill.name, summary: fallbackWorkflowSummary(skill.description) }));
}

export async function generateWorkflowSummaries(
  registry: ModelRegistry,
  model: Model<Api> | undefined,
  skills: UpstreamSkill[],
  signal?: AbortSignal,
): Promise<WorkflowSummary[]> {
  if (!model) return fallbackWorkflowSummaries(skills);
  try {
    const auth = await registry.getApiKeyAndHeaders(model);
    if (!auth.ok) return fallbackWorkflowSummaries(skills);
    const message: UserMessage = { role: "user", content: [{ type: "text", text: summaryPrompt(skills) }], timestamp: Date.now() };
    const response = await registry.complete(model, { systemPrompt: "You create concise, faithful workflow navigation labels.", messages: [message] }, {
      apiKey: auth.apiKey, headers: auth.headers, signal, maxTokens: Math.max(128, skills.length * 32), temperature: 0, cacheRetention: "none",
    });
    const parsed: unknown = JSON.parse(responseText(response));
    if (!Array.isArray(parsed)) throw new Error("Expected an array");
    if (!parsed.every(validWorkflowSummary)) throw new Error("Invalid workflow summary");
    const summaries = new Map(parsed.map((entry) => [entry.skill, entry.summary.trim()]));
    if (summaries.size !== skills.length || skills.some((skill) => !summaries.has(skill.name))) throw new Error("Incomplete workflow summaries");
    return skills.map((skill) => ({ skill: skill.name, summary: summaries.get(skill.name)! }));
  } catch {
    return fallbackWorkflowSummaries(skills);
  }
}

export function suggestCollectionDescription(skills: UpstreamSkill[]): string {
  const capabilities = [...new Set(skills.map((skill) => skill.name.replaceAll("-", " ")))];
  const list = capabilities.length < 2
    ? capabilities[0]
    : `${capabilities.slice(0, -1).join(", ")} and ${capabilities.at(-1)}`;
  return list
    ? `Expert workflows spanning ${list}.`
    : "Expert workflows for the selected collection.";
}

export function defaultCollectionId(spec: RepoSpec): string {
  return spec.url.startsWith("https://github.com/")
    ? slugify(spec.repo.replace("/", "-"))
    : spec.name;
}

function sharedSkillNamespace(skills: UpstreamSkill[]): string | undefined {
  const [first] = skills;
  if (!first) return undefined;
  const namespace = first.name.split("-", 1)[0];
  if (!namespace || !skills.every((skill) => skill.name.startsWith(`${namespace}-`))) return undefined;
  return namespace;
}

function assertNameSpaceAvailable(
  existing: RegistryCollection[],
  candidate: { id: string; gateway: string; sourceUrl?: string; sourceRef?: string },
): void {
  if (existing.some((collection) => collection.id === candidate.id)) {
    throw new Error(`Collection id "${candidate.id}" is already installed`);
  }
  if (existing.some((collection) => collection.source.url === candidate.sourceUrl && collection.source.ref === candidate.sourceRef)) {
    throw new Error(`Source ${candidate.sourceUrl}@${candidate.sourceRef} is already installed`);
  }
  if (existing.some((collection) => collection.gateway === candidate.gateway)) {
    throw new Error(`Gateway "${candidate.gateway}" is already used by another collection`);
  }
}

export async function addCollection(root: string, options: AddCollectionOptions): Promise<AddCollectionResult> {
  return withLock(root, () => addCollectionLocked(root, options));
}

function addCollectionLocked(root: string, options: AddCollectionOptions): AddCollectionResult {
  prepareManagedDirectories(root);
  const spec = parseRepoSpec(options.repo);
  const id = options.id ?? defaultCollectionId(spec);
  if (!isCollectionId(id)) throw new Error(`Invalid or reserved collection id "${id}"`);
  const existing = loadCollections(root);

  const cache = cacheDir(root, spec.cacheKey);
  const resolvedRef = cloneOrUpdate(spec, cache, spec.ref);
  const upstream = scanSkills(cache);
  if (upstream.length === 0) throw new Error(`No skills (SKILL.md with name and description) found in ${spec.repo}`);
  assertUniqueUpstreamNames(upstream);

  const selected =
    options.skills === "all"
      ? upstream
      : options.skills.map((name) => {
          const found = upstream.find((skill) => skill.name === name);
          if (!found) throw new Error(`Skill "${name}" not found. Available: ${upstream.map((skill) => skill.name).join(", ")}`);
          return found;
        });

  const namespace = sharedSkillNamespace(selected);
  const gateway = options.gateway
    ?? (namespace && !existing.some((collection) => collection.gateway === namespace) ? namespace : id);
  if (!isSlug(gateway)) throw new Error(`Invalid gateway name "${gateway}"`);

  assertNameSpaceAvailable(existing, {
    id,
    gateway,
    sourceUrl: spec.url,
    sourceRef: spec.ref ?? resolvedRef,
  });

  const summaryBySkill = new Map(options.summaries?.map((summary) => [summary.skill, summary.summary]));
  const collection: RegistryCollection = {
    id,
    gateway,
    mode: "suggest",
    enabled: true,
    description: options.description ?? suggestCollectionDescription(selected),
    source: { repo: spec.repo, url: spec.url, ref: spec.ref ?? resolvedRef, cacheKey: spec.cacheKey },
    routes: selected.map<RegistryRoute>((skill) => ({
      skill: skill.name,
      path: skill.path,
      terms: deriveTerms(skill.name, skill.description),
      summary: summaryBySkill.get(skill.name) ?? fallbackWorkflowSummary(skill.description),
    })),
  };

  const swap = materialize(root, collection, selected, cache);
  try {
    saveCollections(root, [...existing, collection]);
  } catch (error) {
    swap.rollback();
    throw error;
  }
  swap.commit();
  return { id, gateway, skills: selected.map((skill) => skill.name), exposedDir: swap.exposed };
}

function updateCollectionLocked(root: string, id: string): UpdateCollectionResult {
    prepareManagedDirectories(root);
    const collections = loadCollections(root);
    const collection = collections.find((entry) => entry.id === id);
    if (!collection) throw new Error(`Collection "${id}" is not installed`);

    const cache = cacheDir(root, collection.source.cacheKey);
    assertSafeCacheDirectory(cache);
    cloneOrUpdate(
      { repo: collection.source.repo, url: collection.source.url, ref: collection.source.ref, name: collection.id, cacheKey: collection.source.cacheKey },
      cache,
      collection.source.ref,
    );
    const upstream = scanSkills(cache);
    assertUniqueUpstreamNames(upstream);
    const upstreamByName = new Map(upstream.map((skill) => [skill.name, skill]));

    const kept = collection.routes.flatMap((route) => {
      const current = upstreamByName.get(route.skill);
      return current ? [{ ...route, path: current.path }] : [];
    });
    const dropped = collection.routes.filter((route) => !upstreamByName.has(route.skill)).map((route) => route.skill);
    const selected = new Set(collection.routes.map((route) => route.skill));

    const updated: RegistryCollection = {
      ...collection,
      routes: kept.map((route) => ({
        ...route,
        summary: route.summary ?? fallbackWorkflowSummary(upstreamByName.get(route.skill)!.description),
      })),
    };
    const swap = materialize(root, updated, upstream.filter((skill) => selected.has(skill.name)), cache);
    try {
      saveCollections(root, collections.map((entry) => (entry.id === id ? updated : entry)));
    } catch (error) {
      swap.rollback();
      throw error;
    }
    swap.commit();
    return { id, kept: kept.map((route) => route.skill), dropped, newUpstream: [...upstreamByName.keys()].filter((name) => !selected.has(name)) };
}

export async function updateCollection(root: string, id: string): Promise<UpdateCollectionResult> {
  return withLock(root, () => updateCollectionLocked(root, id));
}

export async function updateCollectionSelection(root: string, id: string, selectedNames: string[]): Promise<SelectionUpdateResult> {
  return withLock(root, () => {
    prepareManagedDirectories(root);
    const collections = loadCollections(root);
    const collection = collections.find((entry) => entry.id === id);
    if (!collection) throw new Error(`Collection "${id}" is not installed`);

    const cache = cacheDir(root, collection.source.cacheKey);
    assertSafeCacheDirectory(cache);
    const upstream = scanSkills(cache);
    assertUniqueUpstreamNames(upstream);
    const upstreamByName = new Map(upstream.map((skill) => [skill.name, skill]));
    const uniqueSelected = [...new Set(selectedNames)];
    const missing = uniqueSelected.filter((name) => !upstreamByName.has(name));
    if (missing.length > 0) throw new Error(`Skills not found upstream: ${missing.join(", ")}`);

    const existingRoutes = new Map(collection.routes.map((route) => [route.skill, route]));
    const routes = uniqueSelected.map<RegistryRoute>((name) => {
      const skill = upstreamByName.get(name)!;
      const existing = existingRoutes.get(name);
      return {
        skill: name,
        path: skill.path,
        terms: existing?.terms ?? deriveTerms(name, skill.description),
        summary: existing?.summary ?? fallbackWorkflowSummary(skill.description),
      };
    });
    const updated: RegistryCollection = { ...collection, routes };
    assertNameSpaceAvailable(
      collections.filter((entry) => entry.id !== id),
      { id, gateway: collection.gateway },
    );

    const swap = materialize(root, updated, routes.map((route) => upstreamByName.get(route.skill)!), cache);
    try {
      saveCollections(root, collections.map((entry) => (entry.id === id ? updated : entry)));
    } catch (error) {
      swap.rollback();
      throw error;
    }
    swap.commit();
    return { id, selected: uniqueSelected };
  });
}

export function collectionSkillNames(root: string, id: string): string[] {
  const collection = loadCollections(root).find((entry) => entry.id === id);
  if (!collection) throw new Error(`Collection "${id}" is not installed`);
  return scanSkills(cacheDir(root, collection.source.cacheKey)).map((skill) => skill.name);
}

export function removeCollection(root: string, id: string): void {
  withLock(root, () => {
    prepareManagedDirectories(root);
    const collections = loadCollections(root);
    if (!collections.some((collection) => collection.id === id)) throw new Error(`Collection "${id}" is not installed`);

    const exposed = exposedDir(root, id);
    const backup = `${exposed}.remove-${process.pid}-${randomUUID()}`;
    const hadExposed = existsSync(exposed);
    if (hadExposed) renameSync(exposed, backup);
    try {
      saveCollections(root, collections.filter((entry) => entry.id !== id));
    } catch (error) {
      if (hadExposed && existsSync(backup)) renameSync(backup, exposed);
      throw error;
    }
    const legacy = legacyExposedDir(root, id);
    if (legacy !== join(root, "exposed", "collections")) {
      rmSync(legacy, { recursive: true, force: true });
    }
    try {
      rmSync(backup, { recursive: true, force: true });
    } catch {
      // Registry state is already committed; an orphaned backup is harmless and can be cleaned later.
    }
  });
}

export function updateCollectionDescription(root: string, id: string, description: string): RegistryCollection {
  const normalized = description.trim();
  if (!normalized) throw new Error("Collection capability summary is required");
  return withLock(root, () => {
    prepareManagedDirectories(root);
    const collections = loadCollections(root);
    const collection = collections.find((entry) => entry.id === id);
    if (!collection) throw new Error(`Collection "${id}" is not installed`);

    const cache = cacheDir(root, collection.source.cacheKey);
    assertSafeCacheDirectory(cache);
    const upstreamByName = new Map(scanSkills(cache).map((skill) => [skill.name, skill]));
    const selected = collection.routes.map((route) => {
      const skill = upstreamByName.get(route.skill);
      if (!skill) throw new Error(`Selected skill "${route.skill}" no longer exists at ${route.path}`);
      return skill;
    });
    const updated = { ...collection, description: normalized };
    const swap = materialize(root, updated, selected, cache);
    try {
      saveCollections(root, collections.map((entry) => (entry.id === id ? updated : entry)));
    } catch (error) {
      swap.rollback();
      throw error;
    }
    swap.commit();
    return updated;
  });
}

export function setCollectionEnabled(root: string, id: string, enabled: boolean): RegistryCollection {
  return withLock(root, () => {
    prepareManagedDirectories(root);
    const collections = loadCollections(root);
    const collection = collections.find((entry) => entry.id === id);
    if (!collection) throw new Error(`Collection "${id}" is not installed`);
    const updated = { ...collection, enabled };
    saveCollections(root, collections.map((entry) => (entry.id === id ? updated : entry)));
    return updated;
  });
}

function containsSymlink(dir: string): boolean {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stats = lstatSync(full);
    if (stats.isSymbolicLink()) return true;
    if (stats.isDirectory() && containsSymlink(full)) return true;
  }
  return false;
}

function isExistingDirectoryWithoutSymlink(path: string): boolean {
  try {
    const stats = lstatSync(path);
    return stats.isDirectory() && !stats.isSymbolicLink();
  } catch {
    return false;
  }
}

export function exposedSkillPaths(root: string): string[] {
  const exposedRoot = join(root, "exposed");
  if (!isExistingDirectoryWithoutSymlink(root) || !isExistingDirectoryWithoutSymlink(exposedRoot)) return [];
  return loadCollections(root)
    .filter((collection) => collection.enabled)
    .map((collection) => gatewayDir(root, collection.id, collection.gateway))
    .filter((path) => {
      if (!isExistingDirectoryWithoutSymlink(path)) return false;
      try {
        if (!realpathSync(path).startsWith(realpathSync(exposedRoot) + sep)) return false;
        return !containsSymlink(path);
      } catch {
        return false;
      }
    });
}

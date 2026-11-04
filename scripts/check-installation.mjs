// Audit every workspace Pi package against the configured package sources.
// Usage: node scripts/check-installation.mjs [settings.json path]
// Exit 0 = clean, 1 = findings.

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const REPO_ROOT = resolve(SCRIPT_PATH, "../..");

export function isPiPackage(manifest) {
  return Boolean(manifest.pi) || (manifest.keywords ?? []).includes("pi-package");
}

export function packageSource(entry) {
  if (typeof entry === "string") return entry.trim();
  if (entry && typeof entry === "object" && typeof entry.source === "string") return entry.source.trim();
  return undefined;
}

/** Match npm names using the same scoped/versioned form as Pi's package manager. */
export function parseNpmPackageName(source) {
  if (!source.startsWith("npm:")) return undefined;
  const spec = source.slice("npm:".length).trim();
  const match = spec.match(/^(@?[^@]+(?:\/[^@]+)?)(?:@(.+))?$/);
  return match?.[1] ?? spec;
}

function isRemoteSource(source) {
  const trimmed = source.trim().toLowerCase();
  return (
    ["git:", "github:", "http:", "https:", "ssh:", "git+"].some((prefix) => trimmed.startsWith(prefix)) ||
    trimmed.startsWith("git@")
  );
}

function resolveLocalEntry(entry, settingsDir) {
  const trimmed = entry.trim();
  if (trimmed.startsWith("file://")) return resolve(fileURLToPath(trimmed));
  const expanded = trimmed === "~" ? homedir() : trimmed.startsWith("~/") ? join(homedir(), trimmed.slice(2)) : trimmed;
  return isAbsolute(expanded) ? resolve(expanded) : resolve(settingsDir, expanded);
}

function loadWorkspaceManifests(packagesDir) {
  const workspaceManifests = new Map();
  for (const directory of readdirSync(packagesDir)) {
    const manifestPath = join(packagesDir, directory, "package.json");
    if (!existsSync(manifestPath)) continue;
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    workspaceManifests.set(manifest.name, { directory, manifest });
  }
  return workspaceManifests;
}

function loadWorkspacePackages(packagesDir) {
  const workspacePackages = new Map();
  for (const [name, { directory, manifest }] of loadWorkspaceManifests(packagesDir)) {
    if (isPiPackage(manifest)) workspacePackages.set(name, directory);
  }
  return workspacePackages;
}

/**
 * Pi loads local package sources in place and never installs them, so a
 * checkout without a workspace install cannot resolve its own runtime
 * dependencies. Resolve each one the way Pi's loader does: a node_modules walk
 * up from the package directory.
 */
function unresolvedDependencies(packageDir, manifest) {
  const unresolved = [];
  for (const dependency of Object.keys(manifest.dependencies ?? {})) {
    let current = resolve(packageDir);
    let found = false;
    for (;;) {
      if (existsSync(join(current, "node_modules", dependency, "package.json"))) {
        found = true;
        break;
      }
      const parent = resolve(current, "..");
      if (parent === current) break;
      current = parent;
    }
    if (!found) unresolved.push(dependency);
  }
  return unresolved;
}

function workspaceInstallCommand() {
  return "bun install";
}

/**
 * Run the audit against an explicit settings file. Only package sources are
 * read from settings; unrelated values are never rendered in diagnostics.
 */
export function checkInstallation(options = {}) {
  const settingsPath = resolve(options.settingsPath ?? join(homedir(), ".pi", "agent", "settings.json"));
  const settingsDir = resolve(settingsPath, "..");
  const packagesDir = resolve(options.packagesDir ?? join(REPO_ROOT, "packages"));
  const workspacePackages = loadWorkspacePackages(packagesDir);
  const settings = JSON.parse(readFileSync(settingsPath, "utf8"));
  const rawEntries = Array.isArray(settings.packages) ? settings.packages : [];
  const entries = [];
  const sourceIndexes = [];
  const invalid = [];
  for (const [index, entry] of rawEntries.entries()) {
    const source = packageSource(entry);
    if (source) {
      entries.push(source);
      sourceIndexes.push(index);
    }
    else invalid.push(index);
  }

  const installedDirs = new Set();
  const npmNames = new Set();
  const dead = [];
  const broken = [];
  for (const [entryPosition, entry] of entries.entries()) {
    const index = sourceIndexes[entryPosition];
    const npmName = parseNpmPackageName(entry);
    if (npmName) {
      npmNames.add(npmName);
      continue;
    }
    if (isRemoteSource(entry)) continue;
    const directory = resolveLocalEntry(entry, settingsDir);
    const manifestPath = join(directory, "package.json");
    if (!existsSync(manifestPath)) {
      dead.push({ index, directory });
      continue;
    }
    installedDirs.add(directory);
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    const dependencies = unresolvedDependencies(directory, manifest);
    if (dependencies.length > 0) broken.push({ index, directory, name: manifest.name, dependencies });
  }

  const missing = [];
  for (const [name, directory] of workspacePackages) {
    const absoluteDirectory = resolve(packagesDir, directory);
    if (!installedDirs.has(absoluteDirectory) && !npmNames.has(name)) {
      missing.push({ name, directory });
    }
  }

  const logger = options.logger ?? console;
  const installCommand = workspaceInstallCommand();
  for (const { directory, name, dependencies } of broken) {
    const relativeDirectory = relative(packagesDir, directory);
    const displayDirectory = relativeDirectory.startsWith("..") || isAbsolute(relativeDirectory)
      ? directory
      : `packages/${relativeDirectory}`;
    const verb = dependencies.length === 1 ? "does" : "do";
    logger.log(`BROKEN   ${displayDirectory} (${name}) — ${dependencies.join(", ")} ${verb} not resolve`);
    logger.log(`         fix: ${installCommand}`);
  }
  for (const { name, directory } of missing) {
    logger.log(`MISSING  packages/${directory} (${name}) — not in configured Pi package sources`);
    logger.log(`         fix: pi install ${join(packagesDir, directory)}`);
  }
  for (const { index } of dead) {
    logger.log(`DEAD     settings.packages[${index}] — local package source has no package.json`);
  }
  for (const index of invalid) {
    logger.log(`INVALID  settings.packages[${index}] — expected a string or an object with a source string`);
  }
  if (missing.length === 0 && dead.length === 0 && invalid.length === 0 && broken.length === 0) {
    logger.log(`OK: ${workspacePackages.size} workspace pi packages installed, ${entries.length} settings entries checked.`);
  }
  return { missing, dead, invalid, broken, entries, workspacePackages };
}

export function isMainModule() {
  return process.argv[1] !== undefined && resolve(process.argv[1]) === SCRIPT_PATH;
}

if (isMainModule()) {
  try {
    const result = checkInstallation({ settingsPath: process.argv[2] });
    process.exitCode =
      result.missing.length + result.dead.length + result.invalid.length + result.broken.length > 0 ? 1 : 0;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

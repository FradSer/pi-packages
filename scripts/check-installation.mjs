// Audit every workspace Pi package against the configured package sources.
// Usage: node scripts/check-installation.mjs [settings.json path]
// Exit 0 = clean, 1 = findings.

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
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

function loadWorkspacePackages(packagesDir) {
  const workspacePackages = new Map();
  for (const directory of readdirSync(packagesDir)) {
    const manifestPath = join(packagesDir, directory, "package.json");
    if (!existsSync(manifestPath)) continue;
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    if (isPiPackage(manifest)) workspacePackages.set(manifest.name, directory);
  }
  return workspacePackages;
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
  for (const [entryPosition, entry] of entries.entries()) {
    const index = sourceIndexes[entryPosition];
    const npmName = parseNpmPackageName(entry);
    if (npmName) {
      npmNames.add(npmName);
      continue;
    }
    if (isRemoteSource(entry)) continue;
    const directory = resolveLocalEntry(entry, settingsDir);
    if (existsSync(join(directory, "package.json"))) installedDirs.add(directory);
    else dead.push({ index, directory });
  }

  const missing = [];
  for (const [name, directory] of workspacePackages) {
    const absoluteDirectory = resolve(packagesDir, directory);
    if (!installedDirs.has(absoluteDirectory) && !npmNames.has(name)) {
      missing.push({ name, directory });
    }
  }

  const logger = options.logger ?? console;
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
  if (missing.length === 0 && dead.length === 0 && invalid.length === 0) {
    logger.log(`OK: ${workspacePackages.size} workspace pi packages installed, ${entries.length} settings entries checked.`);
  }
  return { missing, dead, invalid, entries, workspacePackages };
}

export function isMainModule() {
  return process.argv[1] !== undefined && resolve(process.argv[1]) === SCRIPT_PATH;
}

if (isMainModule()) {
  try {
    const result = checkInstallation({ settingsPath: process.argv[2] });
    process.exitCode = result.missing.length + result.dead.length + result.invalid.length > 0 ? 1 : 0;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

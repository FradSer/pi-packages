import { execFileSync as defaultExecFileSync } from "node:child_process";
import {
  mkdtempSync as defaultMkdtempSync,
  readFileSync as defaultReadFileSync,
  readdirSync as defaultReaddirSync,
  rmSync as defaultRmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// pi-kit publishes first because the consumer packages use it at runtime.
export const PUBLISH_SCOPE = Object.freeze([
  "@fradser/pi-kit",
  "@fradser/pi-impeccable",
  "pi-continual-learning",
  "@fradser/pi-btw",
  "@fradser/pi-monitor",
  "@fradser/pi-utils",
  "@fradser/pi-vision",
  "@fradser/pi-plan-mode",
  "@fradser/pi-recap",
  "pi-keyboard",
  "@fradser/pi-agent-teams",
  "@fradser/pi-context",
  "pi-matt-pocock",
  "pi-skill-router",
  "pi-open-deskos",
]);

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const REPO_ROOT = resolve(dirname(SCRIPT_PATH), "..");

function errorCode(error) {
  return error && typeof error === "object" && typeof error.code === "string" ? error.code : undefined;
}

function errorStatus(error) {
  return error && typeof error === "object" && typeof error.status === "number" ? error.status : undefined;
}

function errorOutput(error, stream) {
  if (!error || typeof error !== "object") return "";
  const value = error[stream];
  return typeof value === "string" ? value : Buffer.isBuffer(value) ? value.toString("utf8") : "";
}

function errorStderr(error) {
  return errorOutput(error, "stderr");
}

function errorStdout(error) {
  return errorOutput(error, "stdout");
}

function structuredNpmErrorCode(error) {
  if (!error || typeof error !== "object") return undefined;
  for (const output of [error.stdout, error.stderr]) {
    const text = Buffer.isBuffer(output) ? output.toString("utf8").trim() : typeof output === "string" ? output.trim() : "";
    if (!text) continue;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.code === "string") return parsed.code;
      if (parsed?.error && typeof parsed.error.code === "string") return parsed.error.code;
    } catch {
      // npm normally writes its error code as a text line; inspect that below.
    }
  }
  return undefined;
}

function stderrNpmErrorCodes(error) {
  return [...errorStderr(error).matchAll(/^\s*npm\s+(?:error|err!)\s+code\s+(E\d+)\s*$/gim)].map(
    (match) => match[1],
  );
}

const REGISTRY_CONFLICT_CODES = new Set(["E409", "EPUBLISHCONFLICT"]);

/**
 * Return true when npm rejected a write because the registry already holds that
 * version. The main-branch retry runs right after the Changesets step published
 * the same versions, and npm can still answer the version query from a stale
 * edge cache, so the conflict means the version landed first, not that the
 * release failed.
 */
export function isRegistryConflict(error) {
  const explicitCode = errorCode(error);
  if (explicitCode) return REGISTRY_CONFLICT_CODES.has(explicitCode);
  const structuredCode = structuredNpmErrorCode(error);
  if (structuredCode) return REGISTRY_CONFLICT_CODES.has(structuredCode);
  const stderrCodes = stderrNpmErrorCodes(error);
  if (stderrCodes.length > 0) return stderrCodes.every((code) => REGISTRY_CONFLICT_CODES.has(code));
  if (errorStatus(error) === 409) return true;
  // pnpm reports the registry's own conflict without an npm error code line.
  return /E409\b|EPUBLISHCONFLICT\b|409 Conflict/i.test(errorStderr(error));
}

/** Return true only when npm explicitly reports that the requested version is absent. */
export function isRegistryNotFound(error) {
  const explicitCode = errorCode(error);
  if (explicitCode) return explicitCode === "E404";
  const structuredCode = structuredNpmErrorCode(error);
  if (structuredCode) return structuredCode === "E404";
  const stderrCodes = stderrNpmErrorCodes(error);
  if (stderrCodes.length > 0) return stderrCodes.every((code) => code === "E404");
  return errorStatus(error) === 404;
}

function registryQueryError(name, version, error) {
  const code = errorCode(error);
  const status = errorStatus(error);
  const detail = code ?? (status === undefined ? undefined : `status ${status}`);
  return new Error(
    `Unable to query npm for ${name}@${version}${detail ? ` (${detail})` : ""}; release stopped.`,
  );
}

function parseVersionOutput(output, name, version) {
  const text = Buffer.isBuffer(output) ? output.toString("utf8").trim() : String(output).trim();
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error(`npm returned an invalid version for ${name}@${version}; release stopped.`);
  }
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`npm returned no usable version for ${name}@${version}; release stopped.`);
  }
  if (value !== version) {
    throw new Error(`npm returned ${value} for ${name}@${version}; release stopped.`);
  }
  return value;
}

/** Query one exact package version. Undefined means npm explicitly returned 404. */
export function queryExactVersion(name, version, execFileSync = defaultExecFileSync) {
  const specifier = `${name}@${version}`;
  try {
    const output = execFileSync("npm", ["view", specifier, "version", "--json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return parseVersionOutput(output, name, version);
  } catch (error) {
    if (isRegistryNotFound(error)) return undefined;
    if (error instanceof Error && error.message.startsWith("npm returned")) throw error;
    throw registryQueryError(name, version, error);
  }
}

/** Read package manifests without touching npm or invoking any release command. */
export function loadWorkspacePackages(
  packagesDir = join(REPO_ROOT, "packages"),
  readFile = defaultReadFileSync,
  readdir = defaultReaddirSync,
) {
  const workspacePackages = new Map();
  for (const directory of readdir(packagesDir)) {
    const manifestPath = join(packagesDir, directory, "package.json");
    try {
      const manifest = JSON.parse(readFile(manifestPath, "utf8"));
      if (typeof manifest.name === "string" && typeof manifest.version === "string") {
        workspacePackages.set(manifest.name, { directory, version: manifest.version });
      }
    } catch (error) {
      if (errorCode(error) === "ENOENT") continue;
      throw error;
    }
  }
  return workspacePackages;
}

function packedFilename(packOutput) {
  const text = Buffer.isBuffer(packOutput) ? packOutput.toString("utf8").trim() : String(packOutput).trim();
  let result;
  try {
    result = JSON.parse(text);
  } catch {
    throw new Error("pnpm pack returned invalid JSON; packed manifest validation stopped.");
  }
  const filename = Array.isArray(result) ? result[0]?.filename : result?.filename;
  if (typeof filename !== "string" || filename.length === 0) {
    throw new Error("pnpm pack returned no tarball filename; packed manifest validation stopped.");
  }
  return filename;
}

/**
 * Pack one package and inspect the manifest that pnpm would publish.
 */
export function verifyPackedManifest(packageDir, options = {}) {
  const execFileSync = options.execFileSync ?? defaultExecFileSync;
  const mkdtemp = options.mkdtemp ?? defaultMkdtempSync;
  const remove = options.remove ?? defaultRmSync;
  const tempDir = mkdtemp(join(tmpdir(), "pi-pack-verify-"));
  try {
    const packOutput = execFileSync(
      "pnpm",
      ["--dir", packageDir, "pack", "--pack-destination", tempDir, "--json"],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
    const packedPath = packedFilename(packOutput);
    const tarballPath = isAbsolute(packedPath) ? packedPath : join(tempDir, packedPath);
    const manifestJson = execFileSync("tar", ["-xOf", tarballPath, "package/package.json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const manifest = JSON.parse(manifestJson);
    const allDeps = {
      ...manifest.dependencies,
      ...manifest.devDependencies,
      ...manifest.peerDependencies,
      ...manifest.optionalDependencies,
    };
    for (const [dependency, spec] of Object.entries(allDeps)) {
      if (typeof spec === "string" && spec.includes("workspace:")) {
        throw new Error(
          `Package in ${packageDir} has unresolved workspace protocol dependency "${dependency}": "${spec}" in packed tarball.`,
        );
      }
    }
    return manifest;
  } finally {
    remove(tempDir, { recursive: true, force: true });
  }
}

function resolveTargets(workspacePackages, publishScope) {
  return publishScope.map((name) => {
    const local = workspacePackages.get(name);
    if (!local) throw new Error(`Missing workspace package: ${name}`);
    return { name, directory: local.directory, version: local.version };
  });
}

function resolvePackedTargets(workspacePackages, publishScope) {
  const additional = [...workspacePackages.keys()].filter((name) => !publishScope.includes(name));
  return resolveTargets(workspacePackages, [...publishScope, ...additional]);
}

/** Select exact versions absent from npm while preserving the explicit kit-first order. */
export function selectUnpublishedPackages(targets, queryVersion) {
  return targets.filter(({ name, version }) => queryVersion(name, version) === undefined);
}

/**
 * Run release publication or registry-free packed-manifest validation.
 * Inject `execFileSync` and `verifyPackedManifest` in tests; the default path is
 * only used by the executable script and never during module import.
 */
export function publishRelease(options = {}) {
  const rootDir = options.rootDir ?? REPO_ROOT;
  const packagesDir = options.packagesDir ?? join(rootDir, "packages");
  const publishScope = options.publishScope ?? PUBLISH_SCOPE;
  const execFileSync = options.execFileSync ?? defaultExecFileSync;
  const workspacePackages =
    options.workspacePackages ?? loadWorkspacePackages(packagesDir, options.readFile, options.readdir);
  const targets = resolveTargets(workspacePackages, publishScope);
  const logger = options.logger ?? console;
  const checkOnly = options.checkOnly === true;
  const packedTargets = checkOnly ? resolvePackedTargets(workspacePackages, publishScope) : targets;
  const useProvenance = options.useProvenance ?? process.env.GITHUB_ACTIONS === "true";
  const verify =
    options.verifyPackedManifest ??
    ((packageDir) => verifyPackedManifest(packageDir, { execFileSync, readFile: options.readFile }));

  if (checkOnly) {
    for (const target of packedTargets) {
      logger.log(`Verifying packed manifest for ${target.name}...`);
      verify(join(packagesDir, target.directory));
    }
    logger.log(`Validated packed manifests for ${packedTargets.length} workspace packages.`);
    return { checked: packedTargets, published: [], skipped: [] };
  }

  // Query every package before publishing any package so a registry outage
  // cannot leave a release half-published before the error is discovered.
  const unpublished = selectUnpublishedPackages(
    targets,
    options.queryVersion ?? ((name, version) => queryExactVersion(name, version, execFileSync)),
  );
  const skipped = targets.filter((target) => !unpublished.includes(target));
  for (const target of unpublished) {
    const packageDir = join(packagesDir, target.directory);
    logger.log(`Verifying packed manifest for ${target.name}...`);
    verify(packageDir);
    logger.log(`Publishing ${target.name}@${target.version}`);
    try {
      // Capture both child streams instead of inheriting them: a registry
      // conflict is only visible on stderr, and an inherited stdio would send it
      // straight to the terminal, leaving the thrown error with just an exit
      // status. The captured text is re-emitted so the log keeps its detail.
      const stdout = execFileSync(
        "pnpm",
        [
          "publish",
          "--filter",
          target.name,
          ...(useProvenance ? ["--provenance"] : []),
          "--access",
          "public",
          "--no-git-checks",
        ],
        { cwd: rootDir, stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" },
      );
      if (typeof stdout === "string" && stdout.trim()) logger.log(stdout.trim());
    } catch (error) {
      for (const text of [errorStdout(error), errorStderr(error)]) {
        if (text.trim()) logger.log(text.trim());
      }
      if (!isRegistryConflict(error)) throw error;
      logger.log(`${target.name}@${target.version} is already published; continuing.`);
    }
  }
  if (unpublished.length === 0) logger.log("All selected packages are already published.");
  return { checked: targets, published: unpublished, skipped };
}

export function isMainModule() {
  return process.argv[1] !== undefined && resolve(process.argv[1]) === SCRIPT_PATH;
}

if (isMainModule()) {
  try {
    await publishRelease({ checkOnly: process.argv.includes("--check") });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

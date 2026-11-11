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
  "pi-sdlc",
  "@fradser/pi-loop",
  "@fradser/pi-subagents",
  "@fradser/pi-tasks",
  "@fradser/pi-impeccable",
  "pi-continual-learning",
  "@fradser/pi-btw",
  "@fradser/pi-monitor",
  "@fradser/pi-utils",
  "@fradser/pi-vision",
  "@fradser/pi-plan-mode",
  "@fradser/pi-goal",
  "@fradser/pi-recap",
  "@fradser/pi-magpie",
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
// "previously staged version" covers npm's staged publish: a trusted publish
// records the version before a registry read can see it.
const REGISTRY_CONFLICT_PATTERN = /E409\b|EPUBLISHCONFLICT\b|409 Conflict|previously staged version/i;

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
  // npm reports the registry's own conflict without an npm error code line, and
  // it can arrive on either captured stream, so search both.
  return REGISTRY_CONFLICT_PATTERN.test(`${errorStdout(error)}\n${errorStderr(error)}`);
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

/**
 * Pack one package with Bun and inspect the manifest npm would publish.
 *
 * Bun rewrites `workspace:*` dependencies to the versions recorded in
 * `bun.lock`, so a version bump must be followed by `bun install` before
 * packing; otherwise the tarball keeps the previous workspace version.
 * The caller owns the returned temporary directory and must clean it up.
 */
export function packAndVerify(packageDir, options = {}) {
  const execFileSync = options.execFileSync ?? defaultExecFileSync;
  const mkdtemp = options.mkdtemp ?? defaultMkdtempSync;
  const remove = options.remove ?? defaultRmSync;
  const tempDir = mkdtemp(join(tmpdir(), "pi-pack-verify-"));
  try {
    const output = execFileSync(
      options.packCommand ?? "bun",
      ["pm", "pack", "--destination", tempDir, "--quiet", "--cwd", packageDir],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
    const filename = Buffer.isBuffer(output)
      ? output.toString("utf8").trim().split("\n").pop()
      : String(output).trim().split("\n").pop();
    if (!filename) {
      throw new Error("bun pm pack returned no tarball filename; packed manifest validation stopped.");
    }
    const tarballPath = isAbsolute(filename) ? filename : join(tempDir, filename);
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
    return { manifest, tarballPath, cleanup: () => remove(tempDir, { recursive: true, force: true }) };
  } catch (error) {
    remove(tempDir, { recursive: true, force: true });
    throw error;
  }
}

/** Pack, validate and return only the manifest (pack validation mode). */
export function verifyPackedManifest(packageDir, options = {}) {
  const packed = packAndVerify(packageDir, options);
  try {
    return packed.manifest;
  } finally {
    packed.cleanup();
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
 * List the versions npm holds for one package name.
 *
 * The exact-version query cannot tell "this version is new" from "this package
 * does not exist", but only the second is outside CI's reach: npm trusted
 * publishing cannot create the first version of an unknown package and no trust
 * relationship can be configured for a package that has never been published.
 * An empty answer therefore means a manual first release, not a bump to ship.
 */
export function queryPublishedVersions(name, execFileSync = defaultExecFileSync) {
  try {
    const output = execFileSync("npm", ["view", name, "versions", "--json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const text = Buffer.isBuffer(output) ? output.toString("utf8") : String(output ?? "");
    if (!text.trim()) return [];
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed.filter((value) => typeof value === "string");
    if (typeof parsed === "string") return [parsed];
    throw new Error(`npm returned no usable version list for ${name}; release stopped.`);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("npm returned")) throw error;
    if (isRegistryNotFound(error)) return [];
    const code = errorCode(error);
    const status = errorStatus(error);
    const detail = code ?? (status === undefined ? undefined : `status ${status}`);
    throw new Error(
      `Unable to query npm for ${name} package versions${detail ? ` (${detail})` : ""}; release stopped.`,
    );
  }
}

/** Select the packages npm has no record of; only a human can publish those. */
export function selectFirstReleaseBootstrap(targets, queryVersions) {
  return targets.filter(({ name }) => queryVersions(name).length === 0);
}

/**
 * Run release publication or registry-free packed-manifest validation.
 * Inject `execFileSync`, `packAndVerify` and `verifyPackedManifest` in tests; the
 * default path is only used by the executable script and never during module
 * import.
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
  // The packed tarball is what npm uploads, so one pack feeds both validation
  // and publication.
  const verify =
    options.verifyPackedManifest ??
    ((packageDir) => verifyPackedManifest(packageDir, { execFileSync, readFile: options.readFile }));
  const pack =
    options.packAndVerify ?? ((packageDir) => packAndVerify(packageDir, { execFileSync }));

  if (checkOnly) {
    for (const target of packedTargets) {
      logger.log(`Verifying packed manifest for ${target.name}...`);
      verify(join(packagesDir, target.directory));
    }
    logger.log(`Validated packed manifests for ${packedTargets.length} workspace packages.`);
    return { checked: packedTargets, published: [], skipped: [] };
  }

  const queryVersions =
    options.queryPublishedVersions ?? ((name) => queryPublishedVersions(name, execFileSync));
  // Query every package before publishing any package so a registry outage
  // cannot leave a release half-published before the error is discovered.
  const unpublished = selectUnpublishedPackages(
    targets,
    options.queryVersion ?? ((name, version) => queryExactVersion(name, version, execFileSync)),
  );
  const firstRelease = selectFirstReleaseBootstrap(unpublished, queryVersions);
  const publishable = unpublished.filter((target) => !firstRelease.includes(target));
  const skipped = targets.filter((target) => !publishable.includes(target));
  for (const target of publishable) {
    const packageDir = join(packagesDir, target.directory);
    logger.log(`Verifying packed manifest for ${target.name}...`);
    const packed = pack(packageDir);
    try {
      logger.log(`Publishing ${target.name}@${target.version}`);
      // Capture both child streams instead of inheriting them: a registry
      // conflict is only visible on stderr, and an inherited stdio would send it
      // straight to the terminal, leaving the thrown error with just an exit
      // status. The captured text is re-emitted so the log keeps its detail.
      // The tarball is published instead of the directory because npm does not
      // understand the workspace protocol; bun already rewrote it.
      const stdout = execFileSync(
        "npm",
        [
          "publish",
          packed.tarballPath,
          ...(useProvenance ? ["--provenance"] : []),
          "--access",
          "public",
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
    } finally {
      packed.cleanup();
    }
  }
  if (firstRelease.length > 0) {
    logger.log(
      `Waiting for a manual first release, because trusted publishing cannot create a package npm has never seen: ${firstRelease
        .map(({ name, version }) => `${name}@${version}`)
        .join(", ")}.`,
    );
  }
  if (publishable.length === 0) logger.log("All selected packages are already published.");
  return { checked: targets, published: publishable, skipped, firstRelease };
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

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const packages = [
  // pi-kit publishes first: consumer packages depend on it.
  "@fradser/pi-kit",
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
];

const workspacePackages = new Map();
for (const directory of readdirSync("packages")) {
  const manifestPath = join("packages", directory, "package.json");
  try {
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    workspacePackages.set(manifest.name, { directory, version: manifest.version });
  } catch {
    // Ignore workspace directories without a package manifest.
  }
}

const unpublished = packages.filter((name) => {
  const local = workspacePackages.get(name);
  if (!local) throw new Error(`Missing workspace package: ${name}`);

  let published;
  try {
    published = execFileSync("npm", ["view", name, "version", "--json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    published = "";
  }

  return published !== JSON.stringify(local.version) && published !== local.version;
});

const useProvenance = process.env.GITHUB_ACTIONS === "true";

export function verifyPackedManifest(packageDir) {
  const tempDir = mkdtempSync(join(tmpdir(), "pi-pack-verify-"));
  try {
    const packOutput = execFileSync("pnpm", ["--dir", packageDir, "pack", "--pack-destination", tempDir], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const tarballMatch = packOutput.match(/([^\s]+\.tgz)/);
    const tarballPath = tarballMatch ? tarballMatch[1] : null;
    if (!tarballPath) throw new Error(`Could not determine tarball path from pnpm pack output: ${packOutput}`);
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
    for (const [dep, spec] of Object.entries(allDeps)) {
      if (typeof spec === "string" && spec.includes("workspace:")) {
        throw new Error(
          `Package in ${packageDir} has unresolved workspace protocol dependency "${dep}": "${spec}" in packed tarball.`
        );
      }
    }
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

for (const name of unpublished) {
  const result = workspacePackages.get(name);
  console.log(`Verifying packed manifest for ${name}...`);
  verifyPackedManifest(join("packages", result.directory));
  console.log(`Publishing ${name}@${result.version}`);
  execFileSync("pnpm", [
    "publish",
    "--filter",
    name,
    ...(useProvenance ? ["--provenance"] : []),
    "--access",
    "public",
    "--no-git-checks",
  ], { stdio: "inherit" });
}

if (unpublished.length === 0) console.log("All selected packages are already published.");

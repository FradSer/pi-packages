import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
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
  "pi-mattpocock",
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

for (const name of unpublished) {
  const result = workspacePackages.get(name);
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

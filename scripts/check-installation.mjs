// Audit: every workspace pi package must be installed in the live agent
// config, and every local settings entry must resolve to an existing package.
// Uninstalled packages fail silently (no error, only absence) — see
// .memory/feedback_pi_package_done_includes_live_install.md.
//
// Usage: node scripts/check-installation.mjs [settings.json path]
// Exit 0 = clean, 1 = findings.

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";

const settingsPath =
  process.argv[2] ?? join(homedir(), ".pi", "agent", "settings.json");
const settingsDir = resolve(settingsPath, "..");

function isPiPackage(manifest) {
  return Boolean(manifest.pi) || (manifest.keywords ?? []).includes("pi-package");
}

// Workspace pi packages: packages/<dir>/package.json with a pi manifest field.
const workspacePackages = new Map(); // name -> dir
for (const dir of readdirSync("packages")) {
  const manifestPath = join("packages", dir, "package.json");
  if (!existsSync(manifestPath)) continue;
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (isPiPackage(manifest)) workspacePackages.set(manifest.name, dir);
}

const settings = JSON.parse(readFileSync(settingsPath, "utf8"));
const entries = (settings.packages ?? []).filter((e) => typeof e === "string");

function resolveLocalEntry(entry) {
  const expanded = entry.startsWith("~") ? join(homedir(), entry.slice(1)) : entry;
  return isAbsolute(expanded) ? expanded : resolve(settingsDir, expanded);
}

const installedDirs = new Map(); // resolved dir -> entry
const npmNames = new Set();
const dead = [];
for (const entry of entries) {
  if (entry.startsWith("npm:")) {
    npmNames.add(entry.slice(4));
    continue;
  }
  if (entry.includes(":")) continue; // git:, ssh:, https: — not auditable locally
  const dir = resolveLocalEntry(entry);
  if (existsSync(join(dir, "package.json"))) {
    installedDirs.set(dir, entry);
  } else {
    dead.push({ entry, dir });
  }
}

const missing = [];
for (const [name, dir] of workspacePackages) {
  const abs = resolve("packages", dir);
  if (!installedDirs.has(abs) && !npmNames.has(name)) {
    missing.push({ name, dir });
  }
}

for (const { name, dir } of missing) {
  console.log(`MISSING  packages/${dir} (${name}) — not in ${settingsPath}`);
  console.log(`         fix: pi install ${resolve("packages", dir)}`);
}
for (const { entry, dir } of dead) {
  console.log(`DEAD     ${entry} — resolves to ${dir}, no package.json there`);
}
if (missing.length === 0 && dead.length === 0) {
  console.log(
    `OK: ${workspacePackages.size} workspace pi packages installed, ${entries.length} settings entries all resolve.`,
  );
}
process.exit(missing.length + dead.length > 0 ? 1 : 0);

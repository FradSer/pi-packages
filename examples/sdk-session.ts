/**
 * Optional createAgentSession harness for these local pi packages.
 *
 * Demonstrates loading package skills + extensions the same way the coding-agent
 * SDK examples do (see @earendil-works/pi-coding-agent examples/sdk).
 *
 * Run (from this repo, with the agent package resolvable):
 *   npx tsx examples/sdk-session.ts
 *
 * Requires a configured model/auth for a live prompt; discovery still works offline.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  createAgentSession,
  DefaultResourceLoader,
  getAgentDir,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const here = path.dirname(fileURLToPath(import.meta.url));
const packagesRoot = path.resolve(here, "..", "packages");

const packageRoots = [
  "code-context",
  "github",
  "git",
  "git-agent",
  "memory",
  "lark",
].map((name) => path.join(packagesRoot, name));

const extensionPaths = [
  path.join(packagesRoot, "memory/extensions/inject-memory.ts"),
  path.join(packagesRoot, "git/extensions/worktree.ts"),
  path.join(packagesRoot, "git-agent/extensions/validate-commit.ts"),
];

const resourceLoader = new DefaultResourceLoader({
  cwd: process.cwd(),
  agentDir: getAgentDir(),
  // Package manifests under packageRoots are discovered when installed via
  // settings packages; for a standalone demo we point at extension files and
  // rely on skillsOverride to surface package skill dirs if needed.
  additionalExtensionPaths: extensionPaths,
  skillsOverride: (current) => {
    // Keep discovered skills; log package skill name collisions for visibility.
    const byName = new Map<string, string[]>();
    for (const s of current.skills) {
      const list = byName.get(s.name) ?? [];
      list.push(s.filePath);
      byName.set(s.name, list);
    }
    for (const [name, paths] of byName) {
      if (paths.length > 1) {
        console.warn(`[collision] skill "${name}" from:`, paths);
      }
    }
    return current;
  },
});

await resourceLoader.reload();

const { skills, diagnostics: skillDiags } = resourceLoader.getSkills();
console.log(
  "Skills loaded:",
  skills.map((s) => s.name).sort(),
);
if (skillDiags.length) {
  console.log("Skill diagnostics:", skillDiags);
}

const { session } = await createAgentSession({
  resourceLoader,
  sessionManager: SessionManager.inMemory(),
});

console.log("createAgentSession OK");
console.log("Package roots (install via pi settings packages):");
for (const p of packageRoots) {
  console.log(" -", p);
}
console.log("Extensions wired:", extensionPaths.map((p) => path.basename(p)));

// Optional live turn when MODEL/auth is configured; otherwise dispose.
if (process.env.PI_SDK_LIVE === "1") {
  try {
    session.subscribe((event) => {
      if (
        event.type === "message_update" &&
        event.assistantMessageEvent.type === "text_delta"
      ) {
        process.stdout.write(event.assistantMessageEvent.delta);
      }
    });
    await session.prompt("Reply with a one-line hello and list available /skill names you know.");
    console.log();
  } finally {
    session.dispose();
  }
} else {
  session.dispose();
  console.log("Skipped live prompt (set PI_SDK_LIVE=1 to exercise the model).");
}

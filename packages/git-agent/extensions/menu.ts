/**
 * @fradser/git-agent — native pi /git-agent command menu.
 *
 * Replaces the /skill:commit|commit-and-push|init|related skill surface with a
 * pi-native command menu (same pattern as @fradser/memory's /memory command):
 *
 *   /git-agent
 *     1. Commit changes        (procedures/commit.md)
 *     2. Commit and push       (procedures/commit-and-push.md)
 *     3. Init / optimize       (procedures/init.md)
 *     4. Related files & tests (procedures/related.md)
 *
 * Selecting an item embeds the full procedure into a follow-up user message
 * via pi.sendUserMessage — no skill doc, no model-side path lookup.
 * `{{PKG_DIR}}` is substituted with the resolved package dir at send time.
 *
 * before_agent_start injects a short guidance block so natural-language
 * requests ("commit this", "commit and push") still route to the procedures
 * even without a skill surface. `/git-agent <keyword>` (e.g. `/git-agent
 * commit --co-author "x"`) runs that workflow directly, skipping the menu.
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";

const PKG_PROBE = path.join("procedures", "commit.md");

interface MenuItem {
  label: string;
  procedure: string;
  keywords: string[];
}

const MENU: MenuItem[] = [
  { label: "Commit changes", procedure: "commit.md", keywords: ["commit"] },
  { label: "Commit and push", procedure: "commit-and-push.md", keywords: ["commit-and-push", "push"] },
  { label: "Init / optimize", procedure: "init.md", keywords: ["init"] },
  { label: "Related files & tests", procedure: "related.md", keywords: ["related"] },
];

const GUIDANCE = `
## Git automation (git-agent)

- **Commit**: follow {{PKG_DIR}}/procedures/commit.md — call the \`session_context\` tool first, build a 2-4 sentence intent from the session, then run \`git-agent commit --intent "<intent>"\` (add \`--no-stage\` when files are already staged; retry with \`--free\` on auth errors).
- **Commit and push**: {{PKG_DIR}}/procedures/commit-and-push.md — same commit, then \`git push\`.
- **Init / optimize**: {{PKG_DIR}}/procedures/init.md — \`git-agent init --scope --force\`, \`--gitignore\`, or both.
- **Related files & tests**: {{PKG_DIR}}/procedures/related.md — \`git-agent related [--tests|-o json] <paths>\`.

The \`/git-agent\` menu lists the same workflows.
`;

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve the @fradser/git-agent package dir. Covers npm/git installs under
 * ~/.pi/agent (via settings.json packages, including relative-path dev
 * checkouts) and the monorepo layout relative to cwd.
 */
async function resolvePackageDir(): Promise<string> {
  try {
    const settingsRaw = await fs.readFile(
      path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "settings.json"),
      "utf-8",
    );
    const settings = JSON.parse(settingsRaw) as { packages?: string[] };
    const base = path.join(os.homedir(), CONFIG_DIR_NAME, "agent");
    for (const p of settings.packages ?? []) {
      if (typeof p !== "string" || !p.includes("git-agent")) continue;
      const dir = path.normalize(path.join(base, p));
      if (await pathExists(path.join(dir, PKG_PROBE))) {
        return dir;
      }
    }
  } catch {
    // settings.json missing/unreadable — fall through
  }

  const fromCwd = path.join(process.cwd(), "packages", "git-agent");
  if (await pathExists(path.join(fromCwd, PKG_PROBE))) {
    return fromCwd;
  }
  return process.cwd();
}

async function loadProcedure(pkgDir: string, name: string): Promise<string> {
  const file = path.join(pkgDir, "procedures", name);
  const procedure = await fs.readFile(file, "utf-8");
  return procedure.replaceAll("{{PKG_DIR}}", pkgDir);
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("git-agent", {
    description: "git-agent workflows: AI commit, commit+push, init/optimize, related (co-change)",
    handler: async (args, ctx) => {
      const pkgDir = await resolvePackageDir();
      const argText = (args ?? "").trim();

      // Shorthand: /git-agent <keyword> [args] runs that workflow directly.
      let item = MENU.find((m) =>
        m.keywords.some((k) => argText === k || argText.startsWith(`${k} `)),
      );
      let invocation = item ? argText.replace(/^\S+\s*/, "") : argText;

      if (!item) {
        if (!ctx.hasUI) {
          ctx.ui.notify(`/git-agent: ${MENU.map((m) => m.label).join(" | ")}`, "info");
          return;
        }
        const choice = await ctx.ui.select("git-agent workflows:", MENU.map((m) => m.label));
        if (!choice) return; // cancelled
        item = MENU.find((m) => m.label === choice);
        if (!item) return;
      }

      let procedure: string;
      try {
        procedure = await loadProcedure(pkgDir, item.procedure);
      } catch (err: unknown) {
        ctx.ui.notify(
          `Could not load procedure (${path.join(pkgDir, "procedures", item.procedure)}): ${(err as Error).message}`,
          "error",
        );
        return;
      }

      const invocationLine = invocation ? `\nInvocation args: ${invocation}` : "";
      pi.sendUserMessage(`Run the "${item.label}" workflow.${invocationLine}\n\n${procedure}`, {
        deliverAs: "followUp",
      });
    },
  });

  pi.on("before_agent_start", async (event) => {
    const pkgDir = await resolvePackageDir();
    return { systemPrompt: event.systemPrompt + GUIDANCE.replaceAll("{{PKG_DIR}}", pkgDir) };
  });
}

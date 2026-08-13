/**
 * @fradser/git — native pi /git command menu.
 *
 * Replaces the /skill:start-*|finish-*|commit|commit-and-push skill surface
 * with a pi-native command menu (same pattern as @fradser/memory's /memory):
 *
 *   /git
 *     1. Start feature   (procedures/start.md,  {{WORKFLOW_TYPE}}=feature)
 *     2. Start hotfix    (procedures/start.md,  {{WORKFLOW_TYPE}}=hotfix)
 *     3. Start release   (procedures/start.md,  {{WORKFLOW_TYPE}}=release)
 *     4. Finish feature  (procedures/finish.md, {{WORKFLOW_TYPE}}=feature)
 *     5. Finish hotfix   (procedures/finish.md, {{WORKFLOW_TYPE}}=hotfix)
 *     6. Finish release  (procedures/finish.md, {{WORKFLOW_TYPE}}=release)
 *     7. Commit changes  (procedures/commit.md)
 *     8. Commit and push (procedures/commit-and-push.md)
 *
 * Selecting an item embeds the full procedure (with {{PKG_DIR}} and
 * {{WORKFLOW_TYPE}} substituted) into a follow-up user message via
 * pi.sendUserMessage — no skill doc, no model-side path lookup.
 * `/git <keyword>` (e.g. `/git start-feature dark-mode`) runs that workflow
 * directly, skipping the menu.
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";

const PKG_PROBE = path.join("procedures", "start.md");

interface MenuItem {
  label: string;
  procedure: string;
  keywords: string[];
  workflowType?: "feature" | "hotfix" | "release";
}

const MENU: MenuItem[] = [
  { label: "Start feature", procedure: "start.md", keywords: ["start-feature", "start feature"], workflowType: "feature" },
  { label: "Start hotfix", procedure: "start.md", keywords: ["start-hotfix", "start hotfix"], workflowType: "hotfix" },
  { label: "Start release", procedure: "start.md", keywords: ["start-release", "start release"], workflowType: "release" },
  { label: "Finish feature", procedure: "finish.md", keywords: ["finish-feature", "finish feature"], workflowType: "feature" },
  { label: "Finish hotfix", procedure: "finish.md", keywords: ["finish-hotfix", "finish hotfix"], workflowType: "hotfix" },
  { label: "Finish release", procedure: "finish.md", keywords: ["finish-release", "finish release"], workflowType: "release" },
  { label: "Commit changes", procedure: "commit.md", keywords: ["commit"] },
  { label: "Commit and push", procedure: "commit-and-push.md", keywords: ["commit-and-push", "commit and push", "push"] },
];

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve the @fradser/git package dir. Covers npm/git installs under
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
      if (typeof p !== "string") continue;
      const dir = path.normalize(path.join(base, p));
      if (path.basename(dir) !== "git") continue;
      if (await pathExists(path.join(dir, PKG_PROBE))) {
        return dir;
      }
    }
  } catch {
    // settings.json missing/unreadable — fall through
  }

  const fromCwd = path.join(process.cwd(), "packages", "git");
  if (await pathExists(path.join(fromCwd, PKG_PROBE))) {
    return fromCwd;
  }
  return process.cwd();
}

function substitute(procedure: string, pkgDir: string, workflowType?: string): string {
  return procedure
    .replaceAll("{{PKG_DIR}}", pkgDir)
    .replaceAll("{{WORKFLOW_TYPE}}", workflowType ?? "");
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("git", {
    description: "GitFlow workflows: start/finish feature, hotfix, release; commit; commit and push",
    handler: async (args, ctx) => {
      const pkgDir = await resolvePackageDir();
      const argText = (args ?? "").trim();

      // Shorthand: /git <keyword> [args] runs that workflow directly.
      let item = MENU.find((m) =>
        m.keywords.some((k) => argText === k || argText.startsWith(`${k} `)),
      );
      let invocation = argText;
      if (item) {
        const matched = item.keywords.find((k) => argText === k || argText.startsWith(`${k} `));
        if (matched) invocation = argText.slice(matched.length).trim();
      }

      if (!item) {
        if (!ctx.hasUI) {
          ctx.ui.notify(`/git: ${MENU.map((m) => m.label).join(" | ")}`, "info");
          return;
        }
        const choice = await ctx.ui.select("GitFlow workflows:", MENU.map((m) => m.label));
        if (!choice) return; // cancelled
        item = MENU.find((m) => m.label === choice);
        if (!item) return;
      }

      let procedure: string;
      try {
        procedure = await fs.readFile(path.join(pkgDir, "procedures", item.procedure), "utf-8");
      } catch (err: unknown) {
        ctx.ui.notify(
          `Could not load procedure (${path.join(pkgDir, "procedures", item.procedure)}): ${(err as Error).message}`,
          "error",
        );
        return;
      }
      procedure = substitute(procedure, pkgDir, item.workflowType);

      const invocationLine = invocation ? `\nInvocation args: ${invocation}` : "";
      pi.sendUserMessage(`Run the "${item.label}" workflow.${invocationLine}\n\n${procedure}`, {
        deliverAs: "followUp",
      });
    },
  });
}

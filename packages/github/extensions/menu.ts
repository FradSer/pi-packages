/**
 * @fradser/github — native pi /github command menu.
 *
 * Replaces the /skill:create-issues|create-pr|resolve-issues|review-pr skill
 * surface with a pi-native command menu (same pattern as @fradser/memory's
 * /memory command):
 *
 *   /github
 *     1. Create issue(s)     (procedures/create-issues.md)
 *     2. Create pull request (procedures/create-pr.md)
 *     3. Resolve issue(s)    (procedures/resolve-issues.md)
 *     4. Review PR           (procedures/review-pr.md)
 *
 * Selecting an item embeds the full procedure (with {{PKG_DIR}} substituted)
 * into a follow-up user message via pi.sendUserMessage — no skill doc, no
 * model-side path lookup. `/github <keyword>` (e.g. `/github review-pr 123`,
 * `/github create-pr Closes #456 --draft`) runs that workflow directly,
 * skipping the menu.
 *
 * before_agent_start injects a short guidance block so natural-language
 * requests ("create a PR", "review PR #123", "resolve issue #4") still route
 * to the procedures even without a skill surface.
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";

const PKG_PROBE = path.join("procedures", "create-pr.md");

interface MenuItem {
  label: string;
  procedure: string;
  keywords: string[];
}

const MENU: MenuItem[] = [
  { label: "Create issue(s)", procedure: "create-issues.md", keywords: ["create-issues", "create issue", "create issues"] },
  { label: "Create pull request", procedure: "create-pr.md", keywords: ["create-pr", "create pr", "pr"] },
  { label: "Resolve issue(s)", procedure: "resolve-issues.md", keywords: ["resolve-issues", "resolve issue", "resolve issues"] },
  { label: "Review PR", procedure: "review-pr.md", keywords: ["review-pr", "review pr", "review"] },
];

const GUIDANCE = `
## GitHub workflows

- **Create a PR**: follow {{PKG_DIR}}/procedures/create-pr.md — quality/security gate first, then the review loop via {{PKG_DIR}}/procedures/review-pr.md. This is the only PR-creating path; never call \`gh pr create\` outside it.
- **Review a PR / watch CI**: follow {{PKG_DIR}}/procedures/review-pr.md — poll via {{PKG_DIR}}/scripts/review-loop.sh, triage comments skeptically, merge decision by asking the user directly in the conversation.
- **Resolve an issue**: follow {{PKG_DIR}}/procedures/resolve-issues.md — worktree + TDD, then hand PR creation to the create-pr procedure.
- **File issues**: follow {{PKG_DIR}}/procedures/create-issues.md.

The \`/github\` menu lists the same workflows.
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
 * Resolve the @fradser/github package dir. Covers npm/git installs under
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
      if (typeof p !== "string" || !p.includes("github")) continue;
      const dir = path.normalize(path.join(base, p));
      if (await pathExists(path.join(dir, PKG_PROBE))) {
        return dir;
      }
    }
  } catch {
    // settings.json missing/unreadable — fall through
  }

  const fromCwd = path.join(process.cwd(), "packages", "github");
  if (await pathExists(path.join(fromCwd, PKG_PROBE))) {
    return fromCwd;
  }
  return process.cwd();
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("github", {
    description: "GitHub workflows: create issues, create PR, resolve issues, review PR (CI + comments)",
    handler: async (args, ctx) => {
      const pkgDir = await resolvePackageDir();
      const argText = (args ?? "").trim();

      // Shorthand: /github <keyword> [args] runs that workflow directly.
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
          ctx.ui.notify(`/github: ${MENU.map((m) => m.label).join(" | ")}`, "info");
          return;
        }
        const choice = await ctx.ui.select("GitHub workflows:", MENU.map((m) => m.label));
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
      procedure = procedure.replaceAll("{{PKG_DIR}}", pkgDir);

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

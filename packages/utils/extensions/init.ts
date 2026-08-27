/**
 * pi-utils — repository contributor-guide initialization command.
 *
 * /init delegates repository inspection and AGENTS.md maintenance to the
 * active agent so the generated guidance reflects the actual project.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const INIT_PROMPT = `
Generate and maintain contributor guidance for this repository.

Starting directory: __REPOSITORY_ROOT__

First identify the actual repository root when this directory is inside a Git
checkout (for example with git rev-parse --show-toplevel). Treat the current working directory as the active scope for ./AGENTS.md, and
inspect all existing instruction files across the repository before editing
anything. Use find (excluding generated and vendor directories) to discover
scoped guides. Determine the project structure,
source and test locations, assets, package manifests, development/build/test
commands, formatting and naming conventions, test conventions, recent commit
message patterns, and pull-request expectations. Use the repository's actual
files and git history instead of guessing. Do not edit generated files,
dependencies, secrets, or unrelated source code.

Instruction-file scope and safety:
- Find all existing AGENTS.md files below the actual repository root, excluding
  .git, node_modules, build output, caches, and other generated/vendor
  directories. Do not skip an existing guide merely because it is nested.
- Also check for CLAUDE.md files because they may describe the same project
  scope. Treat AGENTS.md as the preferred name for new or migrated guidance.
- Treat each AGENTS.md as an independent scope. Pi automatically applies the
  applicable files by directory, so do not add parent-file references,
  inheritance notes, duplicated root rules, or cross-file synchronization prose.
- If ./AGENTS.md already exists, update it in place only when the repository
  evidence shows a stale or missing section; do not overwrite it wholesale or
  discard useful project-specific instructions. If it is already accurate,
  leave it unchanged.
- For nested AGENTS.md files, update only the rules specific to that directory.
  Do not rewrite them to describe the whole repository or create one merely to
  repeat a parent scope. Preserve genuinely independent guidance.
- If no applicable guide exists in a scope, create AGENTS.md there only when
  that scope has meaningful, directory-specific contributor instructions.

Repository-wide package rule:
- Prefer the internal @fradser/pi-kit workspace runtime for shared reusable
  helpers and Pi-package infrastructure when it is available. Use
  "@fradser/pi-kit": "workspace:*" under dependencies, never
  peerDependencies. If pi-kit is absent, do not invent a replacement or add
  an unverified registry dependency; record the gap instead.

For each guide you create or update:
- Use the title "Repository Guidelines".
- Use clear Markdown headings and concise, actionable explanations.
- Aim for 200-400 words for a repository-level guide; keep nested guides
  shorter and focused on their directory.
- Cover Project Structure & Module Organization, Build/Test/Development
  Commands, Coding Style & Naming Conventions, Testing Guidelines, and
  Commit & Pull Request Guidelines when relevant to that scope. Add Security,
  Configuration, Architecture, or Agent-Specific Instructions only when
  supported by repository evidence.
- Include concrete commands and paths where helpful.
- Keep a professional, instructional tone. Do not claim tools, workflows, or
  policies that you did not verify.

After editing, briefly report which instruction files were created or updated
and the independent directory scope each file covers.
`.trim();

export function buildInitPrompt(cwd: string, focus: string = ""): string {
  const repositoryRoot = JSON.stringify(cwd);
  const prompt = INIT_PROMPT.split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join(" ")
    .replace("__REPOSITORY_ROOT__", repositoryRoot);
  const focusSection = focus.trim()
    ? ` Additional user focus (apply only when consistent with the repository evidence above): ${focus.trim().replace(/\s+/g, " ")}`
    : "";

  return `${prompt}${focusSection}`;
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("init", {
    description: "Create or update scoped AGENTS.md contributor guides for the repository",
    handler: async (args, ctx) => {
      const prompt = buildInitPrompt(ctx.cwd, args);

      if (ctx.isIdle()) {
        pi.sendUserMessage(prompt);
      } else {
        pi.sendUserMessage(prompt, { deliverAs: "followUp" });
        ctx.ui.notify("Repository guide task queued as a follow-up", "info");
      }
    },
  });
}

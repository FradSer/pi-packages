/**
 * pi-utils — repository contributor-guide initialization command.
 *
 * /init delegates repository inspection and AGENTS.md maintenance to the
 * active agent so the generated guidance reflects the actual project.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";

const INIT_PROMPT = `
Generate and maintain contributor guidance for this repository.

Starting directory: __REPOSITORY_ROOT__

Identify the actual repository root when inside a Git checkout (for example with git rev-parse --show-toplevel). Outside a Git checkout, use the starting directory as the project root. Treat the current working directory as the active scope for ./AGENTS.md. Use find to discover scoped guides, excluding generated and vendor directories. Read repository evidence as needed to evaluate the guidance: use the target repository's files and documentation, and git history only when available and relevant. This is an instruction audit, not a mandatory full-repository tour. Do not edit generated files, dependencies, secrets, or unrelated source code.

Instruction-file scope and safety:
- Find all existing AGENTS.md files below the actual repository root, excluding .git, node_modules, build output, caches, and other generated/vendor directories. Do not skip an existing guide merely because it is nested.
- Also check for CLAUDE.md files because they may describe the same project scope. Treat AGENTS.md as the preferred name for new or migrated guidance.
- Treat each AGENTS.md as an independent scope. Keep its guidance specific to that directory; do not add parent-file references, inheritance notes, duplicated root rules, or cross-file synchronization prose.
- Read each guide before deciding whether it needs changes. Update existing guidance in place to remove stale, redundant, or overprescriptive rules and fill meaningful gaps; do not overwrite it wholesale or discard useful project-specific instructions. Leave accurate, focused guidance unchanged.
- For nested AGENTS.md files, update only the rules specific to that directory. Do not rewrite them to describe the whole repository or create one merely to repeat a parent scope. Preserve genuinely independent guidance.
- If no applicable guide exists in a scope, create AGENTS.md there only when that scope has meaningful, directory-specific contributor instructions.

Repository-specific conventions:
- Discover the project's languages, toolchain, dependency-management rules, existing shared modules, and contribution workflows from its own manifests, configuration, source, and documentation. Omit unsupported conventions rather than importing policies from another project or the agent's environment.

Keep only guidance that earns its context cost:
- Prefer project-specific pitfalls, non-obvious conventions, and useful commands over generic coding advice or facts easily found in manifests. No word quota or mandatory section checklist. Use "Repository Guidelines" for new guides and concise headings where helpful.
- Replace unconditional reading lists with task-specific documentation pointers: say when a document matters. Keep multi-workflow guidance as a minimal router to existing supporting references rather than loading every procedure upfront; verify referenced paths.
- Where skills are relevant, recommend short, precise triggers and progressive disclosure instead of broad activation rules or elaborate recipes. Do not edit skill files unless explicitly requested; report relevant recommendations instead.
- Keep guidance useful across models. Remove unsupported model-specific assumptions rather than claiming a particular model needs no safeguards.

Decision boundaries and completion:
- Preserve genuine safety and approval boundaries. Distinguish verified safe local workflows from destructive, external, or production-affecting actions; never infer that tests are disposable or isolated without evidence.
- Where repository evidence establishes safety, give permission to complete local work and fix failures caused by the requested change without repeated approval. Replace blanket ask-first rules only when their intended boundary is clear; surface unresolved policy decisions rather than silently relaxing them.
- State concrete completion and stopping conditions for workflows that need them, including running or inspecting the result when relevant. Avoid stopping for review after a first implementation unless a real decision requires it. Scope verification to the change and risk instead of prescribing needless test runs or generic reminders to test everything.

Finish the audit by checking edited guidance against repository evidence, removing contradictions and repetition, and verifying referenced commands and paths without running unrelated workflows. Briefly report files changed, their independent scopes, important removals, and any unresolved decisions. If no changes are warranted, say so.
`.trim();

export function buildInitPrompt(cwd: string, focus: string = ""): string {
  const repositoryRoot = JSON.stringify(cwd);
  const prompt = INIT_PROMPT.replace("__REPOSITORY_ROOT__", repositoryRoot);
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
        notifyPi(ctx.ui, "Repository guide task queued as a follow-up", "info");
      }
    },
  });
}

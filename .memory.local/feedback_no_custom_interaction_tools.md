---
name: no-custom-interaction-tools
description: Packages must not register custom user-interaction tools (gh_confirm, gh_ask_merge, git_ask_name, lark_confirm_action) — asking/confirming with the user uses pi's default: the plain conversation
type: feedback
---

FradSer's packages must not ship custom dialog/confirmation tools (`gh_confirm`, `gh_ask_merge`, `git_ask_name`, `lark_confirm_action`). When the agent needs user input — a merge decision, a yes/no confirmation, a branch name, or consent for a high-risk write — it asks directly in the conversation and waits for the reply. Pi has no dedicated question tool; the conversation IS the default.

**Why:**
User directive (2025): "不应该有类似 gh_confirm 的工具，二次确认的工具应该使用派默认的" — custom native-dialog tools (wrapping `ctx.ui.confirm/select/input`) are redundant with pi's native model↔user conversation. Removed on 2025-06: `packages/github/extensions/interactive.ts` (gh_ask_merge + gh_confirm), `packages/git/extensions/ask-name.ts` (git_ask_name), `packages/lark/extensions/lark-confirm.ts` (lark_confirm_action). The git/github packages were later removed from this monorepo entirely (workflows became pure skills in `~/Developer/FradSer/skills`), and the lark package was removed too — so none of those extensions exist anywhere now; the rule is what survives.

**How to apply:**
1. Do not re-add `registerTool` entries that exist only to ask the user something — the model asks in conversation instead.
2. Menus (`registerCommand` + `ctx.ui.select`) are fine and pi-native — they are commands, not tools; keep them.
3. Functional tools with no pi equivalent are fine: `context_deepwiki/context_context7/context_exa` (code-context), `session_context` (git-agent), `teammate_*` (agent-teams).
4. **Forcing a native confirmation is done with a hook, not a tool**: `pi.on("tool_call")` + `ctx.ui.confirm` (pi's documented permission-gate pattern, cf. pi's `examples/extensions/permission-gate.ts`). The former `risky-gate.ts` extensions in packages/git and packages/github implemented this but were removed with those packages; rebuild any future gate the same way.
5. **A gate presents OPTIONS, not a yes/no on a pre-built command**: the hook calls `ctx.modelRegistry.complete(ctx.model, { messages }, { maxTokens, timeoutMs })` with the command + a ~1500-char slice of recent user messages and asks the model to generate `label ||| command` lines (proposed action, a safer alternative, Cancel); it pops `ctx.ui.select` with those labels, then mutates `event.input.command` to the chosen option's command. On model failure it falls back to Proceed/Cancel. `!ctx.hasUI` → `{ block: true, reason: "... ask the user in the conversation first ..." }`. User's exact framing: "你应该生成的是选项。然后基于选项，模型会去生成不同的命令，不要一次性生成命令让用户选".

**Related:** [[pi-package-conventions]] [[git-github-menu-conversion]]

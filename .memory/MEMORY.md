# Memory Index

- `feedback_agents_skills_symlinks.md` — `~/.agents/skills/` entries are user symlinks to local dev repos — never delete them when cleaning skill installs
- `feedback_git_agent_commit_scope.md` — git-agent commit auto-stages the whole dirty tree; scope it with exact staging plus `--no-stage`
- `feedback_memory_menu_inline_consolidation.md` — /memory menu design — consolidate first, single project-instructions entry (AGENTS.md/CLAUDE.md), consolidation runs in a background child worker process, auto-triggered at 40% context fill when auto-memory is on
- `feedback_no_custom_interaction_tools.md` — no custom dialog/confirmation tools (gh_confirm, gh_ask_merge, git_ask_name); ask in the conversation; permission gates are `tool_call` hooks offering options
- `feedback_no_global_input_interception.md` — extensions must not drive widgets with `onTerminalInput` (breaks pi's model selector/history); own input via `ctx.ui.custom`
- `feedback_stale_session_skill_paths.md` — pi caches package/skill paths at session start; after a repo restructure old sessions throw ENOENT on `/skill:*` — restart pi
- `project_git_agent_session_context.md` — git-agent CLI is conversation-blind; session_context bridges the session record into commit intents
- `project_git_github_menu_conversion.md` — git/git-agent/github expose workflows as pi menu commands with inline procedures (no skill surface); manual selection is settled — no independent commands or autocomplete
- `project_pi_package_conventions.md` — Native Pi package standards for package.json, skills, extensions, worktrees, runtime deps — no Claude plugin artifacts
- `project_teammate_autonomous_and_tui.md` — teammate: autonomous child Pi workers over a shared state file (real-time live polling), blocking spawn, deps, worktree isolation, /teammate console (no global key interception)
- `reference_pi_cli_print_json_usage.md` — `pi --print --mode json` emits JSONL with `message.usage` (tokens/cost) for child-process cost accounting
- `reference_pi_custom_component_rendering.md` — `ctx.ui.custom` `render(width)` must wrap/truncate to terminal width; non-overlay custom = full screen
- `reference_pi_kitty_csi_u_keys.md` — pi negotiates the Kitty keyboard protocol: Esc is `\x1b[27u`, Shift+arrows are `\x1b[1;2:1A/B`; match with CSI-u-aware regexes
